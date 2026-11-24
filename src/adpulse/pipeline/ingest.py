"""Ingestion: land source streams in ClickHouse raw tables.

Modes
-----
* ``airbyte`` - runs real Airbyte connectors through PyAirbyte (``pip install -e .[airbyte]``).
  The demo uses the official ``source-file`` connector over the demo CSVs; enabled ``live``
  connections in ``connections.yaml`` (Meta, Google Ads, Shopify...) go through the same loader.
* ``direct``  - reads the demo CSVs with pandas. A fast path for local dev and CI.

Every stream load is recorded in ``app_sync_runs`` so the UI can show data flowing in.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
import uuid
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from .. import warehouse
from ..config import PACKAGE_ROOT, get_settings

log = logging.getLogger(__name__)
BATCH_ROWS = 50_000
Progress = Callable[[str], None]


def load_connections() -> dict:
    return yaml.safe_load((PACKAGE_ROOT / "pipeline" / "connections.yaml").read_text())


def _table_columns(table: str) -> dict[str, str]:
    s = get_settings()
    df = warehouse.query_df(
        "SELECT name, type FROM system.columns WHERE database = {db:String} AND table = {t:String}",
        {"db": s.clickhouse_database, "t": table},
    )
    return dict(zip(df["name"], df["type"]))


def _coerce(df: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    """Cast a frame to the ClickHouse table's column types (Airbyte emits strings/JSON)."""
    out = pd.DataFrame(index=df.index)
    for name, ctype in columns.items():
        if name == "_airbyte_extracted_at":
            continue
        base = re.sub(r"^(Nullable|LowCardinality)\((.*)\)$", r"\2", ctype)
        col = df[name] if name in df.columns else pd.Series([None] * len(df), index=df.index)
        if base == "Date":
            out[name] = pd.to_datetime(col, errors="coerce").dt.date
        elif base.startswith("DateTime"):
            out[name] = pd.to_datetime(col, errors="coerce", utc=True).dt.tz_localize(None)
        elif base.startswith(("UInt", "Int")):
            out[name] = pd.to_numeric(col, errors="coerce").fillna(0).astype("int64")
        elif base.startswith("Float"):
            out[name] = pd.to_numeric(col, errors="coerce").fillna(0.0).astype("float64")
        else:
            out[name] = col.fillna("").astype(str)
    out["_airbyte_extracted_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
    return out


def _record_run(run: dict) -> None:
    warehouse.admin().insert(
        "app_sync_runs",
        [[run["run_id"], run["source"], run["stream"], run["table"], run["mode"], run["rows"],
          run["status"], run["error"], run["started_at"], run["finished_at"]]],
        column_names=["run_id", "source", "stream", "target_table", "mode", "rows", "status", "error",
                      "started_at", "finished_at"],
    )


def load_batches(batches: Iterable[pd.DataFrame], table: str, *, source: str, stream: str, mode: str,
                 run_id: str) -> int:
    """Insert frames into ``table`` and log the run (success or failure)."""
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    columns = _table_columns(table)
    if not columns:
        raise RuntimeError(f"table {table} does not exist - run `adpulse init-db` first")
    rows, status, error = 0, "succeeded", ""
    try:
        for df in batches:
            if df.empty:
                continue
            frame = _coerce(df, columns)
            warehouse.admin().insert_df(table, frame)
            rows += len(frame)
    except Exception as e:
        status, error = "failed", str(e)[:2000]
        raise
    finally:
        _record_run({"run_id": run_id, "source": source, "stream": stream, "table": table, "mode": mode,
                     "rows": rows, "status": status, "error": error, "started_at": started,
                     "finished_at": datetime.now(timezone.utc).replace(tzinfo=None)})
    return rows


# --------------------------------------------------------------------------- direct
def ingest_direct(progress: Progress = print) -> dict[str, int]:
    s = get_settings()
    conns = load_connections()["demo"]["streams"]
    run_id = uuid.uuid4().hex[:12]
    result = {}
    for st in conns:
        path = s.demo_dir / st["file"]
        if not path.exists():
            raise FileNotFoundError(f"{path} missing - run `adpulse demo-data` first")
        batches = pd.read_csv(path, chunksize=BATCH_ROWS, dtype=str, keep_default_na=False)
        n = load_batches(batches, st["table"], source=st["source"], stream=path.stem, mode="direct",
                         run_id=run_id)
        progress(f"{st['source']:>10} · {path.stem:<28} → {st['table']:<32} {n:>9,} rows")
        result[st["table"]] = n
    return result


# --------------------------------------------------------------------------- airbyte
def _require_pyairbyte():
    # PyAirbyte shells out to `uv` (or `pip`) to install connectors. Make the tools of the
    # interpreter running AdPulse visible even when its virtualenv is not activated.
    bin_dir = os.path.dirname(sys.executable)
    if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    if shutil.which("uv") is None:
        os.environ.setdefault("AIRBYTE_NO_UV", "true")
    try:
        import airbyte as ab  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "PyAirbyte is not installed. Run `pip install -e '.[airbyte]'` or use --mode direct."
        ) from e
    return ab


def _batched_records(records: Iterable, rename: dict[str, str] | None = None) -> Iterator[pd.DataFrame]:
    buf: list[dict] = []
    for rec in records:
        row = _flatten(dict(rec))
        if rename:
            row = {rename[k]: v for k, v in row.items() if k in rename}
        buf.append(row)
        if len(buf) >= BATCH_ROWS:
            yield pd.DataFrame(buf)
            buf = []
    if buf:
        yield pd.DataFrame(buf)


def _flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def _expand_env(obj):
    if isinstance(obj, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    return obj


def ingest_airbyte(progress: Progress = print, include_live: bool = True) -> dict[str, int]:
    """Run Airbyte connectors via PyAirbyte and land each stream in ClickHouse."""
    ab = _require_pyairbyte()
    s = get_settings()
    conns = load_connections()
    run_id = uuid.uuid4().hex[:12]
    result: dict[str, int] = {}

    for st in conns["demo"]["streams"]:
        path: Path = (s.demo_dir / st["file"]).resolve()
        if not path.exists():
            raise FileNotFoundError(f"{path} missing - run `adpulse demo-data` first")
        progress(f"airbyte source-file · reading {path.name}")
        source = ab.get_source(
            "source-file",
            config={"dataset_name": path.stem, "format": "csv", "url": str(path),
                    "provider": {"storage": "local"},
                    # Read every column as text: type inference would turn ids like "6101" into 6101.0
                    # (blank cells make the column float). Types are applied from the ClickHouse schema.
                    "reader_options": json.dumps({"dtype": "str", "keep_default_na": False})},
            install_if_missing=True,
        )
        source.select_streams([path.stem])
        n = load_batches(_batched_records(source.get_records(path.stem)), st["table"], source=st["source"],
                         stream=path.stem, mode="airbyte", run_id=run_id)
        progress(f"{st['source']:>10} · {path.stem:<28} → {st['table']:<32} {n:>9,} rows")
        result[st["table"]] = n

    if include_live:
        for conn in conns.get("live", []):
            if not conn.get("enabled"):
                continue
            progress(f"airbyte {conn['connector']} · connecting ({conn['name']})")
            source = ab.get_source(conn["connector"], config=_expand_env(conn["config"]),
                                   install_if_missing=True)
            source.check()
            source.select_streams(list(conn["streams"]))
            for stream, spec in conn["streams"].items():
                n = load_batches(_batched_records(source.get_records(stream), spec["columns"]), spec["table"],
                                 source=conn["name"], stream=stream, mode="airbyte", run_id=run_id)
                progress(f"{conn['name']:>10} · {stream:<28} → {spec['table']:<32} {n:>9,} rows")
                result[spec["table"]] = result.get(spec["table"], 0) + n
    return result


def ingest(mode: str = "auto", progress: Progress = print) -> dict[str, int]:
    if mode == "auto":
        try:
            _require_pyairbyte()
            mode = "airbyte"
        except RuntimeError:
            mode = "direct"
    progress(f"ingest mode: {mode}")
    return ingest_airbyte(progress) if mode == "airbyte" else ingest_direct(progress)


def sync_history(limit: int = 200) -> pd.DataFrame:
    return warehouse.query_df(
        "SELECT run_id, source, stream, target_table, mode, rows, status, error, started_at, finished_at, "
        "dateDiff('millisecond', started_at, finished_at) / 1000 AS seconds "
        "FROM app_sync_runs ORDER BY started_at DESC LIMIT {n:UInt32}", {"n": limit})
