---
title: Inference Lifecycle Ownership Research
description: Research on how PiWatcher should own optional inference startup, health, and deployment lifecycle
ms.date: 2026-06-28
ms.topic: research
---

## Research Topics

* Determine how PiWatcher currently starts and configures inference across Docker Compose, Make targets, deploy scripts, README guidance, and base package settings.
* Decide whether PiWatcher should own inference as a separate compose profile, compose service, package, or external dependency.
* Identify startup script and systemd changes needed for a Pi 5 that may be reused, shut down, unplugged, or rebooted.
* Recommend health check, dependency, and failure behavior so PiWatcher remains optional and protected when inference is unavailable.
* Incorporate prior research from `.copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md`.

## Current Repository Evidence

### Docker Compose

* `docker-compose.yml` defines `postgres` and `llama-swap` services.
* `postgres` has `restart: unless-stopped`, host port `5432`, volume `pgdata`, and a `pg_isready` health check.
* `llama-swap` uses `${LLAMA_SWAP_IMAGE:-ghcr.io/mostlygeek/llama-swap:unified-vulkan}`, publishes `${LLAMA_SWAP_PORT:-8080}:8080`, mounts `deploy/llama-swap/config.yaml`, mounts `${LLAMA_SWAP_MODELS_DIR:-./tmp/llama-swap/models}` at `/models`, and has a `/health` health check.
* `llama-swap` is not assigned to a Compose profile today. Any `docker compose up -d` without a service selector can start both services.
* There is no direct `llama-server` compose service today.

### Make Targets

* `Makefile` target `base-db-up` runs `docker compose up -d postgres`.
* `Makefile` target `base-llama-up` runs `bash deploy/setup-llama-swap.sh` and `docker compose up -d llama-swap`.
* `Makefile` target `base-up` depends on `base-db-up base-llama-up base-migrate` and then starts `uv run --package piwatcher-base piwatcher-server`.
* Foreground development and smoke-test behavior therefore starts inference unconditionally through `base-up`, even though application inference defaults to disabled.

### Deploy Scripts and Systemd

* `deploy/piwatcher-base.service` has `After=network-online.target docker.service` and `Wants=network-online.target docker.service`.
* `deploy/piwatcher-base.service` runs `ExecStartPre=/usr/bin/docker compose up -d postgres` but does not start `llama-swap` or run `deploy/setup-llama-swap.sh`.
* The boot-time Pi 5 path in `deploy/piwatcher-base.service` is therefore weaker than `make base-up`: after reboot, PiWatcher starts PostgreSQL and the app, but not its configured inference service.
* `deploy/setup-llama-swap.sh` writes `deploy/llama-swap/config.yaml`, creates `${LLAMA_SWAP_MODELS_DIR}`, and optionally downloads model and multimodal projector files from `.env` URLs. It does not install llama.cpp or host-level inference dependencies.
* `deploy/llama-swap/config.yaml` runs `llama-server --host 127.0.0.1 --port ${PORT} --model /models/lfm2-vl-450m.gguf --mmproj /models/lfm2-vl-450m-mmproj.gguf` under llama-swap with `ttl: 300`.
* Camera deployment scripts are unrelated to inference lifecycle except that they depend on the base station URL remaining available.

### README and Configuration

* `README.md` describes the Pi 5 base station as running local AI inference through llama-swap.
* `README.md` says `make base-up` prepares model storage, starts llama-swap, applies migrations, and runs the base server.
* `README.md` Pi 5 systemd setup currently instructs operators to run `make base-db-up`, `make base-migrate`, and install `deploy/piwatcher-base.service`. It does not instruct them to enable or start inference at boot.
* `.env.example` includes `LLAMA_SWAP_URL`, `LLAMA_SWAP_MODEL`, `LLAMA_SWAP_IMAGE`, `LLAMA_SWAP_MODELS_DIR`, `LLAMA_SWAP_MODEL_FILE`, and `LLAMA_SWAP_MMPROJ_FILE`, but it does not include `ENABLE_INFERENCE`.
* `packages/base/src/piwatcher_base/config.py` defaults `inference_enabled` to `False` and accepts `ENABLE_INFERENCE` or `PIWATCHER_ENABLE_INFERENCE`.
* `packages/base/src/piwatcher_base/config.py` treats inference as endpoint configuration: URL, model name, thermal limits, and gap seconds. It does not know model file paths.

### Base Application Behavior

* `packages/base/src/piwatcher_base/routes/events.py` always adds `classify_event_background` as a background task after event upload.
* `packages/base/src/piwatcher_base/inference.py` immediately returns when `settings.inference_enabled` is false.
* `packages/base/src/piwatcher_base/inference.py` sends OpenAI-compatible requests to `{LLAMA_SWAP_URL}/chat/completions` and includes the configured model name.
* `packages/base/src/piwatcher_base/inference.py` catches `httpx.ConnectError`, logs that the endpoint is unavailable, breaks out of sampling, and records an `unknown` classification with zero confidence through `choose_classification([])`.
* Other `httpx.HTTPError`, file, response, validation, and JSON failures are logged per frame and do not fail the event upload response.
* `packages/base/tests/test_inference.py` covers the disabled inference path, confirming that disabled inference leaves the event unclassified.

## Prior Research Incorporated

Prior research in `.copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md` found:

* PiWatcher base only needs an OpenAI-compatible endpoint and model name. Model paths belong to the inference service config, not the FastAPI app.
* The configured `ghcr.io/mostlygeek/llama-swap:unified-vulkan` image appears to include `llama-server` in the tested cached amd64 image, and upstream docs say the unified image family bundles `llama-server`.
* The actual Pi 5 arm64 image still needs target verification.
* Direct `ghcr.io/ggml-org/llama.cpp:server` is a simpler option for one fixed model.
* Running llama-swap plus a separate llama.cpp container is not a good default unless a custom provider runtime or container isolation is required.

## Pi 5 Arm64 Verification Update

* User ran `docker run --rm --platform linux/arm64/v8 --entrypoint sh ghcr.io/mostlygeek/llama-swap:unified-vulkan -c 'command -v llama-server && llama-server --version'` on the Pi 5.
* Docker reported that `ghcr.io/mostlygeek/llama-swap:unified-vulkan` was found as `linux/amd64` and does not provide the specified platform `linux/arm64/v8`.
* This resolves the earlier open question: the current mostlygeek unified image tag is not usable as PiWatcher's owned Pi 5 arm64 inference container.
* The shell output also showed `zsh: command not found` lines after the Docker failure, which appears to be pasted command output being interpreted by the shell rather than additional Docker behavior.

## Key Discoveries

* PiWatcher already partly owns inference in development through `Makefile`, because `make base-up` always runs `base-llama-up`.
* PiWatcher does not fully own inference at boot, because `deploy/piwatcher-base.service` starts only PostgreSQL before the app.
* The base app is already protected from inference absence in the request path. Event upload succeeds, background inference can skip, and endpoint failures are logged rather than propagated to camera uploads.
* The operator experience is inconsistent: README states PiWatcher uses llama-swap, Compose has a llama-swap service, Make starts it, but systemd guidance does not enable it on boot.
* The current service name `llama-swap` bakes an implementation detail into settings and docs. The runtime contract is actually OpenAI-compatible inference, so future names could be clearer as `PIWATCHER_INFERENCE_URL` while keeping `LLAMA_SWAP_URL` as a compatibility alias.
* The current `ghcr.io/mostlygeek/llama-swap:unified-vulkan` image cannot be the Pi 5 owned-inference default because it does not provide `linux/arm64/v8`.
* A separate Python package for inference lifecycle is not necessary for the current architecture. The heavy work is served by llama-swap or llama.cpp, and the base package already contains the client adapter and safety gates.
* A separate service is useful, but it should be an infrastructure service, preferably a Compose service/profile and optionally a systemd unit, not a new Python package.

## Recommended Approach

PiWatcher should own inference lifecycle as an optional infrastructure component, not as a mandatory dependency of the base API process. On Pi 5, the owned default should use an arm64-capable inference backend. Based on the Pi 5 verification, that means a direct llama.cpp `llama-server` container or a custom/alternative arm64 llama-swap image, not `ghcr.io/mostlygeek/llama-swap:unified-vulkan`.

### Compose Ownership

Add an explicit optional inference Compose profile around the owned inference service. For Pi 5, prefer a direct `llama-server` service unless a compatible arm64 llama-swap image is identified.

Recommended shape:

```yaml
services:
  llama-server:
    profiles: ["inference"]
    image: ${LLAMA_SERVER_IMAGE:-ghcr.io/ggml-org/llama.cpp:server}
    restart: unless-stopped
    ports:
      - "${LLAMA_SERVER_PORT:-8080}:8080"
```

This keeps PostgreSQL as the default always-needed service and makes inference explicit:

```bash
docker compose up -d postgres
docker compose --profile inference up -d llama-server
```

For Make targets:

* Keep `base-db-up` focused on PostgreSQL.
* Keep or rename `base-llama-up` to the inference lifecycle target and have it use the inference profile.
* Consider changing `base-up` so inference startup is conditional on `ENABLE_INFERENCE=true` or a new `WITH_INFERENCE=true` variable. This would align app behavior with infrastructure behavior and avoid starting a large model service for local runs that do not classify events.

### Systemd Startup Ownership

Add boot-time guidance that starts inference when inference is enabled. Two implementation paths are viable.

Preferred: a separate `piwatcher-inference.service` that prepares model files and starts the inference profile:

```ini
[Unit]
Description=PiWatcher Inference Services
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/PiWatcher
EnvironmentFile=/home/pi/PiWatcher/.env
ExecStart=/home/pi/PiWatcher/deploy/setup-llama-swap.sh
ExecStart=/usr/bin/docker compose --profile inference up -d llama-server
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Then update `piwatcher-base.service` only when inference is owned by PiWatcher:

```ini
Wants=piwatcher-inference.service
After=network-online.target docker.service piwatcher-inference.service
```

This separates app uptime from model service lifecycle. If inference fails to start, the base API can still run when the dependency is only `Wants`, not `Requires`.

Alternative: add an `ExecStartPre` to `piwatcher-base.service` that runs setup and `docker compose --profile inference up -d llama-swap`. This is simpler but couples base API restarts to inference startup and model preparation. That can slow or destabilize the API when the Pi 5 is hot, missing models, or under load.

### Health Checks and Dependency Behavior

Keep inference health checks in Compose, but do not make the base API hard-depend on inference health.

Recommended behavior:

* `llama-swap` keeps the existing `/health` check.
* If adding a direct `llama-server` option, use `/health` when supported or `/v1/models` as the readiness check.
* The base service should start after Docker and PostgreSQL, not require inference to be healthy.
* A startup script can warn when `ENABLE_INFERENCE=true` and inference health is failing, but it should not block the base app by default.
* In-app inference should remain guarded by `ENABLE_INFERENCE=false` by default.
* Endpoint failures should leave event ingest healthy and should not prevent camera uploads.

The current Python behavior already mostly satisfies the last two points. A future improvement would distinguish skipped inference from a real `unknown` classification so unavailable inference does not look like a confident model decision.

### Direct llama-server Option

The direct `llama-server` service is now the best first Pi 5 implementation because the currently configured llama-swap unified image does not provide `linux/arm64/v8`. The existing llama-swap configuration remains useful on amd64 development machines or if a Pi 5-compatible llama-swap image is found later.

Recommended direct-service shape, if added later:

```yaml
services:
  llama-server:
    profiles: ["inference"]
    image: ${LLAMA_SERVER_IMAGE:-ghcr.io/ggml-org/llama.cpp:server}
    restart: unless-stopped
    ports:
      - "${LLAMA_SERVER_PORT:-8080}:8080"
    volumes:
      - ${LLAMA_SWAP_MODELS_DIR:-./tmp/llama-swap/models}:/models:ro
    command:
      - --host
      - 0.0.0.0
      - --port
      - "8080"
      - --model
      - /models/${LLAMA_SWAP_MODEL_FILE:-lfm2-vl-450m.gguf}
      - --mmproj
      - /models/${LLAMA_SWAP_MMPROJ_FILE:-lfm2-vl-450m-mmproj.gguf}
```

Use this as the owned Pi 5 default if the selected llama.cpp image is verified on target hardware.

### Configuration Naming

For implementation, preserve current variable names to avoid churn:

* `ENABLE_INFERENCE`
* `LLAMA_SWAP_URL`
* `LLAMA_SWAP_MODEL`
* `LLAMA_SWAP_MODELS_DIR`
* `LLAMA_SWAP_MODEL_FILE`
* `LLAMA_SWAP_MMPROJ_FILE`

Consider adding neutral aliases later:

* `PIWATCHER_INFERENCE_URL`
* `PIWATCHER_INFERENCE_MODEL`
* `PIWATCHER_ENABLE_INFERENCE`

The settings class already supports `PIWATCHER_ENABLE_INFERENCE`, but not neutral URL/model aliases.

## Rejected Alternatives

### Keep Inference Purely External

This was a reasonable earlier recommendation when the Pi 5 inference stack was assumed to be separately managed. It no longer satisfies the updated requirement: if the Pi 5 is reused, shut down, unplugged, or rebooted, PiWatcher should help restore required inference services.

External inference should remain supported by setting `LLAMA_SWAP_URL` to another host and leaving the compose inference profile disabled, but it should not be the only documented operational path.

### Make Inference Mandatory for Base Startup

Do not require inference health for base API startup. Cameras should continue uploading events, storing frames, and recording metadata when inference is disabled, missing models, or temporarily unavailable.

This is especially important for a Raspberry Pi 5 that may be power-cycled or used for other workloads. Model download, model load, GPU/Vulkan device availability, and thermal state are more fragile than the ingest API.

### Add a New Python Inference Package Now

A new `packages/inference` package is not warranted yet. PiWatcher needs lifecycle ownership for external processes and containers, not new Python inference logic.

Add a Python package only if PiWatcher later needs an internal inference worker with durable queues, retry state, scheduling, or a local API separate from the base web app. The current need is better served by Compose, systemd, and clearer docs.

### Run llama-swap Plus a Separate llama.cpp Container by Default

Prior research rejected this as the default. After Pi 5 verification, the current unified llama-swap image is also not available for `linux/arm64/v8`, so it cannot be the Pi 5 default orchestration container. A second provider container adds networking, health, and command orchestration complexity without solving the image availability gap.

Use this only for a custom llama-swap build, hardware-specific runtime image, or strict provider isolation.

## Implementation-Ready Guidance

1. Put an arm64-capable inference service behind a Compose `inference` profile.
2. Add `ENABLE_INFERENCE=false` to `.env.example` so application and infrastructure optionality are visible.
3. Make `base-llama-up` run `docker compose --profile inference up -d llama-server` after model preparation, or use `llama-swap` only when an arm64-capable image is configured.
4. Decide whether `make base-up` should always start inference, or only when `ENABLE_INFERENCE=true` or `WITH_INFERENCE=true` is set. Conditional startup best matches optional inference.
5. Add a Pi 5 `piwatcher-inference.service` or equivalent README guidance so inference can be enabled on boot independently of the base API.
6. Update `deploy/piwatcher-base.service` documentation to make clear that it starts PostgreSQL and the base API, while inference is enabled separately or through a weak `Wants` relationship.
7. Keep base app inference failure non-fatal. Do not use hard systemd `Requires` from base to inference.
8. Add an operational check such as `curl http://127.0.0.1:8080/v1/models` or the existing `/health` endpoint to README startup validation.
9. Consider a later schema change or status field so skipped inference due to endpoint outage is not stored exactly like an `unknown` model classification.

## Unresolved Questions

* Should local `make base-up` start inference by default for convenience, or should it respect `ENABLE_INFERENCE` to avoid model startup on every development run?
* Should PiWatcher standardize on llama-swap as the owned inference service, or add a direct `llama-server` profile for one-model installs after Pi 5 target validation?
* Should missing model files make `piwatcher-inference.service` fail, or should it warn and leave the base service running with inference disabled/unavailable?
* Should PiWatcher rename user-facing inference settings from `LLAMA_SWAP_*` to neutral `PIWATCHER_INFERENCE_*` aliases in this iteration or defer that compatibility work?
* Which arm64-capable llama.cpp image and backend flags should PiWatcher standardize on for the Pi 5?
