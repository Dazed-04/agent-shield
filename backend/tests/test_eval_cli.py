import json

from evaluation.__main__ import main


def test_full_pipeline_in_house_only(tmp_path, capsys):
    s = tmp_path / "set.jsonl"
    assert main(["build", "--sources", "inhouse", "--out", str(s)]) == 0
    assert main(["scan", "--set", str(s), "--embeddings", "off", "--tag", "t", "--results-dir", str(tmp_path / "res")]) == 0
    (run,) = (tmp_path / "res").iterdir()
    assert main(["calibrate", str(run), "--systems", "combined"]) == 0
    assert main(["report", str(run), "--n-boot", "20"]) == 0
    rep = json.loads((run / "report.json").read_text())
    assert rep["run"]["jailbreak_mode"] == "heuristic" and rep["calibrated_thresholds"].keys() == {"combined"}
    md = (run / "report.md").read_text()
    assert "Ablation: held-out test split" in md and "Combined (risk engine)" in md and "calibrated TPR / FPR" in md
    assert (run / "report.csv").read_text().startswith("group,system,operating_point")
    assert r"\begin{tabular}" in (run / "ablation.tex").read_text()


def test_build_fails_cleanly_without_prepared_data(tmp_path, capsys):
    rc = main(["build", "--sources", "bipia", "--raw-dir", str(tmp_path / "nothing"), "--out", str(tmp_path / "o.jsonl")])
    assert rc == 2 and "prepare" in capsys.readouterr().err
    assert main(["build", "--sources", "nope", "--out", str(tmp_path / "o.jsonl")]) == 2


def test_agent_scan_dry_run_and_report(tmp_path, capsys):
    res = tmp_path / "res"
    assert main(["agent-scan", "--llm", "scripted-gullible", "--embeddings", "off", "--limit-scenarios", "3",
                 "--systems", "no_shield", "shield_full", "--roles", "Domain Admins", "--tag", "t", "--results-dir", str(res)]) == 0
    (run,) = res.iterdir()
    meta = json.loads((run / "agent_run.json").read_text())
    assert meta["llm"] == "scripted-gullible" and meta["n_scenarios"] == 3 and "datasets" not in meta
    assert len((run / "agent_runs.jsonl").read_text().splitlines()) == 6  # 3 scenarios x 2 systems x 1 role
    assert main(["agent-report", str(run)]) == 0
    md = (run / "agent_report.md").read_text()
    assert "SYNTHETIC RUN" in md and "no_shield" in md and "shield_full" in md
    assert set(json.loads((run / "agent_report.json").read_text())) == {"meta", "systems", "breakdown"}


def test_run_argument_accepts_path_bare_id_and_latest(tmp_path, monkeypatch):
    import pytest

    import evaluation.__main__ as cli

    monkeypatch.setattr(cli, "RESULTS_DIR", tmp_path)
    old, new = tmp_path / "20261101T000000-a", tmp_path / "20261125T000000-b"
    old.mkdir()
    new.mkdir()
    assert cli._resolve_run(str(old)) == old  # full path
    assert cli._resolve_run("20261125T000000-b") == new  # bare id
    assert cli._resolve_run("latest") == new  # newest by name
    with pytest.raises(SystemExit, match="replace the <run> placeholder"):
        cli._resolve_run("<run>")
    with pytest.raises(SystemExit, match="(?s)no run folder 'nope'.*20261125T000000-b"):
        cli._resolve_run("nope")


def _scan(res, *extra):
    return main(["agent-scan", "--llm", "scripted-gullible", "--embeddings", "off", "--limit-scenarios", "3", "--systems", "no_shield",
                 "--results-dir", str(res), *extra])


def test_agent_scan_stops_early_saves_progress_and_resumes(tmp_path, monkeypatch, capsys):
    import evaluation.agent_eval as ae

    real = ae.run_one
    calls = []

    def flaky(system, role, s, model_id=None, repeat=0, **kw):
        calls.append(s.id)
        if len(calls) > 1:  # first run succeeds, every later one fails like an exhausted provider
            return {"id": s.id, "attack": s.attack, "style": s.style, "goal": s.goal, "utility": False, "status": "ERROR", "error": "down",
                    "attempted": False, "executed": False, "system": system, "role": "n/a", "repeat": repeat, "notes": [], "latency_ms": 1.0}
        return real(system, role, s, model_id, repeat, **kw)

    monkeypatch.setattr(ae, "run_one", flaky)
    res = tmp_path / "res"
    assert _scan(res, "--max-consecutive-errors", "2") == 2
    err = capsys.readouterr().err
    (run,) = res.iterdir()
    assert "--resume" in err and run.name in err
    meta = json.loads((run / "agent_run.json").read_text())
    assert meta["complete"] is False and "consecutive" in meta["stopped_reason"]
    assert len((run / "agent_runs.jsonl").read_text().splitlines()) == 3  # 1 good + 2 errors kept on disk

    monkeypatch.setattr(ae, "run_one", real)  # provider recovered
    assert _scan(res, "--resume", str(run)) == 0
    rows = [json.loads(x) for x in (run / "agent_runs.jsonl").read_text().splitlines()]
    assert sum(r["status"] != "ERROR" for r in rows) == 3  # the finished run was not repeated, the two errored ones were redone
    assert json.loads((run / "agent_run.json").read_text())["complete"] is True
