import datetime

from app.metrics import AuditRow, compute_metrics, latency_summary, percentile

NOW = datetime.datetime(2026, 11, 25, 12, 0, 0)


def row(decision="ALLOW", score=5.0, role="Standard Users", latency=20.0, det=None, calls=0, ts=None):
    return AuditRow(ts or NOW - datetime.timedelta(hours=1), role, decision, score, latency, det or {}, calls)


def test_percentiles_interpolate_and_handle_small_inputs():
    assert percentile([], 50) is None and percentile([7.0], 99) == 7.0
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(xs, 50) == 3.0 and percentile(xs, 0) == 1.0 and percentile(xs, 100) == 5.0
    assert percentile(xs, 25) == 2.0 and percentile(xs, 90) == 4.6
    s = latency_summary(xs)
    assert s["n"] == 5 and s["mean"] == 3.0 and s["p50"] == 3.0
    assert latency_summary([]) == {"n": 0, "mean": None, "p50": None, "p95": None, "p99": None}


def test_empty_window_is_well_formed():
    m = compute_metrics([], 7, NOW)
    assert m["thresholds"] == {"allow_max": 25.0, "warn_max": 55.0, "approve_max": 80.0}
    assert m["n"] == 0 and m["decision_mix"] == {"ALLOW": 0, "WARN": 0, "APPROVE": 0, "BLOCK": 0}
    assert len(m["score_histogram"]) == 10 and m["timeseries"] == [] and m["latency_ms"]["total"]["p50"] is None


def test_mix_roles_histogram_and_tool_calls():
    rows = [row("ALLOW", 5), row("BLOCK", 100, role="Data Science", calls=1), row("WARN", 30), row("BLOCK", 95, role="Data Science")]
    m = compute_metrics(rows, 7, NOW)
    assert m["decision_mix"] == {"ALLOW": 1, "WARN": 1, "APPROVE": 0, "BLOCK": 2}
    assert m["decision_by_role"]["Data Science"]["BLOCK"] == 2
    h = {b["from"]: b["count"] for b in m["score_histogram"]}
    assert h[0] == 1 and h[30] == 1 and h[90] == 2  # a score of exactly 100 lands in the top bin
    assert m["with_tool_calls"] == 1


def test_detector_hits_modes_and_stage_latency():
    det = {
        "prompt_scanner": {"score": 90.0},
        "jailbreak_detector": {"score": 10.0, "mode": "semantic"},
        "timings_ms": {"prompt_scanner": 1.0, "jailbreak_detector": 6.0, "agent": 800.0, "total": 810.0},
    }
    quiet = {"prompt_scanner": {"score": 0.0}, "jailbreak_detector": {"score": 0.0, "mode": "heuristic"}}
    m = compute_metrics([row(det=det, latency=810.0), row(det=quiet), row(det={})], 7, NOW)
    ps = m["detector_hits"]["prompt_scanner"]
    assert ps["n"] == 2 and ps["flagged"] == 1 and ps["flag_rate"] == 0.5 and ps["mean_score"] == 45.0
    assert m["jailbreak_mode"] == {"semantic": 1, "heuristic": 1}
    assert set(m["latency_ms"]["stages"]) == {"agent", "jailbreak_detector", "prompt_scanner"}  # "total" is not a stage
    assert m["latency_ms"]["stages"]["agent"]["p50"] == 800.0


def test_malformed_detector_payloads_are_ignored():
    det = {"prompt_scanner": "oops", "jailbreak_detector": {"score": "high"}, "timings_ms": {"agent": "slow", "x": True}}
    m = compute_metrics([row(det=det)], 7, NOW)
    assert m["detector_hits"]["prompt_scanner"]["n"] == 0 and m["detector_hits"]["jailbreak_detector"]["n"] == 0
    assert m["latency_ms"]["stages"] == {}


def test_timeseries_buckets_hourly_for_short_windows_daily_otherwise():
    a, b = NOW - datetime.timedelta(hours=1, minutes=10), NOW - datetime.timedelta(hours=1, minutes=40)
    short = compute_metrics([row(ts=a), row("BLOCK", 90, ts=b)], 1, NOW)
    assert short["window"]["bucket"] == "hour" and len(short["timeseries"]) == 1
    assert short["timeseries"][0]["ALLOW"] == 1 and short["timeseries"][0]["BLOCK"] == 1
    long = compute_metrics([row(ts=NOW - datetime.timedelta(days=2)), row(ts=NOW)], 7, NOW)
    assert long["window"]["bucket"] == "day" and [p["t"][:10] for p in long["timeseries"]] == ["2026-11-23", "2026-11-25"]
