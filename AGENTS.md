# OMYM2 Agent Instructions

This repository uses the archived design document as the canonical source:
`docs/archive/omym2_design_document_v1.01.md`.

Before implementation work, read:

* `ARCHITECTURE.md` for architecture, dependency direction, layer responsibility, and source file naming rules.
* `docs/index.md` as the documentation entry point.
* The task-relevant document under `docs/` before changing files.

Non-negotiable rules:

* Library music file mutations must go through a Plan.
* Apply must use recorded PlanActions, not target paths recalculated from the latest AppConfig.
* FileEvents must be recorded before Library music file mutations.
* Domain and features must not depend on concrete adapters.
* Stored Library-managed paths are Library-root-relative.
* Run the relevant checks before marking work complete.
