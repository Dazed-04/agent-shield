import itertools
import re
import threading
from typing import Any, ClassVar

from app.config import GEMINI_API_KEYS

genai: Any = None
GoogleAPIError: Any = Exception
ResourceExhausted: Any = Exception
GENAI_AVAILABLE: bool = False

try:
    import google.generativeai as _genai  # type: ignore[import-untyped]
    from google.api_core.exceptions import (  # type: ignore[import-untyped]
        GoogleAPIError as _GoogleAPIError,
    )
    from google.api_core.exceptions import (
        ResourceExhausted as _ResourceExhausted,
    )

    genai = _genai
    GoogleAPIError = _GoogleAPIError
    ResourceExhausted = _ResourceExhausted
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class RotatingKeyManager:
    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        self.lock = threading.Lock()
        self._cycler = itertools.cycle(keys) if keys else None

    def get_next_key(self) -> str | None:
        if not self._cycler:
            return None
        with self.lock:
            return next(self._cycler)

    def total_keys(self) -> int:
        return len(self.keys)


key_manager = RotatingKeyManager(GEMINI_API_KEYS)


class MockAgentOrchestrator:
    MODEL_CANDIDATES: ClassVar[list[str]] = [
        "gemini-3.8-flash",
        "models/gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]

    def _generate_with_fallback_models(self, prompt: str) -> str:
        last_error: Exception | None = None

        for candidate in self.MODEL_CANDIDATES:
            try:
                model = genai.GenerativeModel(candidate)
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text
            except (GoogleAPIError, RuntimeError, ValueError) as e:
                last_error = e
                err_msg = str(e)

                suggested_match = re.search(r"use models/([a-zA-Z0-9_.-]+)", err_msg)
                if suggested_match:
                    recommended_tag = suggested_match.group(1)
                    try:
                        print(
                            f"🔄 [Agent Shield] Auto-switching to model: {recommended_tag}"
                        )
                        rec_model = genai.GenerativeModel(recommended_tag)
                        rec_response = rec_model.generate_content(prompt)
                        if rec_response and rec_response.text:
                            return rec_response.text
                    except (GoogleAPIError, RuntimeError, ValueError) as rec_err:
                        last_error = rec_err

                if (
                    "404" in err_msg
                    or "not available" in err_msg
                    or "not found" in err_msg.lower()
                ):
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("No suitable Gemini model found for this key.")

    def execute(self, prompt: str) -> dict[str, Any]:
        prompt_lower = prompt.lower()
        tool_calls: list[dict[str, Any]] = []

        if "delete" in prompt_lower or "drop" in prompt_lower:
            tool_calls.append(
                {"tool": "database_delete", "args": {"target": "user_records"}}
            )
        elif "send" in prompt_lower and "email" in prompt_lower:
            tool_calls.append(
                {
                    "tool": "send_email",
                    "args": {"to": "admin@target.com", "body": prompt},
                }
            )
        elif "run" in prompt_lower or "exec" in prompt_lower:
            tool_calls.append({"tool": "shell_exec", "args": {"cmd": prompt}})

        output_text: str | None = None
        error_details: str | None = None

        if not GENAI_AVAILABLE:
            error_details = "google-generativeai library is not installed in venv."
        elif key_manager.total_keys() == 0:
            error_details = "No GEMINI_API_KEYS found in .env."
        else:
            max_attempts = key_manager.total_keys()
            for _ in range(max_attempts):
                api_key = key_manager.get_next_key()
                if not api_key:
                    break

                try:
                    genai.configure(api_key=api_key)
                    output_text = self._generate_with_fallback_models(prompt)
                    break
                except ResourceExhausted:
                    print(
                        f"⚠️ [Agent Shield] Key {api_key[:8]}... hit rate limit. Rotating..."
                    )
                    continue
                except (GoogleAPIError, RuntimeError, ValueError) as e:
                    print(f"❌ [Agent Shield] Gemini API call error: {e}")
                    error_details = str(e)
                    break

        if not output_text:
            output_text = (
                f"[Gateway Processed]: '{prompt}'. "
                f"Tools identified: {[t['tool'] for t in tool_calls]}. "
                + (f"(Notice: {error_details})" if error_details else "")
            )

        return {
            "output": output_text,
            "tool_calls": tool_calls,
        }
