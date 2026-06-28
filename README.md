---
title: PiWatcher
description: Motion-triggered Raspberry Pi wildlife camera system with a Pi 5 base station, PostgreSQL storage, and LAN dashboard.
ms.date: 2026-06-27
ms.topic: overview
---

## Overview

PiWatcher is a local wildlife camera system for battery-powered Raspberry Pi Zero W camera nodes and a Raspberry Pi 5 base station. Camera nodes detect motion with `picamera2`, capture short JPEG bursts, and upload events over Wi-Fi. The base station receives frames through FastAPI, stores metadata in PostgreSQL, keeps images on disk, runs local AI inference through llama-swap, and serves a LAN dashboard.

```mermaid
flowchart TD
    camera[Pi Zero W camera nodes]
    motion[Motion detection<br>picamera2 lores frames]
    capture[1024x1024 JPEG bursts<br>2 fps while motion continues]
    api[Pi 5 FastAPI ingest<br>Bearer-token API]
    storage[Frame storage<br>NVMe date/camera/event folders]
    db[(PostgreSQL<br>events, frames, heartbeats)]
    inference[llama-swap inference<br>LFM2-VL-450M with thermal gating]
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
│   ├── piwatcher-ttl.service        Heartbeat cleanup oneshot service
│   ├── piwatcher-ttl.timer          Daily heartbeat cleanup timer
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

Run the base server locally after creating `.env` from `.env.example`:

```bash
cp .env.example .env
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
FRAME_STORAGE_PATH=/mnt/nvme/piwatcher/frames
LLAMA_SWAP_URL=http://127.0.0.1:8080/v1
LLAMA_SWAP_MODEL=lfm2-vl-450m
NTFY_TOPIC=piwatcher
NTFY_URL=https://ntfy.sh
MAX_INFERENCE_TEMP_C=72.0
COOLDOWN_TEMP_C=60.0
INFERENCE_GAP_SECONDS=15
HEARTBEAT_TTL_DAYS=90
```

Start PostgreSQL, llama-swap, apply migrations, and run the base server in the foreground:

```bash
make base-up
```

`make base-up` prepares `tmp/llama-swap/models`, starts the llama-swap Compose service, and downloads configured model files when `LLAMA_SWAP_MODEL_URL` and `LLAMA_SWAP_MMPROJ_URL` are set. If those URLs are not set, place the GGUF files listed in `.env` into `LLAMA_SWAP_MODELS_DIR` before using inference.

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

| Variable | Purpose | Default |
| --- | --- | --- |
| `PIWATCHER_API_KEY` | Bearer token required for camera API calls | Required |
| `DATABASE_URL` | Async SQLAlchemy database URL | Required |
| `FRAME_STORAGE_PATH` | Root directory for retained JPEG frames | `/mnt/nvme/piwatcher/frames` |
| `LLAMA_SWAP_URL` | OpenAI-compatible llama-swap endpoint | `http://localhost:8080/v1` |
| `LLAMA_SWAP_MODEL` | Model name sent to llama-swap | `lfm2-vl-450m` |
| `LLAMA_SWAP_IMAGE` | Docker image for the llama-swap service | `ghcr.io/mostlygeek/llama-swap:unified-vulkan` |
| `LLAMA_SWAP_MODELS_DIR` | Host directory mounted into llama-swap at `/models` | `./tmp/llama-swap/models` |
| `LLAMA_SWAP_MODEL_FILE` | Main GGUF model filename expected by llama-swap config | `lfm2-vl-450m.gguf` |
| `LLAMA_SWAP_MMPROJ_FILE` | Multimodal projector GGUF filename expected by llama-swap config | `lfm2-vl-450m-mmproj.gguf` |
| `LLAMA_SWAP_MODEL_URL` | Optional URL downloaded into `LLAMA_SWAP_MODEL_FILE` when missing | Empty |
| `LLAMA_SWAP_MMPROJ_URL` | Optional URL downloaded into `LLAMA_SWAP_MMPROJ_FILE` when missing | Empty |
| `NTFY_TOPIC` | ntfy topic for detection alerts | `piwatcher` |
| `NTFY_URL` | ntfy server URL | `https://ntfy.sh` |
| `MAX_INFERENCE_TEMP_C` | Temperature where inference pauses | `72.0` |
| `COOLDOWN_TEMP_C` | Temperature required before inference resumes | `60.0` |
| `INFERENCE_GAP_SECONDS` | Minimum delay between inference calls | `15` |
| `HEARTBEAT_TTL_DAYS` | Heartbeat retention window | `90` |

Camera settings are loaded from `/home/pi/piwatcher/.env`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `CAMERA_ID` | Stable camera identifier stored with events | Required |
| `SERVER_URL` | Base station URL | Required |
| `PIWATCHER_API_KEY` | Shared bearer token | Required |
| `MOTION_THRESHOLD` | Pixel difference threshold for motion detection | `7.0` |
| `MIN_CHANGED_PCT` | Minimum changed-pixel percentage | `2.0` |
| `CAPTURE_FPS` | JPEG capture rate during motion events | `2.0` |
| `CAPTURE_MIN_DURATION` | Minimum event capture duration in seconds | `10.0` |
| `COOLDOWN_SECONDS` | Quiet period before closing an event | `5.0` |
| `HEARTBEAT_INTERVAL` | Standalone heartbeat interval in seconds | `900` |
| `LORES_WIDTH` | Low-resolution motion frame width | `160` |
| `LORES_HEIGHT` | Low-resolution motion frame height | `120` |
| `MAIN_WIDTH` | Captured JPEG width | `1024` |
| `MAIN_HEIGHT` | Captured JPEG height | `1024` |
| `FRAME_QUEUE_DIR` | Local queue for captured frames | `/tmp/piwatcher/frames` |
| `WIFI_POWER_SAVE` | Whether the camera may turn Wi-Fi off between uploads | `true` |
| `WIFI_STARTUP_GRACE_SECONDS` | Startup recovery window where Wi-Fi stays on before power saving can turn it off | `600` |

## Make Targets

| Target | Description |
| --- | --- |
| `make lint` | Run Ruff lint and format checks |
| `make format` | Format code and apply safe Ruff fixes |
| `make typecheck` | Run `ty` type checking |
| `make test` | Run the test suite |
| `make test-cov` | Run tests with coverage output |
| `make base-db-up` | Start the PostgreSQL Compose service |
| `make base-llama-up` | Prepare model storage and start the llama-swap Compose service |
| `make base-migrate` | Apply Alembic migrations for the base station database |
| `make base-up` | Start PostgreSQL and llama-swap, apply migrations, and run the base server |
| `make deploy-camera` | Generate camera config locally, rsync code/config, run setup, and leave the camera stopped unless `START_CAMERA=true` |
| `make update-cameras` | Rsync camera package code and restart camera services |
| `make setup-camera CAM=<host>` | Copy and run the first-time Pi Zero provisioning script |

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