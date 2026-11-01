"""wazoobench verifiers: grade a captured run against a task spec's checks.

Every check result records HOW it was graded (gradedBy) so no check result
is ever taken on faith:

- "agent-message"        string/regex presence in the final assistant message
- "contract-command"     a pinned check command executed in the workdir
                         (exit code decides; the asset itself defines the
                         per-check pass/fail)
- "workdir-artifact"     file states inside the workdir (existence/content)
- "container-required"   skipped: this check cannot run without the task
                         container; recorded with passed=False and
                         skipped=True — never faked
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "verifier-assets"


def _run_command(command: str, workdir: Path, timeout: int = 1800) -> dict:
    import os

    env = dict(os.environ)
    # keep the sandbox toolchain visible even under `bash -l` profile resets
    for extra in ("/usr/local/go/bin", str(Path.home() / ".bun/bin")):
        if Path(extra).is_dir() and extra not in env.get("PATH", ""):
            env["PATH"] = f"{extra}:{env.get('PATH', '')}"
    proc = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, cwd=str(workdir), timeout=timeout, env=env
    )
    return {"exit_code": proc.returncode, "output": (proc.stdout + proc.stderr)[-20_000:]}


def _contract_command(check: dict, spec: dict, workdir: Path) -> list[dict]:
    """Run a spec's pinned contract command in the workdir.

    The command's asset lives in src/verifier-assets/<taskId-dir>/; for
    check scripts that emit JSON-per-check, we parse it; otherwise a single
    result keyed by the check name is produced from the exit code.
    """
    task_dir = ASSETS / spec["trajId"]
    command = check.get("command") or ""
    # Materialize the asset the command expects, if the spec names one.
    asset = check.get("asset")
    if asset:
        src = None
        candidates = [
            ASSETS / asset,
            task_dir / asset,
            ASSETS / f"{spec['trajId']}-{asset}",
            *ASSETS.glob(f"{spec['trajId']}-*/{asset}"),
        ]
        for candidate in candidates:
            if candidate.exists():
                src = candidate
                break
        if src is None:
            return [{"name": check["name"], "passed": False,
                     "detail": f"verifier asset not found: {asset}", "gradedBy": "contract-command"}]
        if src.is_dir():
            if check.get("assetMode") == "root":
                # contract files must sit in the workdir root (Go module layout)
                for item in src.iterdir():
                    if not (workdir / item.name).exists():
                        shutil.copy(item, workdir / item.name)
            elif not (workdir / src.name).exists():
                shutil.copytree(src, workdir / src.name)
        elif not (workdir / src.name).exists():
            shutil.copy(src, workdir / src.name)
    run = _run_command(command, workdir)
    # Contract scripts may print "FAIL <name>: detail" lines per sub-check.
    results = []
    for line in run["output"].splitlines():
        if line.startswith("PASS ") or line.startswith("FAIL "):
            name, _, detail = line[5:].partition(":")
            results.append(
                {
                    "name": name.strip(),
                    "passed": line.startswith("PASS "),
                    "detail": detail.strip()[:2000],
                    "gradedBy": "contract-command",
                }
            )
    if not results:
        results = [
            {
                "name": check["name"],
                "passed": run["exit_code"] == 0,
                "detail": run["output"][-2000:],
                "gradedBy": "contract-command",
            }
        ]
    return results


def _message_check(check: dict, final_message: str) -> dict:
    """Grade a chat-message check against the final assistant message.

    A check whose spec embeds a regex (r"...") is graded by that regex;
    otherwise the spec's literal expectations are graded as substrings when
    the spec names them in quotes; anything ambiguous is reported as
    not-gradeable (passed=False, gradedBy='ungradeable-spec') — never guessed.
    """
    spec_text = check.get("spec", "")
    match = re.search(r"r\"([^\"]+)\"", spec_text) or re.search(r"r'([^']+)'", spec_text)
    if match:
        pattern = match.group(1)
        try:
            hit = re.search(pattern, final_message, re.MULTILINE) is not None
        except re.error as exc:
            return {"name": check["name"], "passed": False, "detail": f"bad regex: {exc}",
                    "gradedBy": "agent-message"}
        return {
            "name": check["name"],
            "passed": hit,
            "detail": f"regex {pattern!r} {'found' if hit else 'absent'} in final message",
            "gradedBy": "agent-message",
        }
    quoted = re.findall(r'"([^"\\]{6,})"', spec_text)
    if quoted:
        misses = [q for q in quoted if q not in final_message]
        if misses:
            return {"name": check["name"], "passed": False,
                    "detail": f"missing strings in final message: {misses[:3]}",
                    "gradedBy": "agent-message"}
        return {"name": check["name"], "passed": True,
                "detail": "all quoted strings present in final message",
                "gradedBy": "agent-message"}
    return {"name": check["name"], "passed": False,
            "detail": "check spec has no machine-gradeable regex or quoted string; "
                      "needs a container or an authored contract asset",
            "gradedBy": "ungradeable-spec"}


def _artifact_check(check: dict, workdir: Path) -> dict:
    """Grade a file-artifact check from the workdir's current file states."""
    spec_text = check.get("spec", "")
    mentioned = re.findall(r"[A-Za-z0-9_./\-]+\.(?:py|go|md|json|txt|yaml|toml)", spec_text)
    missing = [name for name in mentioned if not (workdir / name).exists()]
    if mentioned and not missing:
        return {"name": check["name"], "passed": True,
                "detail": f"artifacts present: {sorted(set(mentioned))[:5]}",
                "gradedBy": "workdir-artifact"}
    if mentioned:
        return {"name": check["name"], "passed": False,
                "detail": f"missing artifacts in workdir: {missing[:5]}",
                "gradedBy": "workdir-artifact"}
    return {"name": check["name"], "passed": False,
            "detail": "no file artifact named in the check spec",
            "gradedBy": "ungradeable-spec"}


def run_checks(spec: dict, workdir: Path, final_message: str) -> list[dict]:
    """Run every verifier check in the spec; skip container-only ones honestly."""
    results: list[dict] = []
    verifier = spec.get("verifier") or {}
    seen_commands: dict[str, list[dict]] = {}
    for check in verifier.get("checks", []):
        locally_verified = check.get("locallyVerified") is True
        command = check.get("command")
        if command and locally_verified:
            if command in seen_commands:
                # One contract script grades many named checks; run it once.
                prior = seen_commands[command]
                own = [r for r in prior if r["name"] == check["name"]]
                results.extend(own)
            else:
                fresh = _contract_command(check, spec, workdir)
                seen_commands[command] = fresh
                results.extend(fresh)
            continue
        if locally_verified is False and "container-required" in (check.get("localVerification") or ""):
            results.append(
                {
                    "name": check["name"],
                    "passed": False,
                    "skipped": True,
                    "detail": "container-required; not graded locally",
                    "gradedBy": "container-required",
                }
            )
            continue
        vtype = verifier.get("type", "")
        if vtype in ("chat-message-check", "python-asserts") and not command:
            results.append(_message_check(check, final_message))
        elif vtype == "workbook-cell-check":
            results.append(
                {
                    "name": check["name"],
                    "passed": False,
                    "skipped": True,
                    "detail": "workbook container required",
                    "gradedBy": "container-required",
                }
            )
        else:
            results.append(_artifact_check(check, workdir))
    # Collapse duplicates from shared contract commands: the first run of a
    # command emits every named sub-check; each repeat emits its own line.
    final_results: list[dict] = []
    seen_keys: set[tuple] = set()
    for result in results:
        key = (result["gradedBy"], result["name"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        final_results.append(result)
    return final_results
