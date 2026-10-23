import re
from typing import Any


class PromptScanner:
    def __init__(self):
        self.signatures = [
            (
                r"\b(api[-_\s]?keys?|\.env\b|passwords?|credentials?|secret\s*keys?|tokens?)\b",
                85.0,
                "Credential or sensitive environment file exfiltration probe",
            ),
            (
                r"\b(i('m| am)|as)\s+(the\s+)?(system\s+admin|administrator|root|security\s+auditor|engineer)\b",
                75.0,
                "Authority impersonation / social engineering vector",
            ),
            (
                r"ignore\b.*?\binstructions?",
                85.0,
                "System instruction override attempt",
            ),
            (
                r"bypass\b.*?\b(security|guardrail|filter|moderation)",
                90.0,
                "Security filter bypass request",
            ),
            (
                r"(reveal|print|show|output)\b.*?\b(system prompt|base prompt|instructions)",
                80.0,
                "System prompt exfiltration attempt",
            ),
            (r"system\s*override", 85.0, "System override signature"),
            (r"\bact\s+as\s+dan\b", 95.0, "Known DAN jailbreak signature"),
            (r"\bdeveloper\s+mode\b", 85.0, "Developer mode jailbreak vector"),
            (
                r"\b(drop\s+table|delete\s+from|rm\s+-rf)\b",
                90.0,
                "Destructive system payload",
            ),
        ]

    def scan(self, prompt: str, retrieved_context: str | None = None) -> dict[str, Any]:
        combined = f"{prompt} {retrieved_context or ''}".lower()
        highest_score = 0.0
        reasons: list[str] = []

        for pattern, score, reason in self.signatures:
            if re.search(pattern, combined):
                highest_score = max(highest_score, score)
                reasons.append(reason)

        return {
            "score": highest_score,
            "flagged": highest_score >= 50.0,
            "reasons": reasons or ["No malicious injection patterns identified."],
        }
