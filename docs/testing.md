# Testing

## Overview

The project has four test suites:

| Suite | Scope | Command | Requires |
|---|---|---|---|
| ROS node unit tests | All ROS 2 nodes (mocked ROS stack) | `make test` | — |
| S3 GC unit tests | GC logic with mocked S3 client | `make test-gc` | — |
| S3 storage integration tests | Upload, discovery, GC against real S3 (MinIO) | `make test-storage` | Docker (MinIO) |
| Gate integration tests | Recording gate with live ROS 2 stack | `make test-gate` | Docker (ROS 2 image) |

Run all integration tests at once with `make test-integration`.

## Architecture

### ROS/Logic Separation

Business logic is extracted from ROS 2 nodes into pure-Python modules so
it can be tested without the full ROS mock stack:

| Pure module | Extracted from | Functions |
|---|---|---|
| `data_backend/upload.py` | `recording_uploader.py` | `upload_recording()`, `recover_pending_uploads()`, `retention_cleanup()`, `_resolve_s3_prefix()` |
| `data_backend/canonical_path.py` | — (new) | `CanonicalPathFields` — metadata-derived S3 path computation |
| `data_backend/gc.py` | `remote_gc_node.py` | `GCConfig`, `discover_recordings()`, `run_gc_cycle_with_result()`, `compute_diagnostic_level()` |
| `data_backend/upload_state.py` | — (new) | `UploadStateDB` — SQLite per-recording × per-target state tracking |
| `recording_gate.py` | `recording_gate_node.py` | `EscalationLevel`, `ConditionResult`, `ConditionChecker`, `load_gate_config()`, `evaluate_gate()` |

The ROS nodes become thin wrappers: parameters, subscriptions, timers, and
publishers stay in the node; all logic delegates to the extracted functions.

### Test Layers

```
Unit tests (mocked ROS + mocked S3)
  ├── yubi-core/test/test_recording_gate.py           — checker logic + config loading
  ├── yubi-core/test/test_scenario_recording_gate.py  — 18 multi-step gate workflows
  ├── data-backend/tests/test_gc.py               — GC logic with mock S3
  ├── data-backend/tests/test_upload.py            — upload, recovery, retention, path rules
  ├── data-backend/tests/test_canonical_path.py    — canonical path normalization + prefix
  ├── data-backend/tests/test_upload_state.py      — SQLite state DB
  ├── data-backend/tests/test_scenario_gc.py       — GC scenario workflows
  ├── data-backend/tests/test_scenario_upload.py   — canonical/flat upload + GC interplay
  └── data-backend/tests/test_scenario_upload_state.py — upload state scenario workflows

Integration tests (real services, no mocks)
  ├── data-backend/tests/test_integration_gc.py      — GC discovery + deletion against real S3
  ├── data-backend/tests/test_integration_storage.py — full upload→GC lifecycle against real S3
  └── yubi-core/test/test_integration_gate.py         — gate node with live ROS 2 stack
```

## Unit Tests

### ROS Node Tests

```bash
make test
```

All ROS 2 and message dependencies are mocked via
`conftest.py` (`mock_rclpy` fixture). No ROS 2 installation required.

### S3 GC Tests

```bash
make test-gc
```

Uses mocked `minio.Minio` client. Integration tests are
excluded automatically (`-m "not integration"`).

### Scenario Tests

Scenario tests exercise realistic multi-step workflows through the gate
and uploader pipelines. They use the same mock infrastructure as unit tests
but test sequences of operations rather than individual methods.

#### Recording Gate Scenarios (18 tests)

| Test | Feature |
|---|---|
| Startup all-fail then gradual recovery | Fail-closed startup, per-checker recovery |
| Startup settle delay | `settle_sec` timer |
| Condition failure mid-recording | Re-settle trigger (`recovery_sec`) |
| Multiple escalation levels | Max escalation wins across checkers |
| Real checkers startup | `TopicConditionChecker` instances |
| Duration limit triggers stop | `TopicConditionChecker` with `timeout_sec: -1.0` |
| Settle timeout expires with failures | Fail-safe settle completion |
| Config-driven gate construction (flat) | Legacy flat YAML format |
| Multi-group independent settling | Per-group `settle_sec` |
| Multi-group max escalation | Gate level = max across groups |
| TopicConditionChecker rate checking | `min_rate_hz`, `rate_escalation` |
| TopicConditionChecker absence grace period | `absence_timeout_sec`, `absence_escalation` |
| TopicConditionChecker content expression | `condition` field with `msg.data < 100` |
| Debounce with gate integration | `DebouncedChecker` flap/reset/clear cycle |
| DiagnosticsErrorRate sliding window | Error accumulation, expiry, re-blocking |
| Config-driven grouped construction (v2) | Grouped YAML, `default_type` inheritance |
| Re-settle with different group timings | Per-group `recovery_sec` |
| TopicConditionChecker full lifecycle | All facets: absent → no msg → timeout → content → rate → pass |

#### Storage Scenarios (`data-backend/tests`)

Upload, retention, GC, and state-tracking workflows are exercised by the
`data-backend` scenario suites:

| Suite | Feature |
|---|---|
| `test_scenario_upload.py` | Flat/canonical upload, multi-target, GC interplay |
| `test_scenario_upload_state.py` | SQLite state transitions (pending → completed/failed), idempotent re-runs |
| `test_scenario_gc.py` | Strategy-based GC, orphan cleanup, retention |

## Integration Tests

### MinIO Integration Tests

Exercise the full upload and GC pipeline against a real MinIO instance.
Marked `@pytest.mark.integration` and auto-skip if MinIO is unreachable.

#### Prerequisites

- Docker and Docker Compose

#### Running

```bash
# Starts MinIO, runs tests, cleans up automatically
make test-storage
```

#### MinIO Test Environment

Defined in `docker-compose.test.yml`:

| Setting | Value |
|---|---|
| Port | `19000` (avoids conflict with production 9000) |
| Console port | `19001` |
| Access key | `testadmin` |
| Secret key | `testadmin123` |
| Bucket | `test-gc-bucket` (auto-created on startup) |
| Storage | Ephemeral (no persistent volume) |

#### Test Isolation

Each test gets a unique S3 prefix (`test_<name>_<uuid>/`), cleaned up
after the test via the `test_prefix` fixture. Tests never interfere with
each other even when running in parallel.

#### MinIO Integration Test Coverage

| Test | What it exercises |
|---|---|
| `test_upload_and_discover` | `upload_recording()` → `discover_recordings()` round-trip |
| `test_enrich_reads_marker` | `.recording_complete` JSON → `enrich_completed_at()` parses timestamp |
| `test_enrich_fallback_no_marker` | Missing marker → falls back to `latest_object_modified` |
| `test_gc_cycle_deletes_eligible` | Age strategy deletes old eligible recordings, preserves ineligible |
| `test_gc_cycle_dry_run` | `dry_run=True` → no objects removed |
| `test_marker_json_roundtrip` | Upload marker → read back → verify JSON structure |
| `test_space_strategy_real` | Space strategy deletes oldest recordings first |

### Gate Integration Tests

Exercise the recording gate node with a live ROS 2 stack inside the
project Docker image. Each test creates a real `RecordingGateNode`, publishes
real messages, and verifies gate level and diagnostics output.

#### Running

```bash
# Build image and run tests (--build ensures latest code; cleans up afterward)
make test-gate

# Run with FastDDS instead of CycloneDDS
RMW_IMPLEMENTATION=rmw_fastrtps_cpp make test-gate
```

#### Test Harness

`GateTestHarness` manages the test lifecycle:

1. Writes a temporary gate config YAML
2. Creates `RecordingGateNode` with the config
3. Creates a helper node that publishes test messages and subscribes to
   gate output (`~/gate_level`, `/diagnostics`)
4. Spins both nodes in a `MultiThreadedExecutor` on a background thread
5. Provides `publish_*` helpers and `wait_for_gate_level()` assertion

#### DDS Middleware

Tests pass on both CycloneDDS (default) and FastDDS. Override via the
`RMW_IMPLEMENTATION` environment variable.

#### Gate Integration Test Coverage

| Test | Feature | Message types |
|---|---|---|
| Gate starts at HARD_STOP | Fail-closed behavior | — |
| Gate opens after settle | `settle_sec` with `topic_condition` | `Bool` |
| Gate blocks on failure | Freshness timeout + recovery | `Bool` |
| Diagnostics per condition | DiagnosticArray format, `hardware_id` | `DiagnosticArray` |
| Latched QoS late subscriber | TRANSIENT_LOCAL durability | `UInt8` |
| TopicHealth rate + expression | `condition` + `min_rate_hz` | `Float64` |
| TF availability | Multiple dynamic TF frames | `TransformStamped` |
| TF missing frame | Partial TF → gate blocked | `TransformStamped` |
| TF staleness | `max_age_sec` with dynamic TF | `TransformStamped` |
| PoseStamped expression | `msg.pose.position.x` bounds | `PoseStamped` |
| JointState expression + rate | `msg.effort[0]` + `min_rate_hz` | `JointState` |
| Diagnostics error rate | Sliding window, expiry, recovery | `DiagnosticArray` |
| Multi-group settling | Independent `settle_sec` per group | `Bool` |
| Debounce filtering | Flap resets timer | `Bool` |
| Escalation levels | Level 0, 1, 2 transitions | `Bool` |
| Rate + freshness escalation | `rate_escalation=1` vs `escalation=2` | `Float64` |

### Running All Integration Tests

```bash
make test-integration
```

This starts MinIO, runs MinIO integration tests, runs gate integration
tests (builds Docker image), and cleans up. Exits with failure if any
suite fails.

## Makefile Targets

| Target | Description |
|---|---|
| `make test` | Run ROS node unit tests |
| `make test-gc` | Run S3 GC unit tests (excludes integration) |
| `make lint` | Run ruff linter and formatter check |
| `make test-storage` | Start MinIO, run S3 storage integration tests, clean up |
| `make test-gate` | Build Docker image, run gate integration tests, clean up |
| `make test-integration` | Run all integration tests (storage + gate) |
