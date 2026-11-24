"""Choose decision thresholds on the *dev* split only.

Thresholds are fitted on dev and then reported on test; the function refuses test rows outright so a
future refactor cannot quietly tune on the held-out data. The objective is computed as a macro average
over sources (each dataset counts equally) so one large dataset cannot dictate the operating point.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from typing import Any

OBJECTIVES = ("youden", "fpr_cap")


def _per_source(rows: list[dict[str, Any]], system: str) -> dict[str, tuple[list[float], list[float]]]:
    by: dict[str, tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for r in rows:
        by[r["source"]][0 if r["label"] == 1 else 1].append(r["scores"][system])
    return {s: (sorted(p), sorted(n)) for s, (p, n) in by.items() if p and n}


def _macro(by: dict[str, tuple[list[float], list[float]]], t: float) -> tuple[float, float]:
    tprs = [1 - bisect_right(p, t) / len(p) for p, _ in by.values()]
    fprs = [1 - bisect_right(n, t) / len(n) for _, n in by.values()]
    return sum(tprs) / len(tprs), sum(fprs) / len(fprs)


def calibrate(rows: list[dict[str, Any]], system: str, objective: str = "youden", fpr_cap: float = 0.02) -> dict[str, Any]:
    if objective not in OBJECTIVES:
        raise ValueError(f"objective must be one of {OBJECTIVES}")
    if any(r["split"] != "dev" for r in rows):
        raise ValueError("calibration may only use the dev split")
    by = _per_source(rows, system)
    if not by:
        raise ValueError("need at least one dev source containing both attacks and benign samples")
    candidates = sorted({-1.0, *(s for p, n in by.values() for s in (*p, *n))})
    best: tuple[tuple[float, ...], float, float, float] | None = None
    for t in candidates:
        tpr, fpr = _macro(by, t)
        if objective == "youden":
            key = (tpr - fpr, t)  # ties -> higher (more conservative) threshold
        else:
            if fpr > fpr_cap:
                continue
            key = (tpr, -fpr, t)
        if best is None or key > best[0]:
            best = (key, t, tpr, fpr)
    if best is None:  # cap unreachable even at the highest threshold (cannot happen: max score gives fpr 0)
        raise ValueError("no threshold satisfies the FPR cap")
    _, t, tpr, fpr = best
    return {"system": system, "objective": objective, "fpr_cap": fpr_cap if objective == "fpr_cap" else None,
            "threshold": t, "dev_macro_tpr": tpr, "dev_macro_fpr": fpr, "sources": sorted(by), "n_dev_rows": len(rows)}
