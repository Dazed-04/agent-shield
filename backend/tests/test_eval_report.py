import pytest

from evaluation.calibrate import calibrate
from evaluation.report import build_report

META = {"thresholds": {"allow_max": 25, "warn_max": 55, "approve_max": 80}, "run_id": "r", "jailbreak_mode": "heuristic"}


def row(i, label, score, split="test", source="s1", cat="c", jb=None):
    return {"id": i, "label": label, "kind": "jailbreak" if label else "benign", "category": cat, "source": source, "split": split,
            "scores": {"prompt_scanner": score / 2, "jailbreak_detector": jb if jb is not None else score, "combined": score},
            "decision": "BLOCK" if score > 80 else "ALLOW", "timings_ms": {"prompt_scanner": 1.0, "jailbreak_detector": 2.0, "total": 3.0}}


def sample_rows():
    rows = []
    for i in range(20):
        rows.append(row(f"a{i}", 1, 90 if i < 16 else 10, split="dev" if i % 2 else "test"))
        rows.append(row(f"b{i}", 0, 5 if i < 18 else 60, split="dev" if i % 2 else "test"))
    return rows


def test_report_numbers_are_correct_and_complete():
    rep = build_report(sample_rows(), META, n_boot=20)
    allg = rep["groups"]["all"]
    assert allg["n"] == 40 and allg["n_attacks"] == 20
    c = allg["systems"]["combined"]["operating_points"]
    assert c["alert"]["tpr"] == 16 / 20 and c["alert"]["fpr"] == 2 / 20
    assert c["block"]["tpr"] == 16 / 20 and c["block"]["fpr"] == 0.0 and c["block"]["fpr_ci"][0] == 0.0
    assert allg["systems"]["combined"]["auc"] > 0.9 and len(allg["systems"]["combined"]["auc_ci"]) == 2
    assert set(rep["groups"]) >= {"all", "split:dev", "split:test", "source:s1", "source:s1|split:test", "kind:jailbreak", "kind:benign"}
    assert rep["latency_ms"]["total"]["p50"] == 3.0
    assert rep["decision_counts"]["s1"]["attack"]["BLOCK"] == 16
    assert {r["id"] for r in rep["false_negatives"]} == {f"a{i}" for i in range(16, 20)}
    assert rep["attack_detection_by_category"]["s1/c"]["n"] == 20


def test_ablation_systems_are_reported_separately():
    rows = [row("a1", 1, 90, jb=0.0), row("b1", 0, 5, jb=0.0), row("a2", 1, 90, jb=0.0), row("b2", 0, 5, jb=0.0)]
    s = build_report(rows, META, n_boot=0)["groups"]["all"]["systems"]
    assert s["jailbreak_detector"]["operating_points"]["alert"]["tpr"] == 0.0
    assert s["combined"]["operating_points"]["alert"]["tpr"] == 1.0


def test_calibration_uses_dev_only_and_is_applied_to_test():
    rows = sample_rows()
    with pytest.raises(ValueError, match="dev split"):
        calibrate(rows, "combined")  # contains test rows
    dev = [r for r in rows if r["split"] == "dev"]
    cal = calibrate(dev, "combined", "youden")
    # dev attacks: 8x90 + 2x10; dev benign: 9x5 + 1x60.  t=5 -> TPR 1.0 / FPR 0.1 (Youden .9) beats
    # t=60 (.8 / 0 -> .8) and t=10 (.8 / .1 -> .7).
    assert cal["threshold"] == 5 and cal["dev_macro_tpr"] == 1.0 and cal["dev_macro_fpr"] == pytest.approx(0.1)
    capped = calibrate(dev, "combined", "fpr_cap", fpr_cap=0.0)
    assert capped["dev_macro_fpr"] == 0.0
    rep = build_report(rows, META, calibrated={"combined": cal["threshold"]}, n_boot=0)
    assert "calibrated" in rep["groups"]["split:test"]["systems"]["combined"]["operating_points"]
    assert "calibrated" not in rep["groups"]["split:test"]["systems"]["prompt_scanner"]["operating_points"]


def test_calibration_rejects_unusable_input():
    with pytest.raises(ValueError):
        calibrate([row("a", 1, 90, split="dev")], "combined")  # no benign
    with pytest.raises(ValueError):
        calibrate([], "combined", "nope")
