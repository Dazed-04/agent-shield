from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    prompt: str
    user_id: str | None = "default_user"
    role: str | None = "Standard Users"
    thread_id: str | None = None
    rag_context: str | None = None
    attachment: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    log_id: int
    decision: str
    risk_score: float
    justification: str
    reply: str | None = None
    replies: list[str] = []
    approval_needed: bool = False


class ResolveApprovalRequest(BaseModel):
    log_id: int
    action: str


class GrantLeaseRequest(BaseModel):
    thread_id: str
    tool_name: str
    max_uses: int = 3
    duration_seconds: int = 600
