# OMYM2 Agent Instructions

This repository keeps the original preliminary design document here:

`docs/archive/omym2_design_document_v1.01.md`

The archived design document is the original reference. Current task-specific rules are maintained in the split documentation files under `docs/`.

Before non-trivial implementation work, read:

* `ARCHITECTURE.md`
* `docs/index.md`
* `docs/development.md` for quality gates when code or tests change
* The task-relevant document listed in `docs/index.md`

Non-negotiable rules:

* Library music file mutations must go through a Plan.
* Apply must use recorded PlanActions, not recalculated target paths.
* FileEvents must be recorded before Library music file mutations.
* Domain and features must not depend on concrete adapters.
* Stored Library-managed paths are Library-root-relative.
* Run the relevant checks before marking work complete.

If documents conflict, report it. Prefer current task-specific docs over the archived design document.
