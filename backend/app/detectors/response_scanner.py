"""Outbound scanner: redacts secrets and PII from anything leaving the gateway."""

import os
import re
from typing import Any, Callable

_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]  # fmt: skip
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]  # fmt: skip

SECRET_REDACTION = "[REDACTED_SECRET]"
PII_REDACTION = "[REDACTED_PII]"
_PLACEHOLDER = re.compile(r"^(?:your|<|\*{3,}|x{3,}|\$|\{|changeme|example|none|null|true|false)", re.I)


def luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def _mask_assignment(m: re.Match[str]) -> str:
    value = m.group(3)
    if _PLACEHOLDER.match(value):
        return m.group(0)
    return f"{m.group(1)}{m.group(2)}{SECRET_REDACTION}"


def _checked(pattern: re.Pattern[str], validator: Callable[[str], bool]) -> Callable[[re.Match[str]], str]:
    def repl(m: re.Match[str]) -> str:
        return PII_REDACTION if validator(m.group(0)) else m.group(0)

    return repl


_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "OpenAI/Anthropic API Key": re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"),
    "Groq API Key": re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    "Google API Key": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}"),
    "AWS Access Key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "GitHub Token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
    "Slack Token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "Private Key": re.compile(
        r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z]+ )?PRIVATE KEY-----|$)"
    ),
}
_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)(\s*[:=]\s*['\"]?)([^\s'\"]{6,})"
)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")  # no trailing separator in the match
_AADHAAR = re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")
_SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")

_SECRET_ENV_HINT = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD)", re.I)


class ResponseScanner:
    """Secrets score 85 (WARN->BLOCK territory); PII scores 40 (WARN)."""

    def __init__(self, redact_emails: bool | None = None) -> None:
        if redact_emails is None:
            redact_emails = os.getenv("REDACT_EMAILS", "true").lower() in {"1", "true", "yes"}
        self.redact_emails = redact_emails
        self.known_secrets: list[str] = []
        self.refresh_known_secrets()

    def refresh_known_secrets(self) -> None:
        """Remember the *values* of this process's own credentials so they can never be echoed."""
        values = {
            v.strip()
            for k, v in os.environ.items()
            if _SECRET_ENV_HINT.search(k) and len(v.strip()) >= 8
            for v in v.split(",")
            if len(v.strip()) >= 8
        }
        self.known_secrets = sorted(values, key=len, reverse=True)

    def scan(self, response_text: str) -> dict[str, Any]:
        text = response_text or ""
        secrets: list[str] = []
        pii: list[str] = []

        for label, pattern in _SECRET_PATTERNS.items():
            if pattern.search(text):
                secrets.append(label)
                text = pattern.sub(SECRET_REDACTION, text)

        new_text = _ASSIGNMENT.sub(_mask_assignment, text)
        if new_text != text:
            secrets.append("Credential assignment")
            text = new_text

        for value in self.known_secrets:
            if value in text:
                secrets.append("Gateway credential (exact value)")
                text = text.replace(value, SECRET_REDACTION)

        for label, pattern, validator in (
            ("Payment card number", _CARD, luhn_valid),
            ("Aadhaar number", _AADHAAR, lambda s: verhoeff_valid(re.sub(r"\D", "", s))),
        ):
            new_text = pattern.sub(_checked(pattern, validator), text)
            if new_text != text:
                pii.append(label)
                text = new_text

        if _SSN.search(text):
            pii.append("US SSN")
            text = _SSN.sub(PII_REDACTION, text)

        if self.redact_emails and _EMAIL.search(text):
            pii.append("Email address")
            text = _EMAIL.sub(PII_REDACTION, text)

        detected = list(dict.fromkeys(secrets + pii))
        score = 85.0 if secrets else (40.0 if pii else 0.0)
        return {
            "score": score,
            "flagged": bool(detected),
            "leaks": detected,
            "has_secret": bool(secrets),
            "sanitized_response": text,
            "reason": (
                f"Sensitive data redacted: {', '.join(detected)}"
                if detected
                else "Response clear."
            ),
        }
