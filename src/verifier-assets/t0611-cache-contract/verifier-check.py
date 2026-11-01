#!/usr/bin/env python3
"""Contract check for t0611 (vulture incremental cache).

Authored independently from the issue text; stdlib only (no pytest), because
the local evaluator's verifier runs pinned check commands in the workdir.

Run:  python3 verifier-check.py   (from the vulture repo root)

Exit 0 = every check passed; nonzero output lists the failing checks.
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The script is copied into the vulture workdir root; make the repo importable.
sys.path.insert(0, os.getcwd())

import importlib.metadata

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vulture import cache  # noqa: E402
from vulture.core import Vulture  # noqa: E402

FAILURES = []


def check(name, fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - report and continue
        FAILURES.append((name, f"{type(exc).__name__}: {exc}"))
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        print(f"PASS {name}")


def make_tree(root: Path):
    files = {
        "a.py": "import b\nA_UNUSED = 1\n",
        "b.py": "import c\nB_UNUSED = 1\n",
        "c.py": "C_UNUSED = 1\n",
        "d.py": "D_UNUSED = 1\n",
    }
    for name, source in files.items():
        (root / name).write_text(source)
    return root / "cache"


def scan_tree(root: Path, cache_dir, **kwargs):
    v = Vulture(cache_dir=cache_dir, **kwargs)
    v.scavenge([root], exclude=["cache"])
    return v


def test_reuse_on_second_run(root):
    cache_dir = make_tree(root)
    first = scan_tree(root, cache_dir)
    assert first._cache_stats["reused"] == set(), first._cache_stats
    assert len(first._cache_stats["scanned"]) == 4
    second = scan_tree(root, cache_dir)
    assert second._cache_stats["scanned"] == set()
    assert len(second._cache_stats["reused"]) == 4


def test_transitive_invalidation(root):
    cache_dir = make_tree(root)
    scan_tree(root, cache_dir)
    (root / "c.py").write_text("C_UNUSED = 2\n")
    third = scan_tree(root, cache_dir)
    scanned = {Path(p).name for p in third._cache_stats["scanned"]}
    reused = {Path(p).name for p in third._cache_stats["reused"]}
    assert scanned == {"a.py", "b.py", "c.py"}, scanned
    assert reused == {"d.py"}, reused


def test_first_save_writes_backup_and_meta(root):
    cache_dir = make_tree(root)
    scan_tree(root, cache_dir)
    cache_path = cache.get_cache_path(cache_dir)
    assert cache_path.is_file(), cache_path
    assert Path(f"{cache_path}.bak").read_bytes() == cache_path.read_bytes()
    meta = json.loads(Path(f"{cache_path}.meta").read_text())
    assert meta["sha256"] == hashlib.sha256(cache_path.read_bytes()).hexdigest()
    doc = json.loads(cache_path.read_text())
    assert isinstance(doc.get("modules"), dict) and doc["modules"], doc.keys()


def test_corrupt_cache_warns_and_rescans(root):
    cache_dir = make_tree(root)
    scan_tree(root, cache_dir)
    cache_path = cache.get_cache_path(cache_dir)
    cache_path.write_text("{not json")
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        v = scan_tree(root, cache_dir)
    assert "cache is corrupted or unreadable" in buf.getvalue(), buf.getvalue()
    assert len(v._cache_stats["scanned"]) == 4


def test_checksum_mismatch_treated_as_corruption(root):
    cache_dir = make_tree(root)
    scan_tree(root, cache_dir)
    cache_path = cache.get_cache_path(cache_dir)
    doc = json.loads(cache_path.read_text())
    doc["modules"] = {}
    cache_path.write_text(json.dumps(doc))
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        v = scan_tree(root, cache_dir)
    assert "cache is corrupted or unreadable" in buf.getvalue(), buf.getvalue()
    assert len(v._cache_stats["scanned"]) == 4


def test_missing_cache_is_silent(root):
    cache_dir = make_tree(root)
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        v = scan_tree(root, cache_dir)
    assert "corrupt" not in buf.getvalue(), buf.getvalue()
    assert len(v._cache_stats["scanned"]) == 4


def test_settings_change_triggers_rescan(root):
    cache_dir = make_tree(root)
    scan_tree(root, cache_dir)
    v = scan_tree(root, cache_dir, cache_settings={"ignore_names": ["x_*"]})
    assert len(v._cache_stats["scanned"]) == 4, v._cache_stats


def test_vulture_version_change_triggers_rescan(root):
    cache_dir = make_tree(root)
    scan_tree(root, cache_dir)
    real = importlib.metadata.version
    importlib.metadata.version = lambda name: "9.9.9" if name == "vulture" else real(name)
    try:
        v = scan_tree(root, cache_dir)
    finally:
        importlib.metadata.version = real
    assert len(v._cache_stats["scanned"]) == 4, v._cache_stats


def test_deleted_file_cleaned_from_cache(root):
    cache_dir = make_tree(root)
    scan_tree(root, cache_dir)
    cache_path = cache.get_cache_path(cache_dir)
    before = json.loads(cache_path.read_text())["modules"]
    (root / "d.py").unlink()
    scan_tree(root, cache_dir)
    after = json.loads(cache_path.read_text())["modules"]
    assert before != after
    assert not any("d.py" in key for key in after), sorted(after)


def test_cli_flags(root):
    out = subprocess.run(
        [sys.executable, "-m", "vulture", "--help"],
        capture_output=True, text=True,
    )
    text = out.stdout + out.stderr
    for flag in ("--cache", "--cache-clear", "--cache-dir"):
        assert flag in text, flag


def test_keyboard_interrupt_saves_partial_cache(root):
    cache_dir = make_tree(root)
    real_scan = Vulture.scan

    calls = {"n": 0}

    def flaky_scan(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 2:
            raise KeyboardInterrupt
        return real_scan(self, *args, **kwargs)

    Vulture.scan = flaky_scan
    try:
        try:
            scan_tree(root, cache_dir)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("KeyboardInterrupt must re-raise")
    finally:
        Vulture.scan = real_scan
    cache_path = cache.get_cache_path(cache_dir)
    assert cache_path.is_file(), "partial cache not saved"
    meta = json.loads(Path(f"{cache_path}.meta").read_text())
    assert meta["sha256"] == hashlib.sha256(cache_path.read_bytes()).hexdigest()


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for i, (name, fn) in enumerate(sorted(globals().items())):
            if name.startswith("test_"):
                # Plain numbered root: the run root must not contain "cache",
                # or the scavenge exclude pattern would swallow every file.
                root = Path(tmp) / f"run-{i}"
                root.mkdir()
                check(name[len("test_"):], lambda f=fn, r=root: f(r))
    if FAILURES:
        print(f"\n{len(FAILURES)} check(s) FAILED")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
