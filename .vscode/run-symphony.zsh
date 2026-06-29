#!/usr/bin/env zsh
# Summary: Launch OMYM2 Symphony from the VS Code folder-open task.
# Why: Keep startup logic out of fragile nested task JSON shell quoting.
set -euo pipefail

env_file="/home/muray/.config/omym2/symphony.env"
state_root="/home/muray/.local/state/omym2/symphony"
workspace_root="/home/muray/code/omym2-symphony-workspaces"
symphony_root="/home/muray/repos/symphony/elixir"
workflow_file="/home/muray/repos/omym2/WORKFLOW.md"
mise_bin="/home/linuxbrew/.linuxbrew/bin/mise"
flock_bin="/home/linuxbrew/.linuxbrew/bin/flock"

if [[ ! -r "$env_file" ]]; then
    print -u2 -- "Missing Symphony env file: $env_file"
    print -u2 -- "Create it with LINEAR_API_KEY=... and chmod 600."
    exit 1
fi

# Export sourced values so the Symphony child process can read LINEAR_API_KEY.
set -a
source "$env_file"
set +a

if [[ -z "${LINEAR_API_KEY:-}" ]]; then
    print -u2 -- "Missing LINEAR_API_KEY in $env_file"
    exit 1
fi

logs_root="${SYMPHONY_LOGS_ROOT:-$state_root}"
port="${SYMPHONY_PORT:-4001}"
lock_file="$logs_root/symphony.lock"

mkdir -p "$logs_root" "$workspace_root"
cd "$symphony_root"

# flock returns 75 when another VS Code window already owns the Symphony run.
set +e
"$flock_bin" -n -E 75 "$lock_file" \
    "$mise_bin" exec -- ./bin/symphony \
        --i-understand-that-this-will-be-running-without-the-usual-guardrails \
        --logs-root "$logs_root" \
        --port "$port" \
        "$workflow_file"
rc=$?
set -e

if [[ "$rc" -eq 75 ]]; then
    print -- "Symphony is already running for OMYM2."
    exit 0
fi

exit "$rc"
