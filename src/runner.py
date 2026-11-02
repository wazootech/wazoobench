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
import re
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


# --- memory delivery modes (iteration 3) ------------------------------------
#
# iter2 finding: the memory arm read MEMORY.md but opened ZERO skill files
# (the pointers were never followed) and the control beat the memory arm
# 3/3 vs 2/3 at the 800k ceiling. The memory is present but inert — a
# delivery-interface problem. Two candidate fixes, selected by --memory-mode:
#
#   folder (default) = iter2 behavior: full MEMORY.md dumped into the prompt
#   family           = librarian fix: seed only the task family's sections
#                      plus their referenced skill files
#   inline           = presenter fix: no full-index dump; the family's rules
#                      go straight into the system prompt as imperatives
#
# Both fixes reuse the same spec-family -> section mapping.

FAMILY_TO_SECTION = {
    "word2vec-pipeline": "Word2Vec pipeline builder",
    "dapt-pcap-network-stats": "DAPT pcap network stats",
    "algotune-optimization": "Solver speedup optimization",
    "agentic-mcp-sheets": "Agentic MCP workplace (world server)",
    # READY-set tasks whose spec family is "unassigned" are code-issue
    # solving, which the memory's repo-work family covers.
    "unassigned": "Repo work conventions",
}
GENERAL_SECTION = "General working rules"


def resolve_family_id(spec: dict) -> str:
    return spec.get("family") or "unassigned"


def _split_sections(md_text: str) -> dict[str, str]:
    """Split MEMORY.md on '## ' headers into {title: body} (header excluded)."""
    sections: dict[str, str] = {}
    title: str | None = None
    lines: list[str] = []
    for line in md_text.splitlines():
        if line.startswith("## "):
            if title is not None:
                sections[title] = "\n".join(lines).strip()
            title = line[3:].strip()
            lines = []
        elif title is not None:
            lines.append(line)
    if title is not None:
        sections[title] = "\n".join(lines).strip()
    return sections


def family_sections(md_text: str, family_id: str) -> list[tuple[str, str]]:
    """The sections that apply to this task family, in file order.

    Always ends with the general rules section (when present).
    """
    sections = _split_sections(md_text)
    wanted = FAMILY_TO_SECTION.get(family_id)
    picked: list[tuple[str, str]] = []
    for title, text in sections.items():
        if title == GENERAL_SECTION:
            continue
        if wanted is not None and title == wanted:
            picked.append((title, text))
    if GENERAL_SECTION in sections:
        picked.append((GENERAL_SECTION, sections[GENERAL_SECTION]))
    return picked


def prune_memory_folder(memory_root: Path, family_id: str) -> dict:
    """Family mode: rewrite memory/MEMORY.md to the family's sections and
    drop skill files they don't reference. Mutates the seeded copy only.
    """
    entry = memory_root / driver.ENTRY_FILE
    md_text = entry.read_text()
    picked = family_sections(md_text, family_id)
    # keep the original preamble (everything before the first '## ')
    preamble = md_text.split("\n## ", 1)[0].strip()
    kept_titles = {t for t, _ in picked}
    retained = [preamble]
    for title, text in picked:
        retained.append(f"## {title}\n\n{text}")
    new_md = "\n\n".join(retained) + "\n"
    entry.write_text(new_md)
    # prune skills/ to files the retained sections reference
    skills_dir = memory_root / "skills"
    kept_files = set()
    for _title, text in picked:
        for match in re.findall(r"skills/[A-Za-z0-9._/-]+\.md", text):
            kept_files.add(match.split("/", 1)[1])
    removed = 0
    total = 0
    if skills_dir.is_dir():
        for path in sorted(skills_dir.rglob("*.md")):
            total += 1
            if path.name not in kept_files:
                path.unlink()
                removed += 1
    return {
        "full_entry_chars": len(md_text),
        "retained_chars": len(new_md),
        "sections_kept": sorted(kept_titles),
        "skills_kept": total - removed,
        "skills_total": total,
    }


def inline_presenter_block(memory_root: Path, family_id: str) -> str:
    """Inline mode: the family's sections injected directly into the system
    prompt as imperatives. Provenance stays on disk; nothing is dumped twice.
    """
    md_text = (memory_root / driver.ENTRY_FILE).read_text()
    picked = family_sections(md_text, family_id)
    if not picked:
        return ""
    lines = [
        "The following memory rules apply to THIS task. Treat them as standing",
        "instructions: follow them unless the task explicitly overrides them.",
        f"Provenance for each rule lives under {memory_root}/skills/.",
    ]
    for title, text in picked:
        lines += ["", f"## {title}", "", text]
    return "\n".join(lines)


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
    memory_mode: str = "pointer",
    memory_stats: dict | None = None,
    memory_source: Path | None = None,
) -> dict:
    """The deepseek_driver loop, in-process, with a token ceiling."""
    instruction = spec["prompt"]
    presenter = ""
    if memory_mode == "inline":
        # presenter model: rules injected directly; no folder exists, so no
        # pointer in the prompt (pointing at "(none)" would contradict the
        # injected rules).
        if memory_source is not None:
            presenter = inline_presenter_block(memory_source, resolve_family_id(spec))
        system_prompt = driver.SYSTEM_PROMPT.format(memory="(injected below)", entry="(injected below)")
        system_prompt += "\n\n=== MEMORY RULES — distilled from similar past tasks; follow every rule that applies ===\n"
        system_prompt += (presenter or "") + "\n=== END MEMORY RULES ==="
        memory_note = ""
        entry_text = ""
    else:
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
    if memory_mode != "inline" and presenter:
        system_prompt += f"\n\n{presenter}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": instruction},
    ]
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
    bash_outputs: list[dict] = []
    memory_use: list[dict] = []  # evidence the agent USED the memory, not just read it
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
            # memory-USE evidence: commands touching a skill file (the index's
            # pointers), not just the entry file
            if "memory/skills/" in command or ("skills/" in command and "memory" in command):
                memory_use.append({"kind": "skill-open", "command": command[:200]})
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
            # The completion marker means the AGENT chose to finish — the
            # marker must appear in the agent's own tool-call COMMAND (echo
            # COMPLETE_TASK...), never in the COMMAND'S OUTPUT. Tool output
            # can contain the marker string incidentally: our first eval run
            # had the agent `cat memory/MEMORY.md`, whose user-preferences
            # section quotes the marker verbatim, and the run ended after 2
            # turns as "completed" without the task being attempted.
            if completion_marker and driver.find_completion_marker(command, completion_marker):
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
        "memory_mode": memory_mode,
        "memory_stats": memory_stats or {},
        "memory_use_events": memory_use,
        "transcript": messages,
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
    parser.add_argument(
        "--memory-mode",
        choices=["folder", "family", "inline"],
        default="folder",
        help="memory delivery interface (iter3): folder = iter2 full-index "
        "dump; family = seed only the task family's sections; inline = "
        "presenter model, rules injected straight into the system prompt",
    )
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
        memory_source = Path(args.memory) if args.memory else None
        if args.memory_mode == "inline":
            # memory lives in the prompt; no folder on disk
            if memory_source is None or not (memory_source / "MEMORY.md").is_file():
                print("runner: inline mode requires a memory folder to inject from", file=sys.stderr)
                return 2
            memory_used = True
        elif args.memory_mode == "family":
            # existing flow: seed the full folder, then prune to the family
            memory_used = seed_memory(memory_source, workdir)
            memory_dir = workdir / "memory"
            if not memory_used:
                print(
                    "runner: memory folder has no usable MEMORY.md entry point; aborting",
                    file=sys.stderr,
                )
                return 2
        else:
            # pointer mode: seed the full folder. The CONTROL arm has no
            # memory at all — skip seeding (seed_memory(None) returns False
            # and would abort the run).
            if memory_source is not None:
                memory_used = seed_memory(memory_source, workdir)
                memory_dir = workdir / "memory"
                if not memory_used:
                    print(
                        "runner: memory folder has no usable MEMORY.md entry point; aborting",
                        file=sys.stderr,
                    )
                    return 2
        memory_stats: dict = {}
        if args.arm == "memory" and args.memory_mode == "family":
            memory_stats = prune_memory_folder(memory_dir, resolve_family_id(spec))
            print(
                "runner: family mode pruned memory "
                f"({memory_stats['retained_chars']}/{memory_stats['full_entry_chars']} chars, "
                f"skills {memory_stats['skills_kept']}/{memory_stats['skills_total']})",
                flush=True,
            )
        elif args.arm == "memory" and args.memory_mode == "inline":
            # inline mode never seeded a folder; the presenter reads the
            # SOURCE memory (memory_dir is None here by design).
            presenter = inline_presenter_block(memory_source, resolve_family_id(spec))
            if not presenter:
                print(
                    "runner: inline mode matched no memory sections; aborting "
                    "(a presenter run with an empty block is just the control arm)",
                    file=sys.stderr,
                )
                return 2
            memory_stats = {
                "full_entry_chars": len((memory_source / driver.ENTRY_FILE).read_text()),
                "retained_chars": len(presenter),
                "sections_kept": [t for t, _ in family_sections(
                    (memory_dir / driver.ENTRY_FILE).read_text(), resolve_family_id(spec)
                )],
            }

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
            memory_mode=args.memory_mode,
            memory_stats=memory_stats,
            memory_source=Path(args.memory) if args.memory else None,
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
