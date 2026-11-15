"""Sandboxed tools exposed to the agent.

NOTE: ``execute_python_code`` applies defence-in-depth (isolated interpreter, scrubbed
environment, resource limits, wall-clock timeout, static analysis upstream in ToolMonitor) but a
subprocess is not a security boundary. Run the gateway in a container (see docker-compose.yml) -
do not rely on this alone for untrusted code.
"""

import os
import subprocess
import sys

from langchain_core.tools import tool

from app.config import CODE_EXEC_MEMORY_MB, CODE_EXEC_TIMEOUT_S, MAX_TOOL_OUTPUT_CHARS

SANDBOX_DIR = os.path.realpath(
    os.getenv("AGENT_SHIELD_SANDBOX_DIR", os.path.abspath("./sandbox"))
)
os.makedirs(SANDBOX_DIR, exist_ok=True)

MAX_FILE_BYTES = 1_000_000
MAX_CODE_CHARS = 20_000

# Runs inside the child: apply rlimits, then execute the user's snippet.
_LAUNCHER = (
    "import resource,sys;"
    "mb=int(sys.argv[1])*1024*1024;"
    "resource.setrlimit(resource.RLIMIT_AS,(mb,mb));"
    "resource.setrlimit(resource.RLIMIT_CPU,(int(sys.argv[2]),int(sys.argv[2])));"
    "resource.setrlimit(resource.RLIMIT_FSIZE,(10*1024*1024,10*1024*1024));"
    "resource.setrlimit(resource.RLIMIT_NOFILE,(32,32));"
    "exec(compile(sys.argv[3],'<sandbox>','exec'),{'__name__':'__main__'})"
)


def _safe_path(filename: str) -> str:
    if not filename or "\x00" in filename:
        raise PermissionError("Invalid filename.")
    path = os.path.realpath(os.path.join(SANDBOX_DIR, filename))
    if os.path.commonpath([path, SANDBOX_DIR]) != SANDBOX_DIR:
        raise PermissionError("Path traversal attempted outside sandbox.")
    return path


def _truncate(text: str) -> str:
    if len(text) > MAX_TOOL_OUTPUT_CHARS:
        return text[:MAX_TOOL_OUTPUT_CHARS] + f"\n[... truncated {len(text) - MAX_TOOL_OUTPUT_CHARS} chars]"
    return text


@tool
def read_sandbox_file(filename: str) -> str:
    """Reads a file from the restricted sandbox workspace."""
    try:
        path = _safe_path(filename)
    except PermissionError as e:
        return f"PERMISSION_DENIED: {e}"
    if not os.path.isfile(path):
        return f"File '{filename}' not found."
    if os.path.getsize(path) > MAX_FILE_BYTES:
        return f"File '{filename}' is too large to read (limit {MAX_FILE_BYTES} bytes)."
    with open(path, encoding="utf-8", errors="replace") as f:
        return _truncate(f.read())


@tool
def write_sandbox_file(filename: str, content: str) -> str:
    """Writes content to a file inside the restricted sandbox workspace."""
    try:
        path = _safe_path(filename)
    except PermissionError as e:
        return f"PERMISSION_DENIED: {e}"
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"Content too large (limit {MAX_FILE_BYTES} bytes)."
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} characters to '{filename}'."


@tool
def execute_python_code(code: str) -> str:
    """Executes a short snippet of Python code and returns the stdout."""
    if len(code) > MAX_CODE_CHARS:
        return f"ERROR: code exceeds {MAX_CODE_CHARS} characters."
    env = {"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"}
    cmd = [
        sys.executable, "-I", "-c", _LAUNCHER,
        str(CODE_EXEC_MEMORY_MB), str(CODE_EXEC_TIMEOUT_S + 1), code,
    ]  # fmt: skip
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=CODE_EXEC_TIMEOUT_S,
            cwd=SANDBOX_DIR,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: Code execution timed out (limit: {CODE_EXEC_TIMEOUT_S}s)."
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return f"EXECUTION_ERROR: {e!s}"

    stdout, stderr = result.stdout.strip(), result.stderr.strip()
    if stderr:
        return _truncate(f"STDERR: {stderr}\nSTDOUT: {stdout}")
    return _truncate(stdout or "[Execution completed with no stdout]")


ALL_TOOLS = [read_sandbox_file, write_sandbox_file, execute_python_code]
TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}
