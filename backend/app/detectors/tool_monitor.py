import time
from typing import Any


class ToolMonitor:
    def __init__(self):
        self.critical_tools = {"execute_python_code"}
        self.medium_tools = {"write_sandbox_file"}
        self.low_tools = {"read_sandbox_file"}
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
        self, tool_name: str, tool_args: dict[str, Any], thread_id: str | None = None
    ) -> dict[str, Any]:
        args_str = str(tool_args).lower()

        for pattern in self.dangerous_patterns:
            if pattern in args_str:
                return {
                    "score": 95.0,
                    "flagged": True,
                    "reasons": [
                        f"Exploit payload '{pattern}' detected in leased tool. Immediate block."
                    ],
                }

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
                            (
                                f"Authorized via active session lease (Expires in {int(lease['expires_at'] - now)}s, "
                                f"{lease['remaining_uses']} uses remaining)."
                            )
                        ],
                    }

        if tool_name in self.critical_tools:
            return {
                "score": 55.0,
                "flagged": True,
                "reasons": [
                    f"Tool '{tool_name}' requests system runtime code execution. Human approval required."
                ],
            }
        elif tool_name in self.medium_tools:
            return {
                "score": 30.0,
                "flagged": False,
                "reasons": [
                    f"Tool '{tool_name}' performs filesystem write operations."
                ],
            }

        return {"score": 5.0, "flagged": False, "reasons": ["Standard safe tool call."]}
