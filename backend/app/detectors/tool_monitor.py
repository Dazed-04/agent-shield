"""Tool-call policy enforcement point (Layer 2).

Fail-closed: an unknown role, an unregistered tool, or a tool the role's policy does not mention
is denied (or falls back to the role's ``default_policy``). Every decision carries an explicit
``action`` so callers never have to infer it from a numeric score.

Evaluation order
  1. Registered-tool check.
  2. Hard safety rules on the arguments (apply to *every* role, including admins):
     * Python code is parsed with ``ast`` - dangerous imports/calls/dunder access => BLOCK,
       file/OS access => at least APPROVE.
     * Shell/SQL/credential-file signatures in code-like arguments; path rules for file arguments.
  3. Role policy from policies.json: DENY / APPROVE / WARN / ALLOW, ``disallowed_patterns``,
     ``allowed_extensions`` and ``max_invocations_per_session`` (all enforced).
  4. A session lease may downgrade APPROVE -> ALLOW. It can never override DENY or a hard block.
"""

import ast
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from typing import Any

logger = logging.getLogger(__name__)

POLICY_FILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../config/policies.json")
)

# action -> representative score (inside the matching policy band)
SCORE_ALLOW, SCORE_WARN, SCORE_APPROVE, SCORE_BLOCK = 15.0, 40.0, 65.0, 90.0
SEVERITY = {"ALLOW": 0, "WARN": 1, "APPROVE": 2, "BLOCK": 3}
_ACTION_SCORE = {
    "ALLOW": SCORE_ALLOW,
    "WARN": SCORE_WARN,
    "APPROVE": SCORE_APPROVE,
    "BLOCK": SCORE_BLOCK,
}

CODE_ARG_NAMES = {"code", "script", "command", "cmd", "query", "sql", "source"}
PATH_ARG_NAMES = {"filename", "path", "file", "filepath", "file_path", "directory"}

CRITICAL_MODULES = {
    "subprocess", "socket", "ctypes", "multiprocessing", "pty", "requests", "urllib",
    "http", "ftplib", "smtplib", "telnetlib", "importlib", "builtins", "pickle",
    "marshal", "shelve", "cffi", "webbrowser", "asyncio", "threading", "signal",
    "resource", "gc", "inspect", "code", "codeop", "runpy", "pkgutil", "sysconfig",
    "platform", "pwd", "grp", "fcntl", "mmap", "select", "ssl", "xmlrpc", "wsgiref",
}  # fmt: skip
SENSITIVE_MODULES = {"os", "sys", "pathlib", "shutil", "glob", "tempfile", "io", "fileinput", "zipfile", "tarfile"}
CRITICAL_ATTRS = {
    "system", "popen", "execv", "execve", "execl", "execlp", "execvp", "spawnl", "spawnv",
    "fork", "forkpty", "kill", "killpg", "remove", "unlink", "rmdir", "removedirs", "rmtree",
    "rename", "replace", "chmod", "chown", "environ", "getenv", "putenv", "unsetenv",
    "symlink", "link", "startfile", "check_output", "check_call", "run", "Popen",
    "__import__", "_exit", "abort",
}  # fmt: skip
CRITICAL_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint", "globals", "locals", "vars", "setattr", "delattr"}
SENSITIVE_CALLS = {"open", "getattr", "input"}
CRITICAL_DUNDERS = {
    "__class__", "__bases__", "__base__", "__subclasses__", "__mro__", "__globals__",
    "__builtins__", "__code__", "__closure__", "__dict__", "__import__", "__loader__",
    "__getattribute__", "__reduce__", "__reduce_ex__", "__self__", "__func__", "__module__",
    "__traceback__", "__spec__", "__file__",
}  # fmt: skip

_SHELL_PATTERNS = [
    (re.compile(r"\brm\s+-[a-z]*r[a-z]*f?\b|\brm\s+-[a-z]*f[a-z]*r\b", re.I), "recursive delete (rm -rf)"),
    (re.compile(r"\b(?:drop|truncate)\s+(?:table|database)\b|\bdelete\s+from\b", re.I), "destructive SQL"),
    (re.compile(r"\bmkfs\b|\bdd\s+if=|:\(\)\s*\{", re.I), "disk/fork-bomb payload"),
    (re.compile(r"/etc/(?:passwd|shadow|sudoers)|\bid_rsa\b|\.ssh/|\.aws/credentials", re.I), "sensitive system/credential file"),
    (re.compile(r"(?:^|[\s'\"/])\.env(?:\.\w+)?\b", re.I), "environment/secret file (.env)"),
    (re.compile(r"\b(?:curl|wget|nc|ncat)\s+\S+", re.I), "network fetch/exfiltration command"),
]
_PATH_PATTERNS = [
    (re.compile(r"(?:^|[\\/])\.env(?:\.\w+)?$", re.I), "environment/secret file (.env)"),
    (re.compile(r"id_rsa|id_ed25519|\.pem$|\.key$|shadow$|passwd$", re.I), "credential/system file"),
]


class _BoundedDict(OrderedDict):
    def __init__(self, maxsize: int = 10_000) -> None:
        super().__init__()
        self.maxsize = maxsize

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.maxsize:
            self.popitem(last=False)


def _iter_strings(obj: Any, depth: int = 0):
    if depth > 6:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v, depth + 1)


def analyse_python(code: str) -> tuple[list[str], list[str]]:
    """Static analysis of a Python snippet. Returns (critical findings, sensitive findings)."""
    critical: list[str] = []
    sensitive: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return [], []  # will simply fail to run
    except (ValueError, RecursionError, MemoryError):
        return ["code could not be safely analysed (null bytes / excessive nesting)"], []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in CRITICAL_MODULES:
                    critical.append(f"import of dangerous module '{root}'")
                elif root in SENSITIVE_MODULES:
                    sensitive.append(f"import of '{root}' (file/OS access)")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            names = {a.name for a in node.names}
            if root in CRITICAL_MODULES:
                critical.append(f"import from dangerous module '{root}'")
            elif root in SENSITIVE_MODULES:
                if "*" in names or names & CRITICAL_ATTRS:
                    critical.append(f"import of dangerous function from '{root}'")
                else:
                    sensitive.append(f"import from '{root}' (file/OS access)")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                if fn.id in CRITICAL_CALLS:
                    critical.append(f"call to '{fn.id}()'")
                elif fn.id in SENSITIVE_CALLS:
                    sensitive.append(f"call to '{fn.id}()'")
        elif isinstance(node, ast.Attribute):
            if node.attr in CRITICAL_DUNDERS:
                critical.append(f"access to '{node.attr}' (sandbox-escape primitive)")
            elif node.attr in CRITICAL_ATTRS:
                critical.append(f"use of '.{node.attr}' (process/file/env control)")
        elif isinstance(node, ast.Name) and node.id in CRITICAL_DUNDERS:
            critical.append(f"reference to '{node.id}'")
    return list(dict.fromkeys(critical)), list(dict.fromkeys(sensitive))


class ToolMonitor:
    def __init__(self, policy_path: str = POLICY_FILE_PATH) -> None:
        self.policy_path = policy_path
        self._lock = threading.RLock()
        self._last_policy_mtime: float | None = None
        self.policies: dict[str, Any] = {}
        self.session_leases: dict[str, dict[str, Any]] = {}
        self.invocations: _BoundedDict = _BoundedDict()
        self.load_policies()

    # ------------------------------------------------------------------ policy loading
    def load_policies(self) -> dict[str, Any]:
        with self._lock:
            try:
                with open(self.policy_path, encoding="utf-8") as f:
                    self.policies = json.load(f)
                self._last_policy_mtime = os.path.getmtime(self.policy_path)
            except (OSError, json.JSONDecodeError) as e:
                # Keep the previous policies (or none => everything denied) rather than failing open.
                logger.error("Failed to load policies.json (%s); keeping previous policy", e)
            return self.policies

    def _refresh_if_changed(self) -> None:
        try:
            mtime = os.path.getmtime(self.policy_path)
        except OSError:
            return
        if mtime != self._last_policy_mtime:
            self.load_policies()

    # ------------------------------------------------------------------ leases & quotas
    def grant_session_lease(
        self, thread_id: str, tool_name: str, max_uses: int = 3, duration_seconds: int = 600
    ) -> None:
        with self._lock:
            now = time.time()
            for tid in list(self.session_leases):  # opportunistic cleanup
                self.session_leases[tid] = {
                    name: lease for name, lease in self.session_leases[tid].items() if lease["expires_at"] > now
                }
                if not self.session_leases[tid]:
                    del self.session_leases[tid]
            self.session_leases.setdefault(thread_id, {})[tool_name] = {
                "expires_at": now + duration_seconds,
                "remaining_uses": max_uses,
            }

    def _active_lease(self, thread_id: str | None, tool_name: str) -> dict[str, Any] | None:
        if not thread_id:
            return None
        lease = self.session_leases.get(thread_id, {}).get(tool_name)
        if lease and time.time() < lease["expires_at"] and lease["remaining_uses"] > 0:
            return lease
        return None

    def consume_lease(self, thread_id: str | None, tool_name: str) -> None:
        with self._lock:
            lease = self._active_lease(thread_id, tool_name)
            if lease:
                lease["remaining_uses"] -= 1

    def record_invocation(self, thread_id: str | None, tool_name: str) -> None:
        with self._lock:
            key = (thread_id or "", tool_name)
            self.invocations[key] = self.invocations.get(key, 0) + 1

    # ------------------------------------------------------------------ inspection
    @staticmethod
    def _result(action: str, reasons: list[str], uses_lease: bool = False) -> dict[str, Any]:
        return {
            "action": action,
            "score": _ACTION_SCORE[action],
            "flagged": action != "ALLOW",
            "reasons": reasons,
            "uses_lease": uses_lease,
        }

    def _hard_rules(self, tool_name: str, args: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Return (block reasons, escalate-to-approval reasons) independent of role."""
        block: list[str] = []
        escalate: list[str] = []

        for key, value in args.items():
            k = key.lower()
            if k in CODE_ARG_NAMES or k not in PATH_ARG_NAMES and tool_name not in ("write_sandbox_file", "read_sandbox_file"):
                for text in _iter_strings(value):
                    for pattern, label in _SHELL_PATTERNS:
                        if pattern.search(text):
                            block.append(f"Exploit signature in '{key}': {label}")
                    if tool_name == "execute_python_code" or k in {"code", "script"}:
                        crit, sens = analyse_python(text)
                        block += [f"Unsafe code: {c}" for c in crit]
                        escalate += [f"Code touches the system: {s}" for s in sens]
            if k in PATH_ARG_NAMES:
                for text in _iter_strings(value):
                    if "\x00" in text or ".." in re.split(r"[\\/]", text) or os.path.isabs(text) or re.match(r"^[A-Za-z]:", text):
                        block.append(f"Path traversal / absolute path in '{key}': {text[:60]!r}")
                        continue
                    for pattern, label in _PATH_PATTERNS:
                        if pattern.search(text):
                            block.append(f"Sensitive file target in '{key}': {label}")
        return list(dict.fromkeys(block)), list(dict.fromkeys(escalate))

    def inspect(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        thread_id: str | None = None,
        role: str = "Standard Users",
        registered_tools: set[str] | None = None,
    ) -> dict[str, Any]:
        """Decide what to do with one tool call. Pure w.r.t. leases/quotas (see consume_lease)."""
        self._refresh_if_changed()
        tool_args = tool_args if isinstance(tool_args, dict) else {"value": tool_args}

        if registered_tools is not None and tool_name not in registered_tools:
            return self._result("BLOCK", [f"Tool '{tool_name}' is not registered."])

        block, escalate = self._hard_rules(tool_name, tool_args)
        if block:
            return self._result("BLOCK", [*block, "Hard block (applies to every role)."])

        role_config = self.policies.get("roles", {}).get(role)
        if role_config is None:
            return self._result("BLOCK", [f"Unknown role '{role}': denied (fail-closed)."])

        tool_policy = role_config.get("tools", {}).get(tool_name)
        if tool_policy is None:
            default = str(role_config.get("default_policy", "DENY")).upper()
            policy_action = "BLOCK" if default == "DENY" else default
            tool_policy = {}
            reasons = [f"Role '{role}' has no explicit rule for '{tool_name}'; default policy {default}."]
        else:
            raw = str(tool_policy.get("policy", "DENY")).upper()
            policy_action = "BLOCK" if raw == "DENY" else raw
            reasons = []
            if policy_action == "BLOCK":
                reasons.append(f"Role '{role}' is forbidden from invoking '{tool_name}'.")
        if policy_action not in SEVERITY:
            return self._result("BLOCK", [f"Invalid policy value for '{tool_name}'; denied."])
        if policy_action == "BLOCK":
            return self._result("BLOCK", reasons)

        # per-tool argument rules
        flat = " ".join(" ".join(s.split()) for s in _iter_strings(tool_args)).lower()
        for pat in tool_policy.get("disallowed_patterns", []):
            if pat.lower() in flat:
                return self._result("BLOCK", [f"Argument pattern '{pat}' is forbidden for role '{role}'."])

        allowed_ext = [e.lower() for e in tool_policy.get("allowed_extensions", [])]
        if allowed_ext:
            for key in PATH_ARG_NAMES & {k.lower() for k in tool_args}:
                for name in _iter_strings(tool_args.get(key, tool_args.get(key.upper(), ""))):
                    if os.path.splitext(name)[1].lower() not in allowed_ext:
                        return self._result(
                            "BLOCK",
                            [f"File extension of '{name}' not allowed for '{tool_name}' (allowed: {', '.join(allowed_ext)})."],
                        )

        max_calls = tool_policy.get("max_invocations_per_session")
        if max_calls is not None and thread_id is not None:
            if self.invocations.get((thread_id, tool_name), 0) >= int(max_calls):
                return self._result("BLOCK", [f"Session quota of {max_calls} calls to '{tool_name}' exhausted."])

        # compose the final action: policy, raised by hard-rule escalations
        action = policy_action
        reasons = reasons or [f"Role '{role}' policy for '{tool_name}': {policy_action}."]
        if escalate and SEVERITY[action] < SEVERITY["APPROVE"]:
            action = "APPROVE"
            reasons += escalate

        uses_lease = False
        if action == "APPROVE" and not escalate and self._active_lease(thread_id, tool_name):
            action, uses_lease = "ALLOW", True
            reasons = [f"Approved by active session lease for '{tool_name}'."]
        elif action == "APPROVE":
            reasons.append("Human approval required before execution.")

        return self._result(action, reasons, uses_lease)
