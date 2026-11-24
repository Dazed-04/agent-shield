import subprocess
from dataclasses import replace

import pytest

from evaluation.datasets import DATASETS, manifest, prepare


def _repo(tmp_path):
    r = tmp_path / "remote"
    r.mkdir()
    run = lambda *a: subprocess.run(["git", *a], cwd=r, check=True, capture_output=True, text=True).stdout.strip()  # noqa: E731
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    (r / "data.txt").write_text("v1")
    run("add", ".")
    run("commit", "-q", "-m", "one")
    return r, run("rev-parse", "HEAD")


def test_prepare_pins_exact_sha_and_is_idempotent(tmp_path):
    remote, sha = _repo(tmp_path)
    spec = replace(DATASETS["injecagent"], sha=sha)
    dest = prepare(spec, tmp_path / "raw", url=str(remote))
    assert (dest / "data.txt").read_text() == "v1"
    assert prepare(spec, tmp_path / "raw", url="file:///does/not/exist") == dest  # already at SHA: no fetch


def test_prepare_fails_loudly_for_an_unknown_commit(tmp_path):
    remote, _ = _repo(tmp_path)
    spec = replace(DATASETS["bipia"], sha="0" * 40)
    with pytest.raises(RuntimeError):
        prepare(spec, tmp_path / "raw", url=str(remote))


def test_manifest_is_complete():
    assert {m["name"] for m in manifest()} == {"injecagent", "bipia", "jailbreak_llms"}
    for s in DATASETS.values():
        assert len(s.sha) == 40 and s.licence == "MIT" and s.paper
