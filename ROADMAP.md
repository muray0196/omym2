# Web UI Roadmap

## Current State

The large-data browsing foundation, grouped Plan review, grouped Check triage,
Tracks library browser, and consistent faceted search are complete.

## Outcome and Boundary

Evolve the Web UI into a library audit console and safe operations navigator.
It remains a review, triage, and diagnosis surface; CLI apply remains the only
execution path until a later, explicit safety decision. It is not a music
player.

## Remaining Ordered Work

6. **Cross-links** — Navigate directly between related Tracks, Plan actions,
   Check issues, Runs, and Path Preview without copying identifiers.
7. **Dashboard next actions** — Route users from material risks and blocked work
   into the relevant grouped or filtered view.
8. **Command Palette** — Add global navigation and search after the underlying
   browse APIs can support it.
9. **Settings split** — Separate ordinary settings from safety-sensitive or
   advanced controls.
10. **GUI apply decision** — Consider only after the preceding review and
    diagnosis workflows are mature; retain the reviewed-Plan safety model.

## Validation

Keep each milestone independently reviewable, preserve existing CLI execution
safety and API contracts unless deliberately changed, and run the relevant
checks before completion.
