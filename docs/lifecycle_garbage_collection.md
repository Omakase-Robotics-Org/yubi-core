# S3 Garbage Collection — Lifecycle

## Overview

Pure-Python library (`data_backend/gc.py`) that monitors an S3 bucket and
deletes eligible recordings based on a configurable **strategy predicate**
(marker / age / space). It runs inside the `storage_node` ROS 2 node: for
each upload target that has a `gc:` block, the node starts a timer at that
target's `check_interval_sec` and publishes a per-target diagnostic on
`/diagnostics`.

Works with any S3-compatible storage (MinIO, AWS S3, GCS).

## Configuration

GC is configured **per upload target**, inside the `gc:` block of
`upload_targets.yaml` (the same file that defines the target's endpoint,
bucket, prefix, and credentials — there is no separate GC config file). See
[configuration.md](configuration.md#upload_targetsyaml).

| Key | Default | Description |
|-----|---------|-------------|
| `strategy` | _(required)_ | Predicate over `marker` / `age` / `space` (see below) |
| `max_storage_gb` | `0` | Space threshold in GB (0 = disabled) |
| `max_age_hours` | `0` | Age threshold in hours (0 = disabled) |
| `orphan_age_hours` | `1` | Delete unmarked recordings older than this |
| `check_interval_sec` | `300` | Seconds between GC cycles |
| `completion_marker` | `.recording_complete` | Marks a finished recording |
| `storage_marker` | `.uploading_complete` | Marks a recording persisted to permanent storage |
| `dry_run` | `false` | Log what would be deleted but don't remove |

### Strategy predicate

`strategy` is **not** a single enum — it is a list of conditions evaluated as
a boolean predicate over three flags computed per recording: `marker` (storage
marker present), `age` (`completed_at` older than `max_age_hours`), and
`space` (bucket total over `max_storage_gb`). Conditions in a list are AND-ed;
an `{any_of: [...]}` block is OR-ed. For example, the sample's:

```yaml
strategy:
  - marker
  - any_of: [age, space]
```

means *delete a recording only if it has the storage marker AND (it is too old
OR the bucket is over its space budget)*. A strategy that omits `marker` will
delete by age/space regardless of the storage marker.

## Recording Classification

| Category | Condition | Action |
|----------|-----------|--------|
| **Empty** | No files under the prefix | Pruned |
| **Orphan** | No completion marker, newest object older than `orphan_age_hours` | Deleted (race-safe: active recordings are recent) |
| **Good, not stored** | Has completion marker, no storage marker | Kept (awaiting persistent storage) |
| **Good, stored** | Storage marker present | Eligible for strategy-based GC |

## Lifecycle Loop

Each cycle (`run_gc_cycle_with_result`) runs these steps:

1. **Discover** (`discover_recordings`) — list objects recursively and group
   by leaf directory (the parent prefix of each file), at arbitrary nesting
   depth. Tracks object list, total size, marker presence, and the newest
   `last_modified`.
2. **Enrich** (`enrich_completed_at`) — read each `.recording_complete` marker
   (JSON) for its `completed_at` timestamp; fall back to the newest object's
   mtime if missing/unreadable.
3. **Select** (`select_for_deletion`) — sort oldest-first, then for each
   recording evaluate `strategy.evaluate(marker, age, space)`. Deleted
   recordings' bytes are subtracted from the running total so `space` frees up
   progressively within the cycle.
4. **Orphans** (`select_orphans`) — recordings with neither marker whose newest
   object is older than `orphan_age_hours` (abandoned/crashed recordings).
5. **Delete** (`delete_recordings`) — remove all objects for the selected
   recordings via `remove_objects` (skipped under `dry_run`).
6. **Prune** (`prune_empty_branches`) — bottom-up, remove ancestor prefixes
   (and S3 folder placeholders) left empty by deletion, never above the
   target's configured `prefix`.

## Diagnostics

Per cycle, the node publishes one `DiagnosticStatus` named
`storage_gc/<target_name>` (with `hardware_id = <target_name>`) carrying
`total_recordings`, `total_gb`, `eligible_count`, `deleted_count`, and
`orphan_count`. The level (`compute_diagnostic_level`):

| Condition | Level |
|-----------|-------|
| `max_storage_gb = 0` (disabled) | OK (0) |
| Storage ≤ 80% of threshold | OK (0) |
| Storage 80–100% of threshold | WARN (1) |
| Storage > threshold, eligible recordings exist | WARN (1) |
| Storage > threshold, no eligible recordings | ERROR (2) |
| Exception during cycle | ERROR (2) |
