"""wazoobench naive baseline: the both-ways check on the swapped tasks.

For each swapped task (t0188, t0611) it builds two workdirs from the stored
verifier assets and runs the contract checks against both:

- INFORMED: the recorded PASS solution (t0188: the recorded
  promql/labelsort.go recovered verbatim from the trajectory; t0611: the
  PASS run's cache implementation replayed against the pinned base commit).
- NAIVE: a hand-written no-memory variant (t0188: natural-sort-only
  comparator, the behavior the issue replaces; t0611: CLI flags accepted but
  no actual caching).

The verifier discriminates when naive fails at least one grading check while
informed passes all of them. Any check that CANNOT discriminate is flagged
in the report (and in the spec), never faked.

Zero API spend: this script never calls the model.

Usage: python3 src/naive_baseline.py [--keep-workdirs]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "src" / "verifier-assets"
GO = "/usr/local/go/bin/go" if Path("/usr/local/go/bin/go").exists() else shutil.which("go")

VULTURE_BASE = "ef9e6de"  # just before the 2.15 release bump (see the t0611 spec)


def run(cmd: list[str], cwd: str | None = None, env: dict | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, env=env)
    return proc.returncode, (proc.stdout + proc.stderr)


def check_t0188(workdirs: dict[str, Path]) -> dict:
    """Contract: go test ./... with the authored contract test injected."""
    report: dict = {"task": "t0188", "grader": "go test ./... (authored contract test)"}
    for label, workdir in workdirs.items():
        shutil.copy(ASSETS / "t0188-labelsort-contract/labelsort_contract_test.go", workdir / "labelsort_contract_test.go")
        code, output = run([GO, "test", "./..."], cwd=str(workdir))
        failures = [line.split()[2].rstrip("()") for line in output.splitlines() if line.startswith("--- FAIL")]
        report[label] = {"exit_code": code, "pass": code == 0, "failing_checks": failures, "output_tail": output[-400:]}
    return report


def check_t0611(workdirs: dict[str, Path]) -> dict:
    """Contract: the authored stdlib check script (11 checks)."""
    report: dict = {"task": "t0611", "grader": "verifier-check.py (authored contract script)"}
    script = ASSETS / "t0611-cache-contract/verifier-check.py"
    for label, workdir in workdirs.items():
        target = workdir / "t0611-cache-contract"
        if not target.exists():
            shutil.copytree(script.parent, target)
        code, output = run([sys.executable, "t0611-cache-contract/verifier-check.py"], cwd=str(workdir))
        fails = [line[5:].split(":")[0].strip() for line in output.splitlines() if line.startswith("FAIL ")]
        if code != 0 and not fails:
            # e.g. the naive variant has no cache module at all: the script
            # exits on the import itself, which fails every contract check
            tail = [line for line in output.splitlines() if line.strip()][-1:]
            fails = [f"<script aborted: {tail[0][:160] if tail else 'no output'}>"]
        report[label] = {"exit_code": code, "pass": code == 0, "failing_checks": fails, "output_tail": output[-400:]}
    return report


def build_t0188_workdirs(base: Path) -> dict[str, Path]:
    workdirs = {}
    for label in ("informed", "naive"):
        d = base / f"t0188-{label}"
        shutil.copytree(ASSETS / f"t0188-labelsort-{label}", d)
        workdirs[label] = d
    return workdirs


def build_t0611_workdirs(base: Path) -> dict[str, Path]:
    workdirs = {}
    for label in ("informed", "naive"):
        d = base / f"t0611-{label}"
        d.mkdir(parents=True, exist_ok=True)
        # clone from the mirror at the pinned base commit
        code, output = run(["git", "clone", "--filter=blob:none", "https://github.com/jendrikseipp/vulture", "."], cwd=str(d))
        if code != 0:
            raise RuntimeError(f"vulture clone failed: {output[-500:]}")
        code, output = run(["git", "checkout", VULTURE_BASE], cwd=str(d))
        if code != 0:
            raise RuntimeError(f"checkout {VULTURE_BASE} failed: {output[-500:]}")
        patch = ASSETS / f"t0611-cache-{label}/{'informed' if label == 'informed' else 'naive'}-solution.patch"
        code, output = run(["git", "apply", str(patch)], cwd=str(d))
        if code != 0:
            raise RuntimeError(f"{label} patch failed: {output[-500:]}")
        code, output = run([sys.executable, "-m", "pip", "install", "-q", "--no-build-isolation", "--break-system-packages", "-e", "."], cwd=str(d))
        if code != 0:
            raise RuntimeError(f"pip install -e failed for {label}: {output[-500:]}")
        workdirs[label] = d
    return workdirs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-workdirs", action="store_true")
    args = parser.parse_args(argv)

    reports = []
    if args.keep_workdirs:
        base = _fresh_dir(Path(tempfile.gettempdir()) / "wazoobench-naive-baseline")
    else:
        base = Path(tempfile.mkdtemp(prefix="wazoobench-naive-"))

    t0188 = check_t0188(build_t0188_workdirs(base))
    discriminated = t0188["informed"]["pass"] and not t0188["naive"]["pass"]
    t0188["discriminates"] = discriminated
    if not discriminated:
        t0188["flag"] = "informed must pass and naive must fail; a check that both pass cannot discriminate"
    reports.append(t0188)
    print(f"t0188: informed pass={t0188['informed']['pass']} naive pass={t0188['naive']['pass']} "
          f"(naive fails: {t0188['naive']['failing_checks']})")

    t0611 = check_t0611(build_t0611_workdirs(base))
    discriminated = t0611["informed"]["pass"] and not t0611["naive"]["pass"]
    t0611["discriminates"] = discriminated
    if not discriminated:
        t0611["flag"] = "informed must pass and naive must fail; a check that both pass cannot discriminate"
    reports.append(t0611)
    print(f"t0611: informed pass={t0611['informed']['pass']} naive pass={t0611['naive']['pass']} "
          f"(naive fails: {t0611['naive']['failing_checks']})")

    out = ROOT / "docs" / "naive-baseline-report.json"
    out.write_text(json.dumps(reports, indent=2))
    print(f"wrote {out}")

    ok = all(r["discriminates"] for r in reports)
    return 0 if ok else 1


def _fresh_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


if __name__ == "__main__":
    sys.exit(main())
