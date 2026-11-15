import itertools
import json
import logging
import os
import re
import threading
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


_REGISTRY_CACHE: dict[str, Any] = {"mtime": None, "raw": None}


def _read_registry_file() -> dict[str, Any] | None:
    """Parse models.json, re-reading only when the file changes."""
    try:
        mtime = os.path.getmtime(MODELS_CONFIG_PATH)
    except OSError:
        return None
    if _REGISTRY_CACHE["mtime"] != mtime:
        with open(MODELS_CONFIG_PATH, encoding="utf-8") as f:
            _REGISTRY_CACHE["raw"] = json.load(f)
        _REGISTRY_CACHE["mtime"] = mtime
    return _REGISTRY_CACHE["raw"]


def load_model_registry() -> list[dict[str, Any]]:
    try:
        raw_data = _read_registry_file()
        if raw_data is None:
            return []

        providers = raw_data.get("providers", [])
        cleaned = []
        for p in providers:
            if not p.get("enabled", False):
                continue

            entry = p.copy()
            if "base_url" in entry:
                entry["base_url"] = _resolve_env_var(entry["base_url"])

            raw_keys = list(entry.get("api_keys", []))
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
        _REGISTRY_CACHE["mtime"] = None
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


_KEY_LOCK = threading.Lock()


def _get_next_key(provider_id: str, keys: list[str]) -> str | None:
    if not keys:
        return None
    with _KEY_LOCK:
        if provider_id not in _PROVIDER_KEY_CYCLERS:
            _PROVIDER_KEY_CYCLERS[provider_id] = itertools.cycle(keys)
        return next(_PROVIDER_KEY_CYCLERS[provider_id])


def _build_chat_model(target: dict[str, Any]) -> Any | None:
    """Instantiate one provider's chat model (rotating through its API keys). None if unusable."""
    p_type = target.get("type", "openai_compatible").lower()
    p_model = target.get("model", "")
    p_id = target.get("id", "provider")
    keys = target.get("resolved_keys", [])
    timeout = target.get("timeout_seconds", 12)

    try:
        if p_type == "gemini":
            api_key = _get_next_key(p_id, keys)
            if not api_key or ChatGoogleGenerativeAI is None:
                return None
            return ChatGoogleGenerativeAI(
                model=p_model, google_api_key=api_key, temperature=0.2, timeout=timeout
            )
        if p_type == "groq":
            api_key = _get_next_key(p_id, keys)
            if not api_key or ChatGroq is None:
                return None
            return ChatGroq(
                model=p_model,
                api_key=SecretStr(api_key),
                temperature=0.2,
                max_tokens=800,
                timeout=timeout,
            )
        if p_type in ("openai_compatible", "ollama"):
            if ChatOpenAI is None:
                return None
            return ChatOpenAI(
                model=p_model or "llama3.1:8b",
                base_url=target.get("base_url", "http://localhost:11434/v1"),
                api_key=SecretStr(_get_next_key(p_id, keys) or "none"),
                temperature=0.2,
                timeout=timeout,
                max_retries=1,
            )
    except Exception as e:  # noqa: BLE001
        logger.error("Could not initialise provider %s: %s", p_id, e)
    return None


def get_llm_with_fallbacks(tools: list[Any], requested_id: str | None = None) -> Any:
    """Return a tool-bound chat model that fails over across providers *at call time*.

    The requested provider (if any) is tried first, then the rest in models.json order. Failover
    uses LangChain ``with_fallbacks`` so a rate limit / outage during ``invoke`` moves on to the
    next provider (building a client alone can never detect those).
    """
    providers = load_model_registry()
    if not providers:
        raise RuntimeError("No enabled AI providers found in config/models.json.")
    if requested_id:
        providers = sorted(providers, key=lambda p: 0 if p.get("id") == requested_id else 1)

    runnables = []
    for target in providers:
        model = _build_chat_model(target)
        if model is not None:
            runnables.append(model.bind_tools(tools))
    if not runnables:
        raise RuntimeError("All configured providers are unavailable (missing API keys or packages).")
    primary, *rest = runnables
    return primary.with_fallbacks(rest) if rest else primary
