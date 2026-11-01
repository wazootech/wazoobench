"""Persistent cache helpers for Vulture's file-based analysis.

The cache is intentionally JSON-based.  Apart from making the on-disk format
inspectable, this means that a cache produced by an interrupted or older
Vulture process can be rejected without ever unpickling untrusted data.
"""

import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager, suppress
from pathlib import Path

# Increment this whenever the on-disk format or the meaning of cached analysis
# data changes.
__version__ = 1

_CORRUPTION_WARNING = (
    "Warning: cache is corrupted or unreadable; performing a full scan."
)


def normalize_path(path):
    """Return a stable, absolute representation of *path*.

    ``normcase`` performs the platform-specific separator and case handling.
    The explicit ``casefold`` is intentional: it also makes paths
    case-insensitive when tests emulate Windows, and documents that cache keys
    must not differ only by case on Windows.
    """

    normalized = os.path.abspath(os.path.normpath(os.fspath(path)))
    normalized = os.path.normcase(normalized)
    if os.name == "nt" or sys.platform.startswith("win"):
        normalized = normalized.casefold()
    return normalized


def get_cache_path(cache_dir):
    """Return the path of the primary JSON cache file."""

    return Path(cache_dir) / "cache.json"


def get_runtime_signature():
    """Return the values which determine runtime cache compatibility."""

    # Do not use vulture.version.__version__ here.  Distribution metadata is
    # the authoritative package version and also works for vendored builds.
    package_version = importlib.metadata.version("vulture")
    return {
        "cache_version": __version__,
        "python_version": sys.version,
        "vulture_version": package_version,
    }


def _json_default(value):
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def normalize_settings(settings):
    """Convert cache settings to a deterministic JSON-compatible value."""

    # A JSON round trip normalizes tuples and non-string dictionary keys in the
    # same way as writing and reading cache.json would.
    return json.loads(
        json.dumps(
            settings or {},
            default=_json_default,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def new_cache(settings=None):
    """Return an empty cache document for the current runtime and settings."""

    return {
        "runtime_signature": get_runtime_signature(),
        "cache_settings": normalize_settings(settings),
        "modules": {},
    }


def warn_corrupted_cache():
    """Emit the standard warning used for every cache read failure."""

    print(_CORRUPTION_WARNING, file=sys.stderr)


def _validate_top_level(data):
    if not isinstance(data, dict):
        raise ValueError("cache root is not an object")
    if not isinstance(data.get("runtime_signature"), dict):
        raise ValueError("invalid runtime signature")
    if not isinstance(data.get("cache_settings"), dict):
        raise ValueError("invalid cache settings")
    modules = data.get("modules")
    if not isinstance(modules, dict) or not all(
        isinstance(path, str) and isinstance(entry, dict)
        for path, entry in modules.items()
    ):
        raise ValueError("invalid modules mapping")


def load_cache(cache_dir, settings=None):
    """Load and verify a cache document.

    A missing cache is normal and therefore silent.  Invalid runtime/settings
    signatures also silently return a fresh cache because they represent
    expected invalidation rather than corruption.  Every malformed, unreadable
    or checksum-mismatched cache emits the standard corruption warning.
    """

    cache_path = get_cache_path(cache_dir)
    metadata_path = Path(f"{cache_path}.meta")
    try:
        cache_bytes = cache_path.read_bytes()
    except FileNotFoundError:
        return new_cache(settings)
    except OSError:
        warn_corrupted_cache()
        return new_cache(settings)

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("cache metadata is not an object")
        expected_checksum = metadata.get("sha256")
        if not isinstance(expected_checksum, str):
            raise ValueError("cache metadata has no checksum")
        actual_checksum = hashlib.sha256(cache_bytes).hexdigest()
        if expected_checksum != actual_checksum:
            raise ValueError("cache checksum does not match")
        data = json.loads(cache_bytes.decode("utf-8"))
        _validate_top_level(data)
    except (OSError, UnicodeError, ValueError, TypeError):
        warn_corrupted_cache()
        return new_cache(settings)

    expected_settings = normalize_settings(settings)
    if (
        data["runtime_signature"] != get_runtime_signature()
        or data["cache_settings"] != expected_settings
    ):
        return new_cache(settings)
    return data


def _write_temporary_file(directory, data):
    """Write *data* durably and return a temporary file in *directory*."""

    fd, temporary_name = tempfile.mkstemp(prefix=".cache-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        with suppress(OSError):
            os.close(fd)
        with suppress(OSError):
            os.unlink(temporary_name)
        raise
    return Path(temporary_name)


def save_cache(cache_dir, data):
    """Atomically write the cache, its backup, and checksum metadata.

    Callers must hold :func:`cache_lock`.  The three destination files are
    prepared before any is replaced.  Readers use the same lock, so they can
    never observe the small interval between the atomic replacements.
    """

    cache_path = get_cache_path(cache_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = Path(f"{cache_path}.bak")
    metadata_path = Path(f"{cache_path}.meta")

    cache_bytes = (
        json.dumps(
            data,
            default=_json_default,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    metadata_bytes = (
        json.dumps(
            {"sha256": hashlib.sha256(cache_bytes).hexdigest()},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    temporary_files = []
    try:
        temporary_cache = _write_temporary_file(cache_path.parent, cache_bytes)
        temporary_files.append(temporary_cache)
        temporary_backup = _write_temporary_file(
            cache_path.parent, cache_bytes
        )
        temporary_files.append(temporary_backup)
        temporary_metadata = _write_temporary_file(
            cache_path.parent, metadata_bytes
        )
        temporary_files.append(temporary_metadata)

        os.replace(temporary_backup, backup_path)
        temporary_files.remove(temporary_backup)
        os.replace(temporary_cache, cache_path)
        temporary_files.remove(temporary_cache)
        os.replace(temporary_metadata, metadata_path)
        temporary_files.remove(temporary_metadata)

        # Persist the directory entries where the platform supports it.
        try:
            directory_fd = os.open(cache_path.parent, os.O_RDONLY)
        except OSError:
            pass
        else:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        for temporary_file in temporary_files:
            with suppress(OSError):
                temporary_file.unlink()


def _lock_path(cache_dir):
    """Return an external lock path, allowing cache contents to be cleared."""

    cache_dir = Path(cache_dir).absolute()
    return cache_dir.parent / f"{cache_dir.name}.lock"


@contextmanager
def cache_lock(cache_dir):
    """Exclusively lock a cache across processes.

    The lock spans loading, analysis and saving.  This deliberately favors
    correctness over allowing two processes to duplicate work, and prevents a
    reader from observing cache.json before its matching metadata is replaced.
    """

    lock_path = _lock_path(cache_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "a+b")
    lock_acquired = False
    try:
        if os.name == "nt":  # pragma: no cover - exercised on Windows
            import msvcrt

            lock_file.seek(0)
            if lock_file.read(1) == b"":
                lock_file.write(b"\0")
                lock_file.flush()
            while not lock_acquired:
                lock_file.seek(0)
                try:
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    time.sleep(0.05)
                else:
                    lock_acquired = True
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            lock_acquired = True
        yield
    finally:
        try:
            if lock_acquired and os.name == "nt":  # pragma: no cover
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            elif lock_acquired:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


def clear_cache(cache_dir):
    """Remove all files and directories contained in *cache_dir*.

    The caller must hold :func:`cache_lock` when other Vulture processes may be
    using the same directory.
    """

    path = Path(cache_dir)
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
