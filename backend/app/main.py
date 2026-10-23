import asyncio
import contextlib
import json
import os
import re
from collections.abc import AsyncGenerator
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent.langgraph_agent import AgentState, compiled_agent
from app.agent.tools import TOOLS_BY_NAME
from app.config import SECURITY_ENV
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

USERS_FILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "config/users.json")
)


def load_user_registry() -> dict[str, Any]:
    if os.path.exists(USERS_FILE_PATH):
        with contextlib.suppress(Exception) and open(
            USERS_FILE_PATH, "r", encoding="utf-8"
        ) as f:
            return json.load(f)
    return {"api_keys": {}}


Base.metadata.create_all(bind=engine)

# Auto-migrate SQLite schema for thread_id if upgrading existing DB
with engine.connect() as conn, contextlib.suppress(Exception):
    conn.execute(
        text("ALTER TABLE security_audit_logs ADD COLUMN thread_id VARCHAR(64)")
    )
    conn.commit()

app = FastAPI(title="Agent Shield - Production Gateway", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve frontend dist whether running locally or inside Docker container
_candidates = [
    os.path.abspath("./frontend/dist"),
    os.path.abspath("../frontend/dist"),
    os.path.abspath("/app/frontend/dist"),
]
FRONTEND_DIST = next((p for p in _candidates if os.path.exists(p)), _candidates[1])

prompt_scanner = PromptScanner()
jailbreak_detector = JailbreakDetector()
response_scanner = ResponseScanner()


class SSEBroadcaster:
    """Manages persistent SSE connections and pushes real-time gateway events."""

    def __init__(self) -> None:
        self.subscribers: set[asyncio.Queue[tuple[str, Any]]] = set()

    async def subscribe(self) -> asyncio.Queue[tuple[str, Any]]:
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[tuple[str, Any]]) -> None:
        self.subscribers.discard(queue)

    def publish_sync(self, event_type: str, data: Any) -> None:
        """Thread-safe push to all connected browser clients."""
        for queue in list(self.subscribers):
            try:
                queue.put_nowait((event_type, data))
            except Exception:  # noqa: BLE001
                self.subscribers.discard(queue)


broadcaster = SSEBroadcaster()


def serialize_log(log: Any) -> dict[str, Any]:
    return {
        "id": int(log.id),
        "thread_id": str(getattr(log, "thread_id", "default_session")),
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


def get_pending_approvals_list(db: Session) -> list[dict[str, Any]]:
    logs: list[Any] = (
        db.query(SecurityAuditLog)
        .filter(SecurityAuditLog.status == "PENDING_REVIEW")
        .all()
    )
    return [serialize_log(l) for l in logs]


def get_analytics_payload(db: Session) -> dict[str, Any]:
    logs: list[Any] = db.query(SecurityAuditLog).all()
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


@app.get("/api/events/stream")
async def event_stream(request: Request) -> StreamingResponse:
    """Persistent Server-Sent Events stream for zero-polling real-time updates."""

    async def event_generator() -> AsyncGenerator[str, None]:
        queue = await broadcaster.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_type, payload = await asyncio.wait_for(
                        queue.get(), timeout=15.0
                    )
                    yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def resolve_authenticated_context(
    request: Request, req: ChatRequest
) -> tuple[str, str]:
    """
    Dual-Mode Authenticator:
    - In Development: Allows client-specified role and bypasses interface checks.
    - In Production: Enforces API Key, validates allowed interfaces, and resolves server-side role.
    """
    client_interface = request.headers.get("X-Client-Interface", "web").lower()

    # --- MODE A: DEVELOPMENT (Testing & Local Verification) ---
    if SECURITY_ENV == "development":
        effective_role = req.role or "Standard Users"
        print(
            f"🛠️ [Agent Shield DEV MODE] Permissive role accepted from client: '{effective_role}' (Interface: {client_interface})"
        )
        return effective_role, client_interface

    # --- MODE B: PRODUCTION (Strict Zero-Trust Enforcement) ---
    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="[SECURITY VIOLATION]: Production mode requires a valid X-API-Key header.",
        )

    registry = load_user_registry()
    user_data = registry.get("api_keys", {}).get(api_key)

    if not user_data or not user_data.get("enabled", False):
        raise HTTPException(
            status_code=401,
            detail="[SECURITY VIOLATION]: Invalid or revoked API Key.",
        )

    # 1. Interface Restriction Check (e.g. Disallow CLI if user is restricted to web)
    allowed_interfaces = user_data.get("allowed_interfaces", ["web"])
    if client_interface not in allowed_interfaces:
        raise HTTPException(
            status_code=403,
            detail=(
                f"[SECURITY VIOLATION]: User '{user_data.get('user')}' is not authorized to access "
                f"Agent Shield via '{client_interface}'. Allowed interfaces: {allowed_interfaces}."
            ),
        )

    # 2. Server binds the real role (client-supplied req.role is strictly discarded)
    server_bound_role = user_data.get("role", "Standard Users")
    print(
        f"🔒 [Agent Shield PROD MODE] Authenticated '{user_data.get('user')}' -> Bound Role: '{server_bound_role}'"
    )
    return server_bound_role, client_interface


@app.post("/api/chat", response_model=ChatResponse)
def handle_chat_request(
    request: Request,
    req: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ChatResponse:
    # 1. Resolve Identity, Effective Role & Interface via Dual-Mode Authenticator
    effective_role, _ = resolve_authenticated_context(request, req)

    # 2. Resolve Session Thread ID
    thread_id = req.thread_id or "default_session"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    # 3. Prepare execution prompt with attachment context if present
    execution_prompt = req.prompt
    if req.attachment and req.attachment.get("content"):
        att_name = req.attachment.get("name", "attachment")
        att_content = req.attachment.get("content")
        execution_prompt = (
            f"{req.prompt}\n\n--- Attached File ({att_name}) ---\n{att_content}"
        )

    # 4. Inbound Layer 1 Security Scan (Scans prompt + attached payload)
    p_res = prompt_scanner.scan(execution_prompt, req.rag_context)
    j_res = jailbreak_detector.scan(execution_prompt)
    inbound_score, decision, justification = RiskEngine.aggregate_and_decide(
        p_res, j_res
    )

    audit_entry: Any = SecurityAuditLog(
        thread_id=thread_id,
        prompt=req.prompt,
        risk_score=inbound_score,
        decision=decision,
        justification=justification,
        triggered_detectors={"prompt_scanner": p_res, "jailbreak_detector": j_res},
        tool_calls_attempted=[],
        status="COMPLETED",
    )

    # Broadcast helper defined in scope before any returns
    def broadcast_chat_update(reply_text: str, replies: list[str]) -> None:
        broadcaster.publish_sync(
            "chat_message",
            {
                "session_id": thread_id,
                "log_id": int(audit_entry.id),
                "prompt": req.prompt,
                "attachment": req.attachment,
                "reply": reply_text,
                "replies": replies,
                "decision": str(audit_entry.decision),
                "risk_score": float(audit_entry.risk_score),
                "justification": str(audit_entry.justification),
                "tool_calls": audit_entry.tool_calls_attempted or [],
                "approval_needed": bool(audit_entry.status == "PENDING_REVIEW"),
            },
        )

    # Inbound BLOCK Decision
    if decision == "BLOCK":
        block_msg = "[SECURITY BLOCK]: Action aborted by Agent Shield. Direct prompt injection or adversarial phrasing identified."
        audit_entry.final_response = block_msg
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)

        broadcast_chat_update(block_msg, [block_msg])
        broadcaster.publish_sync(
            "analytics_updated", {"analytics": get_analytics_payload(db)}
        )

        return ChatResponse(
            log_id=int(audit_entry.id),
            decision="BLOCK",
            risk_score=inbound_score,
            justification=justification,
            reply=block_msg,
            replies=[block_msg],
            approval_needed=False,
        )

    initial_state: AgentState = {
        "messages": [HumanMessage(content=execution_prompt)],
        "status": "RUNNING",
        "pending_tool_call": None,
        "risk_score": inbound_score,
        "justification": justification,
        "final_output": None,
        "step_count": 0,
        "thread_id": thread_id,
        "role": effective_role,
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

        broadcast_chat_update(audit_entry.final_response, [audit_entry.final_response])
        return ChatResponse(
            log_id=int(audit_entry.id),
            decision="WARN",
            risk_score=45.0,
            justification="Upstream engine limit.",
            reply=f"[Agent Shield Alert]: {err_msg[:200]}",
            replies=[f"[Agent Shield Alert]: {err_msg[:200]}"],
            approval_needed=False,
        )

    # 1. CHECK: Did LangGraph tool inspection block the action?
    if final_state.get("status") == "BLOCKED" or final_state.get("risk_score", 0) > 80:
        audit_entry.decision = "BLOCK"
        audit_entry.risk_score = float(final_state.get("risk_score", 85.0))
        audit_entry.justification = final_state.get(
            "justification", "Tool execution blocked by security policy."
        )
        audit_entry.final_response = (
            final_state.get("final_output")
            or f"[SECURITY FIREWALL]: Execution blocked by policy for role '{effective_role}'."
        )
        audit_entry.status = "COMPLETED"
        audit_entry.tool_calls_attempted = (
            [final_state["pending_tool_call"]]
            if final_state.get("pending_tool_call")
            else []
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)

        broadcast_chat_update(audit_entry.final_response, [audit_entry.final_response])
        broadcaster.publish_sync(
            "analytics_updated", {"analytics": get_analytics_payload(db)}
        )

        return ChatResponse(
            log_id=int(audit_entry.id),
            decision="BLOCK",
            risk_score=audit_entry.risk_score,
            justification=audit_entry.justification,
            reply=audit_entry.final_response,
            replies=[audit_entry.final_response],
            approval_needed=False,
        )

    # 2. CHECK: Did LangGraph pause for human approval?
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
        hold_msg = (
            f"⏸️ **[SECURITY HOLD]**: The agent attempted to execute privileged tool `{tool_name}`. "
            f"This action has been suspended and queued in the **Human Review Queue** for confirmation."
        )
        audit_entry.final_response = hold_msg

        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)

        # Real-time SSE push
        broadcaster.publish_sync(
            "approvals_updated", {"approvals": get_pending_approvals_list(db)}
        )
        broadcaster.publish_sync(
            "analytics_updated", {"analytics": get_analytics_payload(db)}
        )
        broadcast_chat_update(hold_msg, [hold_msg])

        return ChatResponse(
            log_id=int(audit_entry.id),
            decision="APPROVE",
            risk_score=float(audit_entry.risk_score),
            justification=str(audit_entry.justification),
            reply=hold_msg,
            replies=[hold_msg],
            approval_needed=True,
        )

    # Normal Completion
    audit_entry.decision = decision
    audit_entry.risk_score = max(
        inbound_score, float(final_state.get("risk_score", 0.0))
    )
    audit_entry.justification = final_state.get("justification", justification)

    raw_final: str = str(final_state.get("final_output") or "Task completed.")
    audit_entry.final_response = raw_final
    # Extract all successfully executed tools from the message history
    executed_tools = []
    for msg in final_state.get("messages", []):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            executed_tools.extend(msg.tool_calls)

    audit_entry.tool_calls_attempted = executed_tools

    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)

    split_chunks = re.split(
        r"(?:---|###|\n\n)\s*(?:Response|Message)\s*\d+\s*(?:---|:)?\s*", raw_final
    )
    cleaned_replies = [c.strip() for c in split_chunks if c.strip()]
    final_replies = cleaned_replies if len(cleaned_replies) > 1 else [raw_final]

    broadcast_chat_update(raw_final, final_replies)
    broadcaster.publish_sync(
        "analytics_updated", {"analytics": get_analytics_payload(db)}
    )

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
    response: Response,
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return get_pending_approvals_list(db)


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

    broadcaster.publish_sync(
        "approvals_updated", {"approvals": get_pending_approvals_list(db)}
    )
    broadcaster.publish_sync(
        "analytics_updated", {"analytics": get_analytics_payload(db)}
    )

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
    logs: list[Any] = query.order_by(SecurityAuditLog.id.desc()).limit(50).all()
    return [serialize_log(l) for l in logs]


@app.get("/api/analytics")
def get_analytics(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    return get_analytics_payload(db)


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


@app.get("/api/sessions")
def get_all_sessions(db: Annotated[Session, Depends(get_db)]) -> list[dict[str, Any]]:
    """Returns all unique conversational threads from the audit database."""
    logs: list[Any] = (
        db.query(SecurityAuditLog).order_by(SecurityAuditLog.id.desc()).all()
    )
    seen = set()
    sessions = []
    for l in logs:
        t_id = getattr(l, "thread_id", "default_session")
        if t_id and t_id not in seen:
            seen.add(t_id)
            timestamp_val = getattr(l, "timestamp", None)
            sessions.append(
                {
                    "id": t_id,
                    "title": (
                        f"CLI: {l.prompt[:22]}..."
                        if t_id.startswith("cli_")
                        else (l.prompt[:24] + "...")
                    ),
                    "latest_activity": (
                        timestamp_val.isoformat() if timestamp_val else None
                    ),
                }
            )
    return sessions


@app.get("/api/sessions/{thread_id}/messages")
def get_session_messages(
    thread_id: str, db: Annotated[Session, Depends(get_db)]
) -> list[dict[str, Any]]:
    """Loads all historical messages for a specific session thread."""
    logs: list[Any] = (
        db.query(SecurityAuditLog)
        .filter(SecurityAuditLog.thread_id == thread_id)
        .order_by(SecurityAuditLog.id.asc())
        .all()
    )
    result = []
    for l in logs:
        timestamp_val = getattr(l, "timestamp", None)
        ts_str = timestamp_val.strftime("%I:%M %p") if timestamp_val else ""
        result.append(
            {
                "role": "user",
                "content": l.prompt,
                "timestamp": ts_str,
            }
        )
        result.append(
            {
                "role": "agent",
                "content": l.final_response or "",
                "decision": l.decision,
                "risk": l.risk_score,
                "justification": l.justification,
                "logId": l.id,
                "toolCalls": l.tool_calls_attempted or [],
                "approvalNeeded": l.status == "PENDING_REVIEW",
                "timestamp": ts_str,
            }
        )
    return result


# Static Frontend SPA Serving MUST BE AT THE VERY BOTTOM (so it doesn't shadow /api routes)
if os.path.exists(FRONTEND_DIST):
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.exists(assets_dir):
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="assets",
        )

    @app.get("/api/auth/verify")
    def verify_auth(request: Request) -> dict[str, Any]:
        """Pre-flight handshake to verify API Keys and Interface Entitlements."""
        import contextlib
        import json
        import os

        from app.config import SECURITY_ENV

        client_interface = request.headers.get("X-Client-Interface", "web").lower()

        # Dev Mode allows everyone
        if SECURITY_ENV == "development":
            return {"status": "ok", "mode": "development", "role": "Unbound (Dev Mode)"}

        # Production Mode Strict Checks
        api_key = request.headers.get("X-API-Key", "").strip()
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="Production mode requires a valid X-API-Key header.",
            )

        registry = {"api_keys": {}}
        USERS_FILE_PATH = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "config/users.json")
        )
        if os.path.exists(USERS_FILE_PATH):
            with contextlib.suppress(Exception) and open(
                USERS_FILE_PATH, "r", encoding="utf-8"
            ) as f:
                registry = json.load(f)

        user_data = registry.get("api_keys", {}).get(api_key)
        if not user_data or not user_data.get("enabled", False):
            raise HTTPException(status_code=401, detail="Invalid or revoked API Key.")

        allowed_interfaces = user_data.get("allowed_interfaces", ["web"])
        if client_interface not in allowed_interfaces:
            raise HTTPException(
                status_code=403,
                detail=f"User '{user_data.get('user')}' is restricted to interfaces: {allowed_interfaces}. Access via '{client_interface}' denied.",
            )

        return {
            "status": "ok",
            "mode": "production",
            "role": user_data.get("role", "Standard Users"),
            "user": user_data.get("user"),
        }

    @app.get("/{full_path:path}")
    def serve_frontend_spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        direct_file = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(direct_file):
            return FileResponse(direct_file)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
