"""Turn predictions into the numbers the paper reports (pure functions over ``predictions.jsonl``)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .metrics import bootstrap_ci, latency_summary, operating_point, roc_auc, roc_curve
from .runner import SYSTEMS

OP_NAMES = ("alert", "intervene", "block")  # score > ALLOW_MAX / WARN_MAX / APPROVE_MAX
THRESHOLD_KEYS = {"alert": "allow_max", "intervene": "warn_max", "block": "approve_max"}


def _group(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    g: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        for key in ("all", f"split:{r['split']}", f"source:{r['source']}", f"source:{r['source']}|split:{r['split']}", f"kind:{r['kind']}"):
            g[key].append(r)
    return g


def _system_block(rows: list[dict[str, Any]], system: str, ops: dict[str, float], n_boot: int) -> dict[str, Any]:
    scores = [r["scores"][system] for r in rows]
    labels = [r["label"] for r in rows]
    auc = roc_auc(scores, labels)
    return {
        "auc": auc,
        "auc_ci": bootstrap_ci(roc_auc, scores, labels, n_boot=n_boot) if auc is not None and n_boot else None,
        "operating_points": {name: operating_point(scores, labels, t) for name, t in ops.items()},
    }


def build_report(rows: list[dict[str, Any]], run_meta: dict[str, Any], calibrated: dict[str, float] | None = None, n_boot: int = 200) -> dict[str, Any]:
    """``calibrated`` maps system -> threshold fitted on dev; it is evaluated as an extra operating point."""
    base_ops = {name: float(run_meta["thresholds"][key]) for name, key in THRESHOLD_KEYS.items()}
    groups: dict[str, Any] = {}
    for name, grp in sorted(_group(rows).items()):
        labels = [r["label"] for r in grp]
        entry: dict[str, Any] = {"n": len(grp), "n_attacks": sum(labels), "n_benign": len(labels) - sum(labels), "systems": {}}
        for system in SYSTEMS:
            ops = dict(base_ops)
            if calibrated and system in calibrated:
                ops["calibrated"] = calibrated[system]
            entry["systems"][system] = _system_block(grp, system, ops, n_boot if name in ("all", "split:test", "split:dev") else 0)
        groups[name] = entry

    sources = sorted({r["source"] for r in rows})
    macro: dict[str, Any] = {}
    for system in SYSTEMS:
        per_op: dict[str, Any] = {}
        for op in OP_NAMES:
            tprs, fprs = [], []
            for s in sources:
                v = groups.get(f"source:{s}|split:test") or groups.get(f"source:{s}")
                pt = v["systems"][system]["operating_points"][op]
                if pt["tpr"] is not None:
                    tprs.append(pt["tpr"])
                if pt["fpr"] is not None:
                    fprs.append(pt["fpr"])
            per_op[op] = {"tpr": sum(tprs) / len(tprs) if tprs else None, "fpr": sum(fprs) / len(fprs) if fprs else None}
        macro[system] = per_op

    cat: dict[str, Any] = {}
    for r in rows:
        if r["label"] == 1:
            c = cat.setdefault(f"{r['source']}/{r['category']}", {"n": 0, "alert": 0, "intervene": 0})
            c["n"] += 1
            c["alert"] += r["scores"]["combined"] > base_ops["alert"]
            c["intervene"] += r["scores"]["combined"] > base_ops["intervene"]

    decisions: dict[str, Any] = {}
    for r in rows:
        decisions.setdefault(r["source"], {"attack": Counter(), "benign": Counter()})["attack" if r["label"] else "benign"][r["decision"]] += 1

    timing_keys = sorted({k for r in rows for k in r["timings_ms"]})
    latency = {k: latency_summary([r["timings_ms"][k] for r in rows if k in r["timings_ms"]]) for k in timing_keys}

    # Error examples come from the DEV split only. Showing test-split errors would invite fixing the
    # detectors against held-out data, which silently turns the test numbers into training numbers.
    comb = sorted((r for r in rows if r["split"] == "dev"), key=lambda r: r["scores"]["combined"])
    fps = [r for r in reversed(comb) if r["label"] == 0 and r["scores"]["combined"] > base_ops["alert"]][:15]
    fns = [r for r in comb if r["label"] == 1 and r["scores"]["combined"] <= base_ops["alert"]][:15]
    brief = lambda r: {k: r[k] for k in ("id", "source", "category", "split")} | {"score": r["scores"]["combined"]}  # noqa: E731

    return {
        "run": {k: run_meta.get(k) for k in ("run_id", "created_at", "git_sha", "git_dirty", "jailbreak_mode", "embedding_model",
                                             "learned_anchors", "thresholds", "n_samples", "python", "torch")},
        "operating_points": base_ops,
        "calibrated_thresholds": calibrated or {},
        "groups": groups,
        "macro_over_sources": macro,
        "attack_detection_by_category": dict(sorted(cat.items())),
        "decision_counts": {s: {k: dict(v) for k, v in d.items()} for s, d in decisions.items()},
        "latency_ms": latency,
        "roc_combined_test": roc_curve([r["scores"]["combined"] for r in rows if r["split"] == "test"],
                                       [r["label"] for r in rows if r["split"] == "test"]),
        "false_positives": [brief(r) for r in fps],
        "false_negatives": [brief(r) for r in fns],
    }
