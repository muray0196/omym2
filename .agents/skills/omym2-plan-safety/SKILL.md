---
name: omym2-plan-safety
description: Review any change that can affect Plan, PlanAction, Run, FileEvent, apply order, undo, or any Library music file mutation.
---

# OMYM2 Plan Safety

## Inputs
- changed_files
- affected feature or command
- whether Library music files may be mutated
- whether PlanAction / Run / FileEvent status logic is touched

## Read first
- docs/execution/model.md
- docs/execution/apply.md
- docs/execution/failure-policy.md
- docs/domain.md
- docs/storage.md
- docs/contracts/status-reason-catalog.md

## Read when tests or validation are in scope
- docs/testing.md

## Steps
1. Decide whether the change can lead to a Library music file mutation.
2. If yes, require a Plan-centered flow and reject direct mutation designs.
3. Verify the apply contract:
   - use recorded PlanActions
   - do not recalculate target paths from latest AppConfig
   - respect library_root_at_plan
4. Verify state transitions for:
   - Plan
   - PlanAction
   - Run
   - FileEvent
5. For each mutation attempt:
   - check preconditions first
   - persist FileEvent as pending before mutation
   - update FileEvent after mutation
   - update Track / PlanAction after confirmed mutation result
6. Distinguish:
   - blocked at plan time
   - failed before mutation
   - failed after mutation attempt
7. For refresh changes, verify that observed filesystem state updates Track/FileEvent/Plan state only through the documented contracts.
8. Require tests for every changed contract edge.

## Checks
- blocked actions stay blocked
- skip actions become applied without FileEvent
- precondition failure before mutation creates no FileEvent
- root mismatch before run prevents apply start
- terminal plans are single-use
- refresh does not directly mutate Library music files outside a Plan

## Outputs
- safety verdict: safe / risky / blocked
- blocking issues
- contract points touched
- minimum mandatory tests
- docs that must be updated
- docs checked
