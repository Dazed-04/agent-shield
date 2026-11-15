import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest, GrantLeaseRequest, ResolveApprovalRequest


def test_prompt_is_required_and_bounded():
    with pytest.raises(ValidationError):
        ChatRequest(prompt="")
    with pytest.raises(ValidationError):
        ChatRequest(prompt="x" * 60_000)
    assert ChatRequest(prompt="hello").prompt == "hello"


def test_thread_id_must_be_a_safe_token():
    assert ChatRequest(prompt="x", thread_id="cli_ab12-3:4.5").thread_id == "cli_ab12-3:4.5"
    for bad in ("has space", "semi;colon", "a" * 65, "../etc"):
        with pytest.raises(ValidationError):
            ChatRequest(prompt="x", thread_id=bad)


def test_resolve_action_is_restricted():
    assert ResolveApprovalRequest(log_id=1, action="APPROVE").action == "APPROVE"
    with pytest.raises(ValidationError):
        ResolveApprovalRequest(log_id=1, action="MAYBE")


def test_lease_limits():
    assert GrantLeaseRequest(thread_id="t", tool_name="x").max_uses == 3
    with pytest.raises(ValidationError):
        GrantLeaseRequest(thread_id="t", tool_name="x", max_uses=10**6)
    with pytest.raises(ValidationError):
        GrantLeaseRequest(thread_id="t", tool_name="x", duration_seconds=0)
