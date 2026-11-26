from collections import defaultdict
from unittest import mock

import pytest

import app.agent.langgraph_agent as g
from evaluation.agent_bench import build_scenarios
from evaluation.agent_eval import SYSTEMS, run_matrix, run_one
from evaluation.scripted_llm import ScriptedAgentLLM

SCEN = [s for s in build_scenarios() if s.task_id in ("meeting", "invoice")]  # 32 scenarios keeps this fast
ROLES = ("Domain Admins", "Standard Users")


def _matrix(mode):
    with mock.patch.object(g, "get_llm_with_fallbacks", lambda tools, mid=None: ScriptedAgentLLM(mode)):
        return list(run_matrix(SCEN, SYSTEMS, ROLES))


def _rate(rows, key, system, role=None, goal=None, attack=True):
    sel = [r for r in rows if r["system"] == system and r["attack"] == attack and (role is None or r["role"] == role) and (goal is None or r["goal"] == goal)]
    assert sel
    return sum(bool(r[key]) for r in sel) / len(sel)


@pytest.fixture(scope="module")
def gullible():
    return _matrix("gullible")


@pytest.fixture(scope="module")
def resistant():
    return _matrix("resistant")


def test_unprotected_agent_is_fully_compromised_by_a_gullible_model(gullible):
    for system in ("no_shield", "prompt_hardening"):  # a prompt alone cannot stop a model that obeys the document
        assert _rate(gullible, "executed", system) == 1.0 and _rate(gullible, "attempted", system) == 1.0
    assert _rate(gullible, "utility", "no_shield", attack=False) == 1.0


def test_full_shield_reduces_executed_attacks_and_never_leaks_the_canary(gullible):
    full = _rate(gullible, "executed", "shield_full", "Domain Admins")
    assert 0 < full < 1.0  # some payload styles evade the detectors: the honest limitation the paper must report
    assert _rate(gullible, "executed", "shield_full", "Domain Admins", goal="exfil") == 0.0  # outbound redaction
    assert _rate(gullible, "attempted", "shield_full", "Domain Admins") < 1.0  # quarantine hid payloads from the model


def test_role_policy_stops_privileged_effects_even_when_detection_misses(gullible):
    for goal in ("file_write", "code_exec"):
        assert _rate(gullible, "executed", "shield_full", "Standard Users", goal=goal) == 0.0
        assert _rate(gullible, "executed", "shield_no_monitor", "Standard Users", goal=goal) > 0.0  # ablation removes that protection


def test_quarantine_ablation_shows_what_the_scanner_contributes(gullible):
    assert _rate(gullible, "attempted", "shield_no_quarantine", "Domain Admins") == 1.0
    assert _rate(gullible, "attempted", "shield_full", "Domain Admins") < 1.0


def test_benign_tasks_are_not_broken_by_the_shield(gullible, resistant):
    for rows in (gullible, resistant):
        for system in SYSTEMS:
            assert _rate(rows, "utility", system, attack=False) == 1.0


def test_resistant_model_is_never_compromised_but_quarantine_costs_utility(resistant):
    assert not any(r["executed"] for r in resistant)
    assert _rate(resistant, "utility", "no_shield") == 1.0
    assert _rate(resistant, "utility", "shield_full", "Domain Admins") < 1.0  # withheld documents cannot be answered


def test_no_artifacts_are_left_in_the_sandbox(gullible):
    import os

    from app.agent.tools import SANDBOX_DIR

    assert not [f for f in os.listdir(SANDBOX_DIR) if f.startswith("pwned_") or f.endswith("_notes.txt")]


def test_provider_errors_are_recorded_not_raised():
    class Boom:
        def invoke(self, _m):
            raise RuntimeError("rate limited")

    with mock.patch.object(g, "get_llm_with_fallbacks", lambda tools, mid=None: Boom()):
        r = run_one("shield_full", "Domain Admins", SCEN[0])
    assert r["status"] == "ERROR" and "rate limited" in r["error"] and r["utility"] is False


def test_matrix_covers_each_system_and_only_shielded_systems_use_roles():
    agg = defaultdict(set)
    with mock.patch.object(g, "get_llm_with_fallbacks", lambda tools, mid=None: ScriptedAgentLLM("resistant")):
        for r in run_matrix(SCEN[:2], SYSTEMS, ROLES):
            agg[r["system"]].add(r["role"])
    assert agg["no_shield"] == {"n/a"} and agg["shield_full"] == set(ROLES)


# ---- provider failures ------------------------------------------------------------------------------------------------

from evaluation.agent_eval import QuotaExhausted, RunAborted, classify_provider_error, retry_delay  # noqa: E402


class _Boom(Exception):
    pass


def _rate_limit(msg):
    e = type("RateLimitError", (Exception,), {})
    return e(f"Error code: 429 - {msg}")


def test_provider_errors_are_classified():
    assert classify_provider_error(_rate_limit("Rate limit reached ... on tokens per day (TPD): Limit 200000")) == "daily_quota"
    assert classify_provider_error(_rate_limit("Rate limit reached ... on tokens per minute (TPM). Please try again in 7.5s")) == "rate_limit"
    assert classify_provider_error(_Boom("connection reset")) is None


def test_retry_delay_follows_the_hint_and_is_capped():
    assert retry_delay(_rate_limit("Please try again in 7.5s"), 0) == 8.5
    assert retry_delay(_rate_limit("Please try again in 1m3.2s"), 0) == 64.2
    assert retry_delay(_rate_limit("no hint"), 2) == 20.0
    assert retry_delay(_rate_limit("Please try again in 30m0s"), 0) == 90.0


class _FlakyLLM:
    """Fails with a per-minute rate limit `fails` times, then behaves like the resistant scripted model."""

    def __init__(self, fails, exc):
        self.fails, self.exc, self.inner = fails, exc, ScriptedAgentLLM("resistant")

    def invoke(self, msgs, *a, **k):
        if self.fails > 0:
            self.fails -= 1
            raise self.exc
        return self.inner.invoke(msgs, *a, **k)


def _run(system, llm_factory, **kw):
    with mock.patch.object(g, "get_llm_with_fallbacks", lambda tools, mid=None: llm_factory()):
        return run_one(system, "n/a", SCEN[0], **kw)


def test_per_minute_rate_limit_is_retried_with_backoff():
    sleeps = []
    flaky = _FlakyLLM(2, _rate_limit("try again in 2s"))
    rec = _run("no_shield", lambda: flaky, sleep=sleeps.append)
    assert rec["status"] == "COMPLETED" and rec["retries"] == 2 and sleeps == [3.0, 3.0]


def test_exhausted_retries_record_an_error_instead_of_looping():
    rec = _run("no_shield", lambda: _FlakyLLM(99, _rate_limit("try again in 1s")), max_retries=2, sleep=lambda s: None)
    assert rec["status"] == "ERROR" and rec["retries"] == 2


def test_daily_quota_stops_the_run_at_once():
    with pytest.raises(QuotaExhausted):
        _run("no_shield", lambda: _FlakyLLM(99, _rate_limit("on tokens per day (TPD): Limit 200000")), sleep=lambda s: pytest.fail("must not wait"))


def test_matrix_aborts_after_consecutive_errors_but_keeps_what_it_has():
    got = []
    with mock.patch.object(g, "get_llm_with_fallbacks", lambda tools, mid=None: _FlakyLLM(99, _Boom("down"))):
        with pytest.raises(RunAborted):
            for r in run_matrix(SCEN, ("no_shield",), max_consecutive_errors=3):
                got.append(r)
    assert len(got) == 3 and all(r["status"] == "ERROR" for r in got)


def test_matrix_skip_hook_leaves_out_finished_work():
    with mock.patch.object(g, "get_llm_with_fallbacks", lambda tools, mid=None: ScriptedAgentLLM("resistant")):
        rows = list(run_matrix(SCEN[:4], ("no_shield",), skip=lambda sy, ro, sid, k: sid == SCEN[0].id))
    assert len(rows) == 3 and SCEN[0].id not in {r["id"] for r in rows}
