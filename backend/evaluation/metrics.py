"""Pure-Python metrics (no numpy/sklearn, so the harness runs anywhere the backend runs).

Convention: a higher score means "more likely an attack"; a sample is *flagged* when
``score > threshold`` (the same direction the gateway uses: ALLOW is score <= ALLOW_MAX).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from typing import Any


def confusion(scores: Sequence[float], labels: Sequence[int], threshold: float) -> dict[str, int]:
    tp = fp = tn = fn = 0
    for s, y in zip(scores, labels, strict=True):
        flagged = s > threshold
        if y == 1:
            tp += flagged
            fn += not flagged
        else:
            fp += flagged
            tn += not flagged
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def _div(a: float, b: float) -> float | None:
    return a / b if b else None


def rates(c: dict[str, int]) -> dict[str, float | None]:
    tpr = _div(c["tp"], c["tp"] + c["fn"])
    fpr = _div(c["fp"], c["fp"] + c["tn"])
    prec = _div(c["tp"], c["tp"] + c["fp"])
    f1 = _div(2 * prec * tpr, prec + tpr) if prec is not None and tpr is not None else None
    acc = _div(c["tp"] + c["tn"], sum(c.values()))
    return {"tpr": tpr, "fpr": fpr, "precision": prec, "f1": f1, "accuracy": acc}


def roc_auc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    """Mann-Whitney AUC with average ranks for ties. None if a class is missing."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(len(scores)), key=scores.__getitem__)
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rank_sum = sum(r for r, y in zip(ranks, labels, strict=True) if y == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def roc_curve(scores: Sequence[float], labels: Sequence[int], max_points: int = 60) -> list[dict[str, float]]:
    """(fpr, tpr) points over the distinct score cut-offs, thinned for plotting."""
    cuts = sorted({*scores, -1.0, 101.0})
    pts = []
    for t in cuts:
        r = rates(confusion(scores, labels, t))
        if r["tpr"] is not None and r["fpr"] is not None:
            pts.append({"threshold": t, "fpr": r["fpr"], "tpr": r["tpr"]})
    if len(pts) > max_points:
        step = len(pts) / max_points
        pts = [pts[int(i * step)] for i in range(max_points)] + [pts[-1]]
    return pts


def bootstrap_ci(
    fn: Callable[[Sequence[float], Sequence[int]], float | None],
    scores: Sequence[float],
    labels: Sequence[int],
    n_boot: int = 500,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float] | None:
    """Percentile bootstrap CI, resampling each class separately so the class balance is preserved."""
    pos = [i for i, y in enumerate(labels) if y == 1]
    neg = [i for i, y in enumerate(labels) if y == 0]
    if not pos or not neg:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        idx = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
        v = fn([scores[i] for i in idx], [labels[i] for i in idx])
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    lo = vals[int(math.floor(alpha / 2 * (len(vals) - 1)))]
    hi = vals[int(math.ceil((1 - alpha / 2) * (len(vals) - 1)))]
    return lo, hi


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson interval for a proportion: well behaved at 0/n and n/n, unlike the normal approximation."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q / 100
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def latency_summary(ms: Sequence[float]) -> dict[str, float | None]:
    return {"n": len(ms), "mean": (sum(ms) / len(ms)) if ms else None,
            "p50": percentile(ms, 50), "p95": percentile(ms, 95), "p99": percentile(ms, 99), "max": max(ms) if ms else None}


def operating_point(scores: Sequence[float], labels: Sequence[int], threshold: float, with_ci: bool = True) -> dict[str, Any]:
    """Counts, rates and Wilson CIs for TPR / FPR at one threshold."""
    c = confusion(scores, labels, threshold)
    out: dict[str, Any] = {"threshold": threshold, **c, **rates(c)}
    if with_ci:
        out["tpr_ci"] = wilson_ci(c["tp"], c["tp"] + c["fn"])
        out["fpr_ci"] = wilson_ci(c["fp"], c["fp"] + c["tn"])
    return out
