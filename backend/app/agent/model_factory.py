import itertools
import json
import logging
import os
import re
from typing import Any

from pydantic import SecretStr

logger = logging.getLogger(__name__)

MODELS_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../config/models.json")
)

_PROVIDER_KEY_CYCLERS: dict[str, Any] = {}

ChatGoogleGenerativeAI: Any = None
ChatGroq: Any = None
ChatOpenAI: Any = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI as _ChatGoogle

    ChatGoogleGenerativeAI = _ChatGoogle
except ImportError:
    pass

try:
    from langchain_groq import ChatGroq as _ChatGroq

    ChatGroq = _ChatGroq
except ImportError:
    pass

try:
    from langchain_openai import ChatOpenAI as _ChatOpenAI

    ChatOpenAI = _ChatOpenAI
except ImportError:
    pass


def _resolve_env_var(value: str) -> str:
    if not isinstance(value, str):
        return value

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        return os.getenv(var_name, default_val).strip()

    return re.sub(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}", _replace, value).strip()


def load_model_registry() -> list[dict[str, Any]]:
    if not os.path.exists(MODELS_CONFIG_PATH):
        return []

    try:
        with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        providers = raw_data.get("providers", [])
        cleaned = []
        for p in providers:
            if not p.get("enabled", False):
                continue

            entry = p.copy()
            if "base_url" in entry:
                entry["base_url"] = _resolve_env_var(entry["base_url"])

            raw_keys = entry.get("api_keys", [])
            if entry.get("api_key"):
                raw_keys.append(entry["api_key"])

            resolved_keys = []
            for k in raw_keys:
                expanded = _resolve_env_var(k)
                for sub_k in expanded.split(","):
                    if sub_k.strip():
                        resolved_keys.append(sub_k.strip())

            entry["resolved_keys"] = list(dict.fromkeys(resolved_keys))
            cleaned.append(entry)

        return cleaned
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Error parsing models.json: %s", e)
        return []


def get_available_models_for_ui() -> list[dict[str, Any]]:
    """Returns ONLY models that have valid, non-empty keys or are local offline providers."""
    providers = load_model_registry()
    available = []
    for p in providers:
        keys = p.get("resolved_keys", [])
        p_type = p.get("type", "")
        # Include if local model or if real keys exist in env
        if p_type in ("ollama", "openai_compatible") or len(keys) > 0:
            available.append(
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "model": p.get("model"),
                    "type": p_type,
                }
            )
    return available


def _get_next_key(provider_id: str, keys: list[str]) -> str | None:
    if not keys:
        return None
    if provider_id not in _PROVIDER_KEY_CYCLERS:
        _PROVIDER_KEY_CYCLERS[provider_id] = itertools.cycle(keys)
    return next(_PROVIDER_KEY_CYCLERS[provider_id])


def get_configured_llm(
    tools: list[Any], requested_id: str | None = None
) -> tuple[Any, str]:
    providers = load_model_registry()
    if not providers:
        raise RuntimeError("No enabled AI providers found in config/models.json.")

    # If user selected a specific model from the dropdown, prioritize it first!
    if requested_id:
        providers = sorted(
            providers, key=lambda p: 0 if p.get("id") == requested_id else 1
        )

    last_error: Exception | None = None

    for target in providers:
        p_type = target.get("type", "openai_compatible").lower()
        p_model = target.get("model", "")
        p_id = target.get("id", "provider")
        keys = target.get("resolved_keys", [])
        timeout = target.get("timeout_seconds", 12)

        # 1. Google Gemini Provider
        if p_type == "gemini":
            api_key = _get_next_key(p_id, keys)
            if not api_key:
                continue

            if ChatGoogleGenerativeAI is None:
                continue

            try:
                llm = ChatGoogleGenerativeAI(
                    model=p_model or "gemini-1.5-flash",
                    google_api_key=api_key,
                    temperature=0.2,
                    timeout=timeout,
                )
                return llm.bind_tools(tools), f"Gemini ({p_model})"
            except Exception as e:  # noqa: BLE001
                last_error = e
                continue

        # 2. Groq Cloud Provider (With auto-fallback on retired models)
        elif p_type == "groq":
            api_key = _get_next_key(p_id, keys)
            if not api_key:
                continue

            if ChatGroq is None:
                continue

            candidate_models = [
                p_model,
                "openai/gpt-oss-120b",
                "openai/gpt-oss-20b",
                "llama-3.1-8b-instant",
            ]
            for m_candidate in candidate_models:
                if not m_candidate:
                    continue
                try:
                    llm = ChatGroq(
                        model=m_candidate,
                        api_key=SecretStr(api_key),
                        temperature=0.2,
                        max_tokens=800,
                        timeout=timeout,
                    )
                    return llm.bind_tools(tools), f"Groq ({m_candidate})"
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    continue

        # 3. Universal OpenAI-Compatible (Local Ollama, vLLM, etc.)
        elif p_type in ("openai_compatible", "ollama"):
            api_key = _get_next_key(p_id, keys) or "none"
            base_url = target.get("base_url", "http://localhost:11434/v1")

            if ChatOpenAI is None:
                continue

            try:
                llm = ChatOpenAI(
                    model=p_model or "llama3.1:8b",
                    base_url=base_url,
                    api_key=SecretStr(api_key),
                    temperature=0.2,
                    timeout=timeout,
                    max_retries=1,
                )
                return llm.bind_tools(tools), f"Local/Compatible ({p_model})"
            except Exception as e:  # noqa: BLE001
                last_error = e
                continue

    raise RuntimeError(f"All configured providers failed. Last error: {last_error}")
