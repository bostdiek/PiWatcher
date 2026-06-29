---
title: PiWatcher
description: Motion-triggered Raspberry Pi wildlife camera system with a Pi 5 base station, PostgreSQL storage, and LAN dashboard.
ms.date: 2026-06-28
ms.topic: overview
---

## Overview

PiWatcher is a local wildlife camera system for battery-powered Raspberry Pi Zero W camera nodes and a Raspberry Pi 5 base station. Camera nodes detect motion with `picamera2`, capture short JPEG bursts, and upload events over Wi-Fi. The base station receives frames through FastAPI, stores metadata in PostgreSQL, keeps images on disk, optionally runs local AI inference through llama-swap, and serves a LAN dashboard.

```mermaid
flowchart TD
    camera[Pi Zero W camera nodes]
    motion[Motion detection<br>picamera2 lores frames]
    capture[1024x1024 JPEG bursts<br>2 fps while motion continues]
    api[Pi 5 FastAPI ingest<br>Bearer-token API]
    storage[Frame storage<br>NVMe date/camera/event folders]
    db[(PostgreSQL<br>events, frames, heartbeats)]
    inference[optional llama-swap inference<br>LFM2.5-VL-450M with thermal gating]
    dashboard[LAN dashboard<br>htmx + Jinja2 + Chart.js]
    notify[ntfy notifications]

    camera --> motion --> capture
    capture -->|multipart upload over Wi-Fi| api
    api --> storage
    api --> db
    api --> inference
    inference --> db
    inference --> notify
    db --> dashboard
    storage --> dashboard
```

## Repository Layout

```text
.
├── deploy/
│   ├── piwatcher-base.service       Pi 5 base station systemd unit
│   ├── piwatcher-camera.service     Pi Zero camera systemd unit
│   ├── piwatcher-inference.service  Pi 5 host llama-swap systemd unit
│   ├── piwatcher-ttl.service        Heartbeat cleanup oneshot service
│   ├── piwatcher-ttl.timer          Daily heartbeat cleanup timer
│   ├── setup-llama-swap.sh          Host llama-swap config and model setup
│   └── setup-camera.sh              First-time Pi Zero provisioning script
├── packages/
│   ├── base/
│   │   ├── alembic/                 Database migrations
│   │   ├── src/piwatcher_base/      FastAPI app, routes, models, inference, templates
│   │   └── tests/                   Base station tests
│   └── camera/
│       ├── src/piwatcher_camera/    Motion detection, capture, upload, heartbeat runtime
│       └── tests/                   Camera package tests
├── docker-compose.yml               PostgreSQL service for the base station
├── Makefile                         Development and deployment commands
├── pyproject.toml                   uv workspace root
└── ruff.toml                        Ruff lint configuration
```

## Prerequisites

Use these components for the full deployment:

* A Mac or Linux development machine with Python 3.11+, `uv`, SSH, and rsync
* Raspberry Pi 5 base station with Python 3.11+, `uv`, Docker Compose, `psql`, and access to llama-swap
* Raspberry Pi Zero W camera nodes with Raspberry Pi OS, camera module, Wi-Fi, SSH, and optional PiSugar S battery board
* PostgreSQL 16 on the Pi 5 through Docker Compose
* A shared `PIWATCHER_API_KEY` value for every camera and the base station

## Development Quick Start

Install dependencies and run the local checks from the repository root:

```bash
uv sync
make lint
make typecheck
make test
```

Run the base server locally after creating `.env` from `.env.example`. You can
also keep Mac-specific values in a private `mac.env` file and copy it to `.env`
before local startup:

```bash
cp .env.example .env
cp mac.env .env
python3 -c "import secrets; print(secrets.token_hex(32))"
make base-up
```

Put the generated token in `.env` as `PIWATCHER_API_KEY` before starting the server.

The dashboard is served at `http://localhost:8000`.

For Mac development, use a writable local frame path in `.env`:

```text
FRAME_STORAGE_PATH=./tmp/piwatcher/frames
```

## Base Station Setup

Clone or copy the repository to `/home/pi/PiWatcher` on the Pi 5, then install `uv` for the `pi` user. Create `/home/pi/PiWatcher/.env` and set the base station values.

```bash
cd /home/pi/PiWatcher
cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Use the generated token as `PIWATCHER_API_KEY`. For deployment, make sure the database URL points at the Compose PostgreSQL service:

```text
PIWATCHER_API_KEY=<shared-token>
DATABASE_URL=postgresql+asyncpg://piwatcher:piwatcher@127.0.0.1:5432/piwatcher
FRAME_STORAGE_PATH=/home/bostdiek/piwatcher/frames
DISPLAY_TIMEZONE=America/Chicago
ENABLE_INFERENCE=false
LLAMA_SWAP_URL=http://127.0.0.1:8080/v1
LLAMA_SWAP_MODEL=lfm2.5-vl-450m-q4_0
NTFY_TOPIC=piwatcher
NTFY_URL=https://ntfy.sh
MAX_INFERENCE_TEMP_C=72.0
COOLDOWN_TEMP_C=60.0
INFERENCE_GAP_SECONDS=15
HEARTBEAT_TTL_DAYS=90
```

Start PostgreSQL, apply migrations, and run the base server in the foreground:

```bash
make base-up
```

`make base-up` does not start inference unless `ENABLE_INFERENCE=true` is exported for the make command. This keeps event ingestion, storage, heartbeat, and the dashboard available when the Pi 5 inference stack is not installed or is temporarily unavailable.

For local development with Docker llama-swap, prepare the model directory and start the Compose service explicitly:

```bash
make base-llama-up
```

The Docker llama-swap path is intended for local development or systems where the selected image supports the host architecture. On Raspberry Pi 5, prefer the host inference service because `ghcr.io/mostlygeek/llama-swap:unified-vulkan` may not provide a usable `linux/arm64/v8` image.

Pi 5 host inference uses this path:

```text
PiWatcher base app -> http://127.0.0.1:8080/v1 -> host llama-swap -> host llama-server -> local GGUF file
```

Enable it only after `llama-swap`, `llama-server`, and the model file are present:

```text
ENABLE_INFERENCE=true
LLAMA_SWAP_URL=http://127.0.0.1:8080/v1
LLAMA_SWAP_MODEL=lfm2.5-vl-450m-q4_0
LLAMA_SWAP_BIN=/home/bostdiek/.local/bin/llama-swap
LLAMA_SERVER_BIN=/home/bostdiek/Projects/llama.cpp/build/bin/llama-server
LLAMA_SWAP_MODELS_DIR=/home/bostdiek/piwatcher/models
LLAMA_SWAP_MODEL_FILE=LFM2.5-VL-450M-Q4_0.gguf
LLAMA_SWAP_MODEL_URL=<optional-download-url>
LLAMA_SWAP_MMPROJ_FILE=mmproj-LFM2.5-VL-450m-Q8_0.gguf
LLAMA_SWAP_MMPROJ_URL=<optional-download-url>
LLAMA_SWAP_MEDIA_PATH=/home/bostdiek/Downloads
```

The generated llama-swap config passes an explicit local `--model` path to `llama-server`. The `--model` option does not download model files. `deploy/setup-llama-swap.sh` downloads `LLAMA_SWAP_MODEL_URL` only when that URL is configured; otherwise, place `LLAMA_SWAP_MODELS_DIR/LLAMA_SWAP_MODEL_FILE` on disk before starting inference.

Vision classification requires the matching multimodal projector. When `LLAMA_SWAP_MMPROJ_FILE` is configured, `deploy/setup-llama-swap.sh` also downloads `LLAMA_SWAP_MMPROJ_URL` when needed and adds `--mmproj` to the generated llama-server command.

The Pi 5 boots from NVMe, so the default deployment paths use `bostdiek`-owned directories under `/home/bostdiek/piwatcher` instead of a separate `/mnt/nvme` mount.

Prepare the host inference config and install the systemd unit:

```bash
bash deploy/setup-llama-swap.sh
sudo cp deploy/piwatcher-inference.service /etc/systemd/system/piwatcher-inference.service
sudo systemctl daemon-reload
sudo systemctl enable --now piwatcher-inference.service
sudo systemctl status piwatcher-inference.service
```

From a development machine, deploy the host inference files directly to the Pi 5 using the same SSH pattern as camera deploys. This creates the model directory with the correct owner, runs the setup script, installs the systemd unit, and leaves the service stopped unless requested:

```bash
make deploy-inference BASE=pi5.local BASE_USER=bostdiek
START_INFERENCE=true make deploy-inference BASE=pi5.local BASE_USER=bostdiek
```

Keep Pi-specific base settings in a private `pi5.env` file. `make deploy-base`
copies `pi5.env` to the remote project as `.env` when the file exists, which
keeps Mac development paths out of the Pi runtime. Use `BASE_ENV_FILE` to deploy
a different local env profile.

```bash
cp pi5.env.example pi5.env
START_BASE=true ENABLE_BASE_SERVICE=true make deploy-base BASE=pi5.local BASE_USER=bostdiek
BASE_ENV_FILE=staging.env make deploy-base BASE=pi5.local BASE_USER=bostdiek
```

Keep `mac.env`, `pi5.env`, and `.env` out of source control because they contain
the shared API key and host-specific paths.

Validate the host inference path before enabling `ENABLE_INFERENCE=true` for unattended operation:

```bash
"${LLAMA_SERVER_BIN}" --version
test -r "${LLAMA_SWAP_MODELS_DIR}/${LLAMA_SWAP_MODEL_FILE}"
curl http://127.0.0.1:8080/v1/models
curl http://127.0.0.1:8080/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"lfm2.5-vl-450m-q4_0","messages":[{"role":"user","content":"Say ok."}],"max_tokens":8}'
```

Use the foreground command for local development and manual Pi 5 smoke testing. For a Pi 5 that should start PiWatcher automatically on boot, install the systemd service from the repository root instead:

```bash
make base-db-up
make base-migrate
sudo cp deploy/piwatcher-base.service /etc/systemd/system/piwatcher-base.service
sudo systemctl daemon-reload
sudo systemctl enable --now piwatcher-base.service
sudo systemctl status piwatcher-base.service
```

Install the heartbeat TTL timer:

```bash
sudo cp deploy/piwatcher-ttl.service /etc/systemd/system/piwatcher-ttl.service
sudo cp deploy/piwatcher-ttl.timer /etc/systemd/system/piwatcher-ttl.timer
sudo systemctl daemon-reload
sudo systemctl enable --now piwatcher-ttl.timer
systemctl list-timers piwatcher-ttl.timer
```

## Camera Setup

For local testing, deploy a camera from your Mac with a generated camera `.env` based on the root `.env` token:

```bash
make deploy-camera CAM=pizero.local CAMERA_USER=pizero
```

That target detects your Mac's Wi-Fi IP for `SERVER_URL`, copies the camera source package, writes `/home/<user>/piwatcher/.env`, runs the setup script, and leaves the camera service stopped for local safety. Start it explicitly when you are ready to test capture:

```bash
START_CAMERA=true make deploy-camera CAM=pizero.local CAMERA_USER=pizero
```

Enable camera startup on boot only when the node is ready for unattended operation:

```bash
ENABLE_CAMERA_SERVICE=true START_CAMERA=true make deploy-camera CAM=feeder-cam.local CAMERA_USER=pi
```

Provision each Pi Zero manually when you want to run setup without writing the camera `.env` from your local machine:

```bash
make setup-camera CAM=feeder-cam.local
```

The setup script installs Raspberry Pi camera dependencies, enables I2C for PiSugar battery readings, configures passwordless `rfkill` access for Wi-Fi power control, and installs the systemd service. It leaves the service disabled unless `ENABLE_CAMERA_SERVICE=true` is set.

Create `/home/pi/piwatcher/.env` on each camera:

```text
CAMERA_ID=feeder-cam
SERVER_URL=http://pi5.local:8000
PIWATCHER_API_KEY=<shared-token>
MOTION_THRESHOLD=7.0
MIN_CHANGED_PCT=2.0
CAPTURE_FPS=2.0
CAPTURE_MIN_DURATION=10.0
COOLDOWN_SECONDS=5.0
HEARTBEAT_INTERVAL=900
LORES_WIDTH=160
LORES_HEIGHT=120
MAIN_WIDTH=1024
MAIN_HEIGHT=1024
FRAME_QUEUE_DIR=/tmp/piwatcher/frames
WIFI_POWER_SAVE=true
WIFI_STARTUP_GRACE_SECONDS=600
```

Start the camera service after the `.env` file exists:

```bash
ssh pi@feeder-cam.local "sudo systemctl start piwatcher-camera.service"
```

Deploy code updates to all configured cameras:

```bash
make update-cameras
```

Deploy to a specific camera list:

```bash
make update-cameras CAMERAS="feeder-cam.local pond-cam.local"
```

## Configuration Reference

Base station settings are loaded from `.env` by `piwatcher_base.config.Settings`.

| Variable                 | Purpose                                                            | Default                                        |
| ------------------------ | ------------------------------------------------------------------ | ---------------------------------------------- |
| `PIWATCHER_API_KEY`      | Bearer token required for camera API calls                         | Required                                       |
| `DATABASE_URL`           | Async SQLAlchemy database URL                                      | Required                                       |
| `FRAME_STORAGE_PATH`     | Root directory for retained JPEG frames                            | `/home/bostdiek/piwatcher/frames`              |
| `DISPLAY_TIMEZONE`       | IANA timezone used for dashboard timestamp display                 | Local host timezone                            |
| `ENABLE_INFERENCE`       | Enables background inference after event upload                    | `false`                                        |
| `LLAMA_SWAP_URL`         | OpenAI-compatible llama-swap endpoint                              | `http://localhost:8080/v1`                     |
| `LLAMA_SWAP_MODEL`       | Model name sent to llama-swap                                      | `lfm2.5-vl-450m-q4_0`                          |
| `LLAMA_SWAP_IMAGE`       | Docker image for local/development llama-swap                      | `ghcr.io/mostlygeek/llama-swap:unified-vulkan` |
| `LLAMA_SWAP_RUNTIME`     | Setup mode for generated llama-swap config                         | `host`                                         |
| `LLAMA_SWAP_BIN`         | Host llama-swap executable used by systemd                         | `/home/bostdiek/.local/bin/llama-swap`         |
| `LLAMA_SERVER_BIN`       | Host llama-server executable written into llama-swap config        | `/home/.../llama-server`                       |
| `LLAMA_SWAP_LISTEN`      | Host llama-swap listen address                                     | `127.0.0.1:8080`                               |
| `LLAMA_SWAP_MODELS_DIR`  | Host directory containing local GGUF model files                   | `/home/bostdiek/piwatcher/models`              |
| `LLAMA_SWAP_MODEL_FILE`  | Main GGUF model filename expected by llama-swap config             | `LFM2.5-VL-450M-Q4_0.gguf`                     |
| `LLAMA_SWAP_MMPROJ_FILE` | Multimodal projector GGUF filename expected by llama-swap config   | `mmproj-LFM2.5-VL-450m-Q8_0.gguf`              |
| `LLAMA_SWAP_MODEL_URL`   | Optional URL downloaded into `LLAMA_SWAP_MODEL_FILE` when missing  | Empty                                          |
| `LLAMA_SWAP_MMPROJ_URL`  | Optional URL downloaded into `LLAMA_SWAP_MMPROJ_FILE` when missing | Empty                                          |
| `LLAMA_SWAP_MEDIA_PATH`  | Host media path passed to llama-server for vision requests         | `/home/bostdiek/Downloads`                     |
| `NTFY_TOPIC`             | ntfy topic for detection alerts                                    | `piwatcher`                                    |
| `NTFY_URL`               | ntfy server URL                                                    | `https://ntfy.sh`                              |
| `MAX_INFERENCE_TEMP_C`   | Temperature where inference pauses                                 | `72.0`                                         |
| `COOLDOWN_TEMP_C`        | Temperature required before inference resumes                      | `60.0`                                         |
| `INFERENCE_GAP_SECONDS`  | Minimum delay between inference calls                              | `15`                                           |
| `HEARTBEAT_TTL_DAYS`     | Heartbeat retention window                                         | `90`                                           |

Camera settings are loaded from `/home/pi/piwatcher/.env`.

| Variable                      | Purpose                                                                          | Default                 |
| ----------------------------- | -------------------------------------------------------------------------------- | ----------------------- |
| `CAMERA_ID`                   | Stable camera identifier stored with events                                      | Required                |
| `SERVER_URL`                  | Base station URL                                                                 | Required                |
| `PIWATCHER_API_KEY`           | Shared bearer token                                                              | Required                |
| `MOTION_THRESHOLD`            | Pixel difference threshold for motion detection                                  | `7.0`                   |
| `MIN_CHANGED_PCT`             | Minimum changed-pixel percentage                                                 | `2.0`                   |
| `CAPTURE_FPS`                 | JPEG capture rate during motion events                                           | `2.0`                   |
| `CAPTURE_MIN_DURATION`        | Minimum event capture duration in seconds                                        | `10.0`                  |
| `COOLDOWN_SECONDS`            | Quiet period before closing an event                                             | `5.0`                   |
| `HEARTBEAT_INTERVAL`          | Standalone heartbeat interval in seconds                                         | `900`                   |
| `LORES_WIDTH`                 | Low-resolution motion frame width                                                | `160`                   |
| `LORES_HEIGHT`                | Low-resolution motion frame height                                               | `120`                   |
| `MAIN_WIDTH`                  | Captured JPEG width                                                              | `1024`                  |
| `MAIN_HEIGHT`                 | Captured JPEG height                                                             | `1024`                  |
| `FRAME_QUEUE_DIR`             | Local queue for captured frames                                                  | `/tmp/piwatcher/frames` |
| `WIFI_POWER_SAVE`             | Whether the camera may turn Wi-Fi off between uploads                            | `true`                  |
| `WIFI_STARTUP_GRACE_SECONDS`  | Startup recovery window where Wi-Fi stays on before power saving can turn it off | `600`                   |
| `QUEUE_DRAIN_MAX_EVENTS`      | Maximum durable queue events drained per idle cycle                              | `2`                     |
| `QUEUE_DRAIN_MAX_SECONDS`     | Maximum wall-clock seconds spent draining queue per idle cycle                   | `15`                    |
| `QUEUE_RETRY_INITIAL_SECONDS` | Initial retry backoff after a retryable upload failure                           | `30`                    |
| `QUEUE_RETRY_MAX_SECONDS`     | Maximum retry backoff cap for durable queue uploads                              | `3600`                  |
| `QUEUE_UPLOAD_LEASE_SECONDS`  | Lease timeout before stale uploading bundles are returned to pending             | `300`                   |

## Camera Queue Backlog Cleanup

The camera runtime writes new captures into durable event bundles under `FRAME_QUEUE_DIR/events/` with one `event.json` manifest per event bundle. Upload retries rely on these bundles so the original motion event boundaries stay intact across restarts and network failures.

Bundle layout:

```text
FRAME_QUEUE_DIR/
    events/
        YYYY/
            MM/
                DD/
                    <camera-id-slug>/
                        <event-id>/
                            event.json
                            frame_0000.jpg
                            frame_0001.jpg
```

Each bundle manifest stores durable event metadata including `event_id`, `camera_id`, `event_start`, optional `event_end`, ordered frame entries, and retry state fields such as `status`, `attempt_count`, `last_attempt_at`, `next_attempt_at`, and `last_error`.

Top-level loose `*.jpg` files in `FRAME_QUEUE_DIR` are treated as legacy backlog. They are included in `queue_depth` telemetry, but they do not preserve reliable event boundaries and should not be replayed as complete events.

Metric meaning:

* `queue_depth` is queued frame count, not queued event count
* `queued_event_count` is queued durable event bundle count and can be null when the camera has not reported the metric yet

In mixed fleets, older cameras can still report only `queue_depth`. In that case, dashboard views should treat `queued_event_count` as missing data rather than as zero.

Use these explicit cleanup operations for legacy loose JPEG files:

1. Inventory (non-destructive).
2. Quarantine (recommended first destructive action).
3. Delete only after explicit confirmation.

Use this workflow in order to reduce accidental data loss.

1. Inventory only (non-destructive default):

```bash
python - <<'PY'
from pathlib import Path
from piwatcher_camera.queue import inventory_legacy_backlog

summary = inventory_legacy_backlog(Path('/tmp/piwatcher/frames'))
print(summary)
PY
```

1. Quarantine loose files into `FRAME_QUEUE_DIR/legacy/YYYYMMDDTHHMMSSZ/`:

```bash
python - <<'PY'
from datetime import datetime, UTC
from pathlib import Path
from piwatcher_camera.queue import quarantine_legacy_backlog

result = quarantine_legacy_backlog(
    Path('/tmp/piwatcher/frames'),
    now=datetime.now(UTC),
)
print(result)
PY
```

1. Delete loose files only with explicit confirmation:

```bash
python - <<'PY'
from pathlib import Path
from piwatcher_camera.queue import delete_legacy_backlog

result = delete_legacy_backlog(
    Path('/tmp/piwatcher/frames'),
    confirm_delete=True,
)
print(result)
PY
```

Before quarantine or delete actions, stop the camera service or lock queue writes so new files are not created while cleanup runs.

> [!WARNING]
> Legacy loose `*.jpg` files do not carry reliable event start/end boundaries, so replaying them as normal motion events can produce misleading event history.

### Deployment and migration order

Roll out base changes before camera changes:

1. Deploy updated base code.
2. Apply base database migrations so heartbeat writes can persist `queued_event_count`.
3. Restart or redeploy the base service.
4. Deploy updated camera code.
5. Verify dashboard health cards show queued frames and queued events separately.

If you roll out cameras before the base migration, heartbeat writes can fail on the base when cameras submit `queued_event_count`.

Recommended migration command on the base host:

```bash
make base-migrate
```

After camera rollout, evaluate legacy loose files with inventory or quarantine before any deletion.

## Make Targets

| Target                         | Description                                                                                                           |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `make lint`                    | Run Ruff lint and format checks                                                                                       |
| `make format`                  | Format code and apply safe Ruff fixes                                                                                 |
| `make typecheck`               | Run `ty` type checking                                                                                                |
| `make test`                    | Run the test suite                                                                                                    |
| `make test-cov`                | Run tests with coverage output                                                                                        |
| `make base-db-up`              | Start the PostgreSQL Compose service                                                                                  |
| `make base-llama-up`           | Prepare model storage and start the local/development llama-swap Compose service                                      |
| `make base-inference-up`       | Alias for explicit local/development inference startup                                                                |
| `make base-migrate`            | Apply Alembic migrations for the base station database                                                                |
| `make base-up`                 | Start PostgreSQL, apply migrations, and run the base server. Add `ENABLE_INFERENCE=true` to start local inference too |
| `make deploy-base`             | Deploy the base app and copy `pi5.env` to the Pi as `.env` when present                                               |
| `make deploy-camera`           | Generate camera config locally, rsync code/config, run setup, and leave the camera stopped unless `START_CAMERA=true` |
| `make update-cameras`          | Rsync camera package code and restart camera services                                                                 |
| `make setup-camera CAM=<host>` | Copy and run the first-time Pi Zero provisioning script                                                               |

## Operational Checks

Use these commands when checking a deployed system:

```bash
sudo systemctl status piwatcher-base.service
sudo journalctl -u piwatcher-base.service -f
docker compose ps
sudo systemctl list-timers piwatcher-ttl.timer
ssh pi@feeder-cam.local "systemctl status piwatcher-camera.service"
```

Frame storage should be on durable local storage, such as an NVMe mount. Keep enough free space for retained training images, and back up the PostgreSQL volume before replacing or reimaging the Pi 5.
