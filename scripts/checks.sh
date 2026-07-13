#!/usr/bin/env bash
# Summary: One-command wrapper for the OMYM2 quality gates defined in docs/development/harness.md.
# Why: Gives agents a single reliable entry point instead of re-deriving command groups.
#
# Usage:
#   scripts/checks.sh <changed|completion|py|api|web|e2e|package|performance|all|docs|arch>
#   scripts/checks.sh test <pytest-target>
#
# See docs/development/harness.md for canonical mode descriptions and gate policy.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

usage() {
    echo "usage: scripts/checks.sh <changed|completion|py|api|web|e2e|package|performance|all|docs|arch> | scripts/checks.sh test <pytest-target>" >&2
}

if [[ $# -eq 0 ]]; then
    usage
    exit 2
fi

mode="$1"

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

run_api() (
    cd web
    npm run api:check
)

run_web() {
    run_api
    (
    cd web
    npm run format:check
    npm run lint
    npm run typecheck
    npm run test:unit
    npm run build
    )
    uv run python scripts/sync_web_static.py
    uv run python scripts/audit_web_static.py
}

run_e2e_profile() {
    local fixture_profile="$1"
    shift
    uv run python scripts/run_web_test_server.py \
        --environment-variable OMYM2_E2E_BASE_URL \
        --working-directory web \
        --fixture-profile "$fixture_profile" \
        -- npm run test:e2e -- "$@"
}

run_e2e_only() {
    run_e2e_profile registered --grep-invert "@first-run"
    run_e2e_profile first-run --grep "@first-run"
}

run_e2e() {
    run_web
    run_e2e_only
}

run_package() {
    uv run python scripts/build_web_evidence.py
}

run_performance() {
    uv run python scripts/build_web_evidence.py --run-performance
}

run_docs() {
    uv run pytest tests/docs -q
}

run_completion() {
    local comparison
    local -a files=()
    local needs_docs=false
    local needs_python=false
    local needs_web=false
    local file

    if ! comparison="$(git merge-base HEAD origin/main 2>/dev/null)"; then
        echo "checks.sh: origin/main unavailable; running all completion check groups." >&2
        run_docs
        run_web
        run_py
        return
    fi

    mapfile -t files < <(
        {
            git diff --name-only --diff-filter=ACDMR "$comparison" --
            git ls-files --others --exclude-standard
        } | sort -u
    )
    git diff --check "$comparison" --

    if [[ ${#files[@]} -eq 0 ]]; then
        echo "checks.sh: no repository changes; nothing to complete." >&2
        return
    fi

    for file in "${files[@]}"; do
        case "$file" in
        src/omym2/adapters/web/*)
            needs_python=true
            needs_web=true
            ;;
        web/*)
            needs_web=true
            ;;
        *.py | *.pyi | src/* | tests/* | scripts/* | .codex/* | pyproject.toml | uv.lock | .python-version)
            needs_python=true
            ;;
        docs/* | .agents/* | AGENTS.md | ARCHITECTURE.md | README.md)
            needs_docs=true
            ;;
        *)
            needs_python=true
            ;;
        esac
    done

    if [[ "$needs_docs" == true && "$needs_python" == false ]]; then
        run_docs
    fi
    if [[ "$needs_web" == true ]]; then
        run_web
    fi
    if [[ "$needs_python" == true ]]; then
        run_py
    fi
}

case "$mode" in
changed)
    run_changed
    ;;
completion)
    run_completion
    ;;
py)
    run_py
    ;;
api)
    run_api
    ;;
web)
    run_web
    ;;
e2e)
    run_e2e
    ;;
package)
    run_package
    ;;
performance)
    run_performance
    ;;
all)
    run_web
    run_py
    run_e2e_only
    run_performance
    ;;
docs)
    run_docs
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
    usage
    exit 2
    ;;
esac

echo "checks.sh: mode '$mode' passed." >&2
