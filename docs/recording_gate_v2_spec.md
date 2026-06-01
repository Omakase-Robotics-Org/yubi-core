# Recording Gate v2 — Spec

## 1. Config Structure

```
global defaults  →  group defaults  →  condition config
```

Top-level keys configure global defaults. Groups override globals. Conditions override group defaults.

### 1.1 Global Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `eval_rate` | float | `2.0` | Evaluation frequency (Hz). Single timer, all groups. |
| `settle_sec` | float | `20.0` | After boot, all conditions in a group must pass this long before gate opens. |
| `recovery_sec` | float | `5.0` | After gate was open and failed, conditions must hold this long before re-opening. |
| `default_escalation` | int | `2` | Default escalation (0=ok, 1=block start, 2=hard stop). |

### 1.2 Group Settings (`groups.<name>`)

| Key | Type | Inherits from | Description |
|-----|------|---------------|-------------|
| `enabled` | bool | `true` | Disable entire group. |
| `settle_sec` | float | global | Override startup settle for this group. |
| `recovery_sec` | float | global | Override recovery hold for this group. |
| `default_type` | string | *(none)* | Default checker type for conditions in this group. |
| `default_escalation` | int | global | Default escalation for conditions in this group. |
| `default_debounce_sec` | float | `0.0` | Default debounce for conditions in this group. |

### 1.3 Condition Settings (`groups.<name>.conditions.<name>`)

| Key | Type | Inherits from | Description |
|-----|------|---------------|-------------|
| `enabled` | bool | `true` | Disable individual condition. |
| `type` | string | group `default_type` | Checker type (see 2. Checker Types). |
| `escalation` | int | group `default_escalation` | Escalation level on failure. |
| `debounce_sec` | float | group `default_debounce_sec` | Condition must stay true this long before counting as passed. 0 = immediate. |
| `topic` | string | *(required for most types)* | ROS topic to monitor. |

---

## 2. Checker Types

### 2.1 `topic_condition`

All-in-one topic checker: presence, freshness, rate, and content.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `topic` | string | required | ROS topic (type discovered at runtime). |
| `timeout_sec` | float | `5.0` | Max message age (freshness). |
| `expected_type` | string | `""` | Optional type assertion. |
| `condition` | string | *(unset)* | AST-validated Python expression on `msg`. Skipped if unset. |
| `min_rate_hz` | float | *(unset)* | Minimum message rate. Skipped if unset. |
| `rate_window_sec` | float | `5.0` | Sliding window for rate calculation. |
| `rate_escalation` | int | *(inherits)* | Override escalation for rate failures. |
| `absence_timeout_sec` | float | `0.0` | Grace period for missing topic. 0 = fail immediately. |
| `absence_escalation` | int | *(inherits)* | Override escalation for topic absence. |
| `single_shot` | bool | `false` | Require one message, then always pass. Settle-exempt. |
| `latch` | bool | *(single_shot)* | Use transient-local QoS for retained message delivery. |
| `reason` | string | *(auto)* | Failure reason template. See **Reason templates** below. |

Evaluation priority (most severe first):
1. Topic not advertised → absence failure
2. No message received → "no message" failure
3. Last message too old → freshness failure
4. `condition` expression false → content failure
5. Rate below minimum → rate failure
6. All pass → ok

### 2.2 `diagnostics_error_rate`

Sliding window error counting on DiagnosticArray. Cannot be expressed as a topic expression.

| Key | Type | Default |
|-----|------|---------|
| `topic` | string | required |
| `max_errors` | int | `3` |
| `window_sec` | float | `30.0` |
| `name_filter` | string | `""` |

### 2.3 `tf_availability`

TF frame lookup. Not a topic subscription.

| Key | Type | Default |
|-----|------|---------|
| `frames` | list | required |
| `timeout_sec` | float | `5.0` |

### 2.4 Custom class

Set `type` to `"module.path:ClassName"`. Must subclass `ConditionChecker`, implement `setup(node)` and `evaluate() -> ConditionResult`.

### 2.5 Legacy types

`topic_heartbeat`, `topic_bool`, and `topic_threshold` have been removed. Use `topic_condition` with appropriate `condition` expressions instead (e.g. `condition: "msg.data < X"` with `timeout_sec: -1.0` for duration limits). A `topic_condition` with no `condition` field is equivalent to the old `topic_heartbeat`.

---

## 3. Expression Safety

Expressions in `condition` are validated and compiled at setup via `ast`:

**Allowed AST nodes:** `Compare`, `BoolOp` (`and`/`or`), `UnaryOp` (`not`), `Attribute`, `Name` (only `msg`), `Constant`, `BinOp` (`+`/`-`/`*`/`/`), `Subscript`, `Index`.

**Rejected:** `Call`, `Import`, `Lambda`, `ListComp`, dunder attributes (`__*`), any variable other than `msg`.

**Examples:**
- `"msg.temperature < 45.0"`
- `"msg.pose.position.x > -1.0 and msg.pose.position.x < 5.0"`
- `"msg.effort[0] < 10.0"`
- `"not msg.data"`

Compiled to bytecode once. Evaluated at runtime with `{"__builtins__": {}, "msg": last_msg}`.

Invalid or unsafe expressions fail at node startup with a clear error log.

### Reason Templates

When a condition expression fails, the reason string includes actual message values automatically:

```
condition failed: msg.effort[0] < 50.0 (msg.effort[0]=72.3)
```

`msg.*` references are extracted from the expression AST at setup and pre-compiled. At runtime, each reference is evaluated against the current message to build the `detail` string.

**Custom templates** via the `reason` config use Python's `.format()`:

```yaml
reason: "Joint limit exceeded: {condition} ({detail})"
# → "Joint limit exceeded: msg.effort[0] < 50.0 (msg.effort[0]=72.3)"

reason: "E-stop pressed (raw={msg.data})"
# → "E-stop pressed (raw=True)"
```

Available variables: `{msg.*}` (message fields), `{condition}` (expression text), `{name}` (condition name), `{detail}` (auto-generated values). If the template fails (bad key), falls back to the auto-enriched default.

---

## 4. Timing Model

Three distinct timing concerns:

| Timing | Level | Default | When it applies |
|--------|-------|---------|-----------------|
| `settle_sec` | global / group | `20.0` | Once at startup. Group stays blocked until all its conditions pass continuously for this duration. |
| `debounce_sec` | group / condition | `0.0` | Per condition. Condition must stay true for this duration before `evaluate()` reports it as passing. 0 = immediate. |
| `recovery_sec` | global / group | `5.0` | After gate was open (level 0) and a condition fails. All conditions must hold for this duration before re-opening. Prevents flapping. |

**Interaction:** `debounce_sec` filters individual condition noise. `settle_sec` and `recovery_sec` operate on the group level after conditions are already debounced.

**Settle-exempt conditions:** `single_shot` conditions bypass the settle timer entirely — they pass/fail immediately without blocking or resetting the group settle. Settle only applies to periodic conditions (rate, debounce). If all conditions in a group are settle-exempt, the group settles immediately.

---

## 5. Escalation Levels

| Level | Name | Effect |
|-------|------|--------|
| 0 | OK | Recording allowed. |
| 1 | BLOCK_START | Cannot start new recording. Ongoing recording continues. |
| 2 | HARD_STOP | Ongoing recording must be stopped. |

Per-condition escalation overrides (e.g., `rate_escalation`, `absence_escalation`) allow different failure modes to trigger different levels within a single condition.

---

## 6. Structured Status Output

### 6.1 Topics published by gate node

| Topic | Type | Purpose |
|-------|------|---------|
| `~/gate_level` | UInt8 | Overall gate level (max across groups). Backward compat for `task_sequence_manager`. |
| `/diagnostics` | DiagnosticArray | Per-condition health via standard ROS2 diagnostics. Free `rqt_robot_monitor` visualization. |

### 6.2 DiagnosticArray mapping

Each condition → one `DiagnosticStatus` entry:

| DiagnosticStatus field | Value |
|----------------------|-------|
| `name` | `"recording_gate/<group>/<condition>"` (hierarchical naming) |
| `level` | `OK=0`, `WARN=1` (BLOCK_START), `ERROR=2` (HARD_STOP) |
| `message` | Condition reason string (e.g. `"rate 5.1 Hz < 25.0 Hz"`, `"ok"`) |
| `hardware_id` | `"recording_gate"` |
| `values` | Key-value pairs: `escalation`, `group` |

Escalation → DiagnosticStatus level mapping:

| Escalation | DiagnosticStatus level | Meaning |
|-----------|----------------------|---------|
| 0 (OK) | OK (0) | Condition passing |
| 1 (BLOCK_START) | WARN (1) | Cannot start new recording |
| 2 (HARD_STOP) | ERROR (2) | Ongoing recording must stop |

A no-message condition fails at its configured escalation (not a separate STALE level).

Group-level summary entries are also published as `"recording_gate/<group>"` with `values` `settled` and `level`.

### 6.3 Robot status integration

Robot status node subscribes to `/diagnostics`, filters for `hardware_id == "recording_gate"`, and builds a JSON summary for the backend `PUT /robot/status` payload:

```json
{
  "status": {
    "gate_conditions": {
      "gate_level": 2,
      "groups": {
        "safety": {
          "level": 0,
          "settled": true,
          "conditions": [
            {"name": "estop", "passed": true, "reason": "ok"}
          ]
        },
        "health": {
          "level": 2,
          "settled": false,
          "conditions": [
            {"name": "head_camera", "passed": false, "reason": "rate 5.1 Hz < 25.0 Hz", "escalation": 1}
          ]
        }
      }
    }
  }
}
```

This gives both worlds:
- **ROS side:** `rqt_robot_monitor` shows all conditions with standard visualization, no custom tooling needed
- **Backend side:** Robot status node transforms diagnostics into JSON for the API

---

## 7. Services

### `~/invalidate` (`std_srvs/Trigger`)

Soft reboot: destroys all pooled subscriptions, resets TF buffer, and calls `invalidate()` on each checker. Checkers re-subscribe on the next eval cycle. Latched subscriptions re-fetch retained messages. The gate temporarily returns to HARD_STOP and recovers as topics are re-discovered.

Use when topics change (new URDF published, sensor reconnected) without restarting the node.

---

## 8. Backend Integration

Robot status node sends gate conditions to the backend every 30s (periodic) and on state change (throttled to `gate_throttle_sec`, default 2.0s). The payload includes the full group/condition hierarchy:

```json
{
  "gate_conditions": {
    "gate_level": 0,
    "groups": {
      "safety": {
        "level": 0, "settled": true,
        "conditions": [
          {"name": "estop", "passed": true, "reason": "ok", "escalation": 0}
        ]
      }
    }
  }
}
```

Reactive reports trigger only on actual state transitions (level change or condition pass/fail flip), not on reason text updates.

---

## 9. Backward Compatibility

Old flat `conditions:` config auto-wrapped in a single `"default"` group:

```python
if "groups" not in cfg and "conditions" in cfg:
    cfg["groups"] = {"default": {"conditions": cfg["conditions"]}}
```

`topic_heartbeat`, `topic_bool`, and `topic_threshold` have been removed — use `topic_condition` with a `condition` expression instead.

---

## 10. Config Example (Yubi)

```yaml
eval_rate: 2.0
settle_sec: 20.0
recovery_sec: 5.0
default_escalation: 2

groups:
  safety:
    settle_sec: 5.0
    recovery_sec: 2.0
    default_type: topic_condition
    conditions:
      estop:
        topic: /runstop_button
        condition: "not msg.data"
        timeout_sec: 5.0
      wireless_stop_1:
        topic: /wireless_stop_button_1
        condition: "not msg.data"
        timeout_sec: 5.0
      wireless_stop_2:
        topic: /wireless_stop_button_2
        condition: "not msg.data"
        timeout_sec: 5.0

  health:
    settle_sec: 20.0
    recovery_sec: 10.0
    default_type: topic_condition
    conditions:
      joint_states:
        topic: /joint_states
        timeout_sec: 5.0
        expected_type: "sensor_msgs/msg/JointState"
      head_camera:
        topic: /head_camera/color/image_raw/compressed
        timeout_sec: 3.0
        min_rate_hz: 25.0
        rate_escalation: 1
        debounce_sec: 2.0

  diagnostics:
    settle_sec: 10.0
    default_type: diagnostics_error_rate
    conditions:
      errors_warn:
        topic: /diagnostics_agg
        max_errors: 3
        window_sec: 10.0
        escalation: 1
      errors_critical:
        topic: /diagnostics_agg
        max_errors: 5
        window_sec: 30.0

  right_arm:
    settle_sec: 10.0
    default_type: topic_condition
    default_debounce_sec: 1.0
    conditions:
      joint_current:
        topic: /right_arm/joint_states
        condition: "msg.effort[0] < 10.0"
        timeout_sec: 2.0
      joint_limits:
        topic: /right_arm/joint_states
        condition: "msg.position[0] > -1.5 and msg.position[0] < 1.5"
        timeout_sec: 2.0
```
