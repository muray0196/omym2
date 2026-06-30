# Organize Execution

This document is authoritative for `organize --library PATH`, first Library registration, existing Library rescan, unregistered path refusal, clean Library registration without mutation plan, organize Plan creation, and registration after successful apply.

Common execution rules are in [model.md](model.md). Path identity rules are in [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md).

## Library Registration Behavior

Library identity is defined in [../DOMAIN.md](../DOMAIN.md#library).

Registration is per Library and is tied to:

* `library_id`
* `path_policy_hash` or an equivalent identity for the current PathPolicy

Registration is not defined by whether the `tracks` table has rows.

Minimum representative registration fields:

* `library_id`
* `root_path`
* `path_policy_hash`
* `registered_at`
* `status`

Allowed status values are in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md#library-status).

Changing PathPolicy invalidates prior registration for that Library. After a PathPolicy change, `add` refuses to create a plan until the Library is registered again under the new PathPolicy. The expected remedy is `omym2 organize --library PATH`.

`organize` is the only supported path for an unregistered or unorganized Library to become usable by `add`.

`organize --library PATH` is the primary user-facing operation for registering and reconciling a Library.

Relink rules are defined in [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md#identity-rules).

## Organize Behavior

`organize --library PATH` scans the specified Library read-only and computes canonical paths under the current PathPolicy.

In the MVP, `organize --library PATH` supports these identity cases:

| Case | Policy |
| --- | --- |
| `PATH` matches an existing `libraries.root_path` | Rescan and organize the existing Library. |
| No Library exists yet | Create the first Library row and organize it. |
| `PATH` is unregistered while another Library already exists | Stop with a clear message. The path may be a moved Library or a second Library, and both are out of MVP scope. |

The MVP must not silently duplicate a Library when an unregistered path may represent an existing Library.

Plain `omym2 organize` is allowed only when exactly one known Library can be selected unambiguously. Otherwise it fails with a clear message and asks for `omym2 organize --library PATH`.

If files need to move or blocking actions must be reviewed, `organize` creates an organize Plan. `organize` does not move files directly except through `--apply` orchestration.

If no moves are needed and no blocking issues exist, `organize` can register the Library without creating a mutation Plan because DB-only Library state updates are not Library music file mutations.

If the organize Plan is applied successfully and no blocking Library-state issues remain, the Library becomes registered. Updating Library state after apply is a DB-only state change and does not create a FileEvent.

If blocked actions remain, the Library must not become registered.

Blocking issues include:

* missing required metadata
* canonical path conflicts
* invalid paths
* missing source files
* other problems preventing safe acceptance
