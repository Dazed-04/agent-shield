import asyncio
import datetime
import json
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.agent.langgraph_agent import AgentState, compiled_agent
from app.agent.tools import TOOLS_BY_NAME
from app.auth import Principal, authenticate, is_development, require_admin, require_user
from app.config import CORS_ORIGINS, EVAL_RESULTS_DIR
from app.database import SessionLocal, get_db, init_db
from app.eval_results import RunNotFound, RunTooLarge, list_runs, load_run
from app.events import broadcaster
from app.metrics import AuditRow, compute_metrics
from app.models import SecurityAuditLog, utcnow
from app.schemas import (
    AddThreatRequest,
    ChatRequest,
    ChatResponse,
    GrantLeaseRequest,
    ResolveApprovalRequest,
)
from app.shield import (
    jailbreak_detector,
    response_scanner,
    screen_inbound,
    tool_monitor,
)

logger = logging.getLogger("agent_shield")

DbSession = Annotated[Session, Depends(get_db)]
User = Annotated[Principal, Depends(require_user)]
Admin = Annotated[Principal, Depends(require_admin)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    mode = await asyncio.to_thread(jailbreak_detector.warmup)
    logger.info("Jailbreak detector mode: %s", "semantic" if mode else "heuristic fallback")
    if is_development():
        logger.warning(
            "SECURITY_ENV=development: roles are client-declared and admin endpoints are OPEN. "
            "Never expose this mode beyond localhost."
        )
    yield


app = FastAPI(title="Agent Shield - Security Gateway", version="2.1.0", lifespan=lifespan)

_origins = CORS_ORIGINS or (
    ["http://localhost:5173", "http://127.0.0.1:5173"] if is_development() else []
)
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,  # auth is via X-API-Key header, not cookies
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key", "X-Client-Interface"],
    )

_candidates = [
    os.path.abspath("./frontend/dist"),
    os.path.abspath("../frontend/dist"),
    os.path.abspath("/app/frontend/dist"),
]
FRONTEND_DIST = next((p for p in _candidates if os.path.exists(p)), _candidates[1])

ENV_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
BACKEND_ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env"))


# --------------------------------------------------------------------------- serialisation
def serialize_log(log: Any) -> dict[str, Any]:
    return {
        "id": int(log.id),
        "thread_id": str(log.thread_id or "default_session"),
        "user_id": log.user_id,
        "role": log.role,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "prompt": str(log.prompt),
        "risk_score": float(log.risk_score),
        "decision": str(log.decision),
        "justification": str(log.justification),
        "triggered_detectors": log.triggered_detectors or {},
        "tool_calls_attempted": log.tool_calls_attempted or [],
        "final_response": str(log.final_response) if log.final_response else None,
        "status": str(log.status),
        "latency_ms": log.latency_ms,
    }


def _scope(query: Any, principal: Principal) -> Any:
    """Non-admins only ever see their own records."""
    if principal.is_admin:
        return query
    return query.filter(SecurityAuditLog.user_id == principal.user)


def get_pending_approvals_list(db: Session) -> list[dict[str, Any]]:
    logs = (
        db.query(SecurityAuditLog)
        .filter(SecurityAuditLog.status == "PENDING_REVIEW")
        .order_by(SecurityAuditLog.id.asc())
        .limit(200)
        .all()
    )
    return [serialize_log(entry) for entry in logs]


def get_analytics_payload(db: Session, user: str | None = None) -> dict[str, Any]:
    """Aggregates in SQL - O(1) memory regardless of log volume."""
    base = db.query(SecurityAuditLog)
    if user is not None:
        base = base.filter(SecurityAuditLog.user_id == user)

    counts = {"ALLOW": 0, "WARN": 0, "APPROVE": 0, "BLOCK": 0}
    rows = base.with_entities(
        SecurityAuditLog.decision,
        func.count(SecurityAuditLog.id),
        func.avg(SecurityAuditLog.risk_score),
    ).group_by(SecurityAuditLog.decision)
    avg_risk: dict[str, float] = {}
    for decision, n, avg in rows:
        counts[str(decision)] = int(n)
        avg_risk[str(decision)] = round(float(avg or 0.0), 2)

    latency = base.with_entities(func.avg(SecurityAuditLog.latency_ms)).scalar()
    recent = base.order_by(SecurityAuditLog.id.desc()).limit(10).all()[::-1]

    day = func.date(SecurityAuditLog.timestamp)
    timeline: dict[str, dict[str, int]] = {}
    for d, decision, n in (
        base.with_entities(day, SecurityAuditLog.decision, func.count(SecurityAuditLog.id))
        .group_by(day, SecurityAuditLog.decision)
        .order_by(day.desc())
        .limit(14 * 4)
    ):
        timeline.setdefault(str(d), {})[str(decision)] = int(n)

    return {
        "total_requests": sum(counts.values()),
        "breakdown": counts,
        "avg_risk_by_decision": avg_risk,
        "avg_latency_ms": round(float(latency), 2) if latency is not None else None,
        "timeline": dict(sorted(timeline.items())),
        "recent_logs": [serialize_log(entry) for entry in recent],
    }


def _push_state(db: Session) -> None:
    """Notify admin dashboards that approvals/analytics changed (skipped if nobody is listening)."""
    if not broadcaster.subscribers:
        return
    broadcaster.publish_sync(
        "analytics_updated", {"analytics": get_analytics_payload(db)}, admin_only=True
    )
    broadcaster.publish_sync(
        "approvals_updated", {"approvals": get_pending_approvals_list(db)}, admin_only=True
    )


def reload_all_system_configs() -> dict[str, Any]:
    """Reloads .env, policies.json and resets key pools at runtime."""
    reloaded = []
    for path in (BACKEND_ENV_PATH, ENV_FILE_PATH):
        if os.path.exists(path):
            load_dotenv(dotenv_path=path, override=True)
            reloaded.append(f"env ({os.path.basename(path)})")

    tool_monitor.load_policies()
    reloaded.append("policies.json")
    response_scanner.refresh_known_secrets()

    from app.agent.model_factory import _PROVIDER_KEY_CYCLERS

    _PROVIDER_KEY_CYCLERS.clear()
    reloaded.append("models.json & API key pools")

    with SessionLocal() as db:
        _push_state(db)
    logger.info("Hot-reloaded configurations: %s", ", ".join(reloaded))
    return {"status": "success", "reloaded": reloaded}


# --------------------------------------------------------------------------- SSE
@app.get("/api/events/stream")
async def event_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events. Production: pass the key as X-API-Key or ?api_key= (EventSource
    cannot set headers). Admins receive everything; others only events for their own chats."""
    principal = authenticate(request, allow_query_key=True)

    async def event_generator() -> AsyncGenerator[str, None]:
        sub = await broadcaster.subscribe(principal.user, principal.is_admin)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_type, payload = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    yield f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            broadcaster.unsubscribe(sub)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/auth/verify")
def verify_auth(request: Request) -> dict[str, Any]:
    """Pre-flight handshake for CLI and Web clients."""
    if is_development():
        return {"status": "ok", "mode": "development", "role": "Unbound (Dev Mode)", "is_admin": True}
    if not request.headers.get("X-API-Key", "").strip():
        return {"status": "unauthenticated", "mode": "production", "role": "Standard Users", "authenticated": False}
    p = authenticate(request)
    return {
        "status": "ok",
        "mode": "production",
        "role": p.role,
        "user": p.user,
        "is_admin": p.is_admin,
        "authenticated": True,
    }


# --------------------------------------------------------------------------- chat
def _tool_calls_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for msg in messages:
        calls.extend(getattr(msg, "tool_calls", None) or [])
    return calls


@app.post("/api/chat", response_model=ChatResponse)
def handle_chat_request(request: Request, req: ChatRequest, db: DbSession, principal: User) -> ChatResponse:
    t_start = time.perf_counter()

    # 1. Identity (production: server-bound; development: client-declared)
    if is_development():
        effective_role = req.role or "Standard Users"
        user_id = req.user_id or "default_user"
    else:
        effective_role, user_id = principal.role, principal.user
    client_interface = principal.interface

    # 2. Thread ownership: a caller may not write into someone else's session
    thread_id = req.thread_id or f"session_{uuid.uuid4().hex[:16]}"
    owner = (
        db.query(SecurityAuditLog.user_id)
        .filter(SecurityAuditLog.thread_id == thread_id)
        .order_by(SecurityAuditLog.id.asc())
        .first()
    )
    if owner and owner[0] and owner[0] != user_id and not principal.is_admin:
        raise HTTPException(403, "This session belongs to another user.")

    # 3. Build the model-facing prompt. Attachments / RAG are UNTRUSTED data, delimited as such.
    untrusted_parts: list[str] = []
    execution_prompt = req.prompt
    if req.attachment and req.attachment.get("content"):
        att_name = str(req.attachment.get("name", "attachment"))[:120]
        att_content = str(req.attachment["content"])
        untrusted_parts.append(att_content)
        execution_prompt += (
            f'\n\n<untrusted_attachment name="{att_name}">\n'
            f'{att_content.replace("</untrusted_attachment", "</untrusted_attachment_")}\n</untrusted_attachment>'
        )
    if req.rag_context:
        untrusted_parts.append(req.rag_context)
        execution_prompt += (
            "\n\n<untrusted_attachment name=\"retrieved_context\">\n"
            f'{req.rag_context.replace("</untrusted_attachment", "</untrusted_attachment_")}\n</untrusted_attachment>'
        )
    untrusted_text = "\n\n".join(untrusted_parts) or None

    # 4. Inbound Layer 1
    screen = screen_inbound(req.prompt, untrusted_text)
    p_res, j_res = screen.prompt_result, screen.jailbreak_result
    inbound_score, decision, justification = screen.score, screen.decision, screen.justification
    timings: dict[str, float] = screen.timings

    audit = SecurityAuditLog(
        thread_id=thread_id,
        user_id=user_id,
        role=effective_role,
        prompt=req.prompt,
        risk_score=inbound_score,
        decision=decision,
        justification=justification,
        triggered_detectors={"prompt_scanner": p_res, "jailbreak_detector": j_res},
        tool_calls_attempted=[],
        status="COMPLETED",
    )

    def persist() -> None:
        timings["total"] = round((time.perf_counter() - t_start) * 1000, 2)
        audit.triggered_detectors = {
            **(audit.triggered_detectors or {}),
            "timings_ms": timings,
        }
        audit.latency_ms = timings["total"]
        db.add(audit)
        db.commit()
        db.refresh(audit)

    def broadcast(reply_text: str, replies: list[str]) -> None:
        broadcaster.publish_sync(
            "chat_message",
            {
                "session_id": thread_id,
                "client_interface": client_interface,
                "log_id": int(audit.id),
                "prompt": req.prompt,
                "attachment": req.attachment,
                "reply": reply_text,
                "replies": replies,
                "decision": str(audit.decision),
                "risk_score": float(audit.risk_score),
                "justification": str(audit.justification),
                "tool_calls": audit.tool_calls_attempted or [],
                "approval_needed": audit.status == "PENDING_REVIEW",
            },
            owner=user_id,
        )

    def respond(reply: str, replies: list[str] | None = None, approval: bool = False) -> ChatResponse:
        persist()
        replies = replies or [reply]
        broadcast(reply, replies)
        _push_state(db)
        return ChatResponse(
            log_id=int(audit.id),
            decision=str(audit.decision),
            risk_score=float(audit.risk_score),
            justification=str(audit.justification),
            reply=reply,
            replies=replies,
            approval_needed=approval,
        )

    # 5. Hard stop before the model is ever called
    if decision == "BLOCK":
        msg = "[SECURITY BLOCK]: Action aborted by Agent Shield. Prompt injection or adversarial phrasing identified."
        audit.final_response = msg
        return respond(msg)

    # 6. Run the agent (Layers 2 & 3 live inside the graph)
    initial_state: AgentState = {
        "messages": [HumanMessage(content=execution_prompt)],
        "status": "RUNNING",
        "pending_tool_calls": [],
        "risk_score": inbound_score,
        "justification": justification,
        "final_output": None,
        "step_count": 0,
        "thread_id": thread_id,
        "model_id": req.model_id,
        "role": effective_role,
        "worst_action": decision,
        "escalate": decision == "APPROVE",
        "notes": [],
    }
    t = time.perf_counter()
    try:
        final_state: dict[str, Any] = compiled_agent.invoke(initial_state)
    except Exception as e:  # noqa: BLE001
        logger.exception("Agent invocation failed")
        timings["agent"] = round((time.perf_counter() - t) * 1000, 2)
        audit.decision = "WARN"
        audit.risk_score = max(inbound_score, 45.0)
        audit.justification = "Upstream model/provider error; request not completed."
        audit.final_response = "The model provider returned an error. Please try again."
        # Details stay in the server log, not in the user-visible response.
        audit.triggered_detectors = {**audit.triggered_detectors, "error": str(e)[:300]}
        return respond(f"[Agent Shield Alert]: {audit.final_response}")
    timings["agent"] = round((time.perf_counter() - t) * 1000, 2)

    status = final_state.get("status")
    worst = str(final_state.get("worst_action", decision))
    notes: list[str] = final_state.get("notes", [])
    if status in ("BLOCKED", "WAITING_APPROVAL"):
        # The tool layer overrode the inbound verdict: don't lead with "Executing directly".
        _, _, triggered_text = justification.partition(" Triggered: ")
        head = (
            f"Prompt screening passed ({inbound_score}/100)."
            if decision == "ALLOW"
            else f"Prompt screening: {decision} ({inbound_score}/100)."
        )
        justification = head + (f" Triggered: {triggered_text}" if triggered_text else "")
    full_justification = justification + (" | " + " | ".join(notes) if notes else "")
    risk = float(final_state.get("risk_score", inbound_score))

    if status == "BLOCKED":
        audit.decision, audit.risk_score = "BLOCK", max(risk, inbound_score)
        audit.justification = full_justification
        audit.final_response = final_state.get("final_output") or "[SECURITY FIREWALL]: Execution blocked by policy."
        audit.tool_calls_attempted = _tool_calls_from_messages(final_state.get("messages", [])[-1:])
        return respond(audit.final_response)

    if status == "WAITING_APPROVAL":
        pending = final_state.get("pending_tool_calls") or []
        names = ", ".join(c.get("name", "tool") for c in pending) or "tool"
        audit.decision, audit.risk_score = "APPROVE", max(risk, inbound_score)
        audit.justification = full_justification
        audit.status = "PENDING_REVIEW"
        audit.tool_calls_attempted = pending
        hold = (
            f"⏸️ **[SECURITY HOLD]**: The agent attempted to execute privileged tool(s) `{names}`. "
            "This action has been suspended and queued in the **Human Review Queue** for confirmation."
        )
        audit.final_response = hold
        return respond(hold, approval=True)

    # Normal completion (decision = worst severity observed anywhere in the pipeline)
    audit.decision = worst
    audit.risk_score = max(inbound_score, risk)
    audit.justification = full_justification
    raw_final = str(final_state.get("final_output") or "Task completed.")
    audit.final_response = raw_final
    audit.tool_calls_attempted = _tool_calls_from_messages(final_state.get("messages", []))

    chunks = re.split(r"(?:---|###|\n\n)\s*(?:Response|Message)\s*\d+\s*(?:---|:)?\s*", raw_final)
    cleaned = [c.strip() for c in chunks if c.strip()]
    return respond(raw_final, cleaned if len(cleaned) > 1 else [raw_final])


# --------------------------------------------------------------------------- models/providers
@app.get("/api/providers")
def list_providers(_: Admin) -> list[dict[str, Any]]:
    from app.agent.model_factory import load_model_registry

    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "type": p.get("type"),
            "model": p.get("model"),
            "keys_configured": len(p.get("resolved_keys", [])),
        }
        for p in load_model_registry()
    ]


@app.get("/api/models")
def get_available_models() -> list[dict[str, Any]]:
    from app.agent.model_factory import get_available_models_for_ui

    return get_available_models_for_ui()


# --------------------------------------------------------------------------- approvals
@app.get("/api/approvals/pending")
def list_pending_approvals(db: DbSession, response: Response, _: Admin) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    return get_pending_approvals_list(db)


@app.post("/api/approvals/resolve")
def resolve_approval(req: ResolveApprovalRequest, db: DbSession, admin: Admin) -> dict[str, Any]:
    log = db.query(SecurityAuditLog).filter(SecurityAuditLog.id == req.log_id).first()
    if not log:
        raise HTTPException(404, "Log entry not found")

    # Atomic claim: only one resolver can move PENDING_REVIEW -> APPROVED/REJECTED, so a tool
    # call can never be executed twice by double-clicks or replayed requests.
    new_status = "APPROVED" if req.action == "APPROVE" else "REJECTED"
    claimed = db.execute(
        update(SecurityAuditLog)
        .where(SecurityAuditLog.id == req.log_id, SecurityAuditLog.status == "PENDING_REVIEW")
        .values(status=new_status, resolved_by=admin.user)
    )
    db.commit()
    if claimed.rowcount != 1:
        raise HTTPException(409, "This request is not awaiting review (already resolved?).")
    db.refresh(log)

    tool_calls = log.tool_calls_attempted or []
    if req.action == "APPROVE":
        outputs: list[str] = []
        for call in tool_calls:
            name = call.get("name", "")
            # Re-check at execution time: policy may have changed since the hold.
            recheck = tool_monitor.inspect(
                name, call.get("args") or {}, log.thread_id, log.role or "Standard Users", set(TOOLS_BY_NAME)
            )
            if recheck["action"] == "BLOCK":
                outputs.append(f"`{name}` refused at execution time: {'; '.join(recheck['reasons'])}")
                continue
            try:
                tool_monitor.record_invocation(log.thread_id, name)
                raw = TOOLS_BY_NAME[name].invoke(call.get("args") or {})
                outputs.append(f"```\n{response_scanner.scan(str(raw))['sanitized_response']}\n```")
            except Exception as e:  # noqa: BLE001
                outputs.append(f"Execution error: {e!s}")
        names = ", ".join(c.get("name", "tool") for c in tool_calls) or "tool"
        log.final_response = "\n".join(outputs) or f"Tool `{names}` completed."
        decision_label = "AUTHORIZED"
    else:
        names = ", ".join(c.get("name", "tool") for c in tool_calls) or "tool"
        log.final_response = f"Execution of `{names}` was cancelled."
        decision_label = "REJECTED"
    db.commit()

    _push_state(db)
    return {
        "status": "success",
        "log_id": log.id,
        "resolved_action": req.action,
        "new_response": log.final_response,
        "decision": decision_label,
    }


@app.post("/api/session/grant-lease")
def grant_lease(req: GrantLeaseRequest, _: Admin) -> dict[str, Any]:
    if req.tool_name not in TOOLS_BY_NAME:
        raise HTTPException(400, f"Unknown tool '{req.tool_name}'.")
    tool_monitor.grant_session_lease(req.thread_id, req.tool_name, req.max_uses, req.duration_seconds)
    return {
        "status": "success",
        "message": (
            f"Granted lease for '{req.tool_name}' in session '{req.thread_id}' "
            f"(Limit: {req.max_uses} calls, {req.duration_seconds}s)."
        ),
    }


# --------------------------------------------------------------------------- audit & analytics
@app.get("/api/logs")
def get_logs_by_decision(
    db: DbSession,
    principal: User,
    decision: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = _scope(db.query(SecurityAuditLog), principal)
    if decision:
        query = query.filter(SecurityAuditLog.decision == decision.upper())
    rows = (
        query.order_by(SecurityAuditLog.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 200))
        .all()
    )
    return [serialize_log(r) for r in rows]


@app.get("/api/analytics")
def get_analytics(db: DbSession, principal: User) -> dict[str, Any]:
    return get_analytics_payload(db, None if principal.is_admin else principal.user)


@app.get("/api/eval/runs")
def eval_runs(_: Admin) -> list[dict[str, Any]]:
    """Saved evaluation runs (newest first). Empty when nothing has been run on this host."""
    return list_runs(EVAL_RESULTS_DIR)


@app.get("/api/eval/runs/{run_id}")
def eval_run(run_id: str, _: Admin) -> dict[str, Any]:
    try:
        return load_run(EVAL_RESULTS_DIR, run_id)
    except RunNotFound:
        raise HTTPException(status_code=404, detail="Run or report not found. Generate it with `python -m evaluation report|agent-report`.") from None
    except RunTooLarge:
        raise HTTPException(status_code=413, detail="Report file is too large to serve.") from None


MAX_METRIC_ROWS = 50_000


@app.get("/api/analytics/metrics")
def get_metrics(db: DbSession, principal: User, days: int = 7) -> dict[str, Any]:
    """Decision mix, score distribution, detector hit rates, latency percentiles and a time series."""
    days = max(1, min(days, 90))
    now = utcnow()
    q = db.query(SecurityAuditLog).filter(SecurityAuditLog.timestamp >= now - datetime.timedelta(days=days))
    if not principal.is_admin:
        q = q.filter(SecurityAuditLog.user_id == principal.user)
    found = (
        q.with_entities(
            SecurityAuditLog.timestamp,
            SecurityAuditLog.role,
            SecurityAuditLog.decision,
            SecurityAuditLog.risk_score,
            SecurityAuditLog.latency_ms,
            SecurityAuditLog.triggered_detectors,
            SecurityAuditLog.tool_calls_attempted,
        )
        .order_by(SecurityAuditLog.id.desc())
        .limit(MAX_METRIC_ROWS + 1)
        .all()
    )
    truncated = len(found) > MAX_METRIC_ROWS
    rows = [
        AuditRow(ts, role, str(dec), float(score or 0.0), lat, det if isinstance(det, dict) else {}, len(calls) if isinstance(calls, list) else 0)
        for ts, role, dec, score, lat, det, calls in found[:MAX_METRIC_ROWS]
    ]
    return compute_metrics(rows, days, now, truncated)


@app.get("/api/sessions")
def get_all_sessions(db: DbSession, principal: User) -> list[dict[str, Any]]:
    latest_ids = _scope(
        db.query(func.max(SecurityAuditLog.id).label("mid")), principal
    ).group_by(SecurityAuditLog.thread_id).subquery()
    rows = (
        db.query(SecurityAuditLog)
        .join(latest_ids, SecurityAuditLog.id == latest_ids.c.mid)
        .order_by(SecurityAuditLog.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": r.thread_id,
            "title": (f"CLI: {r.prompt[:22]}..." if str(r.thread_id).startswith("cli_") else r.prompt[:24] + "..."),
            "latest_activity": r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ]


@app.get("/api/sessions/{thread_id}/messages")
def get_session_messages(thread_id: str, db: DbSession, principal: User) -> list[dict[str, Any]]:
    logs = (
        _scope(db.query(SecurityAuditLog), principal)
        .filter(SecurityAuditLog.thread_id == thread_id)
        .order_by(SecurityAuditLog.id.asc())
        .limit(500)
        .all()
    )
    result: list[dict[str, Any]] = []
    for entry in logs:
        ts = entry.timestamp.strftime("%I:%M %p") if entry.timestamp else ""
        result.append({"role": "user", "content": entry.prompt, "timestamp": ts})
        result.append(
            {
                "role": "agent",
                "content": entry.final_response or "",
                "decision": entry.decision,
                "risk": entry.risk_score,
                "justification": entry.justification,
                "logId": entry.id,
                "toolCalls": entry.tool_calls_attempted or [],
                "approvalNeeded": entry.status == "PENDING_REVIEW",
                "timestamp": ts,
            }
        )
    return result


@app.post("/api/config/reload")
def trigger_config_reload(_: Admin) -> dict[str, Any]:
    return reload_all_system_configs()


# --------------------------------------------------------------------------- active learning
@app.post("/api/threats/learn")
def learn_new_threat(req: AddThreatRequest, admin: Admin) -> dict[str, Any]:
    """Add a human-validated attack phrase to the semantic detector without a restart."""
    if not jailbreak_detector.add_threat_vector(req.threat_text):
        return {"status": "skipped", "message": "Threat already indexed, invalid, or limit reached."}
    logger.info("Threat vector learned by %s: %r", admin.user, req.threat_text[:80])
    return {
        "status": "learned",
        "total_threat_vectors": len(jailbreak_detector.jailbreak_anchors),
        "sample": req.threat_text[:50],
    }


@app.get("/api/threats")
def list_threats(_: Admin) -> dict[str, Any]:
    return {
        "builtin": len(jailbreak_detector.builtin_anchors),
        "learned": list(jailbreak_detector.learned),
        "mode": jailbreak_detector.mode,
    }


@app.post("/api/threats/forget")
def forget_threat(req: AddThreatRequest, admin: Admin) -> dict[str, Any]:
    """Undo a learned phrase (e.g. one that causes false positives). Built-ins are protected."""
    removed = jailbreak_detector.remove_threat_vector(req.threat_text)
    if removed:
        logger.info("Threat vector removed by %s: %r", admin.user, req.threat_text[:80])
    return {"status": "removed" if removed else "not_found"}


# Static SPA serving MUST stay last so it does not shadow /api routes.
if os.path.exists(FRONTEND_DIST):
    _dist_real = os.path.realpath(FRONTEND_DIST)
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend_spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found")
        candidate = os.path.realpath(os.path.join(_dist_real, full_path))
        if full_path and os.path.commonpath([candidate, _dist_real]) == _dist_real and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_dist_real, "index.html"))
