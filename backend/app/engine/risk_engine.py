from typing import Any

from app.config import ALLOW_MAX, APPROVE_MAX, WARN_MAX


class RiskEngine:
    @staticmethod
    def aggregate_and_decide(
        prompt_res: dict[str, Any],
        jailbreak_res: dict[str, Any],
        tool_res: dict[str, Any] | None = None,
    ) -> tuple[float, str, str]:
        p_score = prompt_res.get("score", 0.0)
        j_score = jailbreak_res.get("score", 0.0)
        t_score = tool_res.get("score", 0.0) if tool_res else 0.0

        weighted_score = (p_score * 0.40) + (j_score * 0.35) + (t_score * 0.25)

        max_threat = max(p_score, j_score, t_score)
        if max_threat >= 70.0:
            final_score = max_threat
        else:
            final_score = max(weighted_score, max_threat * 0.80)

        final_score = round(min(max(final_score, 0.0), 100.0), 2)

        if final_score <= ALLOW_MAX:
            decision = "ALLOW"
            justification = (
                "Request evaluated with low threat likelihood. Executing directly."
            )
        elif final_score <= WARN_MAX:
            decision = "WARN"
            justification = (
                f"Elevated risk detected ({final_score}/100). Logged for audit."
            )
        elif final_score <= APPROVE_MAX:
            decision = "APPROVE"
            justification = f"Privileged or high-risk action detected ({final_score}/100). Suspended for human approval."
        else:
            decision = "BLOCK"
            justification = f"Critical security threat identified ({final_score}/100). Immediate action denial."

        return final_score, decision, justification
