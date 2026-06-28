---
title: Pi 5 Host Inference Current Surfaces Research
description: Current PiWatcher implementation surfaces relevant to planning host-installed Pi 5 inference ownership.
ms.date: 2026-06-28
ms.topic: research
---

## Research Topics

Task Planner request: verify the current implementation surfaces relevant to
planning host-installed Raspberry Pi 5 inference ownership. Inspect only current
workspace files as needed and do not modify source files.

Primary question: what code, configuration, deployment, and documentation
currently own or reference llama-swap, llama-server, model files, and inference
enablement?

Note: the working tree contains user changes. Findings below are grounded in the
current workspace contents observed on 2026-06-28, not a clean repository state.

## Files Found And Missing

Found requested files and surfaces:

* deploy/setup-llama-swap.sh
* deploy/llama-swap/config.yaml
* deploy/piwatcher-base.service
* deploy/piwatcher-camera.service
* deploy/piwatcher-ttl.service
* Makefile
* docker-compose.yml
* README.md
* .env.example
* packages/camera/.env.example
* packages/base/src/piwatcher_base/config.py
* packages/base/src/piwatcher_base/inference.py
* packages/base/src/piwatcher_base/routes/events.py
* packages/base/tests/test_inference.py
* packages/base/tests/test_events.py

Missing or not found in workspace search:

* Root .env file was not found by file search. Only .env.example files were
  found.
* No dedicated host-installed llama-swap systemd service was found under
  deploy/*.service.
* No dedicated host-installed llama-server systemd service was found under
  deploy/*.service.
* No committed host inference install script separate from
  deploy/setup-llama-swap.sh was found in the inspected surfaces.

## Current Implementation Details

### deploy/setup-llama-swap.sh

Line ranges: deploy/setup-llama-swap.sh lines 1-113.

Key details:

* The script prepares llama-swap model storage and optionally downloads model
  files. It does not install llama.cpp, llama-server, Go, or llama-swap.
* It reads configuration from environment variables or root .env through
  read_env_value and setting_value at lines 20-59.
* It writes deploy/llama-swap/config.yaml at lines 65-78.
* The generated model command uses `llama-server` by PATH lookup and container
  paths: `/models/${model_file}` and `/models/${mmproj_file}` at line 74.
* Defaults are resolved at lines 91-96:
  `LLAMA_SWAP_MODELS_DIR`, `LLAMA_SWAP_MODEL`, `LLAMA_SWAP_MODEL_FILE`,
  `LLAMA_SWAP_MMPROJ_FILE`, `LLAMA_SWAP_MODEL_URL`, and
  `LLAMA_SWAP_MMPROJ_URL`.
* Missing model files produce guidance but do not fail the script at lines
  104-111.

Planning implication: this script is the closest current owner for generated
llama-swap config and model file preparation, but it currently assumes a Docker
runtime layout. Host inference planning must change command generation to use
absolute host paths and an explicit llama-server binary path.

### deploy/llama-swap/config.yaml

Line ranges: deploy/llama-swap/config.yaml lines 1-4.

Key details:

* The committed config defines one model: `lfm2-vl-450m`.
* Its command is `llama-server --host 127.0.0.1 --port ${PORT} --model
  /models/lfm2-vl-450m.gguf --mmproj /models/lfm2-vl-450m-mmproj.gguf`.
* The configured TTL is 300 seconds.

Planning implication: this config is currently container-oriented. Host-owned
inference needs generated host paths rather than `/models`, and should avoid
relying on systemd PATH to locate `llama-server`.

### docker-compose.yml

Line ranges: docker-compose.yml lines 1-38.

Key details:

* PostgreSQL is defined independently at lines 2-17.
* The `llama-swap` service is defined at lines 19-36.
* The llama-swap image defaults to
  `ghcr.io/mostlygeek/llama-swap:unified-vulkan` at line 20.
* Port mapping defaults `${LLAMA_SWAP_PORT:-8080}:8080` at line 23.
* The generated config is mounted into the container at line 25.
* `${LLAMA_SWAP_MODELS_DIR:-./tmp/llama-swap/models}` is mounted to `/models`
  at line 26.
* The service starts llama-swap with `--config` and `--listen 0.0.0.0:8080` at
  lines 27-31.
* The healthcheck calls `http://127.0.0.1:8080/health` and checks for `OK` at
  lines 32-36.

Planning implication: Docker Compose currently owns runtime startup for
llama-swap in development and `make base-up`. Host inference ownership either
needs to remove this dependency from Pi 5 paths or split Docker and host targets
so PostgreSQL remains Compose-owned while inference becomes systemd or host
process-owned.

### Makefile

Line ranges: Makefile lines 1-58.

Key details:

* `base-llama-up` runs `bash deploy/setup-llama-swap.sh` then
  `docker compose up -d llama-swap` at lines 33-35.
* `base-up` depends on `base-db-up base-llama-up base-migrate` and then runs
  `uv run --package piwatcher-base piwatcher-server` at lines 40-41.
* `base-db-up` starts only PostgreSQL at lines 29-30.

Planning implication: local foreground startup currently makes llama-swap a
hard prerequisite of `make base-up`, even though the application can skip
inference when disabled. A host inference plan should decide whether `base-up`
remains strict, becomes conditional on `ENABLE_INFERENCE`, or gains separate
host and Docker inference targets.

### deploy/piwatcher-base.service

Line ranges: deploy/piwatcher-base.service lines 1-17.

Key details:

* The unit has `After=network-online.target docker.service` and
  `Wants=network-online.target docker.service` at lines 3-4.
* It loads `/home/pi/PiWatcher/.env` at line 11.
* It starts only PostgreSQL through Docker Compose with
  `ExecStartPre=/usr/bin/docker compose up -d postgres` at line 12.
* It starts the FastAPI server with
  `/home/pi/.local/bin/uv run --package piwatcher-base piwatcher-server` at
  line 13.
* It does not start llama-swap or llama-server.

Planning implication: the deployed base systemd unit already avoids hard-owning
inference. Host inference can be added as a separate service with a soft
relationship, rather than making PiWatcher API startup depend on inference.

### Other deploy/*.service files

Line ranges:

* deploy/piwatcher-camera.service lines 1-15
* deploy/piwatcher-ttl.service lines 1-8

Key details:

* deploy/piwatcher-camera.service starts the camera watcher with
  `/usr/bin/python3 -m piwatcher_camera.watcher` and has no inference ownership.
* deploy/piwatcher-ttl.service deletes old heartbeat rows with psql and has no
  inference ownership.

Planning implication: no existing service file owns host inference. A host plan
needs a new service unit or an explicit decision to keep inference managed by
Make/manual commands.

### .env examples

Line ranges:

* .env.example lines 1-18
* packages/camera/.env.example inspected by file discovery only for presence

Key details:

* Root .env.example contains llama-swap endpoint, model, image, model directory,
  model filenames, optional URL placeholders, and thermal settings at lines
  5-16.
* Root .env.example does not include `ENABLE_INFERENCE`, despite the application
  having an `inference_enabled` setting.
* No root .env was found in workspace search.

Planning implication: enabling inference currently requires a setting that is
implemented in code but missing from the main example environment file and the
README configuration table. Host inference planning should include documenting
`ENABLE_INFERENCE=true` or intentionally preserving disabled-by-default behavior.

### packages/base/src/piwatcher_base/config.py

Line ranges: packages/base/src/piwatcher_base/config.py lines 1-75.

Key details:

* `llama_swap_url` defaults to `http://localhost:8080/v1` and accepts
  `LLAMA_SWAP_URL` or `PIWATCHER_LLAMA_SWAP_URL` at lines 25-28.
* `llama_swap_model` defaults to `lfm2-vl-450m` and accepts
  `LLAMA_SWAP_MODEL` or `PIWATCHER_LLAMA_SWAP_MODEL` at lines 29-32.
* Thermal settings and inference gap settings are present at lines 45-57.
* `inference_enabled` defaults to false and accepts `ENABLE_INFERENCE` or
  `PIWATCHER_ENABLE_INFERENCE` at lines 58-61.
* No model file path or llama-server binary path is present in application
  settings.

Planning implication: application runtime ownership is intentionally endpoint
based. Host-specific model paths and llama-server paths belong in deployment
setup, not base app settings, unless the team wants the app to manage inference
process lifecycle directly.

### packages/base/src/piwatcher_base/inference.py

Line ranges: packages/base/src/piwatcher_base/inference.py lines 1-211.

Key details:

* `LlamaSwapClassifier.classify_frame` base64-encodes a frame and posts to
  `{llama_swap_url}/chat/completions` with OpenAI-compatible request shape at
  lines 56-91.
* The model sent to the endpoint comes from `settings.llama_swap_model` at line
  62.
* `wait_for_safe_temperature` gates inference based on Pi CPU temperature at
  lines 126-132.
* `classify_event_background` returns early when `inference_enabled` is false
  at lines 149-158.
* Endpoint connection failures are logged and break the classification loop
  without crashing the server path at lines 166-173.
* HTTP, file, response, validation, and JSON failures are warning-level per
  frame at lines 174-184.
* The selected classification is stored on the Event and non-empty labels send
  ntfy notifications at lines 189-211.

Planning implication: runtime failure isolation already exists inside the app.
The host inference plan should preserve this property by avoiding hard systemd
dependencies that prevent event ingestion when inference is unavailable.

### packages/base/src/piwatcher_base/routes/events.py

Line ranges: packages/base/src/piwatcher_base/routes/events.py lines 1-140.

Key details:

* The event route imports `classify_event_background` at line 24.
* On event upload, stored frame paths are passed to a FastAPI background task at
  line 97.
* The event route always queues the background task; the task itself decides
  whether inference is enabled.

Planning implication: endpoint startup and event upload do not need to know
whether host inference is installed. This supports a soft ownership boundary:
setup/service orchestration owns inference, while the app remains endpoint-only.

### Tests

Line ranges:

* packages/base/tests/test_inference.py lines 1-101
* packages/base/tests/test_events.py lines 1-50

Key details:

* test_inference.py covers frame sampling, majority label selection, thermal
  wait behavior, and disabled inference leaving an event unclassified.
* test_events.py verifies that event upload queues `classify_event_background`.
* No current test was found for host setup script behavior, generated
  llama-swap config host paths, systemd inference service wiring, or Makefile
  host inference targets.

Planning implication: a host inference implementation should add focused tests
or script checks around config generation and optional inference behavior, not
only Python inference adapter tests.

### README.md

Line ranges: README.md lines 1-292.

Key details:

* README describes Pi 5 local AI inference through llama-swap at lines 10 and
  20.
* Prerequisites mention Docker Compose and access to llama-swap at line 64.
* Base station example environment includes `LLAMA_SWAP_URL` and
  `LLAMA_SWAP_MODEL` at lines 114-115.
* Setup says `make base-up` starts PostgreSQL, llama-swap, migrations, and the
  base server at lines 124-130.
* Configuration reference documents llama-swap image, model directory,
  filenames, and optional model URLs at lines 229-236.
* Make target reference documents `base-llama-up` and `base-up` as starting
  llama-swap through Compose at lines 275-277.
* README does not list `ENABLE_INFERENCE` in the base station configuration
  table, even though code supports it.

Planning implication: docs currently present Docker-backed llama-swap as the
base startup path. Host inference ownership planning should include README and
.env.example updates so users know how inference is installed, started, enabled,
and degraded when unavailable.

## Key Current Ownership Model

Current ownership is split across layers:

* Application code owns inference request shape, optional enablement, thermal
  gating, result persistence, and error isolation.
* deploy/setup-llama-swap.sh owns model directory creation, optional downloads,
  and generated llama-swap config.
* docker-compose.yml owns llama-swap runtime startup today.
* Makefile owns local startup sequencing and currently treats llama-swap Compose
  startup as part of `base-up`.
* deploy/piwatcher-base.service owns only PostgreSQL startup and the base API,
  not inference startup.
* Documentation and .env.example mostly describe Docker-backed llama-swap, but
  do not surface `ENABLE_INFERENCE`.

## Recommended Plan Implications

* Treat host inference as deployment infrastructure, not application business
  logic. Keep packages/base/src/piwatcher_base/inference.py endpoint-oriented.
* Extend or replace deploy/setup-llama-swap.sh as the host inference setup owner
  because it already owns config and model preparation.
* Generate host-oriented deploy/llama-swap/config.yaml using absolute model
  paths and an explicit `LLAMA_SERVER_BIN`; do not rely on `/models` or PATH in
  a systemd context.
* Add a dedicated host llama-swap systemd unit if Pi 5 inference should run on
  boot. Prefer a soft relationship from piwatcher-base.service, such as `Wants`,
  rather than `Requires`.
* Decide whether Makefile should keep Docker llama-swap for local development,
  add host-specific targets, or make `base-up` conditional on
  `ENABLE_INFERENCE`.
* Add `ENABLE_INFERENCE` to .env.example and README if inference is expected to
  be intentionally enabled by operators.
* Preserve failure isolation: model/download/startup failures should not prevent
  PiWatcher base API from starting unless the user explicitly invokes a strict
  inference setup/start target.
* Add tests or script-level checks for generated config paths and missing-model
  behavior. Current tests cover Python adapter behavior but not host deployment
  wiring.

## Unresolved Gaps

* Target Pi 5 host paths are not defined in current repo files. The current
  committed setup defaults to repo-local `./tmp/llama-swap/models` for Compose.
* No current source file defines `LLAMA_SERVER_BIN`, host llama.cpp install
  location, llama-swap binary location, or host inference systemd unit name.
* The desired model naming is not fully resolved in current files. Current repo
  defaults use `lfm2-vl-450m`; prior discussion may involve newer or different
  LFM model IDs, but this pass only verified current workspace contents.
* No current script validates llama-server availability before generating or
  starting llama-swap.
* No current script separates Docker and host inference startup paths.
* README and .env.example do not expose `ENABLE_INFERENCE`, creating a mismatch
  with code defaulting inference off.

## Clarifying Questions

* Should Pi 5 host inference be enabled by default in deployment examples, or
  should operators explicitly set `ENABLE_INFERENCE=true` after validating the
  local model server?
* Should Docker-backed llama-swap remain as the Mac/local development path while
  Pi 5 uses host systemd, or should the repo move fully away from Docker for
  inference?
* What exact host install locations should be standardized for llama-server,
  llama-swap, and model files on the Pi 5?
* Should missing model files make a strict inference setup target fail nonzero,
  while allowing the base API to start, or should setup continue with warnings
  as it does today?

## Status

Complete for current-surface verification. No source files were modified.
