"""
Summary: Runs OMYM2's final quality gate when Codex stops with repository changes.
Why: Prevents an agent from completing changed work before authoritative validation succeeds.
"""
# ruff: noqa: INP001, T201 -- Standalone Codex hook reports protocol feedback to stderr.

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

if __package__:
    from scripts.config import (
        CODEX_STOP_HOOK_DIAGNOSTIC_MAX_CHARACTERS,
        CODEX_STOP_HOOK_FINGERPRINT_CHUNK_BYTES,
        CODEX_STOP_HOOK_GATE_TIMEOUT_SECONDS,
        CODEX_STOP_HOOK_GIT_TIMEOUT_SECONDS,
    )
else:
    from config import (
        CODEX_STOP_HOOK_DIAGNOSTIC_MAX_CHARACTERS,
        CODEX_STOP_HOOK_FINGERPRINT_CHUNK_BYTES,
        CODEX_STOP_HOOK_GATE_TIMEOUT_SECONDS,
        CODEX_STOP_HOOK_GIT_TIMEOUT_SECONDS,
    )

if TYPE_CHECKING:
    from collections.abc import Buffer, Sequence

BLOCK_EXIT_CODE: Final = 2
COMMAND_ENCODING: Final = "utf-8"
FINGERPRINT_ALGORITHM: Final = "sha256"
QUALITY_GATE_COMMAND: Final = ("scripts/checks.sh", "completion")
GIT_SUCCESS_RETURN_CODES: Final = frozenset({0})
STATE_FILE_NAME: Final = "omym2-codex-stop-hook.json"
STATE_STATUS_FAILED: Final = "failed"
STATE_STATUS_PASSED: Final = "passed"


class HookError(RuntimeError):
    """Raised when the hook cannot safely inspect or validate the repository."""


class FingerprintHasher(Protocol):
    """Hash operations used while building a repository fingerprint."""

    def update(self, value: Buffer, /) -> None:
        """Add bytes to the digest."""
        ...

    def hexdigest(self) -> str:
        """Return the completed hexadecimal digest."""
        ...


@dataclass(frozen=True)
class HookPayload:
    """Stop fields used by the repository hook."""

    stop_hook_active: bool


@dataclass(frozen=True)
class HookState:
    """Last validation result for one exact repository fingerprint."""

    fingerprint: str
    status: str


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[bytes]:
    """Run one fixed command without invoking a shell."""
    return subprocess.run(  # noqa: S603 -- Callers provide fixed Git and repository-gate argv.
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


def _parse_payload(raw_payload: str) -> HookPayload:
    """Parse and validate the Stop payload fields used by this hook."""
    try:
        raw_value = cast("object", json.loads(raw_payload))
    except json.JSONDecodeError as error:
        msg = f"malformed JSON input: {error.msg}"
        raise HookError(msg) from error
    if not isinstance(raw_value, dict):
        msg = "hook input must be a JSON object"
        raise HookError(msg)
    payload = cast("dict[str, object]", raw_value)
    if payload.get("hook_event_name") != "Stop":
        msg = "hook_event_name must be Stop"
        raise HookError(msg)
    stop_hook_active = payload.get("stop_hook_active")
    if not isinstance(stop_hook_active, bool):
        msg = "stop_hook_active must be a boolean"
        raise HookError(msg)
    return HookPayload(stop_hook_active=stop_hook_active)


def _decode_output(output: bytes | str | None) -> str:
    """Decode captured subprocess output without raising on invalid bytes."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return output.decode(COMMAND_ENCODING, errors="replace")


def _command_text(command: Sequence[str]) -> str:
    """Render the fixed command for actionable diagnostics."""
    return " ".join(command)


def _git(
    arguments: Sequence[str],
    *,
    cwd: Path,
    accepted_return_codes: frozenset[int] = GIT_SUCCESS_RETURN_CODES,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git and convert operational failures into concise hook errors."""
    command = ("git", *arguments)
    try:
        result = run_command(command, cwd=cwd, timeout_seconds=CODEX_STOP_HOOK_GIT_TIMEOUT_SECONDS)
    except FileNotFoundError as error:
        msg = "git executable was not found"
        raise HookError(msg) from error
    except subprocess.TimeoutExpired as error:
        msg = f"{_command_text(command)} timed out"
        raise HookError(msg) from error
    except OSError as error:
        msg = f"{_command_text(command)} could not start: {error}"
        raise HookError(msg) from error
    if result.returncode not in accepted_return_codes:
        diagnostics = _decode_output(result.stderr).strip() or _decode_output(result.stdout).strip()
        detail = f": {diagnostics}" if diagnostics else ""
        msg = f"{_command_text(command)} failed with exit code {result.returncode}{detail}"
        raise HookError(msg)
    return result


def _resolve_repository_root() -> Path:
    """Resolve the repository root from Git instead of trusting hook input."""
    result = _git(("rev-parse", "--show-toplevel"), cwd=Path.cwd())
    root_text = _decode_output(result.stdout).strip()
    if not root_text:
        msg = "git rev-parse --show-toplevel returned an empty path"
        raise HookError(msg)
    repository_root = Path(root_text).resolve()
    if not repository_root.is_dir():
        msg = f"resolved repository root is not a directory: {repository_root}"
        raise HookError(msg)
    return repository_root


def _has_diff(repository_root: Path, *arguments: str) -> bool:
    """Return whether one Git diff comparison contains changes."""
    result = _git(
        ("diff", "--quiet", "--no-ext-diff", *arguments, "--"),
        cwd=repository_root,
        accepted_return_codes=frozenset({0, 1}),
    )
    return result.returncode == 1


def _origin_merge_base(repository_root: Path) -> str | None:
    """Return the merge base with origin/main, or None when it cannot be resolved."""
    origin = _git(
        ("rev-parse", "--verify", "origin/main^{commit}"),
        cwd=repository_root,
        accepted_return_codes=frozenset({0, 1, 128}),
    )
    if origin.returncode != 0:
        return None
    merge_base = _git(
        ("merge-base", "HEAD", "origin/main"),
        cwd=repository_root,
        accepted_return_codes=frozenset({0, 1, 128}),
    )
    if merge_base.returncode != 0:
        return None
    merge_base_text = _decode_output(merge_base.stdout).strip()
    return merge_base_text or None


def _untracked_paths(repository_root: Path) -> list[bytes]:
    """Return sorted, repository-relative untracked file paths from Git."""
    result = _git(("ls-files", "--others", "--exclude-standard", "-z"), cwd=repository_root)
    return sorted(path for path in result.stdout.split(b"\0") if path)


def _repository_has_work(repository_root: Path) -> bool:
    """Determine whether the repository has committed or working-tree changes."""
    merge_base = _origin_merge_base(repository_root)
    if merge_base is None:
        return True
    if _has_diff(repository_root, merge_base, "HEAD"):
        return True
    if _has_diff(repository_root, "--cached"):
        return True
    if _has_diff(repository_root):
        return True
    return bool(_untracked_paths(repository_root))


def _update_fingerprint(hasher: FingerprintHasher, label: bytes, value: bytes) -> None:
    """Add one length-delimited component to a hashlib-compatible digest."""
    hasher.update(len(label).to_bytes(4, "big"))
    hasher.update(label)
    hasher.update(len(value).to_bytes(8, "big"))
    hasher.update(value)


def _hash_untracked_file(
    hasher: FingerprintHasher,
    repository_root: Path,
    relative_path_bytes: bytes,
) -> None:
    """Add an untracked path and its stable filesystem state to the fingerprint."""
    relative_path = Path(os.fsdecode(relative_path_bytes))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        msg = f"Git returned an unsafe untracked path: {os.fsdecode(relative_path_bytes)}"
        raise HookError(msg)
    path = repository_root / relative_path
    try:
        file_stat = path.lstat()
        _update_fingerprint(hasher, b"untracked-path", relative_path_bytes)
        _update_fingerprint(hasher, b"untracked-mode", str(file_stat.st_mode).encode(COMMAND_ENCODING))
        if stat.S_ISLNK(file_stat.st_mode):
            target = os.fsencode(path.readlink())
            _update_fingerprint(hasher, b"untracked-symlink", target)
            return
        if not stat.S_ISREG(file_stat.st_mode):
            metadata = f"{file_stat.st_size}:{file_stat.st_mtime_ns}".encode(COMMAND_ENCODING)
            _update_fingerprint(hasher, b"untracked-special", metadata)
            return
        with path.open("rb") as untracked_file:
            while chunk := untracked_file.read(CODEX_STOP_HOOK_FINGERPRINT_CHUNK_BYTES):
                _update_fingerprint(hasher, b"untracked-content", chunk)
    except OSError as error:
        msg = f"could not fingerprint untracked file {relative_path}: {error}"
        raise HookError(msg) from error


def _repository_fingerprint(repository_root: Path) -> str:
    """Build a stable fingerprint from HEAD and each working-tree state category."""
    head = _git(("rev-parse", "--verify", "HEAD"), cwd=repository_root).stdout.strip()
    tracked = _git(("diff", "--binary", "--no-ext-diff", "--no-textconv"), cwd=repository_root).stdout
    staged = _git(
        ("diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv"),
        cwd=repository_root,
    ).stdout
    untracked = _untracked_paths(repository_root)
    hasher = hashlib.new(FINGERPRINT_ALGORITHM)
    _update_fingerprint(hasher, b"head", head)
    _update_fingerprint(hasher, b"tracked", tracked)
    _update_fingerprint(hasher, b"staged", staged)
    for relative_path in untracked:
        _hash_untracked_file(hasher, repository_root, relative_path)
    return hasher.hexdigest()


def _state_path(repository_root: Path) -> Path:
    """Return the repository-local ephemeral state path under .git/."""
    git_directory = repository_root / ".git"
    if not git_directory.is_dir():
        msg = f"repository Git directory is unavailable: {git_directory}"
        raise HookError(msg)
    return git_directory / STATE_FILE_NAME


def _read_state(state_path: Path) -> HookState | None:
    """Read valid prior state, treating malformed ephemeral state as absent."""
    try:
        raw_state = state_path.read_text(encoding=COMMAND_ENCODING)
    except FileNotFoundError:
        return None
    except OSError as error:
        msg = f"could not read hook state: {error}"
        raise HookError(msg) from error
    try:
        raw_value = cast("object", json.loads(raw_state))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_value, dict):
        return None
    state = cast("dict[str, object]", raw_value)
    fingerprint = state.get("fingerprint")
    status_value = state.get("status")
    if not isinstance(fingerprint, str) or not isinstance(status_value, str):
        return None
    if status_value not in {STATE_STATUS_FAILED, STATE_STATUS_PASSED}:
        return None
    return HookState(fingerprint=fingerprint, status=status_value)


def _write_state(state_path: Path, state: HookState) -> None:
    """Atomically record one validation result beneath .git/."""
    temporary_path = state_path.with_suffix(".tmp")
    serialized = json.dumps(
        {"fingerprint": state.fingerprint, "status": state.status},
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        _ = temporary_path.write_text(serialized, encoding=COMMAND_ENCODING)
        _ = temporary_path.replace(state_path)
    except OSError as error:
        with suppress(OSError):
            temporary_path.unlink(missing_ok=True)
        msg = f"could not write hook state: {error}"
        raise HookError(msg) from error


def _remove_state(state_path: Path) -> None:
    """Remove stale validation state when the repository is clean."""
    try:
        state_path.unlink(missing_ok=True)
    except OSError as error:
        msg = f"could not remove stale hook state: {error}"
        raise HookError(msg) from error


def _bounded_diagnostics(text: str) -> str:
    """Keep the most recent useful validation diagnostics within the hook feedback bound."""
    stripped = text.strip()
    if len(stripped) <= CODEX_STOP_HOOK_DIAGNOSTIC_MAX_CHARACTERS:
        return stripped
    tail = stripped[-CODEX_STOP_HOOK_DIAGNOSTIC_MAX_CHARACTERS:]
    return f"[earlier validation output omitted]\n{tail}"


def _validation_failure_message(result: subprocess.CompletedProcess[bytes]) -> str:
    """Build actionable blocking feedback from a failed quality gate."""
    combined = "\n".join(
        output for output in (_decode_output(result.stdout).strip(), _decode_output(result.stderr).strip()) if output
    )
    diagnostics = _bounded_diagnostics(combined) or "The command returned no diagnostic output."
    return (
        f"OMYM2 completion validation failed.\n"
        f"Command: {_command_text(QUALITY_GATE_COMMAND)}\n"
        f"{diagnostics}\n"
        "Fix the reported failure, then attempt completion again."
    )


def _run_quality_gate(repository_root: Path) -> str | None:
    """Run the authoritative gate and return blocking feedback on failure."""
    try:
        result = run_command(
            QUALITY_GATE_COMMAND,
            cwd=repository_root,
            timeout_seconds=CODEX_STOP_HOOK_GATE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        partial_output = "\n".join(
            output for output in (_decode_output(error.stdout).strip(), _decode_output(error.stderr).strip()) if output
        )
        diagnostics = _bounded_diagnostics(partial_output)
        diagnostic_suffix = f"\n{diagnostics}" if diagnostics else ""
        return (
            f"OMYM2 completion validation timed out after {CODEX_STOP_HOOK_GATE_TIMEOUT_SECONDS} seconds.\n"
            f"Command: {_command_text(QUALITY_GATE_COMMAND)}{diagnostic_suffix}\n"
            "Investigate the stalled gate, then attempt completion again."
        )
    except FileNotFoundError:
        return (
            "OMYM2 completion validation could not start.\n"
            f"Command: {_command_text(QUALITY_GATE_COMMAND)}\n"
            "The quality-gate executable was not found; restore it, then attempt completion again."
        )
    except OSError as error:
        return (
            "OMYM2 completion validation could not start.\n"
            f"Command: {_command_text(QUALITY_GATE_COMMAND)}\n"
            f"{error}\n"
            "Fix the execution error, then attempt completion again."
        )
    if result.returncode == 0:
        return None
    return _validation_failure_message(result)


def run_hook(payload: HookPayload) -> int:
    """Apply change detection, fingerprint caching, validation, and Stop-loop protection."""
    repository_root = _resolve_repository_root()
    state_path = _state_path(repository_root)
    if not _repository_has_work(repository_root):
        _remove_state(state_path)
        return 0

    fingerprint = _repository_fingerprint(repository_root)
    prior_state = _read_state(state_path)
    if prior_state == HookState(fingerprint=fingerprint, status=STATE_STATUS_PASSED):
        return 0
    if payload.stop_hook_active and prior_state == HookState(fingerprint=fingerprint, status=STATE_STATUS_FAILED):
        print(
            "OMYM2 validation is still failing for this unchanged repository state; allowing Stop to avoid a loop.",
            file=sys.stderr,
        )
        return 0

    failure_message = _run_quality_gate(repository_root)
    if failure_message is None:
        _write_state(state_path, HookState(fingerprint=fingerprint, status=STATE_STATUS_PASSED))
        return 0
    _write_state(state_path, HookState(fingerprint=fingerprint, status=STATE_STATUS_FAILED))
    print(failure_message, file=sys.stderr)
    return BLOCK_EXIT_CODE


def main() -> int:
    """Read one Stop payload and return the Codex hook protocol exit code."""
    try:
        payload = _parse_payload(sys.stdin.read())
        exit_code = run_hook(payload)
    except KeyboardInterrupt:
        print(
            "OMYM2 completion validation was interrupted; run scripts/checks.sh completion and try again.",
            file=sys.stderr,
        )
        return BLOCK_EXIT_CODE
    except HookError as error:
        print(f"OMYM2 completion validation could not run: {error}", file=sys.stderr)
        return BLOCK_EXIT_CODE
    except Exception as error:  # noqa: BLE001 -- Hooks must never expose an uncontrolled traceback.
        print(f"OMYM2 completion validation failed unexpectedly: {error}", file=sys.stderr)
        return BLOCK_EXIT_CODE
    if exit_code == 0:
        print(json.dumps({}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
