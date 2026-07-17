---
type: Development Guide
title: Windows Desktop Packaging
description: Defines the Windows x64 desktop build, renderer and artist-naming distribution boundaries, native filesystem and package-smoke CI evidence, data lifecycle, licensing, and signing.
tags: [development, desktop, windows, packaging, pyinstaller, musicbrainz, smoke-test]
timestamp: 2026-07-17T22:43:57+09:00
---

# Windows Desktop Packaging

This document is authoritative for building, auditing, and smoke-testing the
Windows desktop artifact. The architecture decision is
[ADR 0004](../decisions/0004-windows-desktop-application.md), application-data
ownership is [Storage](../STORAGE.md#application-root-selection), and general
quality-gate routing remains in [Development Harness](harness.md).

## Supported Target And Prerequisite

The only supported desktop v1 target is native Windows 11 x64. Do not
cross-build it, relabel another Windows architecture, or claim macOS or Linux
desktop support from this artifact.

OMYM2 uses pywebview 6.2.1 with the `edgechromium` backend and requires the
shared Evergreen Microsoft Edge WebView2 Runtime. Windows 11 normally includes
this runtime, but native package smoke must check it rather than assume its
presence. Install or repair the Evergreen Runtime through Microsoft's
[WebView2 distribution guidance](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
before retrying a missing-prerequisite failure. A fixed WebView2 Runtime,
Chromium, Electron, CEF, QtWebEngine, or renderer fallback must not be added to
the archive.

Windows 11 includes a compatible .NET Framework 4.x runtime. Before importing
pywebview, OMYM2 checks for .NET Framework 4.6.2 or newer and requires at least
one official per-machine or per-user Evergreen WebView2 registration. Every
present registration value must be readable, valid, and version
`146.0.3856.49` or newer, matching the full-compatibility floor for the WebView2
SDK bundled by pywebview 6.2.1. When both registrations are present, the startup
log reports the lower version as the guaranteed runtime floor. Inherited
`WEBVIEW2_*` and `COREWEBVIEW2_*` overrides are rejected so a custom runtime,
profile, channel, or debugger cannot replace the checked environment.
Applicable HKLM or HKCU loader-policy values for `BrowserExecutableFolder`,
`ChannelSearchKind`, `ReleaseChannels`, `AdditionalBrowserArguments`, and
`UserDataFolder` are also rejected for the packaged executable before startup.
Missing, unreadable, or invalid prerequisites are a visible startup failure;
the application must not enter pywebview's deprecated MSHTML fallback path.

## Audited Input And Toolchain

The Windows package consumes the exact audited wheel produced by the existing
Linux package-evidence gate. It never freezes a source checkout, rebuilds the
React application, or selects a different wheel by version alone. The build
uses an isolated environment, installs that wheel with its `desktop` extra, and
uses PyInstaller 6.21.0.

The audited wheel already contains the synchronized `static_dist`, SQLite
migrations, and package metadata. PyInstaller produces an inspectable `onedir`
tree with `OMYM2.exe`, its frozen Python runtime, native pywebview support, and
those audited resources. The tree is normalized into:

```text
OMYM2-<version>-windows-x86_64.zip
```

Users do not install Python or Node.js separately. Node.js remains a frontend
build dependency and is absent from the ZIP; Chromium is neither a build input
nor a packaged runtime.

## Artist-Naming Distribution Boundary

The audited wheel and Windows ZIP use deterministic Unicode-script eligibility
and contain no artist language-model runtime or data. The packaged default is
`musicbrainz.enabled = true`; users can disable new provider work while
retaining saved original-to-Latin mappings and original metadata fallback
without network work.

Package audit prohibits arbitrary `.bin` or `.ftz` model files. Windows 11 x64
package smoke and startup/memory measurements remain release evidence
requirements, including proof that disabled MusicBrainz lookup performs no
provider request.

## Build And Audit

Run this command on native Windows x64 from the repository root, passing the
audited wheel explicitly:

```powershell
uv run python scripts/desktop/build_windows.py --wheel <audited.whl> --output-directory build/desktop
```

The build must reject the wrong host architecture, an invalid wheel, missing or
changed audited resources, unsafe archive paths, source-tree content, Node.js or
Chromium files, alternate WebView renderers, incorrect PE metadata or icon, and
non-Windows/non-x64 pywebview resources. It emits these three sibling files in
`build/desktop/`:

```text
OMYM2-<version>-windows-x86_64.zip
OMYM2-<version>-windows-x86_64.zip.sha256
OMYM2-<version>-windows-x86_64.zip.json
```

The JSON records the archive size, container SHA-256, canonical member-payload
SHA-256, PE and renderer audit, exact wheel and locked-input identities,
audited resource count, frozen-runtime
distribution/license inventory, and the unresolved project-license state.
The frozen provenance embeds the input wheel SHA-256, and every archive audit
requires it to match the supplied wheel; equal versions or selected resource
hashes cannot substitute for that exact identity.

The package directory is replaceable. Config, SQLite, and logs are never
written into it; replacing or deleting the extracted archive therefore leaves
`%LOCALAPPDATA%\OMYM2` intact. The build and removal workflow must not migrate
or delete that stable user-data root.

## Native Smoke

Smoke the produced archive against the same audited wheel:

```powershell
uv run python scripts/desktop/smoke_windows_package.py --archive <zip> --wheel <audited.whl>
```

That default command relaunches the same audited archive from two extracted
copies. It proves application-directory replacement and removal, not a
transition between builds. To validate the upgrade boundary, provide two
genuinely different audited application builds, such as candidates before and
after an application change, and pass the first pair explicitly:

```powershell
uv run python scripts/desktop/smoke_windows_package.py `
  --previous-archive <build-a.zip> `
  --previous-wheel <build-a.whl> `
  --archive <build-b.zip> `
  --wheel <build-b.whl>
```

Both archive/wheel pairs receive the complete package audit and provenance-to-
wheel identity check. Supplying only one previous input fails. The transition
compares a canonical digest of sorted member paths and uncompressed bytes, so
repacking, recompressing, or changing ZIP metadata on the same payload cannot
masquerade as another build. Reproducible rebuilds of the same inputs may be
identical and are intentionally rejected as cross-build evidence. For two
different builds of the current package version, the retained evidence labels
the transition `cross_build_same_package_version`; it does not claim a version
or database-schema migration. Differing package versions are rejected by this
contract. A genuine cross-version claim requires real successor-version
artifacts and separately defined migration acceptance, not a fabricated
version bump.

The smoke uses one isolated Unicode and long-path `%LOCALAPPDATA%` root and the
real GUI executable. Each process receives an unrelated, dedicated, short,
initially empty working directory; the smoke requires that tree to remain
unchanged after both launches, preventing relative Config, database, log, or
sidecar writes from escaping detection. It extracts and launches copy A, checks the shared
Evergreen WebView2 prerequisite and selected `edgechromium` renderer, requires
exactly one visible OMYM2 window and no new external browser process or window,
and accepts the content-loaded marker only after the exact loopback root returns
HTTP 200 and pywebview's document injection succeeds. Through the packaged
listener it verifies every shell and planning route, a hashed asset, Bootstrap
and Settings responses, production HTTP security, empty-Library registration,
and one tagged-input Add operation whose ready Plan persists across relaunch.

After copy A closes, the smoke records Config and SQLite evidence, deletes the
entire extracted copy, extracts copy B to a different directory, and relaunches
it against the same stable `%LOCALAPPDATA%` root. The Config marker and copy-A
SQLite hash must survive application-directory replacement before the second
interaction. On copy B, Microsoft UI Automation binds the packaged HWND, finds
WebView2's `RootWebArea`, and keeps every subsequent lookup inside that
document. It invokes the Overview action and all six primary shell routes;
finds the loaded Settings editor; opens Add through the Command Center; sets the
real React source field through `ValuePattern`; submits through `InvokePattern`;
and requires the ready Plan-detail controls. API readbacks only snapshot and
verify that this native interaction created exactly one additional ready Add
Plan. Complete before/after manifests require both the incoming and empty
Library trees to remain unchanged. The smoke records the resulting SQLite hash,
sends `WM_CLOSE`, requires the process and listener to terminate, and verifies
that deleting copy B preserves that exact final database state.

The run writes `<archive-stem>-smoke.json` beside the ZIP. The smoke record
identifies the candidate ZIP and exact audited wheel, records both audited
container and payload identities and their honest transition kind, and contains native startup,
graceful-shutdown, relaunch, listener, archive-size, extracted-size, renderer,
process/window, route/security, stable-state, and resolved-path observations.
The sibling package-audit JSON records the build and audit provenance. Keep both
JSON records, the SHA-256 sidecar, and ZIP together as one local evidence set.
Hosted CI keeps the JSON evidence and checksum but does not publish its
ephemeral ZIP. These are measurements from the native run; this guide does not
claim that a native smoke passed merely because the scripts or artifact exist.
The smoke evidence distinguishes HTTP/API contract probes from the UI
Automation interaction and resulting Plan readback. It proves core React
interaction in the native WebView but does not replace the full browser-hosted
Playwright suite or a visual review of unchanged rendering.

## CI Boundary

The hosted `windows-2025` CI job downloads the short-lived audited wheel and
first runs the native filesystem and runtime boundary suite: rooted file
observation and mutation, scanner containment, concrete companion and
unprocessed adapter E2E, real multiprocess lock behavior, and desktop runtime
tests. The retained-HANDLE mechanics exercised there are authoritative in the
[Path Identity And Storage Contract](../contracts/path-identity-storage.md#retained-observation-and-mutation-boundary).
CI then builds the ZIP with the command above, runs the native package smoke,
and retains the package-audit JSON, native-smoke JSON, and SHA-256 sidecar. The
ZIP exists only long enough to build, audit, and smoke it; CI does not upload or
publish that package.

This Windows Server 2025 x64 run is the native development-build and smoke
proxy; it is not evidence that the end-user Windows 11 x64 target has passed
release validation. Windows 11 release validation remains a separate run of
the same packaged smoke on the supported workstation target, including its UI
Automation flow, with the JSON evidence retained. The smoke record includes the
observed Windows edition, build, installation type, product type, and machine
architecture so Server CI cannot be relabeled as Windows 11 workstation
evidence. Its default same-artifact relaunch is replacement evidence, not a
cross-build upgrade claim. Failure to create any required evidence file fails
either run.

## Release Gates

Locally generated ZIPs are unsigned development builds for native validation,
not public releases. CI retains evidence but does not publish its ephemeral ZIP.
Public redistribution remains blocked because the repository does not yet
declare an owner-approved project license and does not ship a complete
third-party notice set. In particular, Mutagen 1.48.1 declares
GPL-2.0-or-later on its [official PyPI record](https://pypi.org/project/mutagen/).
This document does not select a project license; the owner must approve one and
the complete distribution must satisfy its own and every bundled dependency's
notice and source obligations before public redistribution.

A signed release also requires an explicitly authorized Windows code-signing
identity, secret-handling workflow, signature verification gate, and release
policy. Do not present an unsigned local ZIP as a signed or production-trusted
artifact.

## Release Checklist

Every row is a blocking release gate, not a claim that the current development
artifact has passed:

| Gate | Evidence required before release |
| --- | --- |
| Supported target | The candidate ZIP passes the complete packaged HTTP and UI Automation smoke on Windows 11 x64, its smoke JSON is retained, and a native-window visual review confirms unchanged rendering. Hosted Windows Server or HTTP/API-only evidence is insufficient. |
| Artifact integrity | ZIP, `.zip.sha256`, package-audit JSON, and smoke JSON agree on version, archive identity, and canonical payload identity; frozen provenance binds the archive to the exact audited wheel and all required resources. |
| Artist naming | The artifact inventory proves no artist language model is bundled, wheel resources match byte-for-byte, and disabled MusicBrainz lookup preserves the local-only provider boundary. |
| Licensing | The repository contains an owner-approved project license and a complete, verified third-party notice/source-obligation set for every bundled component. |
| Signing | An authorized Windows identity signs the candidate through an approved secret-handling workflow, and an independent gate verifies its signature and expected publisher. |
| Extract, upgrade, remove | Clean extract, payload-distinct cross-build replacement, and application-directory removal all leave `%LOCALAPPDATA%\OMYM2` Config, SQLite state, and logs intact; the retained smoke JSON identifies both artifacts, and deleting user data remains a separate explicit action. |

The current repository has no owner-approved project license or authorized
Windows signing workflow, so public redistribution remains blocked regardless
of package or smoke success. Until every row is satisfied, the ZIP remains an
unsigned development artifact.
