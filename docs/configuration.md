# Configuration Reference

Yubi Core is configured through a small set of YAML files plus a few
environment variables. This document is the detailed reference; for a fast
path to a running system see the [Quick start](#quick-start) below.

## Config files at a glance

All sample files live in `yubi-core/config/`. Copy each `*.sample` file to the
name without the suffix and edit it. `qos_overrides.yaml` ships without a
`.sample` suffix — edit it in place.

| File | Purpose | Loaded by |
|------|---------|-----------|
| `robot_config.yaml` | Single source of node parameters: robot identity, topics to record, backend API, upload toggle, gate toggle, deployment metadata. | All ROS nodes (passed as the `robot_config` launch arg). |
| `upload_targets.yaml` | One or more S3-compatible upload targets, credentials, retention, and garbage-collection policy. | `storage_node` (parsed by `data_backend.config`). |
| `recording_gate.yaml` | Safety/health gate conditions that block or cancel recording. | `recording_gate_node` (opt-in). |
| `qos_overrides.yaml` | Per-topic QoS overrides for `ros2 bag record` (needed for BEST_EFFORT publishers). | `record_manager` (passed as the `qos_overrides_file` launch arg). |
| `task_file.yaml` | Offline task/subtask definitions, used only when `offline_mode: true`. | `OfflineBackend` (record/task nodes). |

## Quick start

1. **Robot config** — `cp yubi-core/config/robot_config.yaml.sample yubi-core/config/robot_config.yaml`.
   Minimum to get going:
   - `record_topics` — the topics you want in each rosbag.
   - `base_url` + `api_key` — your backend (or set `offline_mode: true` and a `task_file`).
   - `record_base_dir` — where rosbags are written locally.
   Leave `robot_type` / `runner_organization` as `"FIXME"` to auto-resolve them
   from the backend.
2. **Upload** (optional) — to push recordings to S3/MinIO, copy
   `upload_targets.yaml.sample`, point `robot_config.yaml`'s
   `upload_targets_file` at it, and keep `upload_enabled: true`.
3. **Recording gate** (optional) — to enable safety gating, set
   `use_recording_gate: true` and `recording_gate_config` to a copy of
   `recording_gate.yaml.sample`.
4. **Launch** — `ros2 launch yubi_core leader_teleop.launch.py`.

## Launch arguments

`leader_teleop.launch.py` declares exactly three arguments:

| Argument | Default | Description |
|----------|---------|-------------|
| `robot_config` | `<pkg_share>/config/robot_config.yaml` | Path to the robot configuration YAML. |
| `qos_overrides_file` | `<pkg_share>/config/qos_overrides.yaml` | Path to the QoS overrides file (empty file = default QoS). |
| `bridge_mode` | `false` | When `true`, skip `task_receiver` so an external node (e.g. a sim bridge) can provide tasks. |

Everything else (API endpoint, S3 settings, gate toggle, …) is a **parameter
inside `robot_config.yaml`**, not a launch argument.

## Environment variables

Set these in `.env` (see `.env.example`) — they are consumed by Docker
Compose and the ROS middleware, not parsed from YAML.

| Variable | Description | Default |
|----------|-------------|---------|
| `ROS_DISTRO` | ROS 2 distribution (`jazzy`, `humble`, `kilted`) | `jazzy` |
| `ROS_DOMAIN_ID` | ROS 2 domain ID | `0` |
| `RMW_IMPLEMENTATION` | RMW (`rmw_cyclonedds_cpp` or `rmw_fastrtps_cpp`) | `rmw_cyclonedds_cpp` |
| `FASTDDS_PROFILE_HOST_PATH` | Host path to the FastDDS profile XML | `./docker/fastdds_profile.xml` |
| `DATA_MOUNT_PATH` | Host path mounted to `/opt/data` for recordings | _(required)_ |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | Credentials for the bundled MinIO service | `minioadmin` |
| `MINIO_DATA_PATH` | Host path for MinIO data | `./minio_data` |
| `SENTRY_DSN` | Sentry DSN for error tracking (empty = disabled) | _(empty)_ |
| `ENV` | Sentry environment tag | `development` |
| `WEB_VIDEO_SERVER_PORT` | Port for the web video server | `9091` |
| `GIT_HASH` / `GIT_BRANCH` | Build metadata baked into the image (set by CI) | _(empty)_ |

## `robot_config.yaml`

A single ROS parameter file (`/**: ros__parameters:`) read by every node. The
sample groups parameters by purpose; the important groups:

- **Robot identity** — `robot_type` (`"FIXME"` → resolved from backend),
  `battery_topic`, `devices` (JSON array string).
- **Recording** — `record_topics`, `rosbag_params` (recorder CLI args, e.g.
  `--storage mcap`), `record_base_dir`, `required_free_space` (GB).
- **Upload** — `upload_enabled` and `upload_targets_file` (path to
  `upload_targets.yaml`). All S3 detail lives in that file, not here.
- **Backend API** — `base_url`, `api_key`, `offline_mode`, `task_file`.
- **Deployment metadata** — `environment_type`, `site`, `location`,
  `runner_organization` (`"FIXME"` → resolved), `runner_name`, and the
  optional `teleop_interface*` git-provenance fields.
- **Recording gate** — `use_recording_gate`, `recording_gate_config`.
- **Status reporting** — `status_interval_sec`, `gate_throttle_sec`.

See `robot_config.yaml.sample` for the full annotated list with per-parameter
defaults and which node reads each one.

## `upload_targets.yaml`

Describes how completed recordings are uploaded and garbage-collected. Read
only when `upload_enabled: true` and `upload_targets_file` points to it.

Top-level keys:

| Key | Default | Description |
|-----|---------|-------------|
| `state_db` | `/var/lib/yubi/upload_state.db` | SQLite DB tracking per-recording × per-target upload state. |
| `state_purge_age_hours` | `720` | Age after which completed state rows are purged. |
| `delete_after_upload` | `false` | Delete local recording immediately after a successful upload. |
| `local_retention_hours` | `24` | Keep uploaded recordings locally for this long. |
| `defaults` | — | Default values merged into every target. |
| `targets` | — | Map of named upload targets. |

Each **target** supports: `endpoint` (required), `bucket`, `access_key` /
`secret_key` (or `access_key_env` / `secret_key_env` to read from the
environment), `use_ssl`, `verify_ssl`, `prefix`, `priority`
(`required` | `preferred` | `optional`), `path_rule`
(`flat` = directory name, or `canonical` = metadata-derived
`org=…/site=…/uuid=…` hierarchy), `enabled`, and a per-target `gc` block.

The **`gc`** block controls garbage collection: `strategy` (a list of
conditions drawn from `marker`, `age`, `space`, optionally combined with
`any_of`), `max_age_hours`, `max_storage_gb`, `orphan_age_hours`,
`check_interval_sec`, `completion_marker`, `storage_marker`, and `dry_run`.
Set `gc: none` (or omit it) to disable GC for a target.

See `upload_targets.yaml.sample` for a fully worked example with multiple
targets and commented alternatives.

### Local MinIO (default, first-class)

The `docker compose` stack ships a **local MinIO** service as the primary,
on-robot storage target — no external infrastructure required:

- The `minio` service serves S3 on `localhost:9000` (web console on
  `localhost:9001`), with data persisted to `${MINIO_DATA_PATH:-./minio_data}`.
- The `minio-init` service auto-creates the `data` bucket on startup.
- Credentials come from `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` (default
  `minioadmin` / `minioadmin`).

The sample's `local` target is already wired to it and is marked
`priority: required`, so recordings upload locally first:

```yaml
targets:
  local:
    endpoint: "localhost:9000"
    access_key: "minioadmin"
    secret_key: "minioadmin"
    path_rule: "flat"
    priority: "required"
```

Browse uploaded data at <http://localhost:9001> (log in with the MinIO
credentials).

### Adding a remote S3 target

To also push recordings off-robot, add another target alongside `local`. Any
S3-compatible endpoint works (AWS S3, GCS, a remote MinIO, …):

```yaml
targets:
  local:        # keep the local target as the required, fast path
    endpoint: "localhost:9000"
    access_key: "minioadmin"
    secret_key: "minioadmin"
    priority: "required"

  cloud:
    endpoint: "s3.amazonaws.com"
    bucket: "company-recordings"
    use_ssl: true                       # TLS for remote endpoints
    # verify_ssl: false                 # only for self-signed/internal certs
    access_key_env: "AWS_ACCESS_KEY_ID"     # read secrets from the environment
    secret_key_env: "AWS_SECRET_ACCESS_KEY" # (preferred over inline keys)
    path_rule: "canonical"              # metadata-derived layout for archives
    priority: "preferred"               # uploaded after required targets
    gc: none                            # don't garbage-collect the remote copy
```

Tips:
- Prefer `access_key_env` / `secret_key_env` so credentials stay out of the
  YAML; export them in `.env` or the container environment.
- Use `priority` to control retention: `required` targets must complete before
  a local recording may be deleted; `preferred` upload after them; `optional`
  never block deletion or trigger retries.
- `canonical` `path_rule` is recommended for shared/long-term remote buckets;
  `flat` is fine for the local target.

## `recording_gate.yaml`

An opt-in safety/health system. When `use_recording_gate: true`, the gate
publishes a level on `~/gate_level`:

| Level | Meaning |
|-------|---------|
| 0 | OK — recording allowed |
| 1 | Block — new episodes cannot start (in-progress episodes continue) |
| 2 | Hard-stop — active recordings are cancelled immediately |

Structure: a top-level `groups:` map, each group containing `conditions:`.
Global/group settings include `eval_rate`, `settle_sec`, `recovery_sec`, and
`default_escalation`. Supported condition `type`s:

- **`topic_condition`** — all-in-one presence / freshness / rate / content
  check on a topic (with optional `absence_timeout_sec` /
  `absence_escalation` for un-advertised topics).
- **`diagnostics_error_rate`** — monitors a `DiagnosticArray` for error rate.
- **`tf_availability`** — checks that a TF transform is available.

Each condition has an `escalation` level (1 = block, 2 = hard-stop) and a
`timeout_sec` (use `-1.0` for "inactive-safe": no message = PASS). See
`recording_gate.yaml.sample` and [`recording_gate_v2_spec.md`](recording_gate_v2_spec.md).

## `qos_overrides.yaml`

`ros2 bag record` defaults to RELIABLE QoS, which cannot receive from
BEST_EFFORT publishers (common for compressed image streams). Add one entry
per topic that needs an override:

```yaml
/camera/image_raw/compressed:
  reliability: best_effort
  durability: volatile
  history: keep_last
  depth: 10
```

The shipped file is an empty template — an empty/all-comments file is valid
and simply applies no overrides.

## `task_file.yaml`

Used only in offline mode (`offline_mode: true`, `task_file` set). Defines the
tasks the system serves without a backend:

```yaml
robot:
  id: my-robot-id
user:
  id: operator-id
tasks:
  - id: task-1
    name: Pick and place
    description: Move the block to the bin
    subtasks:
      - id: sub-1
        name: Approach
        order_index: 0
```

See `task_file.yaml.sample` for the full shape.
