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
