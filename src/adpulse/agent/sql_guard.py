"""Static checks on LLM-written SQL before it reaches the warehouse.

Defence in depth: this guard rejects anything that is not a single read-only SELECT over
approved tables, and the query then runs as a ClickHouse user with ``readonly=1``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

FORBIDDEN_FUNCTIONS = {
    "url", "file", "remote", "remotesecure", "s3", "s3cluster", "mysql", "postgresql", "jdbc", "odbc",
    "hdfs", "input", "cluster", "clusterallreplicas", "executable", "azureblobstorage", "gcs", "mongodb",
    "redis", "sqlite", "dictionary", "generaterandom", "numbers", "zeros", "merge",
}
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|alter|drop|truncate|create|rename|attach|detach|optimize|grant|revoke|"
    r"kill|system|set|exchange|undrop|backup|restore|into\s+outfile)\b",
    re.IGNORECASE,
)


class SQLRejected(ValueError):
    pass


@dataclass
class GuardResult:
    sql: str
    tables: set[str] = field(default_factory=set)
    parsed_ok: bool = True


def _strip_literals(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"'(?:[^'\\]|\\.)*'", "''", sql)


def check_sql(sql: str, allowed_tables: set[str], database: str = "adpulse") -> GuardResult:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise SQLRejected("empty SQL")
    bare = _strip_literals(sql)
    if ";" in bare:
        raise SQLRejected("only a single statement is allowed")
    if not re.match(r"^\s*(with|select|\()", bare, re.IGNORECASE):
        raise SQLRejected("query must start with SELECT or WITH")
    if m := FORBIDDEN_KEYWORDS.search(bare):
        raise SQLRejected(f"forbidden keyword: {m.group(0).upper()}")

    try:
        tree = sqlglot.parse_one(sql, read="clickhouse")
    except sqlglot.errors.ParseError:
        tree = None

    if tree is None:
        # sqlglot doesn't know every ClickHouse construct: fall back to a conservative scan.
        names = {n.lower() for n in re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", bare, re.IGNORECASE)}
        ctes = {n.lower() for n in re.findall(r"\b([a-zA-Z_]\w*)\s+as\s*\(", bare, re.IGNORECASE)}
        tables = {n.split(".")[-1] for n in names} - ctes
        _check_tables(tables, allowed_tables, names, database)
        for fn in re.findall(r"\b([a-zA-Z_]\w*)\s*\(", bare):
            if fn.lower() in FORBIDDEN_FUNCTIONS:
                raise SQLRejected(f"function {fn}() is not allowed")
        return GuardResult(sql=sql, tables=tables, parsed_ok=False)

    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery, exp.Intersect, exp.Except)):
        raise SQLRejected(f"only SELECT queries are allowed (got {type(tree).__name__})")
    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter,
                             exp.Command)):
            raise SQLRejected(f"{type(node).__name__} statements are not allowed")
        if isinstance(node, exp.Anonymous) and str(node.this).lower() in FORBIDDEN_FUNCTIONS:
            raise SQLRejected(f"function {node.this}() is not allowed")
        if isinstance(node, exp.Func) and node.sql_name().lower() in FORBIDDEN_FUNCTIONS:
            raise SQLRejected(f"function {node.sql_name()}() is not allowed")

    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    full_names, tables = set(), set()
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if not name or name in cte_names:
            continue
        if isinstance(t.this, exp.Anonymous):  # table function, e.g. numbers(10)
            raise SQLRejected(f"table function {t.this.this}() is not allowed")
        db = (t.db or "").lower()
        full_names.add(f"{db}.{name}" if db else name)
        tables.add(name)
    _check_tables(tables, allowed_tables, full_names, database)
    return GuardResult(sql=sql, tables=tables)


def _check_tables(tables: set[str], allowed: set[str], full_names: set[str], database: str) -> None:
    for full in full_names:
        if "." in full and full.split(".")[0] != database.lower():
            raise SQLRejected(f"only the '{database}' database may be queried (got {full})")
    bad = sorted(t for t in tables if t not in allowed)
    if bad:
        raise SQLRejected(f"table(s) not allowed: {', '.join(bad)}. Allowed: {', '.join(sorted(allowed))}")
    if not tables:
        raise SQLRejected("query does not read any warehouse table")
