"""Build the modeled layer (dim_/fct_/mart_ tables) from raw tables.

Models are plain SQL files run in name order. Each is a ``CREATE OR REPLACE TABLE``,
which ClickHouse swaps atomically, so readers never see a half-built table.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from .. import warehouse
from ..config import PACKAGE_ROOT


def model_files():
    return sorted((PACKAGE_ROOT / "sql" / "models").glob("*.sql"))


def run_models(progress: Callable[[str], None] = print) -> dict[str, float]:
    timings = {}
    for path in model_files():
        t0 = time.perf_counter()
        for stmt in warehouse.split_sql(path.read_text()):
            warehouse.command(stmt)
        timings[path.stem] = round(time.perf_counter() - t0, 2)
        progress(f"model {path.stem:<24} built in {timings[path.stem]:.2f}s")
    return timings
