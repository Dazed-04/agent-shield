from app.engine.risk_engine import RiskEngine


def test_risk_engine_bands_and_explanations():
    score, decision, why = RiskEngine.aggregate_and_decide(
        {"score": 85, "reasons": ["System instruction override attempt"]}, {"score": 10, "reason": "Safe"}
    )
    assert (score, decision) == (85, "BLOCK") and "override" in why
    assert RiskEngine.aggregate_and_decide({"score": 0}, {"score": 0})[1] == "ALLOW"
    assert RiskEngine.aggregate_and_decide({"score": 60}, {"score": 0})[1] == "WARN"
    assert RiskEngine.decide(56) == "APPROVE" and RiskEngine.decide(25) == "ALLOW"


def test_tool_signal_is_part_of_the_score():
    s_without = RiskEngine.aggregate_and_decide({"score": 30}, {"score": 30})[0]
    s_with = RiskEngine.aggregate_and_decide({"score": 30}, {"score": 30}, {"score": 90})[0]
    assert s_with > s_without
