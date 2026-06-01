# Storage Node — Upload Lifecycle

## Overview

The **storage node** uploads completed recordings to one or more
S3-compatible targets and manages local retention. It is a thin ROS 2
wrapper (`yubi_core/storage_node.py`, node name `storage_node`) around the
pure-Python `StorageManager` in the `data-backend` package. Stdlib logs from
`data_backend` are bridged to ROS via `ros_log_bridge.bridge_to_ros()`.

- ROS node: `yubi_core/storage_node.py`
- Orchestration: `data-backend/src/data_backend/manager.py` (`StorageManager`)
- Upload logic: `data-backend/src/data_backend/upload.py`
- Per-recording × per-target state: `data-backend/src/data_backend/upload_state.py` (SQLite)

The node declares only **three** ROS parameters; everything about *where* and
*how* to upload comes from `upload_targets.yaml` (see
[configuration.md](configuration.md#upload_targetsyaml)).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `upload_targets_file` | _(empty)_ | Path to `upload_targets.yaml` (required when uploading) |
| `record_base_dir` | `/root/datasets/rosbags` | Local directory containing recordings |
| `upload_enabled` | `true` | Master switch for the upload pipeline |

## Startup Sequence

1. Read the three parameters. If `upload_enabled` is false, the node idles.
2. Load `upload_targets.yaml` → `StorageConfig`, and construct
   `StorageManager`, which connects an S3 client per target and opens the
   SQLite state DB (`state_db`). If no targets connect, the node logs an
   error and stops.
3. Subscribe (RELIABLE + TRANSIENT_LOCAL) to:
   - `/record_manager/recording_completed` — enqueue the directory for upload.
   - `/record_manager/recording_cancelled` — logged only, never uploaded.
4. **Recover pending**: scan `record_base_dir` for directories containing
   `meta.json` and enqueue them. The state DB (not a local marker) decides
   which targets still need each recording.
5. Start the background upload worker thread (daemon).
6. Start the retention timer (every `RETENTION_CHECK_INTERVAL_SEC` = 300 s).
7. For each target that has a `gc:` block, start a GC timer at that target's
   `check_interval_sec` (see [lifecycle_garbage_collection.md](lifecycle_garbage_collection.md)).

## Upload Worker

For each dequeued directory, `StorageManager.upload(dir_path)`:

1. Iterates over **all** targets. For each, `state_db.should_upload(rec, target)`
   skips targets already completed (idempotent re-runs / recovery).
2. Calls `upload_recording(...)` per remaining target: uploads every file
   (skipping the `.recording_complete` marker) with `fput_object`, then writes
   a `.recording_complete` JSON marker to S3 (`completed_at` + `filename→etag`
   map). The S3 key prefix comes from the target's `path_rule`:
   - `flat` (default): `{prefix}{dir_name}/`
   - `canonical`: derived from `meta.json` →
     `{prefix}org=…/site=…/…/uuid=…/` (falls back to flat if `meta.json` is
     missing/unreadable).
3. Records the per-target outcome in the state DB: `completed` (with etags) or
   `failed` (failures are recorded for non-`optional` targets).

The worker then:
- Deletes the local directory when the result's priority-based delete policy
  is satisfied (see below).
- Re-queues the recording after `RETRY_BACKOFF_SEC` (5 s) if any
  `required`/`preferred` target still needs it (`needs_retry`).

## Deletion Policy & Retention

**Priority-based delete policy** (`StorageManager._can_delete_local`):
- If there are `required` targets → deletable once **all** of them completed.
- Else if there are `preferred` targets → deletable once **any** completed.
- `optional` targets never block deletion.

Immediate post-upload deletion only happens when `delete_after_upload: true`
**and** the priority policy is satisfied (`StorageManager.can_delete_local`).
With the default `delete_after_upload: false`, recordings stay on disk and are
removed by the retention timer instead.

**Retention timer** (`retention_cleanup`, every 5 min): removes directories
whose **modification time** is older than `local_retention_hours`. It is a
no-op when `delete_after_upload: true` or `local_retention_hours <= 0`. The
timer also purges terminal state-DB rows older than `state_purge_age_hours`.

## Recovery

On restart, `recover_pending` re-enqueues every directory under
`record_base_dir` that contains `meta.json`. Per-target deduplication is
handled by the state DB, so already-completed targets are skipped during the
re-run rather than re-uploaded.
