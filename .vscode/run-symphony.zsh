#!/usr/bin/env zsh
# Summary: Launch OMYM2 Symphony from the VS Code folder-open task.
# Why: Keep startup logic out of fragile nested task JSON shell quoting.
set -euo pipefail

# Resolve repo-local paths from this script so the VS Code task can move with the checkout.
script_dir="${0:A:h}"
repo_root="${script_dir:h}"

config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
state_home="${XDG_STATE_HOME:-$HOME/.local/state}"

env_file="$config_home/omym2/symphony.env"
state_root="$state_home/omym2/symphony"
workspace_root="$HOME/code/omym2-symphony-workspaces"
symphony_root="$HOME/repos/symphony/elixir"
workflow_file="$repo_root/.symphony/WORKFLOW.md"
mise_bin="${commands[mise]:-}"
flock_bin="${commands[flock]:-}"

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

if [[ -z "$mise_bin" ]]; then
    print -u2 -- "Missing mise executable. Add it to PATH before VS Code starts."
    exit 1
fi

if [[ -z "$flock_bin" ]]; then
    print -u2 -- "Missing flock executable. Add it to PATH before VS Code starts."
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
