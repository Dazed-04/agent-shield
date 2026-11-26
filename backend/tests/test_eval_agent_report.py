from evaluation.agent_report import render_markdown, summarize


def row(system="shield_full", role="Domain Admins", attack=True, attempted=True, executed=False, utility=False,
        status="COMPLETED", goal="exfil", style="plain", latency=10.0):
    return {"system": system, "role": role, "attack": attack, "attempted": attempted, "executed": executed,
            "utility": utility, "status": status, "goal": goal, "style": style, "latency_ms": latency}


def test_rates_and_errors_are_computed_per_system_and_role():
    rows = [
        row(system="no_shield", executed=True),
        row(system="no_shield", executed=True),
        row(system="no_shield", attack=False, attempted=False, utility=True),
        row(executed=False, status="BLOCKED"),
        row(executed=False, status="WAITING_APPROVAL"),
        row(attack=False, attempted=False, utility=True),
        row(status="ERROR"),
    ]
    s = summarize(rows)["systems"]
    assert s["no_shield|Domain Admins"]["asr_executed"]["rate"] == 1.0
    assert s["no_shield|Domain Admins"]["utility_clean"]["rate"] == 1.0
    full = s["shield_full|Domain Admins"]
    assert full["errors"] == 1 and full["attacks"] == 2 and full["clean"] == 1
    assert full["asr_executed"]["rate"] == 0.0 and full["stopped_by_shield"]["rate"] == 1.0
    lo, hi = full["asr_executed"]["ci"]
    assert 0.0 <= lo <= hi <= 1.0


def test_empty_groups_report_none_not_zero_division():
    s = summarize([row(attack=False, attempted=False, utility=True)])["systems"]["shield_full|Domain Admins"]
    assert s["asr_executed"]["rate"] is None and s["utility_clean"]["rate"] == 1.0


def test_breakdown_by_goal_and_style():
    rows = [row(goal="exfil", executed=True), row(goal="exfil"), row(goal="write", style="obfuscated", executed=True)]
    b = summarize(rows)["breakdown"]
    assert b["goal|shield_full|Domain Admins"]["exfil"]["rate"] == 0.5
    assert b["style|shield_full|Domain Admins"]["obfuscated"]["rate"] == 1.0


def test_markdown_flags_synthetic_runs_and_dirty_trees():
    md = render_markdown(summarize([row()]), {"run_id": "r1", "llm": "scripted-gullible", "git_sha": "abc", "git_dirty": True,
                                              "repeats": 1, "n_scenarios": 1})
    assert "SYNTHETIC RUN" in md and "(**dirty**)" in md and "## Main table" in md and "ASR (executed) by goal" in md
    real = render_markdown(summarize([row()]), {"run_id": "r2", "llm": "real", "model_id": "m", "repeats": 3, "n_scenarios": 1})
    assert "SYNTHETIC" not in real and "`m`" in real


def test_a_resumed_run_counts_only_the_latest_record_per_scenario():
    from evaluation.agent_report import latest_per_run

    base = {"system": "no_shield", "role": "n/a", "id": "a", "repeat": 0, "attack": True, "style": "polite", "goal": "exfil",
            "utility": False, "attempted": False, "executed": False, "latency_ms": 1.0}
    rows = [{**base, "status": "ERROR"}, {**base, "id": "b", "status": "COMPLETED"}, {**base, "status": "COMPLETED", "executed": True}]
    out = latest_per_run(rows)
    assert len(out) == 2 and {r["id"]: r["status"] for r in out} == {"a": "COMPLETED", "b": "COMPLETED"}
    assert summarize(rows)["systems"]["no_shield|n/a"]["errors"] == 0
