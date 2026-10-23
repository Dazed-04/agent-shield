import re


class ResponseScanner:
    def __init__(self):
        self.leakage_patterns = {
            "API Key / Secret": r"(sk-[a-zA-Z0-9]{20,}|gsk_[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z-_]{35})",
            "Email Address": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            "Credit Card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        }

    def scan(self, response_text: str) -> dict:
        detected = []
        sanitized_text = response_text

        for label, pattern in self.leakage_patterns.items():
            matches = re.findall(pattern, response_text)
            if matches:
                detected.append(label)
                sanitized_text = re.sub(
                    pattern, "[REDACTED_CONFIDENTIAL]", sanitized_text
                )

        score = 85.0 if detected else 0.0
        return {
            "score": score,
            "flagged": len(detected) > 0,
            "leaks": detected,
            "sanitized_response": sanitized_text,
            "reason": (
                f"Potential data exfiltration detected: {', '.join(detected)}"
                if detected
                else "Response clear."
            ),
        }
