# Lock Server

Lightweight service that broadcasts available robot UUIDs for the teleoperation operator machine.

## Configuration

Edit `config.json` to list the robot UUIDs available on this operator device:

```json
{
  "robots": [
    "uuid-1",
    "uuid-2"
  ]
}
```

The file is mounted read-only into the container — no rebuild needed after changes, just restart the service.

## Running

### With Docker Compose (recommended)

```bash
docker compose up -d lock_server
```

The service binds to `127.0.0.1:28080` only (not exposed to the network).

### Standalone

```bash
cd lock_server
docker build -t yubi-lock-server .
docker run --rm -p 127.0.0.1:28080:28080 yubi-lock-server
```

## API

### `GET /v1/robot`

Returns the list of configured robot UUIDs.

```bash
curl http://localhost:28080/v1/robot
```

Response:

```json
{
  "robots": ["uuid-1", "uuid-2"]
}
```
