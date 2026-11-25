"""Operational metrics over the audit log, computed from plain rows (no DB access here).

The gateway keeps one audit row per request. This module turns a window of those rows into the numbers
the dashboard (and the paper's "deployment" section) needs: decision mix, score distribution,
per-detector hit rates, latency percentiles per pipeline stage, and a time series.
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from app.config import ALLOW_MAX, APPROVE_MAX, WARN_MAX

DECISIONS = ("ALLOW", "WARN", "APPROVE", "BLOCK")
DETECTORS = ("prompt_scanner", "jailbreak_detector")
HISTOGRAM_BINS = 10  # 0-10, 10-20, ... 90-100


@dataclass(frozen=True)
class AuditRow:
    timestamp: datetime.datetime
    role: str | None
    decision: str
    risk_score: float
    latency_ms: float | None
    detectors: dict[str, Any]
    tool_calls: int


def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return round(xs[0], 2)
    pos = (len(xs) - 1) * q / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo), 2)


def latency_summary(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values), 2) if values else None,
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
    }


def _bucket_start(ts: datetime.datetime, hourly: bool) -> datetime.datetime:
    return ts.replace(minute=0, second=0, microsecond=0) if hourly else ts.replace(hour=0, minute=0, second=0, microsecond=0)


def _num(x: Any) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def compute_metrics(rows: list[AuditRow], days: int, now: datetime.datetime, truncated: bool = False) -> dict[str, Any]:
    mix = Counter({d: 0 for d in DECISIONS})
    by_role: dict[str, Counter[str]] = defaultdict(Counter)
    hist = [0] * HISTOGRAM_BINS
    hits: dict[str, dict[str, Any]] = {d: {"flagged": 0, "scores": []} for d in DETECTORS}
    modes: Counter[str] = Counter()
    totals: list[float] = []
    stages: dict[str, list[float]] = defaultdict(list)
    hourly = days <= 2
    series: dict[datetime.datetime, Counter[str]] = defaultdict(Counter)
    with_tools = 0

    for r in rows:
        mix[r.decision] += 1
        by_role[r.role or "unknown"][r.decision] += 1
        hist[min(int(max(r.risk_score, 0.0) // (100 / HISTOGRAM_BINS)), HISTOGRAM_BINS - 1)] += 1
        series[_bucket_start(r.timestamp, hourly)][r.decision] += 1
        with_tools += 1 if r.tool_calls else 0
        if r.latency_ms is not None:
            totals.append(float(r.latency_ms))
        for name in DETECTORS:
            d = r.detectors.get(name)
            score = _num(d.get("score")) if isinstance(d, dict) else None
            if score is None:
                continue
            hits[name]["scores"].append(score)
            hits[name]["flagged"] += 1 if score > ALLOW_MAX else 0
        jb = r.detectors.get("jailbreak_detector")
        if isinstance(jb, dict) and jb.get("mode"):
            modes[str(jb["mode"])] += 1
        t = r.detectors.get("timings_ms")
        if isinstance(t, dict):
            for stage, ms in t.items():
                if stage != "total" and _num(ms) is not None:
                    stages[stage].append(float(ms))

    n = len(rows)
    return {
        "window": {"days": days, "from": (now - datetime.timedelta(days=days)).isoformat(), "to": now.isoformat(), "bucket": "hour" if hourly else "day"},
        "thresholds": {"allow_max": ALLOW_MAX, "warn_max": WARN_MAX, "approve_max": APPROVE_MAX},
        "n": n,
        "truncated": truncated,
        "decision_mix": {d: mix[d] for d in DECISIONS},
        "decision_by_role": {role: {d: c[d] for d in DECISIONS} for role, c in sorted(by_role.items())},
        "score_histogram": [{"from": i * 10, "to": (i + 1) * 10, "count": c} for i, c in enumerate(hist)],
        "detector_hits": {
            name: {
                "flagged": v["flagged"],
                "flag_rate": round(v["flagged"] / len(v["scores"]), 4) if v["scores"] else None,
                "mean_score": round(sum(v["scores"]) / len(v["scores"]), 2) if v["scores"] else None,
                "n": len(v["scores"]),
            }
            for name, v in hits.items()
        },
        "jailbreak_mode": dict(modes),
        "with_tool_calls": with_tools,
        "latency_ms": {"total": latency_summary(totals), "stages": {k: latency_summary(v) for k, v in sorted(stages.items())}},
        "timeseries": [{"t": t.isoformat(), **{d: c[d] for d in DECISIONS}} for t, c in sorted(series.items())],
    }
