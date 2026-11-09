"""wazoobench eval: run the READY tasks in both arms and write a report.

READY = the spec's verifier can grade without the missing task container
(at least one check with locallyVerified=true + a runnable command) AND the
task's local workdir prep is defined. Container-only checks are recorded as
skipped (passed=False, gradedBy='container-required') — never faked.

Usage (the one command that triggers the first PAID eval):

    bun run eval
    # which is: python3 src/eval.py [--model deepseek-v4-flash] [--arms 2]

For a dry check of what would run, without any API spend:

    python3 src/eval.py --list
"""

from __future__ import annotations

import argparse
import json
import re
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
RUNS = ROOT / "docs" / "runs"
DRIVER_PATH = Path(
    os.environ.get(
        "WAZOO_DRIVER_PATH",
        str(Path.home() / "workspace/wazoo-frontiermemory/adapter/deepseek_driver.py"),
    )
)

WORKER = Path(__file__).resolve().parent / "runner.py"



SECRET_ENV_NAMES = {
    "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GH_TOKEN", "GITHUB_TOKEN", "WORLDS_PLATFORM_TOKEN", "WORLDS_TOKEN",
    "HUGGINGFACE_TOKEN", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET",
    "ANYONE_SANDBOX_TOKEN", "SKYDIVE_SANDBOX_TOKEN", "GT_API_KEY",
    "OPENHACK_API_KEY", "ASSEMBLYAI_API_KEY",
}


def redact_secrets(text: str) -> str:
    """Scrub secret material out of persisted run outputs.

    The eval agent sometimes runs probe commands (env, printenv, cat) whose
    output lands verbatim in results.json; on 2026-11-06 that captured a
    live DeepSeek key into a public commit. Match known secret env names
    AND the common key shapes, so an unknown-but-shaped secret still gets
    caught.
    """
    if not isinstance(text, str):
        return text
    for name in SECRET_ENV_NAMES:
        text = text.replace(f"{name}=", f"{name}=[REDACTED]")
    # Bearer tokens, sk- keys, and JWTs regardless of variable name
    text = re.sub(r"sk-[A-Za-z0-9]{16,}", "sk-[REDACTED]", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9_\-.]{16,}", "Bearer [REDACTED]", text)
    text = re.sub(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
                  "[REDACTED-JWT]", text)
    return text


def redact_result(result: dict) -> dict:
    """Apply redact_secrets to every string field (recursively)."""
    if isinstance(result, dict):
        return {k: redact_result(v) for k, v in result.items()}
    if isinstance(result, list):
        return [redact_result(v) for v in result]
    if isinstance(result, str):
        return redact_secrets(result)
    return result


def load_specs() -> list[dict]:
    specs = []
    curated = json.loads((ROOT / "docs/curated-tasks.json").read_text())
    curated_ids = {t["trajId"] for t in curated["tasks"]}
    for path in sorted(TASKS.glob("*.json")):
        spec = json.loads(path.read_text())
        if spec["trajId"] not in curated_ids:
            continue  # dropped in the v2 curation (t0124/t0339/t0720 stay on disk)
        specs.append(spec)
    return specs


def is_ready(spec: dict) -> tuple[bool, str]:
    """A task is READY when its verifier can grade locally and its local
    workdir prep is defined."""
    checks = (spec.get("verifier") or {}).get("checks", [])
    runnable = [c for c in checks if c.get("command") and c.get("locallyVerified") is True]
    env = spec.get("environment") or {}
    if not runnable:
        return False, "no locally runnable check"
    if "setupScript" not in env:
        return False, "no local workdir setupScript"
    return True, f"{len(runnable)} runnable check(s)"


def prep_workdir(spec: dict, workdir: Path) -> bool:
    """Set the workdir up per the spec's setupScript. Returns success."""
    script = (spec.get("environment") or {}).get("setupScript")
    if not script:
        return False
    proc = subprocess.run(["bash", "-lc", script], capture_output=True, text=True, cwd=str(workdir))
    if proc.returncode != 0:
        print(f"eval: workdir prep failed for {spec['trajId']}: {proc.stderr[-500:]}", file=sys.stderr)
        return False
    return True


def run_task(spec: dict, arm: str, memory: Path | None, workdir: Path, model: str, out: Path,
             max_turns: int, token_ceiling: int, memory_mode: str = "folder") -> dict:
    # spec files are named <trajId>-<slug>.json
    matches = sorted(TASKS.glob(f"{spec['trajId']}-*.json"))
    spec_path = matches[0]
    cmd = [
        sys.executable, str(WORKER),
        "--task", str(spec_path),
        "--arm", arm,
        "--workdir", str(workdir),
        "--model", model,
        "--out", str(out),
        "--max-turns", str(max_turns),
        "--token-ceiling", str(token_ceiling),
    ]
    if memory is not None:
        cmd += ["--memory", str(memory)]
        if memory_mode != "folder":
            cmd += ["--memory-mode", memory_mode]
    env = dict(os.environ)
    if not env.get("DEEPSEEK_API_KEY"):
        # "sentinel" only works when the subprocess rides the Skydive egress
        # proxy (it stamps the real credential). The runner's balance check
        # hit api.deepseek.com directly and got a 401 with the sentinel, so
        # the eval now requires a real key in the environment.
        print(
            "eval: DEEPSEEK_API_KEY not set in environment; refusing to fall "
            "back to a placeholder after the runner's balance check 401'd. "
            "Export the key and rerun.",
            file=sys.stderr,
        )
        return {"error": "missing DEEPSEEK_API_KEY"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        print(f"eval: runner failed for {spec['trajId']} arm={arm}: {proc.stderr[-500:]}", file=sys.stderr)
        return {"taskId": spec["trajId"], "arm": arm, "passed": False, "status": "runner-error",
                "error": proc.stderr[-2000:], "turns": 0, "tokens": {}, "seconds": 0,
                "checks": [], "memoryUsed": arm == "memory"}
    return json.loads(out.read_text())


def summarize(results: list[dict]) -> dict:
    by_arm: dict[str, list[dict]] = {}
    for r in results:
        if "arm" in r and "taskId" in r: by_arm.setdefault(r["arm"], []).append(r)

    def pass_at_1(rows):
        done = [r for r in rows if not r.get("error")]
        if not done:
            return None
        return sum(1 for r in done if r["passed"]) / len(done)

    table = {arm: {"pass@1": pass_at_1(rows), "n": len(rows)} for arm, rows in by_arm.items()}
    families: dict[str, dict] = {}
    tags: dict[str, dict] = {}
    specs = {s["trajId"]: s for s in load_specs()}
    for arm, rows in by_arm.items():
        for r in rows:
            spec = specs.get(r["taskId"], {})
            fam = spec.get("family", "unassigned")
            families.setdefault(fam, {}).setdefault(arm, []).append(r["passed"])
            for tag in spec.get("tags", ["none"]):
                tags.setdefault(tag, {}).setdefault(arm, []).append(r["passed"])
    return {"by_arm": table, "by_family": families, "by_tag": tags}


def markdown_report(results: list[dict], ready: list[tuple[str, str]], blocked: list[tuple[str, str]]) -> str:
    summary = summarize(results)
    lines = [
        "# wazoobench eval run",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()} by src/eval.py (deepseek_driver in-process loop).",
        "",
        "## Summary",
        "",
        "| arm | n | pass@1 |",
        "|---|---|---|",
    ]
    for arm, row in summary["by_arm"].items():
        p = row["pass@1"]
        lines.append(f"| {arm} | {row['n']} | {'n/a' if p is None else format(p, '.0%')} |")
    lines += ["", "## Per-task results", "",
              "| task | arm | passed | status | turns | tokens (in/cached/out) | seconds |",
              "|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: (x["taskId"], x["arm"])):
        tokens = r.get("tokens") or {}
        lines.append(
            f"| {r['taskId']} | {r['arm']} | {'PASS' if r['passed'] else 'FAIL'} "
            f"| {r.get('status', '?')} | {r.get('turns', '?')} "
            f"| {tokens.get('input_tokens', '?')}/{tokens.get('cached_input_tokens', '?')}/{tokens.get('output_tokens', '?')} "
            f"| {r.get('seconds', '?')} |"
        )
    lines += ["", "## READY for this run", ""]
    lines += [f"- **{tid}** — {why}" for tid, why in ready]
    lines += ["", "## Blocked (container-required), not run", ""]
    lines += [f"- {tid} — {why}" for tid, why in blocked]
    lines += ["", "## By family", ""]
    for fam, arms in summary["by_family"].items():
        parts = []
        for arm, values in arms.items():
            parts.append(f"{arm}: {sum(v for v in values)}/{len(values)}")
        lines.append(f"- {fam} — " + ", ".join(parts))
    lines += ["", "## By tag", ""]
    for tag, arms in summary["by_tag"].items():
        parts = []
        for arm, values in arms.items():
            parts.append(f"{arm}: {sum(v for v in values)}/{len(values)}")
        lines.append(f"- {tag} — " + ", ".join(parts))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--arms", type=int, choices=[1, 2], default=2,
                        help="2 = memory + control (default); 1 = memory arm only")
    parser.add_argument("--tasks", default=None, help="glob of spec files (default: READY set)")
    parser.add_argument("--memory", default="/tmp/train-only-mem",
                        help="shared train-only memory folder (regenerate per docs/data-split.json if missing)")
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--token-ceiling", type=int, default=400_000)
    parser.add_argument(
        "--memory-mode", choices=["folder", "family", "inline"], default="folder",
        help="memory delivery interface (iter3): folder = full-index dump; "
        "family = family-sectioned memory; inline = presenter injection",
    )
    parser.add_argument("--list", action="store_true", help="print the READY/blocked split and exit (no API spend)")
    args = parser.parse_args(argv)

    specs = load_specs()
    ready: list[tuple[dict, str]] = []
    blocked: list[tuple[str, str]] = []
    for spec in specs:
        ok, why = is_ready(spec)
        if ok:
            ready.append((spec, why))
        else:
            blocked.append((spec["trajId"], why))

    if args.list:
        print("READY (what the first eval runs):")
        for spec, why in ready:
            print(f"  {spec['trajId']}: {why}")
        print("BLOCKED (container-required):")
        for tid, why in blocked:
            print(f"  {tid}: {why}")
        return 0

    if not ready:
        print("eval: no READY tasks", file=sys.stderr)
        return 1

    if args.tasks:
        wanted = {Path(p.strip()).stem.split("-")[0] for p in args.tasks.split(",")}
        ready = [(s, w) for s, w in ready if s["trajId"] in wanted]

    memory = Path(args.memory)
    if not memory.is_dir():
        print(
            f"eval: memory folder {memory} missing — regenerate per docs/data-split.json "
            "(claims filter + dream/export via wazoo-frontiermemory) before the paid run",
            file=sys.stderr,
        )
        return 1

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = RUNS / (f"{date}-eval" if args.memory_mode == "folder" else f"{date}-eval-{args.memory_mode}")
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for index, (spec, _why) in enumerate(ready, start=1):
        for arm in (["memory", "control"] if args.arms == 2 else ["memory"]):
            workdir = out_dir / f"workdir-{spec['trajId']}-{arm}"
            if workdir.exists():
                # never reuse a workdir across runs
                import shutil

                shutil.rmtree(workdir)
            workdir.mkdir(parents=True)
            if not prep_workdir(spec, workdir):
                results.append({"taskId": spec["trajId"], "arm": arm, "passed": False,
                                "error": "workdir prep failed", "checks": [], "turns": 0,
                                "tokens": {}, "seconds": 0, "memoryUsed": arm == "memory",
                                "status": "prep-failed"})
                continue
            result_path = out_dir / f"result-{spec['trajId']}-{arm}.json"
            print(f"eval: [{index}/{len(ready)}] {spec['trajId']} arm={arm} ...", flush=True)
            result = run_task(spec, arm, memory if arm == "memory" else None,
                              workdir, args.model, result_path,
                              args.max_turns, args.token_ceiling,
                              memory_mode=args.memory_mode)
            result = redact_result(result)
            if arm == "memory" and args.memory_mode != "folder":
                result["arm"] = f"memory-{args.memory_mode}"
            results.append(result)
            (out_dir / "results.json").write_text(json.dumps(results, indent=2))
    (out_dir / "report.md").write_text(
        markdown_report(results, [(s["trajId"], w) for s, w in ready], blocked)
    )
    print(f"eval: wrote {out_dir}/results.json and {out_dir}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
