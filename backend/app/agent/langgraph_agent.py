import logging
import os
from typing import Any, TypedDict

from groq import APIError, Groq
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import SecretStr

from app.agent.tools import ALL_TOOLS, TOOLS_BY_NAME
from app.detectors.response_scanner import ResponseScanner
from app.detectors.tool_monitor import ToolMonitor

logger = logging.getLogger(__name__)

tool_monitor = ToolMonitor()
response_scanner = ResponseScanner()

ACTIVE_GROQ_MODEL: str | None = None


def get_available_groq_model(api_key: str) -> str:
    global ACTIVE_GROQ_MODEL
    if ACTIVE_GROQ_MODEL:
        return ACTIVE_GROQ_MODEL

    try:
        client = Groq(api_key=api_key)
        raw_models = [m.id for m in client.models.list().data]
        blacklist = ["safeguard", "guard", "whisper", "orpheus", "vision", "embed"]
        chat_models = [
            m for m in raw_models if not any(b in m.lower() for b in blacklist)
        ]

        priority_keywords = [
            "llama-3.3-70b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "llama-3.1-8b",
        ]
        for kw in priority_keywords:
            for model_id in chat_models:
                if kw in model_id.lower():
                    ACTIVE_GROQ_MODEL = model_id
                    print(
                        f"⚡ [Agent Shield] Bound LangGraph to model: {ACTIVE_GROQ_MODEL}"
                    )
                    return ACTIVE_GROQ_MODEL

        if chat_models:
            ACTIVE_GROQ_MODEL = chat_models[0]
            return ACTIVE_GROQ_MODEL
    except (APIError, KeyError, IndexError, ValueError, ConnectionError) as e:
        logger.warning("Groq auto-detect failed: %s", e)

    ACTIVE_GROQ_MODEL = "llama-3.3-70b-versatile"
    return ACTIVE_GROQ_MODEL


class AgentState(TypedDict):
    messages: list[BaseMessage]
    status: str
    pending_tool_call: dict[str, Any] | None
    risk_score: float
    justification: str
    final_output: str | None
    step_count: int
    thread_id: str
    role: str


SYSTEM_INSTRUCTION = SystemMessage(
    content=(
        "You are an AI Agent protected by the Agent Shield security framework. "
        "Provide direct, concise, and structured responses using clean Markdown. "
        "Avoid unnecessary conversational filler or overly long essays unless explicitly asked."
        "Formatting Guidelines:\n"
        "- Do NOT enclose regular sentences or output phrases in backticks.\n"
        "- Reserve single backticks (`...`) strictly for filenames, tool names, shell commands, and code variables.\n"
        '- For quotes or file content excerpts, use standard quotation marks ("...") or blockquotes (>), not backticks.\n'
        "- Use clean Markdown tables with bold column headers when presenting tabular data."
    )
)


def get_llm():
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        raise ValueError("GROQ_API_KEY missing from backend/.env")
    model_name = get_available_groq_model(groq_key)
    return ChatGroq(
        model=model_name,
        api_key=SecretStr(groq_key),
        temperature=0.2,
        max_tokens=800,
    ).bind_tools(ALL_TOOLS)


def agent_node(state: AgentState):
    llm = get_llm()
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SYSTEM_INSTRUCTION, *messages]

    response = llm.invoke(messages)
    current_step = state.get("step_count", 0) + 1

    return {
        "messages": [*state["messages"], response],
        "status": "RUNNING",
        "step_count": current_step,
    }


def shield_interceptor_node(state: AgentState):
    last_msg = state["messages"][-1]

    if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
        output_text = (
            last_msg.content
            if isinstance(last_msg.content, str)
            else str(last_msg.content)
        )
        scan_res = response_scanner.scan(output_text)
        return {
            "status": "COMPLETED",
            "final_output": scan_res["sanitized_response"],
            "risk_score": scan_res["score"],
            "justification": "Final agent answer verified safe.",
        }

    tool_call = last_msg.tool_calls[0]
    t_id = state.get("thread_id", "default_session")
    user_role = state.get("role", "Standard Users")
    inspection = tool_monitor.inspect(
        tool_call["name"], tool_call["args"], thread_id=t_id, role=user_role
    )

    risk_score = inspection["score"]
    reasons = " | ".join(inspection["reasons"])
    if risk_score > 80:
        return {
            "status": "BLOCKED",
            "risk_score": risk_score,
            "justification": f"Blocked Tool Execution: {reasons}",
            "final_output": f"[SECURITY FIREWALL]: Execution of tool '{tool_call['name']}' was blocked due to critical risk.",
        }
    elif risk_score >= 50:
        return {
            "status": "WAITING_APPROVAL",
            "pending_tool_call": tool_call,
            "risk_score": risk_score,
            "justification": f"Privileged Tool Call Suspended: {reasons}",
        }

    return {
        "status": "TOOL_APPROVED",
        "pending_tool_call": tool_call,
        "risk_score": risk_score,
        "justification": f"Low risk tool call allowed: {reasons}",
    }


def tool_execution_node(state: AgentState):
    tool_call = state["pending_tool_call"]
    if not tool_call:
        return {"status": "COMPLETED", "pending_tool_call": None}

    tool_obj = TOOLS_BY_NAME.get(tool_call["name"])
    if not tool_obj:
        tool_output = f"Tool '{tool_call['name']}' not registered."
    else:
        try:
            tool_output = tool_obj.invoke(tool_call["args"])
        except Exception as e:  # noqa: BLE001
            tool_output = f"Tool execution failed: {e!s}"

    scan_res = response_scanner.scan(str(tool_output))
    clean_output = scan_res["sanitized_response"]

    tool_msg = ToolMessage(
        content=clean_output, tool_call_id=tool_call["id"], name=tool_call["name"]
    )

    return {
        "messages": [*state["messages"], tool_msg],
        "pending_tool_call": None,
        "status": "RUNNING",
    }


def route_shield(state: AgentState):
    status = state["status"]
    if status in ("COMPLETED", "BLOCKED", "WAITING_APPROVAL"):
        return END
    if state.get("step_count", 0) >= 6:
        return END
    return "execute_tool"


builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("shield_interceptor", shield_interceptor_node)
builder.add_node("execute_tool", tool_execution_node)

builder.set_entry_point("agent")
builder.add_edge("agent", "shield_interceptor")
builder.add_conditional_edges(
    "shield_interceptor", route_shield, {END: END, "execute_tool": "execute_tool"}
)
builder.add_edge("execute_tool", "agent")

checkpointer = MemorySaver()
compiled_agent = builder.compile(checkpointer=checkpointer)
