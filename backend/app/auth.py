"""Authentication & authorisation for the gateway.

* production  - every protected call needs a valid ``X-API-Key``; the role is bound server-side.
* development - permissive: the client may declare its role and admin endpoints are open.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request

from app.config import DEFAULT_SECURITY_ENV

logger = logging.getLogger(__name__)

USERS_FILE_PATH = os.getenv(
    "AGENT_SHIELD_USERS_FILE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "config/users.json")),
)

_registry_cache: dict[str, Any] = {"mtime": None, "data": {}}


def get_security_env() -> str:
    """Read dynamically so the mode can be switched without restarting."""
    return os.getenv("SECURITY_ENV", DEFAULT_SECURITY_ENV).lower()


def is_development() -> bool:
    return get_security_env() == "development"


def load_user_registry() -> dict[str, Any]:
    """Loads users.json, re-reading only when the file changes."""
    try:
        mtime = os.path.getmtime(USERS_FILE_PATH)
    except OSError:
        return {}
    if _registry_cache["mtime"] != mtime:
        try:
            with open(USERS_FILE_PATH, encoding="utf-8") as f:
                _registry_cache["data"] = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Could not read users file: %s", e)
            _registry_cache["data"] = {}
        _registry_cache["mtime"] = mtime
    return _registry_cache["data"]


@dataclass(frozen=True)
class Principal:
    user: str
    role: str
    interface: str
    is_admin: bool
    authenticated: bool


def _lookup_key(api_key: str) -> dict[str, Any] | None:
    registry = load_user_registry()
    digest = hashlib.sha256(api_key.encode()).hexdigest()

    for stored_hash, data in registry.get("api_key_hashes", {}).items():
        if hmac.compare_digest(stored_hash.lower(), digest):
            return data
    for stored_key, data in registry.get("api_keys", {}).items():
        if stored_key.startswith("REPLACE_ME"):
            continue  # never honour the shipped placeholders
        if hmac.compare_digest(stored_key.encode(), api_key.encode()):
            return data
    return None


def authenticate(request: Request, allow_query_key: bool = False) -> Principal:
    """Resolve the caller. Raises 401/403 in production when credentials are bad."""
    interface = request.headers.get("X-Client-Interface", "web").lower()

    if is_development():
        return Principal(
            user=request.headers.get("X-User", "dev_user"),
            role="",  # dev: role is taken from the request body
            interface=interface,
            is_admin=True,
            authenticated=False,
        )

    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key and allow_query_key:
        api_key = request.query_params.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(401, "Production mode requires a valid X-API-Key header.")

    data = _lookup_key(api_key)
    if not data or not data.get("enabled", False):
        time.sleep(0.2)  # blunt brute-force guessing
        raise HTTPException(401, "Invalid or revoked API Key.")

    allowed = data.get("allowed_interfaces", ["web"])
    if interface not in allowed:
        raise HTTPException(
            403,
            f"User '{data.get('user')}' is not authorized to access via "
            f"'{interface}'. Allowed interfaces: {allowed}.",
        )

    role = data.get("role", "Standard Users")
    return Principal(
        user=str(data.get("user", "unknown")),
        role=role,
        interface=interface,
        is_admin=bool(data.get("is_admin", role == "Domain Admins")),
        authenticated=True,
    )


def require_user(request: Request) -> Principal:
    return authenticate(request)


def require_admin(request: Request) -> Principal:
    principal = authenticate(request)
    if not principal.is_admin:
        raise HTTPException(403, "Administrator privileges required.")
    return principal
