#!/usr/bin/env python3
import argparse
import atexit
import base64
import contextlib
import glob
import mimetypes
import os
import readline
import subprocess
import sys
import uuid
from typing import Any

import requests

Console: Any = None
Markdown: Any = None
Panel: Any = None
Table: Any = None
Syntax: Any = None
console: Any = None
RICH_AVAILABLE: bool = False

try:
    from rich.console import Console as _Console
    from rich.markdown import Markdown as _Markdown
    from rich.panel import Panel as _Panel
    from rich.syntax import Syntax as _Syntax
    from rich.table import Table as _Table

    Console = _Console
    Markdown = _Markdown
    Panel = _Panel
    Table = _Table
    Syntax = _Syntax
    console = Console()
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

GATEWAY_URL = "http://localhost:8000/api"
SESSION_ID = f"cli_{uuid.uuid4().hex[:8]}"
HISTORY_FILE = os.path.expanduser("~/.agent_shield_history")
SANDBOX_DIR = os.path.abspath("./sandbox")

parser = argparse.ArgumentParser(description="Agent Shield CLI")
parser.add_argument("--role", default="Standard Users", help="Role in policies.json")
parser.add_argument(
    "--admin", action="store_true", help="Shortcut flag to launch as 'Domain Admins'"
)
parser.add_argument(
    "--key", default="", help="API Key for Production Mode authentication"
)
cli_args, _ = parser.parse_known_args()

CURRENT_ROLE = "Domain Admins" if cli_args.admin else cli_args.role
API_KEY = cli_args.key or os.getenv("AGENT_SHIELD_KEY", "")
SERVER_MODE = "development"


def preflight_auth_check() -> None:
    """Performs a secure handshake with the Gateway before launching the shell."""
    global CURRENT_ROLE, SERVER_MODE
    headers = {
        "X-Client-Interface": "cli",
        "X-API-Key": API_KEY,
    }
    try:
        res = requests.get(f"{GATEWAY_URL}/auth/verify", headers=headers, timeout=5)
        if not res.ok:
            # Cleanly catch 401s and 403s
            err_msg = (
                res.json().get("detail", res.text)
                if "application/json" in res.headers.get("Content-Type", "")
                else res.text
            )
            print(f"\n\033[1;31m[ACCESS DENIED]: {err_msg}\033[0m\n")
            sys.exit(1)

        data = res.json()
        SERVER_MODE = data.get("mode", "development")

        # If the server is in production, it dictates the role, not the client args
        if SERVER_MODE == "production":
            CURRENT_ROLE = data.get("role", CURRENT_ROLE)

    except requests.RequestException:
        print(
            f"\n\033[1;31m[Gateway Offline]: Could not connect to Agent Shield at {GATEWAY_URL}\033[0m\n"
        )
        sys.exit(1)


def setup_shell_features() -> None:
    if os.path.exists(HISTORY_FILE):
        with contextlib.suppress(Exception):
            readline.read_history_file(HISTORY_FILE)

    readline.set_history_length(1000)
    atexit.register(readline.write_history_file, HISTORY_FILE)

    readline.set_completer_delims(" \t\n")
    readline.set_completer(cli_tab_completer)
    readline.parse_and_bind("tab: complete")


def cli_tab_completer(text: str, state: int) -> str | None:
    line_buffer = readline.get_line_buffer()

    for cmd in ("/attach ", "/open ", "/view "):
        if line_buffer.startswith(cmd):
            search_path = line_buffer[len(cmd) :]
            matches = glob.glob(search_path + "*")
            matches = [m + ("/" if os.path.isdir(m) else " ") for m in matches]
            return matches[state] if state < len(matches) else None

    commands = [
        "/attach ",
        "/open ",
        "/view ",
        "/artifacts",
        "/role ",
        "/reload",
        "pending",
        "exit",
        "quit",
    ]
    matches = [c for c in commands if c.startswith(text)]
    return matches[state] if state < len(matches) else None


def print_banner() -> None:
    print("\033[1;36m🛡️  AGENT SHIELD CLI - Shell-Enabled Autonomous Agent\033[0m")

    mode_badge = (
        "\033[1;31mPROD\033[90m"
        if SERVER_MODE == "production"
        else "\033[1;32mDEV\033[90m"
    )
    print(
        f"\033[90mSession: {SESSION_ID} | Mode: {mode_badge} | Role: \033[1;33m{CURRENT_ROLE}\033[90m | Gateway: {GATEWAY_URL}\033[0m"
    )
    print(
        "\033[90mNavigation: [↑/↓] History | [TAB] Autocomplete files & commands\033[0m"
    )
    print(
        "\033[90mCommands:   /role <name> | /attach <path> | /artifacts | /view <path> | pending | exit\033[0m\n"
    )


def list_sandbox_artifacts() -> None:
    if not os.path.exists(SANDBOX_DIR):
        print("\033[90mSandbox directory is empty.\033[0m\n")
        return

    files = os.listdir(SANDBOX_DIR)
    if not files:
        print("\033[90mNo files currently stored in sandbox/.\033[0m\n")
        return

    if RICH_AVAILABLE and console is not None and Table is not None:
        table = Table(title="Generated Sandbox Artifacts", border_style="cyan")
        table.add_column("Filename", style="bold white")
        table.add_column("Size", style="green")
        table.add_column("Type", style="sky")
        for f in files:
            path = os.path.join(SANDBOX_DIR, f)
            size = f"{os.path.getsize(path)} bytes"
            mime, _ = mimetypes.guess_type(path)
            table.add_row(f, size, mime or "binary")
        console.print(table)
        print()
    else:
        print("\033[1;36mGenerated Sandbox Artifacts:\033[0m")
        for f in files:
            path = os.path.join(SANDBOX_DIR, f)
            print(f"  • {f} ({os.path.getsize(path)} bytes)")
        print()


def view_artifact(file_path: str) -> None:
    target = file_path.strip()
    if not os.path.exists(target):
        target = os.path.join(SANDBOX_DIR, target)

    if not os.path.exists(target):
        print(f"\033[31m[File Error]: Could not find '{file_path}'\033[0m\n")
        return

    mime, _ = mimetypes.guess_type(target)
    if mime and mime.startswith("image/"):
        print(
            f"\033[33m'{target}' is an image. Use '/open {target}' to launch in system viewer.\033[0m\n"
        )
        return

    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if (
            RICH_AVAILABLE
            and console is not None
            and Panel is not None
            and Syntax is not None
        ):
            lang = (
                "python"
                if target.endswith(".py")
                else "markdown"
                if target.endswith(".md")
                else "text"
            )
            console.print(
                Panel(
                    Syntax(content, lang, theme="monokai", line_numbers=True),
                    title=os.path.basename(target),
                    border_style="cyan",
                )
            )
        else:
            print(f"\n--- {target} ---\n{content}\n")
    except (OSError, UnicodeDecodeError, ValueError) as e:
        print(f"\033[31m[Read Error]: {e}\033[0m\n")


def open_in_system_viewer(file_path: str) -> None:
    target = file_path.strip()
    if not os.path.exists(target):
        target = os.path.join(SANDBOX_DIR, target)

    if not os.path.exists(target):
        print(f"\033[31m[File Error]: Could not find '{file_path}'\033[0m\n")
        return

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", target], check=False)
        else:
            startfile_fn = getattr(os, "startfile", None)
            if startfile_fn:
                startfile_fn(target)
            else:
                subprocess.run(["xdg-open", target], check=False)
        print(f"\033[32m✔ Launched '{target}' in default system viewer.\033[0m\n")
    except (OSError, subprocess.SubprocessError) as e:
        print(f"\033[31m[Open Error]: Could not launch system viewer: {e}\033[0m\n")


def load_file_attachment(file_path: str) -> dict[str, Any] | None:
    clean_path = file_path.strip()
    if not os.path.exists(clean_path):
        print(f"\033[31m[File Error]: File not found at '{clean_path}'\033[0m\n")
        return None

    filename = os.path.basename(clean_path)
    mime_type, _ = mimetypes.guess_type(clean_path)
    mime_type = mime_type or "text/plain"

    try:
        if mime_type.startswith("image/"):
            with open(clean_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                preview = f"data:{mime_type};base64,{encoded}"
                return {
                    "name": filename,
                    "type": "image",
                    "preview": preview,
                    "content": f"[Attached Image: {filename}]",
                }
        else:
            with open(clean_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                return {
                    "name": filename,
                    "type": mime_type,
                    "content": content,
                }
    except (OSError, UnicodeDecodeError, ValueError) as e:
        print(f"\033[31m[File Error]: Could not read file: {e}\033[0m\n")
        return None


def handle_pending_approvals() -> None:
    try:
        res = requests.get(f"{GATEWAY_URL}/approvals/pending", timeout=10)
        items = res.json()
    except requests.RequestException as e:
        print(f"\033[31m[Network Error]: Could not reach gateway: {e}\033[0m\n")
        return

    if not items:
        print("\033[32m✔ No actions currently pending review.\033[0m\n")
        return

    for item in items:
        tool_name = (
            item["tool_calls_attempted"][0]["name"]
            if item.get("tool_calls_attempted")
            else "Unknown"
        )
        print(
            f"\n\033[1;33m[HOLD #{item['id']}] Tool: '{tool_name}' | Risk: {item['risk_score']}/100\033[0m"
        )
        print(f'Prompt: "{item["prompt"]}"')
        print(f"Reason: {item['justification']}")

        choice = input("\nAuthorize this execution? [y/N]: ").strip().lower()
        action = "APPROVE" if choice == "y" else "REJECT"

        try:
            resolve_res = requests.post(
                f"{GATEWAY_URL}/approvals/resolve",
                json={"log_id": item["id"], "action": action},
                timeout=10,
            )
            result_data = resolve_res.json()
            print(f"\033[32m✔ {result_data.get('new_response', 'Resolved')}\033[0m\n")
        except requests.RequestException as e:
            print(f"\033[31m[Resolution Error]: {e}\033[0m\n")


def display_agent_reply(reply_text: str) -> None:
    if RICH_AVAILABLE and console is not None and Markdown is not None:
        print()
        console.print("[bold cyan]Agent >[/bold cyan]")
        console.print(Markdown(reply_text))
        print()
    else:
        print(f"\n\033[1;37mAgent > \033[0m{reply_text}\n")


def main() -> None:
    # 1. Preflight Auth Check
    preflight_auth_check()

    # 2. Start Interface
    setup_shell_features()
    print_banner()

    global CURRENT_ROLE

    while True:
        try:
            raw_input_text = input("\033[1;34mUser > \033[0m").strip()
            if not raw_input_text:
                continue
            if raw_input_text in ("exit", "quit"):
                break
            if raw_input_text == "pending":
                handle_pending_approvals()
                continue
            if raw_input_text in ("/artifacts", "/files"):
                list_sandbox_artifacts()
                continue
            if raw_input_text.startswith("/view "):
                view_artifact(raw_input_text[6:])
                continue
            if raw_input_text.startswith("/open "):
                open_in_system_viewer(raw_input_text[6:])
                continue

            # Role Switching Blocker
            if raw_input_text.startswith("/role "):
                if SERVER_MODE == "production":
                    print(
                        "\033[31m❌ Role switching is disabled in Production mode. Your role is tightly bound by your API Key.\033[0m\n"
                    )
                    continue

                target_role = raw_input_text[6:].strip()
                if target_role.lower() in ("admin", "domain admin", "domain admins"):
                    CURRENT_ROLE = "Domain Admins"
                elif target_role.lower() in ("ds", "data science"):
                    CURRENT_ROLE = "Data Science"
                elif target_role.lower() in ("standard", "user", "standard users"):
                    CURRENT_ROLE = "Standard Users"
                else:
                    CURRENT_ROLE = target_role
                print(f"\033[32m✔ Active role switched to: '{CURRENT_ROLE}'\033[0m\n")
                continue

            attachment_data = None
            prompt_text = raw_input_text

            if raw_input_text == "/reload":
                try:
                    res = requests.post(f"{GATEWAY_URL}/config/reload", timeout=5)
                    data = res.json()
                    print(
                        f"\033[32m✔ Gateway Hot-Reload Complete: {', '.join(data.get('reloaded', []))}\033[0m\n"
                    )
                except Exception as e:
                    print(f"\033[31m[Reload Error]: {e}\033[0m\n")
                continue

            if raw_input_text.startswith("/attach "):
                parts = raw_input_text.split(" ", 2)
                file_path = parts[1]
                prompt_text = (
                    parts[2]
                    if len(parts) > 2
                    else f"Process attached file: {os.path.basename(file_path)}"
                )

                attachment_data = load_file_attachment(file_path)
                if not attachment_data:
                    continue
                print(
                    f"\033[32m✔ Attached: {attachment_data['name']} ({attachment_data.get('type')})\033[0m"
                )

            payload = {
                "prompt": prompt_text,
                "thread_id": SESSION_ID,
                "role": CURRENT_ROLE,
                "attachment": attachment_data,
            }

            headers = {
                "X-Client-Interface": "cli",
                "X-API-Key": API_KEY,
            }

            res = requests.post(
                f"{GATEWAY_URL}/chat", json=payload, headers=headers, timeout=30
            )

            # Cleanly handle HTTP 401/403 Errors without crashing
            if not res.ok:
                try:
                    err_detail = res.json().get("detail", res.text)
                except Exception:  # noqa: BLE001
                    err_detail = res.text
                print(
                    f"\033[1;31m[HTTP {res.status_code} ERROR]: {err_detail}\033[0m\n"
                )
                continue

            data = res.json()

            decision = data.get("decision", "UNKNOWN")
            risk = data.get("risk_score", 0)

            if decision == "BLOCK":
                print(
                    f"\033[1;31m[BLOCK (Risk: {risk}/100)] {data.get('justification', '')}\033[0m"
                )
            elif decision == "APPROVE":
                print(
                    f"\033[1;33m[HOLD FOR REVIEW (Risk: {risk}/100)] {data.get('justification', '')}\033[0m"
                )
                print("\033[90m(Type 'pending' to inspect and authorize)\033[0m")
            else:
                print(f"\033[1;32m[{decision} (Risk: {risk}/100)]\033[0m")

            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                if tc.get("name") == "write_sandbox_file":
                    fname = tc.get("args", {}).get("filename", "")
                    print(
                        f"\033[36m📁 Artifact Created: sandbox/{fname} (Type '/view {fname}' or '/open {fname}')\033[0m"
                    )

            if data.get("replies"):
                for r in data["replies"]:
                    display_agent_reply(r)
            else:
                display_agent_reply(data.get("reply", ""))

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except requests.RequestException as e:
            print(f"\033[31m[Gateway Network Error]: {e}\033[0m\n")
        except (RuntimeError, ValueError) as e:
            print(f"\033[31m[Runtime Error]: {e}\033[0m\n")


if __name__ == "__main__":
    main()
