import json

import pytest

from app.detectors.tool_monitor import ToolMonitor, analyse_python

REG = {"execute_python_code", "read_sandbox_file", "write_sandbox_file"}


@pytest.fixture
def tm():
    return ToolMonitor()


def act(tm, name, args, role, thread="t"):
    return tm.inspect(name, args, thread, role, REG)["action"]


@pytest.mark.parametrize(
    "code",
    [
        "import os; os.system('id')",
        "__import__('o'+'s').system('id')",
        "exec(bytes.fromhex('6f732e73797374656d').decode())",
        "import socket; socket.socket()",
        "import subprocess; subprocess.run(['ls'])",
        "print(().__class__.__bases__[0].__subclasses__())",
        "import os; print(os.environ)",
        "from os import system",
        "import pathlib; pathlib.Path('/etc/shadow').read_text()",
        "eval('1+1')",
    ],
)
def test_dangerous_code_blocked_even_for_admins(tm, code):
    assert act(tm, "execute_python_code", {"code": code}, "Domain Admins") == "BLOCK"


def test_file_access_from_code_needs_approval_and_plain_code_runs(tm):
    assert act(tm, "execute_python_code", {"code": "import os; print(os.listdir('.'))"}, "Domain Admins") == "APPROVE"
    assert act(tm, "execute_python_code", {"code": "print(sum(range(10)))"}, "Domain Admins") == "ALLOW"


def test_fail_closed_behaviour(tm):
    assert act(tm, "read_sandbox_file", {"filename": "a.txt"}, "No Such Role") == "BLOCK"
    assert tm.inspect("send_email", {"to": "x"}, "t", "Domain Admins", REG)["action"] == "BLOCK"
    assert act(tm, "execute_python_code", {"code": "print(1)"}, "Standard Users") == "BLOCK"


def test_policy_values_are_honoured(tm):
    assert act(tm, "write_sandbox_file", {"filename": "a.txt", "content": "x"}, "Data Science") == "WARN"
    assert act(tm, "execute_python_code", {"code": "print(1)"}, "Data Science") == "APPROVE"


def test_extension_and_path_rules(tm):
    assert act(tm, "write_sandbox_file", {"filename": "run.py", "content": "x"}, "Domain Admins") == "BLOCK"
    assert act(tm, "read_sandbox_file", {"filename": "../../etc/hosts"}, "Standard Users") == "BLOCK"
    assert act(tm, "read_sandbox_file", {"filename": "/etc/hosts"}, "Standard Users") == "BLOCK"
    assert act(tm, "read_sandbox_file", {"filename": ".env"}, "Standard Users") == "BLOCK"


def test_innocent_words_are_not_hard_blocked(tm):
    args = {"filename": "report.txt", "content": "Remove the delete button; passwd policy review"}
    assert act(tm, "write_sandbox_file", args, "Domain Admins") == "ALLOW"


def test_lease_downgrades_approve_but_never_overrides_deny(tm):
    tm.grant_session_lease("t", "execute_python_code", max_uses=1, duration_seconds=60)
    r = tm.inspect("execute_python_code", {"code": "print(1)"}, "t", "Data Science", REG)
    assert r["action"] == "ALLOW" and r["uses_lease"]
    tm.consume_lease("t", "execute_python_code")
    assert act(tm, "execute_python_code", {"code": "print(1)"}, "Data Science") == "APPROVE"  # used up
    tm.grant_session_lease("t", "execute_python_code", 5, 60)
    assert act(tm, "execute_python_code", {"code": "print(1)"}, "Standard Users") == "BLOCK"
    assert act(tm, "execute_python_code", {"code": "import os; os.system('x')"}, "Data Science") == "BLOCK"


def test_session_quota_enforced(tm):
    # Domain Admins: max_invocations_per_session = 50 for execute_python_code
    for _ in range(50):
        tm.record_invocation("q", "execute_python_code")
    assert act(tm, "execute_python_code", {"code": "print(1)"}, "Domain Admins", thread="q") == "BLOCK"
    assert act(tm, "execute_python_code", {"code": "print(1)"}, "Domain Admins", thread="other") == "ALLOW"


def test_broken_policy_file_keeps_previous_policy(tmp_path):
    p = tmp_path / "policies.json"
    p.write_text(json.dumps({"roles": {"R": {"default_policy": "DENY", "tools": {"read_sandbox_file": {"policy": "ALLOW"}}}}}))
    tm = ToolMonitor(str(p))
    assert act(tm, "read_sandbox_file", {"filename": "a.txt"}, "R") == "ALLOW"
    p.write_text("{ not json")
    import os

    os.utime(p, (os.path.getmtime(p) + 5, os.path.getmtime(p) + 5))
    assert act(tm, "read_sandbox_file", {"filename": "a.txt"}, "R") == "ALLOW"  # did not fail open or crash


def test_ast_analysis_ignores_unparseable_code():
    assert analyse_python("this is not python (") == ([], [])
