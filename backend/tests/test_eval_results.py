import json

import pytest

from app import eval_results
from app.eval_results import RunNotFound, list_runs, load_run
from tests.conftest import ADMIN_KEY, DS_KEY, STD_KEY


def H(key):
    return {"X-API-Key": key}


def make_run(base, name, kind="detector", report=True, **meta):
    d = base / name
    d.mkdir(parents=True)
    meta = {"created_at": "2026-11-20T10:00:00+00:00", "git_sha": "abc", **meta}
    (d / ("run.json" if kind == "detector" else "agent_run.json")).write_text(json.dumps(meta))
    if report:
        (d / ("report.json" if kind == "detector" else "agent_report.json")).write_text(json.dumps({"ok": name}))
    return d


def test_lists_newest_first_and_flags_synthetic_runs(tmp_path):
    make_run(tmp_path, "old", created_at="2026-11-01T00:00:00+00:00", jailbreak_mode="heuristic", n_samples=10)
    make_run(tmp_path, "new-agent", kind="agent", llm="scripted-gullible", created_at="2026-11-22T00:00:00+00:00")
    make_run(tmp_path, "no-report", report=False)
    (tmp_path / "junk").mkdir()
    (tmp_path / "stray.txt").write_text("x")
    runs = list_runs(tmp_path)
    assert [r["run_id"] for r in runs] == ["new-agent", "no-report", "old"]
    assert runs[0]["synthetic"] is True and runs[0]["kind"] == "agent"
    assert runs[1]["has_report"] is False and runs[2]["jailbreak_mode"] == "heuristic" and runs[2]["n_samples"] == 10


def test_missing_base_dir_is_empty(tmp_path):
    assert list_runs(tmp_path / "nope") == []


def test_load_returns_report_and_rejects_bad_ids(tmp_path):
    make_run(tmp_path, "r1")
    assert load_run(tmp_path, "r1")["report"] == {"ok": "r1"}
    for bad in ["../r1", "r1/..", "a/b", "", ".hidden", "x" * 200, "r1\x00"]:
        with pytest.raises(RunNotFound):
            load_run(tmp_path, bad)
    with pytest.raises(RunNotFound):
        load_run(tmp_path, "missing")


def test_no_report_symlinks_or_oversize(tmp_path, monkeypatch):
    make_run(tmp_path, "nr", report=False)
    with pytest.raises(RunNotFound):
        load_run(tmp_path, "nr")
    secret = tmp_path.parent / "secret.json"
    secret.write_text('{"leak": 1}')
    d = make_run(tmp_path, "sl", report=False)
    (d / "report.json").symlink_to(secret)
    with pytest.raises(RunNotFound):
        load_run(tmp_path, "sl")
    (tmp_path / "linked").symlink_to(tmp_path / "sl", target_is_directory=True)
    assert "linked" not in [r["run_id"] for r in list_runs(tmp_path)]
    make_run(tmp_path, "big")
    monkeypatch.setattr(eval_results, "MAX_BYTES", 5)
    with pytest.raises(eval_results.RunTooLarge):
        load_run(tmp_path, "big")


def test_endpoints_are_admin_only_and_serve_runs(client, tmp_path, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "EVAL_RESULTS_DIR", str(tmp_path))
    make_run(tmp_path, "r1")
    for key in (STD_KEY, DS_KEY):
        assert client.get("/api/eval/runs", headers=H(key)).status_code == 403
        assert client.get("/api/eval/runs/r1", headers=H(key)).status_code == 403
    assert client.get("/api/eval/runs").status_code == 401
    assert [r["run_id"] for r in client.get("/api/eval/runs", headers=H(ADMIN_KEY)).json()] == ["r1"]
    r = client.get("/api/eval/runs/r1", headers=H(ADMIN_KEY))
    assert r.status_code == 200 and r.json()["report"] == {"ok": "r1"}
    assert client.get("/api/eval/runs/nope", headers=H(ADMIN_KEY)).status_code == 404
    assert client.get("/api/eval/runs/..%2Fetc", headers=H(ADMIN_KEY)).status_code == 404
