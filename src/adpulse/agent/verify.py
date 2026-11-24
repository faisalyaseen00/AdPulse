"""Number verification ("every number is checked").

Every number the narrative quotes must be traceable to the query result:

* a **cell**, or a column **aggregate** (total / average / min / max / count), at the precision
  it was printed with; or
* a **declared computation**: the narrator lists derived figures ("3.6x", "+42%") together with
  the arithmetic over result values ("125.75 / 34.81"). Each operand must itself be a cell or
  aggregate, and the arithmetic is re-evaluated here - the model's own math is never trusted.

Numbers inside entity names (e.g. "Static - 20% Off") or in the question are ignored.
Guessing at undeclared ratios is deliberately not supported: with many cells, almost any
ratio can be "explained", which would make the check meaningless.
"""
from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

NUM_RE = re.compile(
    r"(?P<neg>[-−])?(?P<cur>\$)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<suf>\s?(?:[kKmMbB](?![a-zA-Z])|%|x(?![a-zA-Z])|×))?"
)
DATE_RE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b|\b(?:19|20)\d{2}\b")
LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


@dataclass
class NumberCheck:
    text: str
    value: float
    verified: bool
    source: str = ""


def _parse(m: re.Match) -> tuple[float, int, str]:
    raw = m.group("num").replace(",", "")
    val = float(raw)
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    suf = (m.group("suf") or "").strip().lower()
    scale = {"k": 1e3, "m": 1e6, "b": 1e9}.get(suf, 1.0)
    if m.group("neg"):
        val = -val
    return val * scale, decimals, suf


def extract_numbers(text: str, ignore_strings: list[str] = ()) -> list[tuple[str, float, int, str]]:
    clean = text
    for s in sorted({s for s in ignore_strings if s and re.search(r"\d", s)}, key=len, reverse=True):
        clean = clean.replace(s, " ")
    clean = DATE_RE.sub(" ", clean)
    clean = LIST_MARKER_RE.sub(" ", clean)
    clean = re.sub(r"\*\*|__|`", "", clean)
    out = []
    for m in NUM_RE.finditer(clean):
        # skip digits glued to letters (e.g. "LAL1", "Q3", "90d" handled as words)
        before = clean[m.start() - 1] if m.start() > 0 else " "
        after = clean[m.end()] if m.end() < len(clean) else " "
        if before.isalpha() or (after.isalpha() and not m.group("suf")):
            continue
        val, dec, suf = _parse(m)
        out.append((m.group(0).strip(), val, dec, suf))
    return out


def _candidates(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Named pools of values a quoted number may legitimately come from."""
    pools: dict[str, list[float]] = {"cell": [], "aggregate": []}
    num = df.select_dtypes(include=["number", "bool"]).astype(float)
    for col in num.columns:
        vals = num[col].dropna().to_numpy()
        vals = vals[np.isfinite(vals)]
        if not len(vals):
            continue
        pools["cell"].extend(vals.tolist())
        pools["aggregate"].extend([vals.sum(), vals.mean(), vals.min(), vals.max(), float(len(vals))])
    pools["aggregate"].append(float(len(df)))
    return {k: np.array(v, dtype=float) for k, v in pools.items()}


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _eval(expr: str) -> tuple[float, list[float]]:
    """Safely evaluate + - * / arithmetic over number literals; return (value, operands)."""
    operands: list[float] = []

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            operands.append(float(node.value))
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -ev(node.operand)
        raise ValueError(f"unsupported expression: {expr}")

    clean = expr.replace(",", "").replace("$", "").replace("×", "*")
    return ev(ast.parse(clean, mode="eval")), operands


def _matches(value: float, decimals: int, suf: str, pool: np.ndarray) -> bool:
    """True if some pool value rounds to ``value`` at the precision it was written with.

    "$125.75" must match within ±0.005, "$6.6k" within ±50, "36%" within ±0.5 points.
    No extra relative slack: with hundreds of derived candidates, slack lets invented numbers through.
    """
    if not len(pool):
        return False
    scale = {"k": 1e3, "m": 1e6, "b": 1e9}.get(suf, 1.0)
    tol = 0.5 * 10 ** (-decimals) * scale * 1.0001 + 1e-9
    if np.any(np.abs(pool - value) <= tol):
        return True
    if suf == "%":  # the result may hold the fraction (0.35) rather than the percent (35)
        return bool(np.any(np.abs(pool * 100 - value) <= tol))
    return False


def verify_numbers(text: str, df: pd.DataFrame, question: str = "",
                   computations: list[tuple[str, str]] = ()) -> list[NumberCheck]:
    """Check every number in ``text``. ``computations`` = [(quoted_text, arithmetic_expression)]."""
    ignore = [str(v) for v in df.select_dtypes(exclude=["number", "bool"]).astype(str).to_numpy().ravel()]
    ignore.extend(df.columns.astype(str))
    question_nums = {round(v, 6) for _, v, _, _ in extract_numbers(question)}
    pools = _candidates(df) if len(df) else {}
    base = np.concatenate(list(pools.values())) if pools else np.array([])

    # Declared computations: operands must be real values, result is recomputed here.
    computed: list[tuple[float, int, str, str]] = []
    for quoted, expr in computations:
        found = extract_numbers(quoted)
        if not found:
            continue
        _, qval, qdec, qsuf = found[0]
        try:
            result, operands = _eval(expr)
        except (ValueError, SyntaxError, ZeroDivisionError):
            continue
        if not operands or not all(_matches(o, _decimals(o), "", base) for o in operands):
            continue
        candidates = np.array([result, result * 100])  # "+42%" may be written from a 0.42 ratio
        if _matches(qval, qdec, qsuf, candidates):
            computed.append((qval, qdec, qsuf, expr))

    checks: list[NumberCheck] = []
    for raw, val, dec, suf in extract_numbers(text, ignore):
        if round(val, 6) in question_nums:
            continue
        if not suf and dec == 0 and abs(val) <= 10 and not raw.startswith("$"):
            # small bare integers ("top 3", "2 ads") are counts the reader can see in the table
            checks.append(NumberCheck(raw, val, True, "count"))
            continue
        source = ""
        for name in ("cell", "aggregate"):
            if name in pools and _matches(val, dec, suf, pools[name]):
                source = name
                break
        if not source:
            for cval, cdec, csuf, expr in computed:
                if abs(cval - val) <= 0.5 * 10 ** (-min(dec, cdec)) * 1.0001 and csuf == suf:
                    source = f"computed: {expr}"
                    break
        checks.append(NumberCheck(raw, val, bool(source), source))
    return checks


def _decimals(x: float) -> int:
    """Decimals needed to write an operand as given (12.5 -> 1, 34.81 -> 2, 300 -> 0)."""
    text = repr(round(x, 6))
    return len(text.split(".")[1].rstrip("0")) if "." in text else 0


def summarize(checks: list[NumberCheck]) -> tuple[int, int]:
    return len(checks), sum(c.verified for c in checks)
