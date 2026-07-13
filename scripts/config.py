"""
Summary: Centralizes standalone repository-script tunables.
Why: Keeps lifecycle-hook timeouts and output bounds out of control flow.
"""
# ruff: noqa: INP001 -- Standalone repository-script configuration is not an importable package layer.

CODEX_STOP_HOOK_GIT_TIMEOUT_SECONDS = 30  # timeout for one Git inspection command, seconds, >= 1
CODEX_STOP_HOOK_GATE_TIMEOUT_SECONDS = 120  # timeout for scripts/checks.sh completion, seconds, >= 1
CODEX_STOP_HOOK_DIAGNOSTIC_MAX_CHARACTERS = 8_000  # maximum returned gate diagnostics, characters, >= 1
CODEX_STOP_HOOK_FINGERPRINT_CHUNK_BYTES = 1_048_576  # untracked-file hashing chunk, bytes, >= 1
