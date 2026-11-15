from typing import Any

from pydantic import BaseModel, Field

from app.config import MAX_PROMPT_CHARS


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    user_id: str | None = "default_user"  # development mode only; ignored in production
    role: str | None = "Standard Users"  # development mode only; ignored in production
    thread_id: str | None = Field(default=None, max_length=64, pattern=r"^[\w\-.:]+$")
    model_id: str | None = None
    rag_context: str | None = Field(default=None, max_length=MAX_PROMPT_CHARS)
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
    action: str = Field(pattern=r"^(APPROVE|REJECT)$")


class GrantLeaseRequest(BaseModel):
    thread_id: str = Field(max_length=64)
    tool_name: str = Field(max_length=64)
    max_uses: int = Field(default=3, ge=1, le=20)
    duration_seconds: int = Field(default=600, ge=1, le=3600)
