---
type: Development Guide
title: Pipeline Performance Benchmark
description: Defines the reproducible end-to-end pipeline benchmark, its dataset, release measurement record, naming-runtime qualification, and trust-stat comparison procedure.
tags: [development, performance, benchmark, pipeline, fasttext, musicbrainz, hashing]
timestamp: 2026-07-16T03:48:55+09:00
---

# Pipeline Performance Benchmark

This document is authoritative for the end-to-end pipeline benchmark used to
measure performance changes. Developer quality gates remain in
[harness.md](harness.md).

Run the benchmark before and after a performance change:

```bash
uv run python scripts/benchmark_pipeline.py \
  --tracks 100 \
  --file-size-bytes 1048576 \
  --tracks-per-album 10
```

`--tracks` controls the total dataset size. `--file-size-bytes` controls the
exact size of each generated file, and `--tracks-per-album` controls the album
shape. The minimum file size is 4096 bytes so every fixture can contain valid
FLAC metadata. Use `--workspace-root PATH` to place the disposable workspace on
the filesystem being measured; otherwise the operating system's temporary
directory is used.

The harness first registers an empty Library through the public `organize`
command, then generates tagged synthetic FLAC files in Incoming. Its clean
baseline runs `add`, `apply latest --yes`, `organize`, and `check` through fresh
`python -m omym2` processes. Each stage timing therefore includes CLI startup
and the real composition, metadata, filesystem, hashing, and SQLite pathways.

After the clean check, setup changes the path-neutral genre tag on every managed
FLAC and appends a one-byte payload sentinel so every filesystem reports a size
mismatch from the persisted baseline. It then creates an unapplied
`refresh --all` Plan containing one `refresh_metadata` action per Track. A
second measured `check_ready_plan` stage exercises the overlap between
managed-Track and `ready` Plan source diagnostics. That diagnostic check
intentionally exits nonzero because every Track differs from persisted managed
state; the harness requires one `content_hash_changed` and one
`metadata_hash_changed` result per Track.

Bootstrap, fixture generation, tag mutation, and `ready` Plan creation are
reported as `setup.*` timings. `stage.measured_total_seconds` retains the
original clean-baseline total, while `stage.extended_measured_total_seconds`
adds only the measured `check_ready_plan` stage; neither includes setup. The
temporary workspace is deleted after the run.

Compare runs only when dataset arguments and workspace filesystem are the same.
The harness does not clear operating-system filesystem caches.

## Release Measurement Record

A release performance record uses a fixed dataset and records all of the
following together:

* the benchmark header and every `setup.*` and `stage.*` value;
* total input bytes (`tracks * file_size_bytes`) and effective hash throughput
  for each full-observation stage (`total input bytes / stage seconds`);
* peak resident memory or peak working set for each fresh CLI process, captured
  with the target operating system's process monitor;
* the exclusive-operation wall time represented by each state-changing command
  stage; and
* storage medium, operating system, Python version, OMYM2 revision, hashing
  chunk size, and whether `--trust-stat` was used.

Effective throughput includes metadata, SQLite, and process-startup overhead;
it is an end-to-end comparison metric, not a claim about raw SHA-256 speed.
Compare memory and throughput only across records with the same dataset and
measurement environment.

The supported distribution currently includes neither a fastText runtime nor a
model, so its naming-runtime fields are recorded as `not distributed` rather
than replaced with synthetic timings. If a future runtime/model candidate is
qualified, add a separate persisted-settings run that records:

* model identity, artifact hash, license, runtime version, Python version, and
  Windows architecture;
* cold time and peak working set through the first eligible prediction;
* warm same-process prediction time after the shared model has loaded;
* unique eligible source-name count, accepted-cache hit count, and provider
  request count; and
* a second-run sticky-cache result, which must make no provider request for an
  already accepted source.

Provider counts use deterministic fixtures or a controlled test endpoint, never
the live MusicBrainz service. The request count must not exceed the unique
eligible cache misses, and disabled, low-confidence, ambiguous, timeout, and
offline cases remain part of the normal automated test gates. The packaging
qualification decision and required Windows smoke evidence are authoritative in
[Desktop Packaging](desktop-packaging.md#artist-naming-distribution-boundary).

## Trust-Stat Comparison

Add `--trust-stat` to forward the explicit opt-in to measured organize/check
stages and to the post-mutation refresh/check setup:

```bash
uv run python scripts/benchmark_pipeline.py \
  --tracks 100 \
  --file-size-bytes 1048576 \
  --tracks-per-album 10 \
  --trust-stat
```

The output header records `trust_stat=false` or `trust_stat=true`. Apply remains
unchanged in both modes and always performs full source hashing. On the clean
organize/check stages, a true run measures the stat-only path after apply has
populated verified baselines. After tag mutation, the sentinel-forced size
mismatch sends refresh and `ready` Plan check back to full capture, which also
verifies the fallback behavior independently of filesystem timestamp precision.
