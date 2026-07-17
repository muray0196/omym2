---
type: Development Guide
title: Windows Desktop Packaging
description: Windows x64 desktop build, audit, native smoke commands and evidence, CI boundary, and release gates.
tags: [development, desktop, windows, packaging, pyinstaller, musicbrainz, smoke-test]
timestamp: 2026-07-18T12:00:00+09:00
---

# Windows Desktop Packaging

Authoritative for building, auditing, and smoke-testing the Windows desktop artifact. Decision: [ADR 0004](../decisions/0004-windows-desktop-application.md); application-data ownership: [Storage](../STORAGE.md#application-root-selection); quality-gate routing: [Development Harness](harness.md).

## Supported Target And Prerequisite

The only supported desktop v1 target is native Windows 11 x64 — no cross-builds, no relabeled architectures, no macOS/Linux claims.

pywebview 6.2.1 with the `edgechromium` backend requires the shared Evergreen Microsoft Edge WebView2 Runtime; native package smoke must check it rather than assume it (repair via Microsoft's [WebView2 distribution guidance](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)). A fixed WebView2 Runtime, Chromium, Electron, CEF, QtWebEngine, or renderer fallback must not be added to the archive.

Before importing pywebview, OMYM2 checks for .NET Framework 4.6.2+ and at least one official per-machine or per-user Evergreen WebView2 registration; every present registration value must be readable, valid, and version `146.0.3856.49` or newer (the full-compatibility floor for pywebview 6.2.1's bundled WebView2 SDK). With both registrations present, the startup log reports the lower version as the guaranteed floor. Inherited `WEBVIEW2_*`/`COREWEBVIEW2_*` overrides are rejected, as are applicable HKLM/HKCU loader-policy values for `BrowserExecutableFolder`, `ChannelSearchKind`, `ReleaseChannels`, `AdditionalBrowserArguments`, and `UserDataFolder`. Missing, unreadable, or invalid prerequisites are a visible startup failure; the application must not enter pywebview's deprecated MSHTML fallback.

## Audited Input And Toolchain

The Windows package consumes the exact audited wheel from the Linux package-evidence gate — never freezing a source checkout, rebuilding the React app, or selecting a wheel by version alone. The build uses an isolated environment, installs the wheel with its `desktop` extra, and uses PyInstaller 6.21.0. The wheel already contains the synchronized `static_dist`, SQLite migrations, and package metadata; PyInstaller produces an inspectable `onedir` tree (`OMYM2.exe`, frozen Python runtime, native pywebview support, audited resources) normalized into `OMYM2-<version>-windows-x86_64.zip`. Users install no separate Python or Node.js; Node stays a frontend build dependency absent from the ZIP; Chromium is neither build input nor packaged runtime.

## Artist-Naming Distribution Boundary

The audited wheel and Windows ZIP use deterministic Unicode-script eligibility and contain no artist language-model runtime or data. The packaged default is `musicbrainz.enabled = true`; users can disable new provider work while retaining saved mappings and original-metadata fallback without network work. Package audit prohibits arbitrary `.bin`/`.ftz` model files. Windows 11 x64 package smoke and startup/memory measurements remain release evidence requirements, including proof that disabled MusicBrainz lookup performs no provider request.

## Build And Audit

On native Windows x64 from the repository root, passing the audited wheel explicitly:

```powershell
uv run python scripts/desktop/build_windows.py --wheel <audited.whl> --output-directory build/desktop
```

The build must reject: wrong host architecture, invalid wheel, missing or changed audited resources, unsafe archive paths, source-tree content, Node.js or Chromium files, alternate WebView renderers, incorrect PE metadata or icon, and non-Windows/non-x64 pywebview resources. It emits three sibling files in `build/desktop/`: the ZIP, `.zip.sha256`, and `.zip.json`. The JSON records archive size, container SHA-256, canonical member-payload SHA-256, PE and renderer audit, exact wheel and locked-input identities, audited resource count, frozen-runtime distribution/license inventory, and the unresolved project-license state. Frozen provenance embeds the input wheel SHA-256; every archive audit requires it to match the supplied wheel — equal versions or selected resource hashes cannot substitute.

The package directory is replaceable: Config, SQLite, and logs are never written into it, so replacing or deleting the extracted archive leaves `%LOCALAPPDATA%\OMYM2` intact. Build and removal workflows must not migrate or delete that stable user-data root.

## Native Smoke

```powershell
uv run python scripts/desktop/smoke_windows_package.py --archive <zip> --wheel <audited.whl>
```

The default command relaunches the same audited archive from two extracted copies — proving application-directory replacement and removal, not a build transition. To validate the upgrade boundary, pass two genuinely different audited builds explicitly:

```powershell
uv run python scripts/desktop/smoke_windows_package.py `
  --previous-archive <build-a.zip> `
  --previous-wheel <build-a.whl> `
  --archive <build-b.zip> `
  --wheel <build-b.whl>
```

Both pairs receive the complete package audit and provenance-to-wheel identity check; supplying only one previous input fails. The transition compares a canonical digest of sorted member paths and uncompressed bytes, so repacking or ZIP-metadata changes cannot masquerade as another build, and reproducible rebuilds of identical inputs are intentionally rejected as cross-build evidence. Two different builds of the current version are labeled `cross_build_same_package_version` — not a version or database-schema migration claim; differing package versions are rejected. A genuine cross-version claim requires real successor-version artifacts and separately defined migration acceptance.

The smoke uses one isolated Unicode and long-path `%LOCALAPPDATA%` root and the real GUI executable; each process gets an unrelated, dedicated, short, initially empty working directory that must remain unchanged after both launches (catching relative Config/database/log/sidecar writes). Copy A: extract, launch, check the WebView2 prerequisite and selected `edgechromium` renderer, require exactly one visible OMYM2 window and no external browser, accept the content-loaded marker only after the exact loopback root returns HTTP 200 with successful pywebview injection; verify every shell and planning route, a hashed asset, Bootstrap and Settings responses, production HTTP security, empty-Library registration, and one tagged-input Add operation whose ready Plan persists across relaunch.

After copy A closes: record Config and SQLite evidence, delete the entire extracted copy, extract copy B to a different directory, relaunch against the same stable `%LOCALAPPDATA%` root — the Config marker and copy-A SQLite hash must survive. On copy B, Microsoft UI Automation binds the packaged HWND, finds WebView2's `RootWebArea`, and keeps every lookup inside that document: invoke the Overview action and all six primary shell routes, find the loaded Settings editor, open Add through the Command Center, set the real React source field through `ValuePattern`, submit through `InvokePattern`, and require the ready Plan-detail controls. API readbacks only verify that this native interaction created exactly one additional ready Add Plan. Before/after manifests require both the incoming and empty Library trees unchanged. The smoke records the resulting SQLite hash, sends `WM_CLOSE`, requires process and listener termination, and verifies that deleting copy B preserves the exact final database state.

The run writes `<archive-stem>-smoke.json` beside the ZIP: candidate ZIP and exact audited wheel identity, both audited container and payload identities with their honest transition kind, and native startup, graceful-shutdown, relaunch, listener, archive/extracted-size, renderer, process/window, route/security, stable-state, and resolved-path observations. Keep both JSON records, the SHA-256 sidecar, and the ZIP as one local evidence set. These are measurements from the native run — this guide never claims a smoke passed merely because scripts or artifacts exist. The smoke evidence distinguishes HTTP/API contract probes from the UI Automation interaction; it proves core React interaction in the native WebView but does not replace the browser-hosted Playwright suite or a visual review of unchanged rendering.

## CI Boundary

The hosted `windows-2025` CI job downloads the short-lived audited wheel, first runs the native filesystem and runtime boundary suite (rooted observation/mutation, scanner containment, concrete companion and unprocessed adapter E2E, real multiprocess lock behavior, desktop runtime tests; retained-HANDLE mechanics: [Path Identity And Storage Contract](../contracts/path-identity-storage.md#retained-observation-and-mutation-boundary)), then builds the ZIP, runs the native package smoke, and retains the package-audit JSON, native-smoke JSON, and SHA-256 sidecar. The ZIP exists only long enough to build, audit, and smoke; CI does not upload or publish it.

This Windows Server 2025 x64 run is the native development-build and smoke proxy, not Windows 11 release evidence. Release validation is a separate run of the same packaged smoke (including UI Automation) on the supported workstation target with JSON evidence retained; the smoke record includes the observed Windows edition, build, installation type, product type, and machine architecture so Server CI cannot be relabeled. Failure to create any required evidence file fails either run.

## Release Gates

Locally generated ZIPs are unsigned development builds; CI retains evidence but does not publish its ephemeral ZIP. Public redistribution remains blocked: the repository declares no owner-approved project license and ships no complete third-party notice set — in particular Mutagen 1.48.1 declares GPL-2.0-or-later on its [official PyPI record](https://pypi.org/project/mutagen/). This document does not select a license; the owner must approve one, and the distribution must satisfy its own and every bundled dependency's notice and source obligations first. A signed release also requires an explicitly authorized Windows code-signing identity, secret-handling workflow, signature verification gate, and release policy. Never present an unsigned local ZIP as signed or production-trusted.

## Release Checklist

Every row is a blocking release gate, not a claim the current artifact has passed:

| Gate | Evidence required before release |
| --- | --- |
| Supported target | The candidate ZIP passes the complete packaged HTTP and UI Automation smoke on Windows 11 x64, its smoke JSON is retained, and a native-window visual review confirms unchanged rendering. Hosted Windows Server or HTTP/API-only evidence is insufficient. |
| Artifact integrity | ZIP, `.zip.sha256`, package-audit JSON, and smoke JSON agree on version, archive identity, and canonical payload identity; frozen provenance binds the archive to the exact audited wheel and all required resources. |
| Artist naming | The artifact inventory proves no artist language model is bundled, wheel resources match byte-for-byte, and disabled MusicBrainz lookup preserves the local-only provider boundary. |
| Licensing | The repository contains an owner-approved project license and a complete, verified third-party notice/source-obligation set for every bundled component. |
| Signing | An authorized Windows identity signs the candidate through an approved secret-handling workflow, and an independent gate verifies its signature and expected publisher. |
| Extract, upgrade, remove | Clean extract, payload-distinct cross-build replacement, and application-directory removal all leave `%LOCALAPPDATA%\OMYM2` Config, SQLite state, and logs intact; the retained smoke JSON identifies both artifacts, and deleting user data remains a separate explicit action. |

Until every row is satisfied, the ZIP remains an unsigned development artifact.
