"""Test environment. Variables must be set BEFORE any `app.*` import (config reads them once)."""

import hashlib
import json
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="agent_shield_tests_")
os.environ["AGENT_SHIELD_DISABLE_EMBEDDINGS"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["AGENT_SHIELD_SANDBOX_DIR"] = os.path.join(_TMP, "sandbox")
os.environ["AGENT_SHIELD_USERS_FILE"] = os.path.join(_TMP, "users.json")
os.environ["THREAT_VECTORS_PATH"] = os.path.join(_TMP, "threat_vectors.json")
os.environ.pop("SECURITY_ENV", None)

ADMIN_KEY, DS_KEY, STD_KEY, STD2_KEY = "k_admin_test", "k_ds_test", "k_std_test", "k_std2_test"
with open(os.environ["AGENT_SHIELD_USERS_FILE"], "w") as f:
    json.dump(
        {
            "api_keys": {
                ADMIN_KEY: {"user": "alice", "role": "Domain Admins", "allowed_interfaces": ["web", "cli"], "enabled": True},
                DS_KEY: {"user": "dave", "role": "Data Science", "allowed_interfaces": ["web"], "enabled": True},
                "REPLACE_ME_ADMIN_KEY": {"user": "evil", "role": "Domain Admins", "allowed_interfaces": ["web"], "enabled": True},
            },
            "api_key_hashes": {
                hashlib.sha256(STD_KEY.encode()).hexdigest(): {"user": "sam", "role": "Standard Users", "allowed_interfaces": ["web"], "enabled": True},
                hashlib.sha256(STD2_KEY.encode()).hexdigest(): {"user": "sue", "role": "Standard Users", "allowed_interfaces": ["web"], "enabled": True},
            },
        },
        f,
    )

import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from app.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def reset_shield():
    """Clear the process-wide lease/quota state held by the shared ToolMonitor."""
    from app.shield import tool_monitor

    tool_monitor.session_leases.clear()
    tool_monitor.invocations.clear()
    yield


@pytest.fixture
def dev_mode(monkeypatch):
    monkeypatch.setenv("SECURITY_ENV", "development")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


class ScriptedLLM:
    """Stands in for the real model: returns queued AIMessages and records what it was shown."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[list] = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        return self.replies.pop(0) if self.replies else AIMessage(content="done")


def tool_call(name, args, call_id="c1"):
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


@pytest.fixture
def llm(monkeypatch):
    def install(*replies):
        fake = ScriptedLLM(replies)
        monkeypatch.setattr("app.agent.langgraph_agent.get_llm_with_fallbacks", lambda tools, mid=None: fake)
        return fake

    return install
