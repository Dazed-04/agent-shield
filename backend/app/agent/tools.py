import os
import subprocess

from langchain_core.tools import tool

SANDBOX_DIR = os.path.abspath("./sandbox")
os.makedirs(SANDBOX_DIR, exist_ok=True)


@tool
def read_sandbox_file(filename: str) -> str:
    """Reads a file from the restricted sandbox workspace."""
    safe_path = os.path.abspath(os.path.join(SANDBOX_DIR, filename))
    if not safe_path.startswith(SANDBOX_DIR):
        return "PERMISSION_DENIED: Path traversal attempted outside sandbox."
    if not os.path.exists(safe_path):
        return f"File '{filename}' not found."
    with open(safe_path, "r", encoding="utf-8") as f:
        return f.read()


@tool
def write_sandbox_file(filename: str, content: str) -> str:
    """Writes content to a file inside the restricted sandbox workspace."""
    safe_path = os.path.abspath(os.path.join(SANDBOX_DIR, filename))
    if not safe_path.startswith(SANDBOX_DIR):
        return "PERMISSION_DENIED: Path traversal attempted outside sandbox."
    with open(safe_path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Successfully wrote {len(content)} characters to '{filename}'."


@tool
def execute_python_code(code: str) -> str:
    """Executes a short snippet of Python code and returns the stdout."""
    try:
        result = subprocess.run(
            ["python", "-c", code],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if stderr:
            return f"STDERR: {stderr}\nSTDOUT: {stdout}"
        return stdout or "[Execution completed with no stdout]"
    except subprocess.TimeoutExpired:
        return "ERROR: Code execution timed out (limit: 5s)."
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return f"EXECUTION_ERROR: {e!s}"


ALL_TOOLS = [read_sandbox_file, write_sandbox_file, execute_python_code]
TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}
