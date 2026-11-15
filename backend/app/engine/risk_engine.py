from typing import Any

from app.config import (
    ALLOW_MAX,
    APPROVE_MAX,
    WARN_MAX,
    WEIGHT_JAILBREAK,
    WEIGHT_PROMPT,
    WEIGHT_TOOL,
)

SEVERITY = {"ALLOW": 0, "WARN": 1, "APPROVE": 2, "BLOCK": 3}


def worse(a: str, b: str) -> str:
    """Return the more severe of two actions."""
    return a if SEVERITY[a] >= SEVERITY[b] else b


class RiskEngine:
    @staticmethod
    def decide(score: float) -> str:
        if score <= ALLOW_MAX:
            return "ALLOW"
        if score <= WARN_MAX:
            return "WARN"
        if score <= APPROVE_MAX:
            return "APPROVE"
        return "BLOCK"

    @staticmethod
    def aggregate_and_decide(
        prompt_res: dict[str, Any],
        jailbreak_res: dict[str, Any],
        tool_res: dict[str, Any] | None = None,
    ) -> tuple[float, str, str]:
        """Combine detector outputs into (risk score 0-100, decision, human-readable explanation).

        Score = weighted mean of the detectors that ran (weights renormalised), floored at 80% of
        the strongest single detector, and equal to that detector outright once it reaches 70:
        one confident detector must not be diluted by quiet ones.
        """
        signals: list[tuple[str, float, float, str]] = []  # name, weight, score, reason
        p = float(prompt_res.get("score", 0.0))
        j = float(jailbreak_res.get("score", 0.0))
        signals.append(("prompt_scanner", WEIGHT_PROMPT, p, "; ".join(prompt_res.get("reasons", [])) if p > ALLOW_MAX else ""))
        signals.append(("jailbreak_detector", WEIGHT_JAILBREAK, j, str(jailbreak_res.get("reason", "")) if j > ALLOW_MAX else ""))
        if tool_res is not None:
            t = float(tool_res.get("score", 0.0))
            signals.append(("tool_monitor", WEIGHT_TOOL, t, "; ".join(tool_res.get("reasons", [])) if t > ALLOW_MAX else ""))

        total_w = sum(w for _, w, _, _ in signals) or 1.0
        weighted = sum(w * s for _, w, s, _ in signals) / total_w
        max_threat = max(s for _, _, s, _ in signals)
        final = max_threat if max_threat >= 70.0 else max(weighted, max_threat * 0.80)
        final = round(min(max(final, 0.0), 100.0), 2)

        decision = RiskEngine.decide(final)
        triggered = [f"{name}: {reason}" for name, _, s, reason in signals if reason and s > ALLOW_MAX]

        if decision == "ALLOW":
            justification = "Low risk: no malicious patterns detected. Executing directly."
        else:
            headline = {
                "WARN": f"Elevated risk ({final}/100). Proceeding; logged for audit.",
                "APPROVE": f"High risk ({final}/100). Any tool use requires human approval.",
                "BLOCK": f"Critical threat ({final}/100). Request denied before reaching the model.",
            }[decision]
            justification = headline + (" Triggered: " + " | ".join(triggered) if triggered else "")
        return final, decision, justification
