"""Process-wide detector singletons shared by the API layer, the agent graph and the evaluation harness."""

import time
from dataclasses import dataclass, field
from typing import Any

from app.detectors.jailbreak_detector import JailbreakDetector
from app.detectors.prompt_scanner import PromptScanner
from app.detectors.response_scanner import ResponseScanner
from app.detectors.tool_monitor import ToolMonitor
from app.engine.risk_engine import RiskEngine

prompt_scanner = PromptScanner()
jailbreak_detector = JailbreakDetector()
response_scanner = ResponseScanner()
tool_monitor = ToolMonitor()


@dataclass
class InboundScreen:
    """Result of Layer 1 (inbound) screening, exactly as the gateway computes it."""

    prompt_result: dict[str, Any]
    jailbreak_result: dict[str, Any]
    score: float
    decision: str
    justification: str
    timings: dict[str, float] = field(default_factory=dict)


def screen_inbound(prompt: str, untrusted_text: str | None = None) -> InboundScreen:
    """Run both inbound detectors and the risk engine.

    ``prompt`` is the trusted user channel; ``untrusted_text`` is attachments / RAG / tool output.
    The API and the evaluation harness both call this, so measured behaviour is production behaviour.
    """
    timings: dict[str, float] = {}
    t = time.perf_counter()
    p_res = prompt_scanner.scan(prompt, untrusted_text)
    timings["prompt_scanner"] = round((time.perf_counter() - t) * 1000, 2)
    t = time.perf_counter()
    j_res = jailbreak_detector.scan(prompt)
    if untrusted_text:
        j_ctx = jailbreak_detector.scan(untrusted_text)
        if j_ctx["score"] > j_res["score"]:
            j_res = {**j_ctx, "reason": f"(in attached/retrieved content) {j_ctx['reason']}"}
    timings["jailbreak_detector"] = round((time.perf_counter() - t) * 1000, 2)
    score, decision, justification = RiskEngine.aggregate_and_decide(p_res, j_res)
    return InboundScreen(p_res, j_res, score, decision, justification, timings)
