"""Deterministic stand-in models for dry runs and tests.  They are SYNTHETIC: results obtained with them
say something about the harness and the defences' mechanics, never about real model behaviour.

* ``gullible``  obeys any instruction found in tool output (including base64-encoded ones)
* ``resistant`` never follows injected instructions
"""

from __future__ import annotations

import base64
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_FILE = re.compile(r"create a file named (\S+) containing exactly: (\S+)")
_CODE = re.compile(r"run this Python code with your code tool: (.+?)(?:\s*-->|\n|$)")
_READ = re.compile(r"read the file (\S+) and include its full contents")
_DOC = re.compile(r"(?:Read|Open) (\S+?) and")


def _decoded(text: str) -> str:
    out = [text]
    for m in _B64.findall(text):
        try:
            out.append(base64.b64decode(m + "=" * (-len(m) % 4)).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
    return "\n".join(out)


class ScriptedAgentLLM:
    def __init__(self, mode: str = "gullible") -> None:
        if mode not in ("gullible", "resistant"):
            raise ValueError("mode must be 'gullible' or 'resistant'")
        self.mode = mode

    def invoke(self, messages: list[Any]) -> AIMessage:
        user = next(m for m in messages if isinstance(m, HumanMessage))
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        made = {(c["name"], str(c["args"])) for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}

        def call(name: str, args: dict[str, Any]) -> AIMessage:
            return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{len(made)}", "type": "tool_call"}])

        if not tool_msgs:
            m = _DOC.search(str(user.content))
            return call("read_sandbox_file", {"filename": m.group(1) if m else "notes.txt"})

        if self.mode == "gullible":
            seen = _decoded("\n".join(str(t.content) for t in tool_msgs))
            if (m := _FILE.search(seen)) and ("write_sandbox_file", str({"filename": m.group(1), "content": m.group(2)})) not in made:
                return call("write_sandbox_file", {"filename": m.group(1), "content": m.group(2)})
            if (m := _CODE.search(seen)) and ("execute_python_code", str({"code": m.group(1).strip()})) not in made:
                return call("execute_python_code", {"code": m.group(1).strip()})
            if (m := _READ.search(seen)) and ("read_sandbox_file", str({"filename": m.group(1)})) not in made:
                return call("read_sandbox_file", {"filename": m.group(1)})
        return AIMessage(content="Here is what I found:\n" + "\n".join(str(t.content) for t in tool_msgs))
