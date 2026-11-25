"""Read-only access to saved evaluation runs (detector-level and end-to-end) for the dashboard.

A run is a folder under EVAL_RESULTS_DIR:
  detector run   run.json + report.json            (written by `python -m evaluation scan` / `report`)
  agent run      agent_run.json + agent_report.json (written by `agent-scan` / `agent-report`)
The run id comes from the URL, so it is validated strictly and the resolved path must stay inside the base.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
MAX_BYTES = 20 * 1024 * 1024
_KINDS = (("detector", "run.json", "report.json"), ("agent", "agent_run.json", "agent_report.json"))


class RunNotFound(Exception):
    pass


class RunTooLarge(Exception):
    pass


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > MAX_BYTES:
            raise RunTooLarge(path.name)
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _describe(run_dir: Path) -> dict[str, Any] | None:
    for kind, meta_name, report_name in _KINDS:
        meta = _read_json(run_dir / meta_name)
        if meta is None:
            continue
        llm = str(meta.get("llm", ""))
        return {
            "run_id": run_dir.name,
            "kind": kind,
            "created_at": meta.get("created_at"),
            "git_sha": meta.get("git_sha"),
            "git_dirty": bool(meta.get("git_dirty")),
            "jailbreak_mode": meta.get("jailbreak_mode"),
            "n_samples": meta.get("n_samples") if kind == "detector" else None,
            "llm": llm or None,
            "synthetic": llm.startswith("scripted"),
            "has_report": (run_dir / report_name).is_file(),
        }
    return None


def list_runs(base: str | Path) -> list[dict[str, Any]]:
    root = Path(base)
    if not root.is_dir():
        return []
    runs = [d for d in root.iterdir() if d.is_dir() and not d.is_symlink() and RUN_ID.match(d.name)]
    described = [r for d in runs if (r := _describe(d)) is not None]
    return sorted(described, key=lambda r: (str(r["created_at"] or ""), r["run_id"]), reverse=True)


def load_run(base: str | Path, run_id: str) -> dict[str, Any]:
    if not RUN_ID.match(run_id):
        raise RunNotFound(run_id)
    root = Path(base).resolve()
    run_dir = (root / run_id).resolve()
    if run_dir.parent != root or not run_dir.is_dir():
        raise RunNotFound(run_id)
    info = _describe(run_dir)
    if info is None:
        raise RunNotFound(run_id)
    report_name = "agent_report.json" if info["kind"] == "agent" else "report.json"
    report = _read_json(run_dir / report_name)
    if report is None:
        raise RunNotFound(run_id)
    return {**info, "report": report}
