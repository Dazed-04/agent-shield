"""Provenance of every public dataset, pinned to an exact commit, plus the fetch step.

Nothing is vendored: ``prepare`` clones each repository at its pinned SHA into
``evaluation/data/raw/<name>``. Licences were checked on 2026-11-23 against each repository's
LICENSE file. Raw and processed data are git-ignored.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parent / "data"
RAW_ROOT = DATA_ROOT / "raw"


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    repo_url: str
    sha: str
    licence: str
    paper: str
    used_for: str


DATASETS: dict[str, DatasetSpec] = {
    "injecagent": DatasetSpec(
        name="injecagent",
        repo_url="https://github.com/uiuc-kang-lab/InjecAgent",
        sha="f19c9f2c79a41046eb13c03c51a24c567a8ffa07",
        licence="MIT",
        paper="Zhan et al., InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated LLM Agents (2024)",
        used_for="indirect injection inside tool responses (base and enhanced attacker instructions)",
    ),
    "bipia": DatasetSpec(
        name="bipia",
        repo_url="https://github.com/microsoft/BIPIA",
        sha="a004b69ec0dd446e0afd461d98cb5e96e120a5d0",
        licence="MIT",
        paper="Yi et al., Benchmarking and Defending Against Indirect Prompt Injection Attacks on LLMs (2023)",
        used_for="indirect injection inside email / table / code contexts, with clean paired contexts",
    ),
    "jailbreak_llms": DatasetSpec(
        name="jailbreak_llms",
        repo_url="https://github.com/verazuo/jailbreak_llms",
        sha="4f4031bf8be187f4478c7f94f42b08714722c12e",
        licence="MIT",
        paper="Shen et al., 'Do Anything Now': Characterizing In-The-Wild Jailbreak Prompts on LLMs (2023)",
        used_for="in-the-wild jailbreak prompts (attacks) versus regular prompts (benign)",
    ),
}


def _git(args: list[str], cwd: Path) -> str:
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()[:400]}")
    return r.stdout.strip()


def prepare(spec: DatasetSpec, raw_root: Path = RAW_ROOT, url: str | None = None) -> Path:
    """Fetch ``spec`` at exactly its pinned SHA (idempotent). ``url`` overrides the remote (tests)."""
    dest = raw_root / spec.name
    if (dest / ".git").exists() and _git(["rev-parse", "HEAD"], dest) == spec.sha:
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        _git(["init", "-q"], dest)
    _git(["fetch", "-q", "--depth", "1", url or spec.repo_url, spec.sha], dest)
    _git(["checkout", "-q", "--detach", "FETCH_HEAD"], dest)
    head = _git(["rev-parse", "HEAD"], dest)
    if head != spec.sha:  # defence in depth: never silently evaluate on different data
        raise RuntimeError(f"{spec.name}: expected {spec.sha}, got {head}")
    return dest


def manifest() -> list[dict[str, str]]:
    return [vars(s).copy() for s in DATASETS.values()]
