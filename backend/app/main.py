import re
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.agent.langgraph_agent import AgentState, compiled_agent
from app.agent.tools import TOOLS_BY_NAME
from app.database import Base, engine, get_db
from app.detectors.jailbreak_detector import JailbreakDetector
from app.detectors.prompt_scanner import PromptScanner
from app.detectors.response_scanner import ResponseScanner
from app.engine.risk_engine import RiskEngine
from app.models import SecurityAuditLog
from app.schemas import (
    ChatRequest,
    ChatResponse,
    GrantLeaseRequest,
    ResolveApprovalRequest,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Shield - Production Gateway", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prompt_scanner = PromptScanner()
jailbreak_detector = JailbreakDetector()
response_scanner = ResponseScanner()


def serialize_log(log: Any) -> dict[str, Any]:
    return {
        "id": int(log.id),
        "timestamp": (
            log.timestamp.isoformat()
            if hasattr(log, "timestamp") and log.timestamp
            else None
        ),
        "prompt": str(log.prompt),
        "risk_score": float(log.risk_score),
        "decision": str(log.decision),
        "justification": str(log.justification),
        "triggered_detectors": log.triggered_detectors or {},
        "tool_calls_attempted": log.tool_calls_attempted or [],
        "final_response": str(log.final_response) if log.final_response else None,
        "status": str(log.status),
    }


@app.post("/api/chat", response_model=ChatResponse)
def handle_chat_request(
    req: ChatRequest, db: Annotated[Session, Depends(get_db)]
) -> ChatResponse:
    p_res = prompt_scanner.scan(req.prompt, req.rag_context)
    j_res = jailbreak_detector.scan(req.prompt)
    inbound_score, decision, justification = RiskEngine.aggregate_and_decide(
        p_res, j_res
    )

    audit_entry: Any = SecurityAuditLog(
        prompt=req.prompt,
        risk_score=inbound_score,
        decision=decision,
        justification=justification,
        triggered_detectors={"prompt_scanner": p_res, "jailbreak_detector": j_res},
        tool_calls_attempted=[],
        status="COMPLETED",
    )

    if decision == "BLOCK":
        audit_entry.final_response = (
            "[BLOCKED BY GATEWAY]: Malicious instruction pattern detected."
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        return ChatResponse(
            log_id=int(audit_entry.id),
            decision="BLOCK",
            risk_score=inbound_score,
            justification=justification,
            reply="[SECURITY BLOCK]: Action aborted by Agent Shield. Direct prompt injection or adversarial phrasing identified.",
            replies=["[SECURITY BLOCK]: Action aborted by Agent Shield."],
            approval_needed=False,
        )

    thread_id = req.thread_id or "default_session"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    initial_state: AgentState = {
        "messages": [HumanMessage(content=req.prompt)],
        "status": "RUNNING",
        "pending_tool_call": None,
        "risk_score": inbound_score,
        "justification": justification,
        "final_output": None,
        "step_count": 0,
        "thread_id": thread_id,
    }

    try:
        final_state: dict[str, Any] = compiled_agent.invoke(
            cast(Any, initial_state), config=config
        )
    except Exception as e:  # noqa: BLE001
        err_msg = str(e)
        audit_entry.decision = "WARN"
        audit_entry.risk_score = 45.0
        audit_entry.justification = f"Inference Error: {err_msg[:120]}"
        audit_entry.final_response = f"Execution limitation: {err_msg[:200]}"
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        return ChatResponse(
            log_id=int(audit_entry.id),
            decision="WARN",
            risk_score=45.0,
            justification="Upstream engine limit.",
            reply=f"[Agent Shield Alert]: {err_msg[:200]}",
            replies=[f"[Agent Shield Alert]: {err_msg[:200]}"],
            approval_needed=False,
        )

    if final_state.get("status") == "WAITING_APPROVAL" or (
        final_state.get("pending_tool_call") and final_state.get("risk_score", 0) >= 50
    ):
        tool_call = final_state.get("pending_tool_call", {})
        tool_name = tool_call.get("name", "unknown_tool")

        audit_entry.decision = "APPROVE"
        audit_entry.risk_score = float(final_state.get("risk_score", 55.0))
        audit_entry.justification = final_state.get(
            "justification", f"Tool '{tool_name}' requires human authorization."
        )
        audit_entry.status = "PENDING_REVIEW"
        audit_entry.tool_calls_attempted = [tool_call]
        audit_entry.final_response = (
            f"[HOLD FOR HUMAN REVIEW]: Tool '{tool_name}' execution paused."
        )

        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)

        hold_msg = (
            f"⏸️ **[SECURITY HOLD]**: The agent attempted to execute privileged tool `{tool_name}`. "
            f"This action has been suspended and queued in the **Human Review Queue** for confirmation."
        )
        return ChatResponse(
            log_id=int(audit_entry.id),
            decision="APPROVE",
            risk_score=float(audit_entry.risk_score),
            justification=str(audit_entry.justification),
            reply=hold_msg,
            replies=[hold_msg],
            approval_needed=True,
        )

    audit_entry.decision = decision
    audit_entry.risk_score = max(
        inbound_score, float(final_state.get("risk_score", 0.0))
    )
    audit_entry.justification = final_state.get("justification", justification)

    raw_final: str = str(final_state.get("final_output") or "Task completed.")
    audit_entry.final_response = raw_final
    audit_entry.tool_calls_attempted = (
        [final_state["pending_tool_call"]]
        if final_state.get("pending_tool_call")
        else []
    )

    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)

    split_chunks = re.split(
        r"(?:---|###|\n\n)\s*(?:Response|Message)\s*\d+\s*(?:---|:)?\s*", raw_final
    )
    cleaned_replies = [c.strip() for c in split_chunks if c.strip()]
    final_replies = cleaned_replies if len(cleaned_replies) > 1 else [raw_final]

    return ChatResponse(
        log_id=int(audit_entry.id),
        decision=str(audit_entry.decision),
        risk_score=float(audit_entry.risk_score),
        justification=str(audit_entry.justification),
        reply=raw_final,
        replies=final_replies,
        approval_needed=False,
    )


@app.get("/api/approvals/pending")
def list_pending_approvals(
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    logs = (
        db.query(SecurityAuditLog)
        .filter(SecurityAuditLog.status == "PENDING_REVIEW")
        .all()
    )
    return [serialize_log(l) for l in logs]


@app.post("/api/approvals/resolve")
def resolve_approval(
    req: ResolveApprovalRequest, db: Annotated[Session, Depends(get_db)]
) -> dict[str, Any]:
    log: Any = (
        db.query(SecurityAuditLog).filter(SecurityAuditLog.id == req.log_id).first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")

    if req.action == "APPROVE":
        log.status = "APPROVED"
        tool_call = log.tool_calls_attempted[0] if log.tool_calls_attempted else None

        execution_output = ""
        if tool_call and tool_call.get("name") in TOOLS_BY_NAME:
            tool_obj = TOOLS_BY_NAME[tool_call["name"]]
            try:
                raw_result = tool_obj.invoke(tool_call.get("args", {}))
                sanitized = response_scanner.scan(str(raw_result))["sanitized_response"]
                execution_output = f"\n\n**Execution Result:**\n```\n{sanitized}\n```"
            except (RuntimeError, ValueError, OSError) as e:
                execution_output = f"\n\n**Tool Error:** {e!s}"

        log.final_response = (
            f"✅ **[AUTHORIZED BY OPERATOR]**: Execution of `{tool_call.get('name') if tool_call else 'tool'}` "
            f"was explicitly approved and completed.{execution_output}"
        )
        decision_label = "AUTHORIZED"
    else:
        log.status = "REJECTED"
        tool_name = (
            log.tool_calls_attempted[0].get("name")
            if log.tool_calls_attempted
            else "tool"
        )
        log.final_response = f"❌ **[DENIED BY OPERATOR]**: Execution of `{tool_name}` was cancelled by the human reviewer."
        decision_label = "REJECTED"

    db.commit()
    return {
        "status": "success",
        "log_id": log.id,
        "resolved_action": req.action,
        "new_response": log.final_response,
        "decision": decision_label,
    }


@app.get("/api/logs")
def get_logs_by_decision(
    db: Annotated[Session, Depends(get_db)],
    decision: str | None = None,
) -> list[dict[str, Any]]:
    query = db.query(SecurityAuditLog)
    if decision:
        query = query.filter(SecurityAuditLog.decision == decision.upper())
    logs = query.order_by(SecurityAuditLog.id.desc()).limit(50).all()
    return [serialize_log(l) for l in logs]


@app.get("/api/analytics")
def get_analytics(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    logs = db.query(SecurityAuditLog).all()
    total = len(logs)
    counts: dict[str, int] = {"ALLOW": 0, "WARN": 0, "APPROVE": 0, "BLOCK": 0}
    for item in logs:
        key = str(item.decision)
        counts[key] = counts.get(key, 0) + 1

    recent = logs[-10:] if total > 10 else logs
    return {
        "total_requests": total,
        "breakdown": counts,
        "recent_logs": [serialize_log(l) for l in recent],
    }


@app.post("/api/session/grant-lease")
def grant_lease(req: GrantLeaseRequest) -> dict[str, Any]:
    from app.agent.langgraph_agent import tool_monitor

    tool_monitor.grant_session_lease(
        thread_id=req.thread_id,
        tool_name=req.tool_name,
        max_uses=req.max_uses,
        duration_seconds=req.duration_seconds,
    )
    return {
        "status": "success",
        "message": (
            f"Granted lease for '{req.tool_name}' in session '{req.thread_id}' "
            f"(Limit: {req.max_uses} calls, {req.duration_seconds}s)."
        ),
    }
