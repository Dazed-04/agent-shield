"""Detector-level runner: score every sample through the production Layer-1 path.

One call to ``screen_inbound`` per sample yields all three systems we compare:
``prompt_scanner`` (rules), ``jailbreak_detector`` (semantic or heuristic) and ``combined``
(the risk engine's final score = what the gateway acts on). Predictions are stored per sample so
every metric can be recomputed offline, on any machine, without the model.
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from .datasets import manifest
from .schema import Sample

SYSTEMS = ("prompt_scanner", "jailbreak_detector", "combined")
RESULTS_ROOT = Path(__file__).resolve().parent / "results"
WARMUP_SCANS = 3


def _git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=10, check=False)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def run_metadata(n_samples: int, sources: list[str]) -> dict[str, Any]:
    """Everything needed to reproduce (or distrust) a run."""
    from app import config
    from app.shield import jailbreak_detector

    try:
        import torch  # type: ignore[import-not-found]

        torch_version: str | None = torch.__version__
    except ImportError:
        torch_version = None
    sha = _git("rev-parse", "HEAD")
    return {
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "git_sha": sha or "unknown",
        "git_dirty": bool(_git("status", "--porcelain")) if sha else None,
        "jailbreak_mode": jailbreak_detector.mode,  # "semantic" or "heuristic": never mix them in one table
        "embedding_model": config.EMBEDDING_MODEL_NAME if jailbreak_detector.mode == "semantic" else None,
        "builtin_anchors": len(jailbreak_detector.builtin_anchors),
        "learned_anchors": len(jailbreak_detector.learned),
        "thresholds": {"allow_max": config.ALLOW_MAX, "warn_max": config.WARN_MAX, "approve_max": config.APPROVE_MAX},
        "weights": {"prompt": config.WEIGHT_PROMPT, "jailbreak": config.WEIGHT_JAILBREAK},
        "max_prompt_chars": config.MAX_PROMPT_CHARS,
        "n_samples": n_samples,
        "sources": sources,
        "datasets": manifest(),
        "python": sys.version.split()[0],
        "torch": torch_version,
        "platform": platform.platform(),
    }


def scan_samples(samples: Iterable[Sample], progress: Callable[[int], None] | None = None) -> Iterator[dict[str, Any]]:
    from app.shield import jailbreak_detector, screen_inbound

    jailbreak_detector.warmup()  # keep model load out of the latency numbers
    for _ in range(WARMUP_SCANS):
        screen_inbound("warm up the detectors", "warm up")
    for i, s in enumerate(samples, 1):
        scr = screen_inbound(s.prompt, s.context)
        t = scr.timings
        yield {
            "id": s.id, "label": s.label, "kind": s.kind, "category": s.category, "source": s.source, "split": s.split,
            "scores": {
                "prompt_scanner": float(scr.prompt_result["score"]),
                "jailbreak_detector": float(scr.jailbreak_result["score"]),
                "combined": float(scr.score),
            },
            "decision": scr.decision,
            "timings_ms": {**t, "total": round(sum(t.values()), 2)},
        }
        if progress and i % 200 == 0:
            progress(i)


def run(samples: list[Sample], out_dir: Path | None = None, tag: str = "", progress: Callable[[int], None] | None = None) -> Path:
    """Score ``samples`` and write ``run.json`` + ``predictions.jsonl`` under a fresh run directory."""
    meta = run_metadata(len(samples), sorted({s.source for s in samples}))
    t0 = time.perf_counter()
    rid = f"{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%S}-{meta['jailbreak_mode']}" + (f"-{tag}" if tag else "")
    out = (out_dir or RESULTS_ROOT) / rid
    out.mkdir(parents=True, exist_ok=False)
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for rec in scan_samples(samples, progress):
            f.write(json.dumps(rec) + "\n")
    meta["run_id"] = rid
    meta["wall_seconds"] = round(time.perf_counter() - t0, 1)
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def read_predictions(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
