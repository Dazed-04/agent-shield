import os

from app.agent.tools import SANDBOX_DIR, execute_python_code, read_sandbox_file, write_sandbox_file


# ---- the tools themselves
def test_sandbox_blocks_traversal_and_symlink_escape(tmp_path):
    assert "PERMISSION_DENIED" in read_sandbox_file.invoke({"filename": "../../etc/passwd"})
    assert "PERMISSION_DENIED" in write_sandbox_file.invoke({"filename": "../escape.txt", "content": "x"})
    link = os.path.join(SANDBOX_DIR, "link")
    if not os.path.lexists(link):
        os.symlink("/etc", link)
    assert "PERMISSION_DENIED" in read_sandbox_file.invoke({"filename": "link/hostname"})
    assert "PERMISSION_DENIED" in read_sandbox_file.invoke({"filename": SANDBOX_DIR + "_evil/x"}) or "not found" in read_sandbox_file.invoke({"filename": SANDBOX_DIR + "_evil/x"})


def test_write_then_read_roundtrip():
    assert "Successfully" in write_sandbox_file.invoke({"filename": "sub/note.txt", "content": "hello"})
    assert read_sandbox_file.invoke({"filename": "sub/note.txt"}) == "hello"


def test_python_runs_without_inheriting_secrets(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_should_never_be_visible")
    out = execute_python_code.invoke({"code": "import os\nprint(os.environ.get('GROQ_API_KEY'), len(os.environ))"})
    assert "gsk_should" not in out and out.startswith("None")


def test_python_timeout_and_output_cap():
    assert "timed out" in execute_python_code.invoke({"code": "while True: pass"})
    big = execute_python_code.invoke({"code": "print('x'*100000)"})
    assert "truncated" in big and len(big) < 25000
