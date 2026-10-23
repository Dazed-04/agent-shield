#!/usr/bin/env python3
import uuid

import requests

GATEWAY_URL = "http://localhost:8000/api"
SESSION_ID = f"cli_{uuid.uuid4().hex[:8]}"


def print_banner() -> None:
    print("\033[1;36m🛡️  AGENT SHIELD CLI - Autonomous Agent Sandbox\033[0m")
    print(f"\033[90mSession ID: {SESSION_ID} | Gateway: {GATEWAY_URL}\033[0m")
    print("\033[90mCommands: 'exit' to quit | 'pending' to check review queue\033[0m\n")


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


def main() -> None:
    print_banner()
    while True:
        try:
            prompt = input("\033[1;34mUser > \033[0m").strip()
            if not prompt:
                continue
            if prompt in ("exit", "quit"):
                break
            if prompt == "pending":
                handle_pending_approvals()
                continue

            res = requests.post(
                f"{GATEWAY_URL}/chat",
                json={"prompt": prompt, "thread_id": SESSION_ID},
                timeout=30,
            )
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

            if data.get("replies"):
                for r in data["replies"]:
                    print(f"\n\033[1;37mAgent > \033[0m{r}\n")
            else:
                print(f"\n\033[1;37mAgent > \033[0m{data.get('reply', '')}\n")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except requests.RequestException as e:
            print(f"\033[31m[Gateway Network Error]: {e}\033[0m\n")
        except Exception as e:  # noqa: BLE001 - Interactive CLI catch-all
            print(f"\033[31m[Unexpected Error]: {e}\033[0m\n")


if __name__ == "__main__":
    main()
