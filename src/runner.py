"""wazoobench runner: single-task evaluator for one DeepSeek agent run.

Given a task spec, an arm ('memory' | 'control'), a model handle and a
working directory, it:

1. Pre-flights the DeepSeek account balance (aborts below $1.00 remaining).
2. Seeds the memory folder into the workdir (the deepseek_driver contract:
   MEMORY.md at the top of the folder, read into the system prompt).
3. Runs the deepseek_driver agent loop IN-PROCESS (bash tool, completion
   marker, max-turns, plus a per-task token ceiling; a ceiling breach aborts
   the task with status='budget-aborted').
4. Captures the final assistant message, every bash tool output, turn count,
   token usage and elapsed time.
5. Runs the spec's verifier (see verifiers.py).
6. Writes the result JSON.

The runner performs paid API calls ONLY when executed; building and testing
it costs nothing (verifiers and naive baselines run offline).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

# The driver loop to reuse, verbatim.
DRIVER_PATH = Path(
    os.environ.get(
        "WAZOO_DRIVER_PATH",
        str(Path.home() / "workspace/wazoo-frontiermemory/adapter/deepseek_driver.py"),
    )
)
if str(DRIVER_PATH.parent) not in sys.path:
    sys.path.insert(0, str(DRIVER_PATH.parent))

import deepseek_driver as driver  # noqa: E402

import verifiers  # noqa: E402

DEFAULT_TOKEN_CEILING = 400_000
MIN_BALANCE_USD = 1.00
# DeepSeek accounts report balances in the currency they were topped up in.
# The hard floor is USD; for CNY accounts we keep a conservative conversion
# so the "$1.00" floor still protects the account (documented approximation,
# not a market quote).
CNY_PER_USD_FLOOR = 7.0
DEFAULT_COMPLETION_MARKER = driver.DEFAULT_COMPLETION_MARKER


class BudgetAbort(Exception):
    pass


def balance_remaining_usd(api_key: str, api_base: str) -> tuple[float | None, str]:
    """GET /user/balance; returns (remaining in USD-equivalent, detail)."""
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/user/balance",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode())
    infos = data.get("balance_infos") or []
    detail = json.dumps(data)
    if not infos:
        return None, detail
    total = sum(float(info.get("total_balance") or 0) for info in infos)
    currencies = {info.get("currency", "?") for info in infos}
    if currencies == {"CNY"}:
        return total / CNY_PER_USD_FLOOR, f"remaining CNY {total} (>= / {CNY_PER_USD_FLOOR})"
    if currencies == {"USD"} or len(currencies) == 1:
        return total, f"remaining {total} {next(iter(currencies))}"
    return None, detail


def seed_memory(memory_source: Path | None, workdir: Path) -> bool:
    """Copy the memory folder into <workdir>/memory/ (driver seeding contract).

    Returns whether a usable memory folder was seeded.
    """
    target = workdir / "memory"
    if target.exists():
        shutil.rmtree(target)
    if memory_source is None or not memory_source.is_dir():
        return False
    shutil.copytree(memory_source, target)
    return driver.entry_index(target)


def run_agent(
    spec: dict,
    workdir: Path,
    model: str,
    api_key: str,
    api_base: str,
    memory_dir: Path | None,
    max_turns: int = 30,
    token_ceiling: int = DEFAULT_TOKEN_CEILING,
    completion_marker: str = DEFAULT_COMPLETION_MARKER,
) -> dict:
    """The deepseek_driver loop, in-process, with a token ceiling."""
    instruction = spec["prompt"]
    system_prompt = driver.SYSTEM_PROMPT.format(
        memory=str(memory_dir) if memory_dir else "(none)", entry=driver.ENTRY_FILE
    )
    if memory_dir:
        memory_note = driver.MEMORY_PROMPT.format(memory=memory_dir, entry=memory_dir / driver.ENTRY_FILE)
        entry_text = (memory_dir / driver.ENTRY_FILE).read_text()
    else:
        memory_note = driver.NO_MEMORY_PROMPT
        entry_text = ""
    system_prompt = system_prompt + "\n\n" + memory_note
    if entry_text:
        system_prompt += f"\n\n{driver.ENTRY_FILE} content:\n\n{entry_text}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    bash_outputs: list[dict] = []
    steps: list[dict] = []
    final = ""
    reason = "max-turns"
    status = "completed"

    for _turn in range(1, max_turns + 1):
        payload = {"model": model, "messages": messages, "tools": driver.TOOLS}
        response = driver.chat(api_base, api_key, model, payload)
        counts = response.get("usage") or {}
        usage["input_tokens"] += int(counts.get("prompt_tokens") or 0)
        usage["cached_input_tokens"] += int(
            (counts.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        )
        usage["output_tokens"] += int(counts.get("completion_tokens") or 0)
        if usage["input_tokens"] + usage["output_tokens"] > token_ceiling:
            status = "budget-aborted"
            reason = "token-ceiling"
            break

        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls = driver.assistant_tool_calls(message)
        if not calls:
            final = message.get("content") or ""
            steps.append({"source": "agent", "message": final})
            reason = "final-answer"
            break
        steps.append(
            {
                "source": "agent",
                "message": message.get("content") or "",
                "tool_calls": [
                    {"tool_call_id": c["id"], "function_name": c["name"], "arguments": c["arguments"]}
                    for c in calls
                ],
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                    }
                    for c in calls
                ],
            }
        )
        for call in calls:
            command = str(call["arguments"].get("command") or "")
            result = driver.run_bash(command, str(workdir))
            bash_outputs.append(
                {"command": command, "exit_code": result["exit_code"], "output": result["output"]}
            )
            steps.append(
                {
                    "source": "tool",
                    "name": "bash",
                    "observation": {
                        "results": [
                            {
                                "source_call_id": call["id"],
                                "content": result["output"],
                                "extra": {
                                    "is_error": result["exit_code"] != 0,
                                    "exit_code": result["exit_code"],
                                },
                            }
                        ]
                    },
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": f"exit_code={result['exit_code']}\n{result['output']}",
                }
            )
            if completion_marker and driver.find_completion_marker(result["output"], completion_marker):
                final = result["output"]
                reason = "completion-marker"
                break
        if reason == "completion-marker":
            break

    return {
        "status": status,
        "stop_reason": reason,
        "final_message": final,
        "bash_outputs": bash_outputs,
        "steps": steps,
        "turns": len(steps),
        "tokens": usage,
        "memory_seeded": bool(memory_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="path to a task spec JSON")
    parser.add_argument("--arm", choices=["memory", "control"], required=True)
    parser.add_argument("--memory", default=None, help="memory folder (None for the control arm)")
    parser.add_argument("--workdir", required=True, help="working directory the agent operates in")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--out", required=True, help="result JSON path")
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--token-ceiling", type=int, default=DEFAULT_TOKEN_CEILING)
    parser.add_argument("--api-base", default=driver.DEFAULT_API_BASE)
    parser.add_argument("--env", default="DEEPSEEK_API_KEY", help="env var holding the API key")
    args = parser.parse_args(argv)

    api_key = os.environ.get(args.env)
    if not api_key:
        print(f"runner: {args.env} is required", file=sys.stderr)
        return 2
    if args.arm == "memory" and not args.memory:
        print("runner: the memory arm requires --memory", file=sys.stderr)
        return 2

    spec = json.loads(Path(args.task).read_text())
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    # (a) pre-flight balance check.
    try:
        remaining, detail = balance_remaining_usd(api_key, args.api_base)
    except Exception as exc:  # noqa: BLE001 - never run on an unknown balance
        print(f"runner: balance check failed ({exc}); aborting before any paid call", file=sys.stderr)
        return 3
    if remaining is None or remaining < MIN_BALANCE_USD:
        print(f"runner: balance below the ${MIN_BALANCE_USD} floor ({detail}); aborting", file=sys.stderr)
        return 3

    # (b) seed memory by copying the folder into the workdir.
    memory_dir = None
    memory_used = False
    if args.arm == "memory":
        memory_used = seed_memory(Path(args.memory), workdir)
        memory_dir = workdir / "memory"
        if not memory_used:
            print(
                "runner: memory folder has no usable MEMORY.md entry point; aborting",
                file=sys.stderr,
            )
            return 2

    # (c) run the agent loop in-process.
    started = time.monotonic()
    try:
        run = run_agent(
            spec,
            workdir,
            args.model,
            api_key,
            args.api_base,
            memory_dir,
            max_turns=args.max_turns,
            token_ceiling=args.token_ceiling,
        )
    except BudgetAbort:
        run = {"status": "budget-aborted"}
    except Exception as exc:  # noqa: BLE001 - surface, don't fake
        run = {"status": "agent-error", "final_message": "", "bash_outputs": [], "steps": [],
               "turns": 0, "tokens": {}, "memory_seeded": memory_used, "error": str(exc)}
    run["seconds"] = round(time.monotonic() - started, 1)

    # (e) verifier.
    checks = verifiers.run_checks(spec, workdir, run["final_message"])

    # (f) result JSON. Container-required checks are recorded as skipped and
    # don't gate `passed` — the run is graded only on what actually graded.
    graded = [check for check in checks if not check.get("skipped")]
    result = {
        "taskId": spec["trajId"],
        "arm": args.arm,
        "passed": bool(graded) and all(check["passed"] for check in graded),
        "skippedChecks": [check["name"] for check in checks if check.get("skipped")],
        "checks": checks,
        "turns": run.get("turns", 0),
        "tokens": run.get("tokens", {}),
        "seconds": run["seconds"],
        "memoryUsed": memory_used,
        "status": run.get("status", "completed"),
        "stop_reason": run.get("stop_reason"),
        "final_message": run.get("final_message", ""),
        "bash_outputs": run.get("bash_outputs", []),
        "model": args.model,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    passed = sum(check["passed"] for check in checks)
    print(
        f"runner: {spec['trajId']} arm={args.arm} status={result['status']} "
        f"checks {passed}/{len(checks)} tokens={run.get('tokens', {}).get('output_tokens', '?')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
