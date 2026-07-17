---
type: Development Guide
title: Pipeline Performance Benchmark
description: Reproducible end-to-end pipeline benchmark procedure, release measurement record, and trust-stat comparison.
tags: [development, performance, benchmark, pipeline, musicbrainz, hashing]
timestamp: 2026-07-18T12:00:00+09:00
---

# Pipeline Performance Benchmark

Authoritative for the end-to-end pipeline benchmark used to measure performance changes. Developer quality gates: [harness.md](harness.md). Run before and after a performance change:

```bash
uv run python scripts/benchmark_pipeline.py \
  --tracks 100 \
  --file-size-bytes 1048576 \
  --tracks-per-album 10
```

`--tracks` sets dataset size; `--file-size-bytes` the exact size of each generated file (minimum 4096 bytes so fixtures contain valid FLAC metadata); `--tracks-per-album` the album shape. Use `--workspace-root PATH` to place the disposable workspace on the filesystem being measured (default: OS temp directory).

The harness registers an empty Library through the public `organize` command, generates tagged synthetic FLAC files in Incoming, then runs the clean baseline — `add`, `apply latest --yes`, `organize`, `check` — through fresh `python -m omym2` processes, so each stage timing includes CLI startup and the real composition, metadata, filesystem, hashing, and SQLite pathways.

After the clean check, setup changes the path-neutral genre tag on every managed FLAC and appends a one-byte payload sentinel so every filesystem reports a size mismatch from the persisted baseline, then creates an unapplied `refresh --all` Plan with one `refresh_metadata` action per Track. A second measured `check_ready_plan` stage exercises the managed-Track / `ready` Plan source diagnostic overlap; it intentionally exits nonzero and requires one `content_hash_changed` and one `metadata_hash_changed` result per Track.

Bootstrap, fixture generation, tag mutation, and `ready` Plan creation report as `setup.*` timings. `stage.measured_total_seconds` is the clean-baseline total; `stage.extended_measured_total_seconds` adds only the measured `check_ready_plan` stage; neither includes setup. The workspace is deleted after the run. Compare runs only with identical dataset arguments and workspace filesystem; the harness does not clear OS filesystem caches.

## Release Measurement Record

A release performance record uses a fixed dataset and records together: the benchmark header and every `setup.*`/`stage.*` value; total input bytes (`tracks * file_size_bytes`) and effective hash throughput per full-observation stage (total input bytes / stage seconds); peak resident memory or working set per fresh CLI process via the target OS's process monitor; the exclusive-operation wall time of each state-changing command stage; and storage medium, OS, Python version, OMYM2 revision, hashing chunk size, and whether `--trust-stat` was used. Effective throughput includes metadata, SQLite, and process-startup overhead — an end-to-end comparison metric, not raw SHA-256 speed. Compare memory and throughput only across records with the same dataset and environment.

Release evidence includes a separate persisted-settings run recording: Python version and Windows architecture; unique non-Latin source-name count, accepted-cache hit count, and provider request count; cold time and peak working set through the first eligible provider lookup; and a second-run sticky-cache result that must make no provider request for an already accepted source. Provider counts use deterministic fixtures or a controlled test endpoint, never live MusicBrainz. The request count must not exceed unique eligible cache misses; disabled, ambiguous, timeout, and offline cases stay in the normal automated test gates. Packaging qualification and required Windows smoke evidence: [Desktop Packaging](desktop-packaging.md#artist-naming-distribution-boundary).

## Trust-Stat Comparison

Add `--trust-stat` to forward the explicit opt-in to measured organize/check stages and the post-mutation refresh/check setup:

```bash
uv run python scripts/benchmark_pipeline.py \
  --tracks 100 --file-size-bytes 1048576 --tracks-per-album 10 --trust-stat
```

The output header records `trust_stat=true|false`. Apply is unchanged in both modes and always performs full source hashing. On the clean organize/check stages, a true run measures the stat-only path after apply populated verified baselines; after tag mutation, the sentinel-forced size mismatch sends refresh and `ready` Plan check back to full capture, verifying fallback independently of filesystem timestamp precision.
