"""``python -m evaluation <command>``  (run from ``backend/``).

  prepare    fetch the public datasets at their pinned commits
  build      assemble data/processed/eval_set.jsonl from the datasets (+ in-house set)
  scan       score every sample through the production detectors -> results/<run>/
  calibrate  fit thresholds on the dev split of a run
  report     compute metrics and write report.json / report.md / report.csv / ablation.tex
  agent-scan    run the end-to-end agent benchmark (needs a model key, or --llm scripted-gullible for a dry run)
  agent-report  summarise an agent-scan run into tables
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .datasets import DATA_ROOT, DATASETS, RAW_ROOT, prepare


RESULTS_DIR = Path(__file__).parent / "results"


def _resolve_run(arg: str) -> Path:
    """Accept a run folder path, a bare run id from the results folder, or 'latest'."""
    direct = Path(arg)
    if direct.is_dir():
        return direct
    runs = sorted((d for d in RESULTS_DIR.iterdir() if d.is_dir()), key=lambda d: d.name) if RESULTS_DIR.is_dir() else []
    if arg == "latest" and runs:
        return runs[-1]
    if (RESULTS_DIR / arg).is_dir():
        return RESULTS_DIR / arg
    hint = "replace the <run> placeholder with a real run" if arg.startswith("<") else f"no run folder '{arg}'"
    listing = "\n  ".join(d.name for d in runs[-5:]) or "(none yet; run `python -m evaluation scan` first)"
    raise SystemExit(f"error: {hint}. Looked in {RESULTS_DIR}. Most recent runs:\n  {listing}")


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

    rows = [r for r in read_predictions(_resolve_run(a.run) / "predictions.jsonl") if r["split"] == "dev"]
    result = {s: calibrate(rows, s, a.objective, a.fpr_cap) for s in a.systems}
    path = _resolve_run(a.run) / "thresholds.json"
    path.write_text(json.dumps(result, indent=2))
    for s, c in result.items():
        print(f"{s}: threshold {c['threshold']} (dev macro TPR {c['dev_macro_tpr']:.3f}, FPR {c['dev_macro_fpr']:.3f})")
    print(f"wrote {path}")
    return 0


def _cmd_report(a: argparse.Namespace) -> int:
    from .report import build_report
    from .runner import read_predictions
    from .tables import render_csv, render_latex_ablation, render_markdown

    run = _resolve_run(a.run)
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


def _cmd_agent_scan(a: argparse.Namespace) -> int:
    import datetime as dt

    sandbox = Path(tempfile.mkdtemp(prefix="eval_sandbox_"))
    os.environ["AGENT_SHIELD_SANDBOX_DIR"] = str(sandbox)
    os.environ["AGENT_SHIELD_DISABLE_EMBEDDINGS"] = "1" if a.embeddings == "off" else os.environ.get("AGENT_SHIELD_DISABLE_EMBEDDINGS", "0")
    os.environ["THREAT_VECTORS_PATH"] = str(Path(tempfile.mkdtemp(prefix="eval_tv_")) / "none.json")
    if a.llm == "real":
        try:
            from dotenv import load_dotenv

            load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        except ImportError:
            pass
    from unittest import mock

    import app.agent.langgraph_agent as graph

    from .agent_bench import build_scenarios
    from .agent_eval import DEFAULT_ROLES, SHIELDED, SYSTEMS, QuotaExhausted, RunAborted, run_matrix
    from .runner import run_metadata
    from .scripted_llm import ScriptedAgentLLM

    scenarios = build_scenarios()
    if a.limit_scenarios:
        scenarios = scenarios[: a.limit_scenarios]
    systems = a.systems or list(SYSTEMS)
    roles = a.roles or list(DEFAULT_ROLES)
    n_jobs = sum(len(roles) if s in SHIELDED else 1 for s in systems) * len(scenarios) * a.repeats
    print(f"{n_jobs} runs ({len(scenarios)} scenarios x {len(systems)} systems x {a.repeats} repeat(s)); "
          f"each run makes ~2-4 model calls" + (" (REAL model: check your provider quota)" if a.llm == "real" else " (scripted: free)"))
    patch = (mock.patch.object(graph, "get_llm_with_fallbacks", lambda tools, mid=None: ScriptedAgentLLM(a.llm.split("-", 1)[1]))
             if a.llm.startswith("scripted") else mock.patch.object(graph, "__name__", graph.__name__))
    done: set[tuple[str, str, str, int]] = set()
    if a.resume:
        out = _resolve_run(a.resume)
        rid = out.name
        prior = out / "agent_runs.jsonl"
        if prior.exists():  # only runs that produced a verdict count as done; errored ones are retried
            from .runner import read_predictions

            done = {(r["system"], r["role"], r["id"], r["repeat"]) for r in read_predictions(prior) if r["status"] != "ERROR"}
        print(f"resuming {rid}: {len(done)} runs already complete")
    else:
        rid = f"{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%S}-agent-{a.llm}" + (f"-{a.tag}" if a.tag else "")
        out = Path(a.results_dir) / rid
        out.mkdir(parents=True, exist_ok=False)
    stopped = ""
    with patch, (out / "agent_runs.jsonl").open("a", encoding="utf-8") as f:
        try:
            for rec in run_matrix(scenarios, systems, roles, a.model_id or None, a.repeats, progress=lambda i, n: print(f"  {i}/{n}", flush=True),
                                  max_consecutive_errors=a.max_consecutive_errors, skip=lambda sy, ro, sid, k: (sy, ro, sid, k) in done):
                f.write(json.dumps(rec) + "\n")
                f.flush()
        except QuotaExhausted as e:
            stopped = f"provider daily quota exhausted: {e}"
        except RunAborted as e:
            stopped = str(e)
    meta = run_metadata(0, [])
    meta.update({"run_id": rid, "llm": a.llm, "model_id": a.model_id or None, "repeats": a.repeats, "n_scenarios": len(scenarios),
                 "systems": systems, "roles": roles, "complete": not stopped, "stopped_reason": stopped or None})
    meta.pop("datasets", None)
    (out / "agent_run.json").write_text(json.dumps(meta, indent=2))
    print(f"run {out}")
    if stopped:
        print(f"STOPPED EARLY: {stopped}\nResults so far are saved. Resume later with:\n  python -m evaluation agent-scan --resume {rid} "
              f"--llm {a.llm} --repeats {a.repeats}", file=sys.stderr)
        return 2
    return 0


def _cmd_agent_report(a: argparse.Namespace) -> int:
    from .agent_report import render_markdown, summarize
    from .runner import read_predictions

    run = _resolve_run(a.run)
    rows = read_predictions(run / "agent_runs.jsonl")
    meta = json.loads((run / "agent_run.json").read_text())
    summary = summarize(rows)
    (run / "agent_report.json").write_text(json.dumps({"meta": meta, **summary}, indent=2))
    (run / "agent_report.md").write_text(render_markdown(summary, meta))
    print(f"wrote agent_report.json and agent_report.md in {run}")
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
    p.add_argument("--results-dir", default=str(RESULTS_DIR))
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

    p = sub.add_parser("agent-scan")
    p.add_argument("--llm", choices=["real", "scripted-gullible", "scripted-resistant"], default="real")
    p.add_argument("--model-id", default="", help="provider id from config/models.json (real runs)")
    p.add_argument("--systems", nargs="+", choices=["no_shield", "prompt_hardening", "shield_full", "shield_no_quarantine", "shield_no_monitor"])
    p.add_argument("--roles", nargs="+", choices=["Domain Admins", "Data Science", "Standard Users"])
    p.add_argument("--repeats", type=int, default=1, help="repeat each scenario (LLMs are non-deterministic)")
    p.add_argument("--limit-scenarios", type=int, default=0)
    p.add_argument("--resume", default="", help="continue an interrupted run (folder, run id or 'latest'): finished runs are kept, errored ones retried")
    p.add_argument("--max-consecutive-errors", type=int, default=8, help="stop (and save) after this many provider errors in a row")
    p.add_argument("--embeddings", choices=["on", "off"], default="on")
    p.add_argument("--tag", default="")
    p.add_argument("--results-dir", default=str(RESULTS_DIR))
    p.set_defaults(fn=_cmd_agent_scan)

    p = sub.add_parser("agent-report")
    p.add_argument("run")
    p.set_defaults(fn=_cmd_agent_report)

    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
