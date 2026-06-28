# Codex Subagents

This document is authoritative for OMYM2 Codex subagent routing, model choice,
reasoning effort, and handoff rules.

OMYM2 uses subagents for bounded evidence gathering, test triage, focused
patches, contract checks, and risk review. The main agent owns planning,
architecture judgment, final correctness judgment, and the final user response.

## Operating Model

Default pattern:

```text
Spark collects evidence.
Spark may patch only after the parent defines exact scope.
5.4-mini checks contract surfaces.
5.4 reviews risky behavior.
Main agent decides.
```

Do not spawn subagents just to use every configured model. Use a subagent only
when parallelism, context isolation, or a focused specialist prompt improves the
task.

## Configured Agents

| Agent | Model | Reasoning | Sandbox | Purpose |
| --- | --- | --- | --- | --- |
| `scout` | `gpt-5.3-codex-spark` | `medium` | `read-only` | Find files, symbols, call paths, related tests, and dependency edges. |
| `test_triage` | `gpt-5.3-codex-spark` | `medium` | `workspace-write` | Run targeted tests and classify failures without source edits. |
| `patch_spark` | `gpt-5.3-codex-spark` | `medium` | `workspace-write` | Make a small parent-scoped patch and run focused verification. |
| `contract_check` | `gpt-5.4-mini` | `medium` | `read-only` | Check API, type, schema, config, docs, prompt, and skill consistency. |
| `risk_review` | `gpt-5.4` | `high` | `read-only` | Review Plan, apply, undo, storage, paths, DB, security, and data-loss risk. |

Avoid Spark `high`. If a Spark task appears to need high reasoning, keep the
work with the main agent or escalate to `risk_review`.

## Spark Boundaries

Spark agents are evidence collectors first.

Spark may:

* run targeted `rg`, `sed`, `git diff`, and focused test commands
* identify relevant files, symbols, call paths, and test targets
* summarize logs or failures
* apply a narrow patch when the parent names the files, behavior, and limits

Spark must not:

* make architecture decisions
* decide that a risky path is safe
* treat "not found" as proof that behavior does not exist
* change Plan, apply, undo, storage, path identity, DB schema, or file mutation
  behavior without parent review
* perform broad cleanup, renames, or formatting churn

Every Spark response must include commands run, file/path evidence, unknowns,
and a confidence label.

## Escalation Rules

Use `contract_check` for surface consistency:

* DTOs, ports, config, schema, CLI/Web forms, docs, prompts, and skills
* renamed fields, changed command behavior, or changed validation contracts
* contract docs under `docs/contracts/`, execution docs under `docs/execution/`, and architecture docs under `docs/architecture/`

Use `risk_review` for high-risk behavior:

* Plan, PlanAction, Run, FileEvent, apply, undo, refresh, organize, or check
* Library identity, stored paths, PathPolicy, relink, registration, or DB state
* security, permission, data-loss, migration, cross-module, or race-condition
  risk

The main agent must re-read cited code before accepting any risky conclusion.

## Concurrency

Keep `agents.max_depth = 1`.

Use at most one write-capable subagent at a time. Read-only scout, contract, and
risk-review agents may run in parallel when their scopes do not overlap heavily.

Subagents should return concise summaries, not raw logs.
