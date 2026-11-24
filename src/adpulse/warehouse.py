"""ClickHouse access.

Two clients:
* ``admin()``  - read/write, used by ingestion, transforms and the app's own tables.
* ``reader()`` - a read-only ClickHouse user. Every SQL statement the LLM writes runs
  through this client, so even a guard bypass cannot modify data.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import clickhouse_connect
import pandas as pd
from clickhouse_connect.driver.client import Client

from .config import PACKAGE_ROOT, get_settings

log = logging.getLogger(__name__)


def _client(user: str, password: str, database: str | None) -> Client:
    s = get_settings()
    return clickhouse_connect.get_client(
        host=s.clickhouse_host,
        port=s.clickhouse_port,
        username=user,
        password=password,
        database=database or "",
        secure=s.clickhouse_secure,
        # ClickHouse Cloud idles when unused; the first request may wait while it wakes up.
        connect_timeout=30,
        send_receive_timeout=300,
        # Streamlit runs queries from several threads; a shared HTTP session id would make them collide.
        autogenerate_session_id=False,
    )


@lru_cache
def admin() -> Client:
    s = get_settings()
    return _client(s.clickhouse_user, s.clickhouse_password, s.clickhouse_database)


@lru_cache
def reader() -> Client:
    s = get_settings()
    return _client(s.clickhouse_reader_user, s.clickhouse_reader_password, s.clickhouse_database)


def ensure_database() -> None:
    """Create the AdPulse database if missing (ClickHouse Cloud services start with only `default`)."""
    s = get_settings()
    db = s.clickhouse_database
    if not db.replace("_", "").isalnum():
        raise ValueError(f"invalid database name: {db!r}")
    _client(s.clickhouse_user, s.clickhouse_password, None).command(f"CREATE DATABASE IF NOT EXISTS {db}")
    admin.cache_clear()


def query_df(sql: str, parameters: dict | None = None) -> pd.DataFrame:
    """Trusted (app-authored) read query via the admin client."""
    return admin().query_df(sql, parameters=parameters or {})


def command(sql: str, parameters: dict | None = None):
    return admin().command(sql, parameters=parameters or {})


def run_untrusted(sql: str) -> pd.DataFrame:
    """Run LLM-written SQL on the read-only user with hard limits."""
    # Limits (timeout, row cap) are set on the ClickHouse user itself in init_db(): a readonly=1 user
    # cannot change settings, so generated SQL cannot lift them with a SETTINGS clause either.
    return reader().query_df(sql)


def split_sql(text: str) -> list[str]:
    """Split a .sql file into statements (no semicolons inside our literals)."""
    stmts = []
    for chunk in text.split(";"):
        lines = [ln for ln in chunk.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            stmts.append(stmt)
    return stmts


def run_sql_file(name: str) -> int:
    path = PACKAGE_ROOT / "sql" / name
    stmts = split_sql(path.read_text())
    for stmt in stmts:
        command(stmt)
    return len(stmts)


def init_db() -> None:
    """Create raw + app tables and the read-only agent user (idempotent)."""
    s = get_settings()
    ensure_database()
    run_sql_file("schema.sql")
    db = s.clickhouse_database
    user = s.clickhouse_reader_user
    pwd = s.clickhouse_reader_password.replace("'", "\\'")
    command(f"CREATE USER IF NOT EXISTS {user} IDENTIFIED WITH sha256_password BY '{pwd}'")
    command(f"ALTER USER {user} IDENTIFIED WITH sha256_password BY '{pwd}'")
    command(
        f"ALTER USER {user} SETTINGS readonly = 1, max_execution_time = {int(s.agent_query_timeout_s)}, "
        f"max_result_rows = {int(s.agent_max_rows)}, result_overflow_mode = 'break', "
        f"max_memory_usage = 4000000000"
    )
    command(f"REVOKE ALL ON *.* FROM {user}")
    command(f"GRANT SELECT ON {db}.* TO {user}")
    # app_* tables hold operational state, not analytics: hide them from the agent.
    for t in ("app_recommendations", "app_reports", "app_questions"):
        command(f"REVOKE SELECT ON {db}.{t} FROM {user}")
    reader.cache_clear()
    log.info("database initialised")


@dataclass
class Health:
    ok: bool
    version: str = ""
    error: str = ""


def ping() -> Health:
    """Is the ClickHouse server up and are the admin credentials valid? (No database needed.)"""
    s = get_settings()
    try:
        v = _client(s.clickhouse_user, s.clickhouse_password, None).command("SELECT version()")
        return Health(ok=True, version=str(v))
    except Exception as e:  # noqa: BLE001
        return Health(ok=False, error=str(e))


def health(retries: int = 2) -> Health:
    """Ping ClickHouse. Retries briefly so a cloud service that is waking up isn't reported as down."""
    import time
    err = ""
    for attempt in range(retries + 1):
        try:
            v = admin().command("SELECT version()")
            return Health(ok=True, version=str(v))
        except Exception as e:  # noqa: BLE001
            err = str(e)
            if "database" in err.lower() and "does not exist" in err.lower():
                break  # not a wake-up problem: run `adpulse bootstrap`
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    return Health(ok=False, error=err)


def table_counts() -> pd.DataFrame:
    s = get_settings()
    return query_df(
        """
        SELECT name AS table, engine, total_rows AS rows,
               formatReadableSize(total_bytes) AS size
        FROM system.tables
        WHERE database = {db:String} AND NOT startsWith(name, '.')
        ORDER BY startsWith(name, 'raw_') DESC, name
        """,
        {"db": s.clickhouse_database},
    )
