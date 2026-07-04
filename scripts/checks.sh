#!/usr/bin/env bash
# Summary: One-command wrapper for the OMYM2 quality gates defined in docs/DEVELOPMENT.md.
# Why: Gives agents a single reliable entry point instead of re-deriving command groups.
#
# Usage:
#   scripts/checks.sh [changed|py|web|all|docs|arch]
#   scripts/checks.sh test <pytest-target>
#
# See docs/DEVELOPMENT.md for canonical mode descriptions and gate policy.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

mode="${1:-changed}"

run_changed() {
    local -a files=()
    local f
    while IFS= read -r f; do
        [[ -f "$f" ]] && files+=("$f")
    done < <(
        {
            git diff --name-only --diff-filter=ACMR HEAD -- '*.py' '*.pyi'
            git ls-files --others --exclude-standard -- '*.py' '*.pyi'
        } | sort -u
    )
    if [[ ${#files[@]} -eq 0 ]]; then
        echo "checks.sh: no changed Python files; nothing to check." >&2
        return 0
    fi
    echo "checks.sh: checking ${#files[@]} changed Python file(s)." >&2
    uv run ruff check "${files[@]}" --fix --output-format=concise
    uv run ruff format "${files[@]}" -q
    uv run basedpyright "${files[@]}" --level error
}

run_py() {
    uv run ruff check . --output-format=concise
    uv run ruff format . --check -q
    uv run basedpyright
    uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout
}

run_web() {
    cd web
    npm ci
    npm run format:check
    npm run lint
    npm run build
    cd ..
}

case "$mode" in
changed)
    run_changed
    ;;
py)
    run_py
    ;;
web)
    run_web
    ;;
all)
    run_web
    run_py
    ;;
docs)
    uv run pytest tests/docs -q
    ;;
arch)
    uv run pytest tests/architecture -q
    ;;
test)
    target="${2:?usage: scripts/checks.sh test <pytest-target>}"
    uv run pytest "$target" -q --tb=short --show-capture=all
    ;;
*)
    echo "checks.sh: unknown mode '$mode'" >&2
    echo "usage: scripts/checks.sh [changed|py|web|all|docs|arch] | scripts/checks.sh test <pytest-target>" >&2
    exit 2
    ;;
esac

echo "checks.sh: mode '$mode' passed." >&2
