import json
import os
import time
from typing import Any

POLICY_FILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../config/policies.json")
)


class ToolMonitor:
    def __init__(self):
        self.session_leases: dict[str, dict[str, Any]] = {}
        self.dangerous_patterns = [
            "os.system",
            "subprocess",
            "rm -rf",
            "delete",
            "drop table",
            "id_rsa",
            ".env",
            "passwd",
            "shutil.rmtree",
        ]
        self.policies = self.load_policies()

    def load_policies(self) -> dict[str, Any]:
        """Dynamically loads policies.json if present on disk."""
        if os.path.exists(POLICY_FILE_PATH):
            try:
                with open(POLICY_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ [ToolMonitor] Failed to load policies.json: {e}")
        return {}

    def grant_session_lease(
        self,
        thread_id: str,
        tool_name: str,
        max_uses: int = 3,
        duration_seconds: int = 600,
    ):
        if thread_id not in self.session_leases:
            self.session_leases[thread_id] = {}

        self.session_leases[thread_id][tool_name] = {
            "expires_at": time.time() + duration_seconds,
            "remaining_uses": max_uses,
        }

    def inspect(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        thread_id: str | None = None,
        role: str = "Standard Users",
    ) -> dict[str, Any]:

        if os.path.exists(POLICY_FILE_PATH):
            current_mtime = os.path.getmtime(POLICY_FILE_PATH)
            if getattr(self, "_last_policy_mtime", 0) != current_mtime:
                self.policies = self.load_policies()
                self._last_policy_mtime = current_mtime

        args_str = str(tool_args).lower()

        # 1. HARD SAFETY CHECK: Always block known exploit signatures
        for pattern in self.dangerous_patterns:
            if pattern in args_str:
                return {
                    "score": 95.0,
                    "flagged": True,
                    "reasons": [
                        f"Exploit signature '{pattern}' detected in arguments. Hard block."
                    ],
                }

        # 2. CHECK ACTIVE SESSION LEASE
        if thread_id and thread_id in self.session_leases:
            lease = self.session_leases[thread_id].get(tool_name)
            if lease:
                now = time.time()
                if now < lease["expires_at"] and lease["remaining_uses"] > 0:
                    lease["remaining_uses"] -= 1
                    return {
                        "score": 15.0,
                        "flagged": False,
                        "reasons": [
                            f"Authorized via active session lease ({lease['remaining_uses']} uses remaining)."
                        ],
                    }

        # 3. EVALUATE POLICIES.JSON BASED ON CALLER'S ROLE
        role_config = self.policies.get("roles", {}).get(role)
        if role_config:
            tool_policy = role_config.get("tools", {}).get(tool_name)
            if tool_policy:
                policy_action = tool_policy.get("policy", "APPROVE")

                # Check disallowed argument patterns specific to this role
                disallowed = tool_policy.get("disallowed_patterns", [])
                for d_pat in disallowed:
                    if d_pat.lower() in args_str:
                        return {
                            "score": 90.0,
                            "flagged": True,
                            "reasons": [
                                f"Argument pattern '{d_pat}' forbidden for role '{role}'."
                            ],
                        }

                if policy_action == "ALLOW":
                    return {
                        "score": 15.0,
                        "flagged": False,
                        "reasons": [
                            f"Role '{role}' is pre-authorized for '{tool_name}'."
                        ],
                    }
                elif policy_action == "DENY":
                    return {
                        "score": 85.0,
                        "flagged": True,
                        "reasons": [
                            f"Role '{role}' is forbidden from invoking '{tool_name}'."
                        ],
                    }
                else:  # APPROVE
                    return {
                        "score": 55.0,
                        "flagged": True,
                        "reasons": [
                            f"Role '{role}' requires human approval for '{tool_name}'."
                        ],
                    }

        # 4. DEFAULT FALLBACK RULES (if role not found in policies.json)
        if tool_name == "execute_python_code":
            return {
                "score": 55.0,
                "flagged": True,
                "reasons": [f"Default policy: '{tool_name}' requires human approval."],
            }
        return {"score": 5.0, "flagged": False, "reasons": ["Standard safe tool call."]}
