"""Render a report as paper-ready tables: Markdown, CSV and LaTeX. Numbers only come from the report."""

from __future__ import annotations

import csv
import io
from typing import Any

from .report import OP_NAMES
from .runner import SYSTEMS

LABELS = {"prompt_scanner": "Prompt scanner (rules)", "jailbreak_detector": "Jailbreak detector", "combined": "Combined (risk engine)"}


def f3(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def with_ci(v: float | None, ci: Any) -> str:
    return "n/a" if v is None else (f"{v:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else f"{v:.3f}")


def _ops(report: dict[str, Any], group: str, system: str) -> dict[str, Any]:
    return report["groups"][group]["systems"][system]["operating_points"]


def ablation_rows(report: dict[str, Any], group: str = "split:test") -> list[list[str]]:
    ops_names = [*OP_NAMES, *(["calibrated"] if report["calibrated_thresholds"] else [])]
    header = ["System", "AUC [95% CI]", *[f"{o} TPR / FPR" for o in ops_names]]
    rows = [header]
    for s in SYSTEMS:
        blk = report["groups"][group]["systems"][s]
        cells = [LABELS[s], with_ci(blk["auc"], blk["auc_ci"])]
        for o in ops_names:
            p = blk["operating_points"].get(o)
            cells.append("n/a" if p is None else f"{f3(p['tpr'])} / {f3(p['fpr'])}")
        rows.append(cells)
    return rows


def _md(rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join("---" for _ in rows[0]) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def per_source_rows(report: dict[str, Any], system: str = "combined", split: str = "test") -> list[list[str]]:
    rows = [["Source", "attacks", "benign", "AUC", "alert TPR / FPR", "intervene TPR / FPR", "block TPR / FPR"]]
    for name in sorted(k for k in report["groups"] if k.startswith("source:") and k.endswith(f"|split:{split}")):
        g = report["groups"][name]
        blk = g["systems"][system]
        o = blk["operating_points"]
        rows.append([name.split(":", 1)[1].split("|")[0], str(g["n_attacks"]), str(g["n_benign"]), f3(blk["auc"]),
                     *[f"{f3(o[k]['tpr'])} / {f3(o[k]['fpr'])}" for k in OP_NAMES]])
    return rows


def latency_rows(report: dict[str, Any]) -> list[list[str]]:
    rows = [["Stage", "n", "mean ms", "p50", "p95", "p99", "max"]]
    for k, v in report["latency_ms"].items():
        rows.append([k, str(v["n"]), *[f3(v[x]) for x in ("mean", "p50", "p95", "p99", "max")]])
    return rows


def category_rows(report: dict[str, Any]) -> list[list[str]]:
    rows = [["Source / category", "n", "detected (alert)", "detected (intervene)"]]
    for k, v in report["attack_detection_by_category"].items():
        rows.append([k, str(v["n"]), f"{v['alert'] / v['n']:.3f}", f"{v['intervene'] / v['n']:.3f}"])
    return rows


def render_markdown(report: dict[str, Any]) -> str:
    r = report["run"]
    head = (f"# Evaluation report `{r['run_id']}`\n\n"
            f"- jailbreak detector mode: **{r['jailbreak_mode']}**"
            + (f" ({r['embedding_model']})" if r.get("embedding_model") else "")
            + f"\n- commit: `{r['git_sha']}`" + (" (**dirty working tree**)" if r.get("git_dirty") else "")
            + f"\n- samples: {r['n_samples']}, learned anchors in use: {r['learned_anchors']}"
            f"\n- operating points: alert > {report['operating_points']['alert']}, intervene > {report['operating_points']['intervene']},"
            f" block > {report['operating_points']['block']}"
            + (f"\n- dev-calibrated thresholds: {report['calibrated_thresholds']}" if report["calibrated_thresholds"] else "") + "\n")
    parts = [head,
             "## Ablation: held-out test split (all sources pooled)\n\n" + _md(ablation_rows(report, "split:test")),
             "## Ablation: dev split (for comparison)\n\n" + _md(ablation_rows(report, "split:dev")),
             "## Combined system by source (test split)\n\n" + _md(per_source_rows(report)),
             "## Latency (per request, detectors only)\n\n" + _md(latency_rows(report)),
             "## Attack detection by category (all splits)\n\n" + _md(category_rows(report))]
    fps = report["false_positives"]
    if fps:
        parts.append("## Highest-scoring false positives\n\n" + _md([["id", "source", "category", "score"], *[[x["id"], x["source"], x["category"], f"{x['score']:.1f}"] for x in fps]]))
    fns = report["false_negatives"]
    if fns:
        parts.append("## Missed attacks (alert threshold)\n\n" + _md([["id", "source", "category", "score"], *[[x["id"], x["source"], x["category"], f"{x['score']:.1f}"] for x in fns]]))
    return "\n\n".join(parts) + "\n"


def render_csv(report: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["group", "system", "operating_point", "threshold", "n_attacks", "n_benign", "tp", "fp", "tn", "fn", "tpr", "fpr", "precision", "f1", "auc"])
    for gname, g in report["groups"].items():
        for s, blk in g["systems"].items():
            for op, p in blk["operating_points"].items():
                w.writerow([gname, s, op, p["threshold"], g["n_attacks"], g["n_benign"], p["tp"], p["fp"], p["tn"], p["fn"],
                            p["tpr"], p["fpr"], p["precision"], p["f1"], blk["auc"]])
    return buf.getvalue()


def _tex(s: str) -> str:
    return s.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_").replace("/", "/")


def render_latex_ablation(report: dict[str, Any], group: str = "split:test") -> str:
    rows = ablation_rows(report, group)
    cols = "l" + "r" * (len(rows[0]) - 1)
    lines = [r"\begin{tabular}{" + cols + "}", r"\hline", " & ".join(_tex(c) for c in rows[0]) + r" \\", r"\hline"]
    lines += [" & ".join(_tex(c) for c in r) + r" \\" for r in rows[1:]]
    lines += [r"\hline", r"\end{tabular}"]
    return "\n".join(lines) + "\n"
