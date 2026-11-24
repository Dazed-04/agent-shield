import math

import pytest

from evaluation.metrics import (
    bootstrap_ci,
    confusion,
    latency_summary,
    operating_point,
    percentile,
    rates,
    roc_auc,
    roc_curve,
    wilson_ci,
)


def test_confusion_and_rates_use_strictly_greater_than():
    c = confusion([10, 25, 26, 90], [0, 0, 1, 1], 25)
    assert c == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}  # 25 is NOT flagged (matches ALLOW_MAX)
    r = rates({"tp": 8, "fp": 2, "tn": 18, "fn": 2})
    assert r["tpr"] == 0.8 and r["fpr"] == 0.1 and r["precision"] == 0.8 and round(r["f1"], 3) == 0.8
    assert rates({"tp": 0, "fp": 0, "tn": 0, "fn": 0})["tpr"] is None


def test_auc_known_values():
    assert roc_auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0
    assert roc_auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == 0.0
    assert roc_auc([5, 5, 5, 5], [0, 1, 0, 1]) == 0.5  # all ties
    assert roc_auc([1, 2], [1, 1]) is None
    # sklearn reference: roc_auc_score([0,0,1,1],[0.1,0.4,0.35,0.8]) == 0.75
    assert roc_auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)


def test_roc_curve_endpoints():
    pts = roc_curve([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1])
    assert {"fpr": 1.0, "tpr": 1.0} == {k: pts[0][k] for k in ("fpr", "tpr")}
    assert pts[-1]["fpr"] == 0.0 and pts[-1]["tpr"] == 0.0


def test_wilson_matches_reference_and_handles_edges():
    lo, hi = wilson_ci(8, 10)
    assert (round(lo, 3), round(hi, 3)) == (0.490, 0.943)
    assert wilson_ci(0, 20)[0] == 0.0 and wilson_ci(0, 20)[1] > 0
    assert wilson_ci(0, 0) is None


def test_bootstrap_is_deterministic_and_brackets_the_estimate():
    s = [i / 100 for i in range(100)]
    y = [1 if i > 40 else 0 for i in range(100)]
    ci = bootstrap_ci(roc_auc, s, y, n_boot=200)
    assert ci == bootstrap_ci(roc_auc, s, y, n_boot=200)
    assert ci[0] <= roc_auc(s, y) <= ci[1]
    assert bootstrap_ci(roc_auc, [1, 2], [1, 1]) is None


def test_percentiles():
    assert percentile([1, 2, 3, 4], 50) == 2.5 and percentile([], 50) is None
    lat = latency_summary([float(i) for i in range(1, 101)])
    assert lat["p50"] == pytest.approx(50.5) and lat["p95"] == pytest.approx(95.05) and lat["max"] == 100
    assert math.isclose(lat["mean"], 50.5)


def test_operating_point_bundle():
    op = operating_point([10, 30, 60, 90], [0, 0, 1, 1], 25)
    assert op["fp"] == 1 and op["tp"] == 2 and "fpr_ci" in op and op["threshold"] == 25
