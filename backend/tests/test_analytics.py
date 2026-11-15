import pytest
from langchain_core.messages import AIMessage

from tests.conftest import ADMIN_KEY, STD_KEY

pytestmark = pytest.mark.usefixtures("reset_shield")


def H(key, iface="web"):
    return {"X-API-Key": key, "X-Client-Interface": iface}


def chat(client, prompt, headers=None, **body):
    return client.post("/api/chat", json={"prompt": prompt, **body}, headers=headers or {})


def test_analytics_shape_and_latency_recorded(client, llm):
    llm(AIMessage(content="hi"))
    chat(client, "hello", H(STD_KEY))
    a = client.get("/api/analytics", headers=H(ADMIN_KEY)).json()
    assert a["total_requests"] == 1 and a["breakdown"]["ALLOW"] == 1
    assert a["avg_latency_ms"] is not None and a["timeline"]
    log = client.get("/api/logs", headers=H(ADMIN_KEY)).json()[0]
    assert {"prompt_scanner", "jailbreak_detector", "agent", "total"} <= set(log["triggered_detectors"]["timings_ms"])




def test_analytics_are_computed_in_sql_and_scoped(client, llm):
    llm(AIMessage(content="hi"))
    chat(client, "hello", H(STD_KEY))
    admin = client.get("/api/analytics", headers=H(ADMIN_KEY)).json()
    other = client.get("/api/analytics", headers=H(STD_KEY)).json()
    assert admin["total_requests"] == other["total_requests"] == 1
    assert set(admin["breakdown"]) == {"ALLOW", "WARN", "APPROVE", "BLOCK"}
    assert len(client.get("/api/logs?limit=1&offset=0", headers=H(ADMIN_KEY)).json()) == 1
    assert client.get("/api/logs?limit=1&offset=1", headers=H(ADMIN_KEY)).json() == []
