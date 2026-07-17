#!/usr/bin/env bash
# Summary: One-command wrapper for the OMYM2 quality gates defined in docs/development/harness.md.
# Why: Gives agents a single reliable entry point instead of re-deriving command groups.
#
# Usage:
#   scripts/checks.sh <changed|completion|py|api|web|e2e|e2e-ci|package|performance|performance-ci|all|docs|arch>
#   scripts/checks.sh test <pytest-target>
#
# See docs/development/harness.md for canonical mode descriptions and gate policy.

set -euo pipefail

repository_root="$(git rev-parse --show-toplevel)"
check_output_script="$repository_root/scripts/check_output.py"
cd "$repository_root"

usage() {
    echo "usage: scripts/checks.sh <changed|completion|py|api|web|e2e|e2e-ci|package|performance|performance-ci|all|docs|arch> | scripts/checks.sh test <pytest-target>" >&2
}

run_check() {
    local label="$1"
    shift
    python3 "$check_output_script" --label "$label" -- "$@"
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
        return 0
    fi
    run_check "changed Python lint" uv run ruff check "${files[@]}" --fix --output-format=concise
    run_check "changed Python format" uv run ruff format "${files[@]}" -q
    run_check "changed Python types" uv run basedpyright "${files[@]}" --level error
}

run_py() {
    run_check "Python lint" uv run ruff check . --output-format=concise
    run_check "Python format" uv run ruff format . --check -q
    run_check "Python types" uv run basedpyright
    run_check "Python tests" uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout
}

run_api() (
    cd web
    run_check "generated API drift" npm run api:check
)

run_web() {
    run_api
    (
    cd web
    run_check "frontend format" npm run format:check
    run_check "frontend lint" npm run lint
    run_check "frontend types" npm run typecheck
    run_check "frontend unit tests" npm run test:unit
    run_check "frontend build" npm run build
    )
    run_check "Web static synchronization" uv run python scripts/web/sync_web_static.py
    run_check "Web static audit" uv run python scripts/web/audit_web_static.py
}

run_e2e_profile() {
    local fixture_profile="$1"
    shift
    run_check "browser tests ($fixture_profile profile)" uv run python scripts/web/run_web_test_server.py \
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

run_e2e_ci() {
    (
    cd web
    run_check "frontend build for browser tests" npm run build
    )
    run_check "Web static synchronization for browser tests" uv run python scripts/web/sync_web_static.py
    run_e2e_only
}

run_package() {
    run_check "package evidence" uv run python scripts/web/build_web_evidence.py
}

run_performance() {
    run_check "package performance" uv run python scripts/web/build_web_evidence.py --run-performance
}

run_performance_ci() {
    local wheel="$1"
    run_check "package performance" uv run python scripts/web/build_web_evidence.py --performance-wheel "$wheel"
}

run_docs() {
    run_check "docs bundle" uv run pytest tests/docs -q
}

run_completion() {
    local comparison
    local -a files=()
    local needs_docs=false
    local needs_python=false
    local needs_web=false
    local file

    if ! comparison="$(git merge-base HEAD origin/main 2>/dev/null)"; then
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
    run_check "Git whitespace" git diff --check "$comparison" --

    if [[ ${#files[@]} -eq 0 ]]; then
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
e2e-ci)
    run_e2e_ci
    ;;
package)
    run_package
    ;;
performance)
    run_performance
    ;;
performance-ci)
    wheel="${2:?usage: scripts/checks.sh performance-ci <wheel>}"
    run_performance_ci "$wheel"
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
    run_check "architecture tests" uv run pytest tests/architecture -q
    ;;
test)
    target="${2:?usage: scripts/checks.sh test <pytest-target>}"
    run_check "focused Python test" uv run pytest "$target" -q --tb=short --show-capture=all
    ;;
*)
    echo "checks.sh: unknown mode '$mode'" >&2
    usage
    exit 2
    ;;
esac

echo "checks.sh: mode '$mode' passed." >&2
