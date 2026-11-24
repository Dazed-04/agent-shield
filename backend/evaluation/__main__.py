"""``python -m evaluation <command>``  (run from ``backend/``).

  prepare    fetch the public datasets at their pinned commits
  build      assemble data/processed/eval_set.jsonl from the datasets (+ in-house set)
  scan       score every sample through the production detectors -> results/<run>/
  calibrate  fit thresholds on the dev split of a run
  report     compute metrics and write report.json / report.md / report.csv / ablation.tex
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .datasets import DATA_ROOT, DATASETS, RAW_ROOT, prepare


def _cmd_prepare(a: argparse.Namespace) -> int:
    for name in a.names or DATASETS:
        print(f"{name}: {prepare(DATASETS[name], Path(a.raw_dir))}")
    return 0


def _cmd_build(a: argparse.Namespace) -> int:
    from .inhouse import load_inhouse
    from .loaders import load_bipia, load_injecagent, load_jailbreak_llms
    from .schema import check_unique_ids, write_jsonl

    raw = Path(a.raw_dir)
    makers = {
        "injecagent": lambda: load_injecagent(raw / "injecagent"),
        "bipia": lambda: load_bipia(raw / "bipia", seed=a.seed),
        "jailbreak_llms": lambda: load_jailbreak_llms(raw / "jailbreak_llms", max_regular=a.max_regular, seed=a.seed),
    }
    rows = []
    for name in a.sources:
        if name == "inhouse":
            rows += list(load_inhouse())
        elif name in makers:
            if not (raw / name).exists():
                print(f"missing {raw / name}: run `python -m evaluation prepare` first", file=sys.stderr)
                return 2
            rows += list(makers[name]())
        else:
            print(f"unknown source {name!r}", file=sys.stderr)
            return 2
    out = Path(a.out)
    n = write_jsonl(out, check_unique_ids(rows))
    print(f"wrote {n} samples to {out}")
    return 0


def _cmd_scan(a: argparse.Namespace) -> int:
    # Environment must be fixed BEFORE the app modules are imported.
    if a.embeddings == "off":
        os.environ["AGENT_SHIELD_DISABLE_EMBEDDINGS"] = "1"
    if not a.use_learned:  # learned phrases would contaminate a benchmark: use an empty file
        os.environ["THREAT_VECTORS_PATH"] = str(Path(tempfile.mkdtemp(prefix="eval_tv_")) / "none.json")
    from .runner import run
    from .schema import read_jsonl

    samples = list(read_jsonl(a.set))
    if a.limit:
        samples = samples[: a.limit]
    out = run(samples, Path(a.results_dir), a.tag, progress=lambda i: print(f"  {i}/{len(samples)}", flush=True))
    meta = json.loads((out / "run.json").read_text())
    print(f"run {out} | mode={meta['jailbreak_mode']} | {meta['wall_seconds']}s")
    return 0


def _cmd_calibrate(a: argparse.Namespace) -> int:
    from .calibrate import calibrate
    from .runner import read_predictions

    rows = [r for r in read_predictions(Path(a.run) / "predictions.jsonl") if r["split"] == "dev"]
    result = {s: calibrate(rows, s, a.objective, a.fpr_cap) for s in a.systems}
    path = Path(a.run) / "thresholds.json"
    path.write_text(json.dumps(result, indent=2))
    for s, c in result.items():
        print(f"{s}: threshold {c['threshold']} (dev macro TPR {c['dev_macro_tpr']:.3f}, FPR {c['dev_macro_fpr']:.3f})")
    print(f"wrote {path}")
    return 0


def _cmd_report(a: argparse.Namespace) -> int:
    from .report import build_report
    from .runner import read_predictions
    from .tables import render_csv, render_latex_ablation, render_markdown

    run = Path(a.run)
    meta = json.loads((run / "run.json").read_text())
    cal = None
    tpath = Path(a.thresholds) if a.thresholds else run / "thresholds.json"
    if tpath.exists():
        cal = {s: c["threshold"] for s, c in json.loads(tpath.read_text()).items()}
    rep = build_report(read_predictions(run / "predictions.jsonl"), meta, cal, n_boot=a.n_boot)
    (run / "report.json").write_text(json.dumps(rep, indent=2))
    (run / "report.md").write_text(render_markdown(rep))
    (run / "report.csv").write_text(render_csv(rep))
    (run / "ablation.tex").write_text(render_latex_ablation(rep))
    print(f"wrote report.json, report.md, report.csv, ablation.tex in {run}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evaluation", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("names", nargs="*", choices=list(DATASETS))
    p.add_argument("--raw-dir", default=str(RAW_ROOT))
    p.set_defaults(fn=_cmd_prepare)

    p = sub.add_parser("build")
    p.add_argument("--sources", nargs="+", default=[*DATASETS, "inhouse"])
    p.add_argument("--raw-dir", default=str(RAW_ROOT))
    p.add_argument("--out", default=str(DATA_ROOT / "processed" / "eval_set.jsonl"))
    p.add_argument("--max-regular", type=int, default=2000)
    p.add_argument("--seed", type=int, default=2023)
    p.set_defaults(fn=_cmd_build)

    p = sub.add_parser("scan")
    p.add_argument("--set", default=str(DATA_ROOT / "processed" / "eval_set.jsonl"))
    p.add_argument("--embeddings", choices=["on", "off"], default="on", help="off = keyword fallback only (heuristic mode)")
    p.add_argument("--use-learned", action="store_true", help="include runtime-learned anchors (off by default: they contaminate benchmarks)")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--tag", default="")
    p.add_argument("--results-dir", default=str(Path(__file__).parent / "results"))
    p.set_defaults(fn=_cmd_scan)

    p = sub.add_parser("calibrate")
    p.add_argument("run")
    p.add_argument("--systems", nargs="+", default=["prompt_scanner", "jailbreak_detector", "combined"])
    p.add_argument("--objective", choices=["youden", "fpr_cap"], default="youden")
    p.add_argument("--fpr-cap", type=float, default=0.02)
    p.set_defaults(fn=_cmd_calibrate)

    p = sub.add_parser("report")
    p.add_argument("run")
    p.add_argument("--thresholds", default="")
    p.add_argument("--n-boot", type=int, default=200)
    p.set_defaults(fn=_cmd_report)

    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
