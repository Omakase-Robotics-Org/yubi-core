# Quick Evaluation Scripts

Helper scripts for interacting with the data collection state machine from the host.
Each script runs `docker compose exec` to call ROS 2 services/topics inside the running container.

## Prerequisites

- The `yubi-core` container must be running (`docker compose up`)
- Run scripts from the repository root (where `docker-compose.yml` lives)

## Scripts

| Script | Description |
|--------|-------------|
| `get_task.sh` | Print current state machine status and active task |
| `accept.sh` | Accept the current task (trigger `/data_collection/accept`) |
| `decline.sh` | Decline the current task (trigger `/data_collection/reject`) |
| `cancel.sh` | Cancel the current episode; optionally pass a reason string |
| `rewind.sh` | Rewind the current episode (trigger `/data_collection/rewind`) |
| `repeat.sh` | Repeat the last episode (trigger `/data_collection/repeat`) |

## Usage

```bash
./scripts/get_task.sh      # check current state
./scripts/accept.sh        # accept a task
./scripts/decline.sh       # decline a task
./scripts/cancel.sh        # cancel the episode
./scripts/rewind.sh        # rewind the episode
./scripts/repeat.sh        # repeat the last episode
```
