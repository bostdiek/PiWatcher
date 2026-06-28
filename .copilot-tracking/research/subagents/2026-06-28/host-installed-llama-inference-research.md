<!-- markdownlint-disable-file -->
# Task Research: Host-installed llama.cpp and llama-swap inference on Pi 5

Research whether PiWatcher should install llama.cpp `llama-server` and llama-swap on the Raspberry Pi 5 host instead of relying on Docker images for inference.

## Task Implementation Requests

* Evaluate the strategy of updating setup scripts to install the required llama.cpp server on the Pi 5 host and install llama-swap via Go, instead of relying on Docker images for inference.
* Investigate existing `deploy/setup-llama-swap.sh`, `docker-compose.yml`, `Makefile`, `deploy/piwatcher-base.service`, `README.md`, and prior research docs under `.copilot-tracking/research/2026-06-28/`.
* Focus on Pi 5 arm64 behavior: build/runtime dependencies, llama.cpp server build or install, llama-swap Go install, PATH and systemd behavior, idempotency, updates, offline/model file behavior, direct Docker llama-server comparison, and protecting PiWatcher if inference install/start fails.

## Scope and Success Criteria

* Scope: Pi 5 base station inference lifecycle, local setup scripts, systemd integration, repo-owned inference operations, and failure isolation.
* Out of scope: Editing source files, changing Compose, or validating on a physical Pi during this research pass.
* Success criteria:
  * State whether the host-installed llama.cpp plus host-installed llama-swap strategy is recommended.
  * Identify concrete implementation requirements and guardrails.
  * Compare against direct Docker `llama-server` and the current llama-swap Docker image.
  * Provide implementation-ready guidance without modifying source files.

## Research Executed

### Local repository evidence

* `deploy/setup-llama-swap.sh`
  * Currently prepares model storage, writes `deploy/llama-swap/config.yaml`, optionally downloads the main GGUF and mmproj files, and reports missing files without exiting nonzero.
  * It requires only `curl` today.
  * It writes a config command that assumes `llama-server` is resolvable on `PATH` in the runtime where llama-swap launches model commands.
  * It does not install llama.cpp, llama-swap, Go, build dependencies, systemd units, or PATH wrappers.
* `deploy/llama-swap/config.yaml`
  * Configures `lfm2-vl-450m` with `cmd: llama-server --host 127.0.0.1 --port ${PORT} --model /models/lfm2-vl-450m.gguf --mmproj /models/lfm2-vl-450m-mmproj.gguf` and `ttl: 300`.
  * The `/models` paths are container-specific. A host-installed strategy should write host paths such as `/home/pi/PiWatcher/tmp/llama-swap/models/...` or a configured absolute model directory.
* `docker-compose.yml`
  * PostgreSQL is independent and still useful as a Compose service.
  * Inference currently uses `ghcr.io/mostlygeek/llama-swap:unified-vulkan`, mounts the generated config into `/etc/llama-swap/config/config.yaml`, mounts `${LLAMA_SWAP_MODELS_DIR}` at `/models`, exposes port `8080`, and checks `/health` for `OK`.
  * This makes `make base-llama-up` and `make base-up` depend on Docker for inference.
* `Makefile`
  * `base-llama-up` runs `bash deploy/setup-llama-swap.sh` and then `docker compose up -d llama-swap`.
  * `base-up` depends on `base-db-up`, `base-llama-up`, and `base-migrate`, then runs the base server in the foreground.
  * If inference startup fails in `base-llama-up`, `base-up` will not start PiWatcher, even though app-level inference is optional through `ENABLE_INFERENCE`.
* `deploy/piwatcher-base.service`
  * The unit starts only PostgreSQL with `ExecStartPre=/usr/bin/docker compose up -d postgres`.
  * It does not start llama-swap or llama-server.
  * It depends on `docker.service`, which is still required for PostgreSQL but should not imply that inference must be Docker-owned.
  * The service loads `/home/pi/PiWatcher/.env`, so `ENABLE_INFERENCE`, `LLAMA_SWAP_URL`, and related settings already control app behavior.
* `packages/base/src/piwatcher_base/config.py`
  * PiWatcher only needs `llama_swap_url`, `llama_swap_model`, and `inference_enabled` for inference.
  * The app has no model path setting; model paths belong to the inference service setup layer.
* `packages/base/src/piwatcher_base/inference.py`
  * The classifier posts to `{LLAMA_SWAP_URL}/chat/completions` with OpenAI-compatible message content and the configured model name.
  * `classify_event_background` returns early when `inference_enabled` is false.
  * If the endpoint is unavailable, it logs a warning, skips the event classification, and continues. This is already a good runtime isolation property.
  * HTTP and parsing failures are warning-level per frame and do not crash the base app.
* `README.md`
  * Documents Pi 5 inference as llama-swap-based.
  * States that `make base-up` prepares model storage and starts the llama-swap Compose service.
  * Documents `LLAMA_SWAP_IMAGE` as the inference image, model filenames, optional model URLs, thermal settings, and `make base-llama-up` as a Compose startup target.

### Prior research evidence

* `.copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md`
  * Verified that PiWatcher is decoupled from local model files and consumes an OpenAI-compatible endpoint.
  * Verified that the tested `ghcr.io/mostlygeek/llama-swap:unified-vulkan` image includes `llama-server` on amd64.
  * Verified that the same image tag does not provide a usable `linux/arm64/v8` image for Pi 5.
  * Recommended direct arm64-capable llama.cpp server container for repo-owned Docker inference, or external Pi 5 inference when already available.
  * Kept llama-swap as useful when a Pi 5-compatible runtime exists and model TTL/model switching matters.

### User verification evidence

* Pi 5 interactive zsh validation
  * `uname -m` returned `aarch64`.
  * `go version` and `GOBIN="$HOME/.local/bin" go install github.com/mostlygeek/llama-swap@v230` both failed with `zsh: command not found: go`, so repeatable `go install` is not yet validated on this host.
  * `$HOME/.local/bin/llama-swap --help` succeeded and printed the expected flags: `-config`, `-config-dir`, `-listen`, TLS options, `-version`, and `-watch-config`.
  * `$HOME/.local/bin/llama-swap --version` succeeded and reported `version: 230 (32bc7813261000228ea5274d89a8c89e7cce2725), built at 2026-06-25T04:03:31Z`.
  * Conclusion: an arm64-capable llama-swap binary is already installed at `/home/bostdiek/.local/bin/llama-swap`, but Go is missing from the current shell PATH or not installed. The next required validation is host `llama-server`, not llama-swap itself.
* User-provided existing Pi 5 llama-swap config from `/home/bostdiek/llamaswapconfig.yaml`
  * The config was intended to run with `llama-swap --config /home/bostdiek/llamaswapconfig.yaml --listen 127.0.0.1:8080`.
  * It defines `macros.llama_bin: /home/bostdiek/Projects/llama.cpp/build/bin/llama-server`, which is the current candidate `LLAMA_SERVER_BIN`.
  * It defines `macros.downloads_dir: /home/bostdiek/Downloads`, used as the vision model `--media-path`.
  * It preloads model `lfm2.5-vl-450m-q4_0` through `hooks.on_startup.preload`.
  * It sets `healthCheckTimeout: 300`, `startPort: 10001`, `sendLoadingState: false`, `includeAliasesInList: true`, and `globalTTL: 0`.
  * It includes text model `gemma-4-e4b-it` with a local GGUF file under `/home/bostdiek/Projects/unsloth/.../gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf`.
  * It includes vision model `lfm2.5-vl-450m-q4_0` using `--hf-repo LiquidAI/LFM2.5-VL-450M-GGUF` and `--hf-file LFM2.5-VL-450M-Q4_0.gguf` rather than explicit local `--model` and `--mmproj` paths.
  * User clarified that this exploratory config should not be treated as the target standard and that PiWatcher should use explicit `--model` paths.
  * Conclusion: the Pi 5 config is useful for discovering the binary path and model ID, but PiWatcher-generated config should use explicit local `--model` paths for deterministic startup. PiWatcher should use `LLAMA_SWAP_MODEL=lfm2.5-vl-450m-q4_0` if it points at this service, and setup automation must validate `/home/bostdiek/Projects/llama.cpp/build/bin/llama-server` plus the local GGUF path.

### Upstream documentation evidence

* llama.cpp upstream README and build docs
  * `llama-server` is a lightweight OpenAI-compatible HTTP server.
  * It serves `http://localhost:8080/v1/chat/completions`, matching PiWatcher’s request path.
  * Local builds use CMake: `cmake -B build` and `cmake --build build --config Release`.
  * OpenBLAS can be enabled with `-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS` when OpenBLAS is installed.
  * Arm CPU optimizations can be enabled with `-DGGML_CPU_KLEIDIAI=ON`; runtime output can verify whether KleidiAI is used.
  * Vulkan on Linux requires packages such as `libvulkan-dev`, `glslc`, and `spirv-headers`, but Pi 5 Vulkan behavior should be treated as optional until validated on the target OS and driver stack.
  * Models must be GGUF. Local model files and Hugging Face download mode are both supported by llama.cpp, but PiWatcher’s setup should favor explicit local files for offline boot behavior.
* llama-swap upstream README
  * llama-swap is a Go binary with one config file and no runtime dependencies once built.
  * It supports OpenAI-compatible endpoints including `/v1/chat/completions`, `/v1/models`, `/health`, logs, and `/running`.
  * It starts an upstream server based on the request `model`, replaces the running upstream when needed, and supports `ttl` for automatic unload.
  * The minimum config is a `models` map where each model has a `cmd`, and `${PORT}` is injected for the upstream server.
  * It can be installed from Docker, Homebrew, release binaries, or source. Source builds require Go and Node.js for UI via `make clean all`.
  * Upstream docs do not present `go install` as the primary source install path, but the repository is a Go module with a top-level `llama-swap.go`; `go install github.com/mostlygeek/llama-swap@<version>` is a plausible lightweight install mechanism if it produces the expected binary and UI behavior for the chosen version.

## Key Findings

### Host installation fits PiWatcher’s architecture

PiWatcher’s base app already treats inference as optional external infrastructure. The app needs only an OpenAI-compatible endpoint, model name, and `ENABLE_INFERENCE=true`. It does not need Docker-specific details or model paths. That makes host-installed `llama-swap` plus host-installed `llama-server` a natural fit for the Pi 5.

The strongest local reason to prefer host installation is that the current Docker image `ghcr.io/mostlygeek/llama-swap:unified-vulkan` was previously verified as unsuitable for Pi 5 arm64. Host installation avoids depending on third-party multi-arch inference images while preserving llama-swap’s TTL and model-switching behavior.

### The setup script is the right owner, but it must become explicit

`deploy/setup-llama-swap.sh` already owns model directory preparation and llama-swap config generation. Extending it is coherent, but it should be renamed in behavior, if not filename, from "prepare config and models" to "prepare host inference runtime".

The script should explicitly handle these responsibilities:

* Install apt packages needed for building and running host inference.
* Install Go if a suitable `go` binary is missing, or fail with clear instructions if automatic Go installation is not desired.
* Build or install `llama-server` to a stable path outside ephemeral build directories.
* Install `llama-swap` to a stable path.
* Generate a host-path config, not a container-path config.
* Install or update systemd units for llama-swap, and optionally a target dependency from PiWatcher.
* Keep model downloads optional and preserve manual/offline model placement.
* Exit zero when optional inference is disabled or intentionally skipped, and exit nonzero only when the user requested inference install/start and it failed.

### Host paths must replace container paths

The current config command uses `/models/...`, which only works inside the Compose container. On the host, config generation should use absolute paths based on `LLAMA_SWAP_MODELS_DIR` after resolving it.

The generated command should also use an explicit `LLAMA_SERVER_BIN` path. Relying on `llama-server` lookup through `PATH` is fragile under systemd and can silently differ from an interactive shell. The setup script should discover or require `LLAMA_SERVER_BIN`, verify it is executable, and write that exact path into `deploy/llama-swap/config.yaml`.

Example host command shape:

```yaml
models:
  lfm2-vl-450m:
    cmd: /home/bostdiek/.local/bin/llama-server --host 127.0.0.1 --port ${PORT} --model /home/bostdiek/PiWatcher/tmp/llama-swap/models/lfm2-vl-450m.gguf --mmproj /home/bostdiek/PiWatcher/tmp/llama-swap/models/lfm2-vl-450m-mmproj.gguf
    ttl: 300
```

Using absolute paths matters because systemd services do not inherit the same working directory or shell PATH assumptions as an interactive terminal.

### Systemd and PATH are the main operational traps

If `go install` is used, the binary normally lands in `$GOBIN` or `$GOPATH/bin`, commonly `/home/pi/go/bin`. A systemd service running as `pi` may not include that path. Relying on shell profile initialization will be fragile.

User verification on the Pi 5 showed this issue in a lighter form: `go` is not available, but `/home/bostdiek/.local/bin/llama-swap` already exists and runs. The setup script should therefore support both states: reuse an existing valid `LLAMA_SWAP_BIN`, and install Go only when the user requests installing or updating llama-swap from source.

Prefer one of these stable install patterns:

* Install `llama-swap` directly to `/usr/local/bin/llama-swap` using `GOBIN=/usr/local/bin go install github.com/mostlygeek/llama-swap@<pinned-version>`.
* Install to `/home/pi/.local/bin/llama-swap` and set absolute `ExecStart=/home/pi/.local/bin/llama-swap` in the unit.
* Avoid PATH lookup entirely in generated llama-swap config by using an absolute path to `llama-server`.

For `llama-server`, prefer `/usr/local/bin/llama-server` as a symlink or copied binary from a versioned build directory such as `/opt/llama.cpp/<ref>/bin/llama-server`. This allows idempotent updates and rollback.

If the user already has a working host binary, prefer preserving it with `LLAMA_SERVER_BIN=/absolute/path/to/llama-server` rather than rebuilding. The setup script can search common locations as a convenience, but the final config should always contain the resolved absolute executable path.

The current user-provided Pi 5 config identifies the candidate path as `/home/bostdiek/Projects/llama.cpp/build/bin/llama-server`. Implementation should validate that exact path first before rebuilding or installing a second copy.

### Idempotency should be version-aware

A robust setup script should be rerunnable. It should not rebuild llama.cpp or reinstall llama-swap on every invocation unless the requested version changes or a force flag is set.

Recommended controls:

* `LLAMA_CPP_REF`, defaulting to a pinned tag, release, or commit rather than `master`.
* `LLAMA_SWAP_VERSION`, defaulting to a pinned release tag such as `v230` after target validation.
* `FORCE_REBUILD_LLAMA_CPP=false`.
* `FORCE_INSTALL_LLAMA_SWAP=false`.
* Stamp files under an install state directory, for example `/opt/piwatcher-inference/.llama-cpp-ref` and `/opt/piwatcher-inference/.llama-swap-version`.
* A `--check` or `CHECK_ONLY=true` mode that verifies binaries, config, model files, and health endpoints without building.

The script should report installed versions through `llama-server --version` and `llama-swap --version` if available, or through explicit stamp files when upstream binaries do not expose enough version metadata.

### Offline behavior should favor existing local model files

The current script already behaves well for model files: it downloads when URLs are configured, otherwise it prints missing-file guidance. Keep that behavior. The host inference service should not start if required model files are missing, but PiWatcher should still start with inference disabled or degraded.

The selected PiWatcher standard is explicit local model files with llama.cpp `--model`, not `--hf-repo` and `--hf-file`. Hugging Face loading can remain a manual escape hatch, but project-owned setup should resolve the model into a local GGUF path and write that path into the generated llama-swap command. This avoids hidden network/cache behavior at service startup.

Using `--model /path/to/file.gguf` does not download the model. The file must already exist at that path before `llama-server` starts. Therefore PiWatcher needs an explicit setup responsibility: either download the configured GGUF file into `LLAMA_SWAP_MODELS_DIR` when a `LLAMA_SWAP_MODEL_URL` is provided, or fail the inference start with clear manual placement instructions.

Recommended behavior:

* If `LLAMA_SWAP_MODEL_URL` and `LLAMA_SWAP_MMPROJ_URL` are empty, never attempt network model download.
* If `LLAMA_SWAP_MODEL_URL` is configured, download the model into `LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MODEL_FILE` before starting llama-swap.
* Use resume/atomic behavior for downloads so a power loss or interrupted SSH session does not leave a corrupt file at the final model path.
* If model files are missing, write config but do not start llama-swap unless `ALLOW_MISSING_MODELS=true` is explicitly set for diagnostics.
* Keep GGUF files outside Git and outside system install directories.
* Prefer `LLAMA_SWAP_MODELS_DIR=/mnt/nvme/piwatcher/models` on Pi 5 if NVMe is available; use the repo-local default only for development.
* Use `curl -fL --continue-at - --create-dirs` or an atomic temporary download plus rename to avoid corrupt partial files.

### PiWatcher is already runtime-protected, but startup wiring should also be protected

At runtime, `classify_event_background` handles disabled inference and endpoint failures without crashing the API. Startup scripts and systemd dependencies should preserve that property.

Avoid making `piwatcher-base.service` hard-require llama-swap. Use a soft relationship if the project wants startup coordination:

```ini
Wants=piwatcher-inference.service
After=network-online.target docker.service piwatcher-inference.service
```

Do not use `Requires=piwatcher-inference.service` for the base API. If inference fails, event ingestion, storage, heartbeat, dashboard, and PostgreSQL should remain available.

For `make base-up`, split strict setup from optional start:

* `base-db-up` remains strict.
* `base-llama-up` can be host-backed and strict when called directly.
* `base-up` should either skip inference unless `ENABLE_INFERENCE=true`, or run inference setup/start in a way that does not block the base server when inference is disabled.

## Selected and Recommended Approach

Adopt a host-installed inference stack for Pi 5, managed by the setup script and systemd, while keeping PiWatcher’s base application independent from inference failures.

Recommended architecture:

```text
PiWatcher base app -> http://127.0.0.1:8080/v1 -> host llama-swap -> host llama-server -> local GGUF files
```

This is the best fit for the requested strategy because:

* It avoids the current amd64-only llama-swap Docker image problem on Pi 5 arm64.
* It preserves llama-swap TTL unload and future model switching.
* It keeps PostgreSQL in Docker while moving CPU-bound inference to host binaries.
* It matches PiWatcher’s existing app contract: OpenAI-compatible HTTP, model name, optional inference.
* It allows deterministic systemd startup without pulling large images or relying on platform-specific container images.

Use direct host `llama-server` without llama-swap only as a simpler fallback mode if model switching and TTL are not needed. For the current PiWatcher design, llama-swap remains useful because its `ttl: 300` can release model memory between wildlife events.

## Rejected Alternatives

### Keep current llama-swap Docker image

Rejected for Pi 5 ownership because prior research verified `ghcr.io/mostlygeek/llama-swap:unified-vulkan` does not provide a usable `linux/arm64/v8` image for the target. It works as a local amd64 development convenience, but not as the Pi 5 production strategy.

### Add a direct Docker llama-server as the primary Pi 5 path

This remains viable if a known-good arm64 llama.cpp image and device/backend flags are validated on the Pi 5. It is simpler than custom host builds, but it gives up llama-swap TTL/model switching unless combined with a host or container llama-swap layer. It also leaves the project dependent on image availability, platform manifests, and container device mapping.

### Build a custom arm64 unified llama-swap image

Rejected as the first implementation path because it adds Docker build and image maintenance work to solve a problem host binaries can solve more directly. It may become attractive later if the project needs reproducible containerized inference across multiple Pi 5 hosts.

### Treat inference as entirely external and manually managed

This is operationally clean and already supported through `LLAMA_SWAP_URL`, but it does not satisfy the strategy of setup scripts installing inference. Keep it as an escape hatch: users with an existing inference stack can point PiWatcher at it and skip host install.

## Operational Risks

* Pi 5 build time and thermal load: Building llama.cpp on-device can be slow and hot. The setup script should warn, use limited parallelism such as `-j$(nproc)`, and avoid rebuilding unless necessary.
* Moving upstream targets: Building `master` can break unexpectedly. Pin `LLAMA_CPP_REF` and `LLAMA_SWAP_VERSION`.
* Go install uncertainty: Upstream llama-swap documents release binaries and source `make clean all`; `go install` should be validated because UI asset embedding or build tags may differ from release binaries.
* PATH mismatch: systemd will not reliably see `/home/pi/go/bin`. Use absolute paths or install into `/usr/local/bin`.
* Model path mismatch: Current `/models` config paths are container-only. Host config must use resolved absolute paths.
* Missing model files: Do not let missing GGUF files prevent the base API from starting unless the user explicitly requested a strict inference start.
* Network dependency: First install and optional model download require network. Provide offline/manual placement behavior and avoid network access when URLs are empty.
* Service dependency inversion: `piwatcher-base.service` should not require inference. Inference is optional and can be down while ingestion continues.
* Security surface: llama-swap should listen on `127.0.0.1:8080` by default. LAN exposure should be explicit because llama-swap can expose logs, model management endpoints, and OpenAI-compatible inference.
* Update behavior: Blindly reinstalling from latest upstream may change llama-server API, multimodal handling, or performance. Updates should be explicit, pinned, and restart services only after health checks pass.
* Resource contention: llama-server can compete with FastAPI, PostgreSQL, and file uploads on the Pi 5. Preserve PiWatcher’s thermal gate and llama-swap TTL; consider systemd resource limits later.

## Implementation-Ready Guidance

### Script responsibilities

Extend `deploy/setup-llama-swap.sh` or create a companion host inference setup script with this sequence:

1. Load `.env` using the existing `setting_value` pattern.
2. Resolve model directory to an absolute path.
3. Install apt dependencies when running on Debian/Raspberry Pi OS:

```bash
sudo apt-get update
sudo apt-get install -y git cmake build-essential pkg-config curl ca-certificates libopenblas-dev libssl-dev golang
```

Add optional Vulkan dependencies only behind an explicit flag:

```bash
sudo apt-get install -y libvulkan-dev glslc spirv-headers vulkan-tools
```

4. Install or verify Go before `go install`; prefer an explicit minimum version check.
5. Install llama-swap to a deterministic path:

```bash
GOBIN=/usr/local/bin go install github.com/mostlygeek/llama-swap@v230
```

Validate this on Pi 5 before relying on it. If it fails or produces an incomplete binary, use upstream release binaries or source build with `make clean all`.

6. Build llama.cpp from a pinned ref:

```bash
sudo mkdir -p /opt/piwatcher-inference/src /opt/piwatcher-inference/bin
sudo chown -R pi:pi /opt/piwatcher-inference
cd /opt/piwatcher-inference/src
if [ ! -d llama.cpp ]; then git clone https://github.com/ggml-org/llama.cpp; fi
cd llama.cpp
git fetch --tags --prune
git checkout "${LLAMA_CPP_REF}"
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DGGML_CPU_KLEIDIAI=ON
cmake --build build --config Release -j "$(nproc)"
install -m 0755 build/bin/llama-server /opt/piwatcher-inference/bin/llama-server
sudo ln -sfn /opt/piwatcher-inference/bin/llama-server /usr/local/bin/llama-server
```

7. Generate host llama-swap config using absolute binary and model paths.
8. Download model files only when URLs are configured; otherwise print manual placement instructions.
9. Install a dedicated systemd service for llama-swap.
10. Start or restart inference only when `ENABLE_INFERENCE=true` or an explicit install/start flag is set.
11. Health check `http://127.0.0.1:8080/health` and optionally `http://127.0.0.1:8080/v1/models`.
12. Return nonzero only for strict requested failures; leave PiWatcher base start unblocked when inference is optional or disabled.

### Suggested systemd unit shape

```ini
[Unit]
Description=PiWatcher host llama-swap inference
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/PiWatcher
EnvironmentFile=/home/pi/PiWatcher/.env
ExecStart=/usr/local/bin/llama-swap --config /home/pi/PiWatcher/deploy/llama-swap/config.yaml --listen 127.0.0.1:8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Keep the base service soft-linked at most:

```ini
Wants=piwatcher-inference.service
After=network-online.target docker.service piwatcher-inference.service
```

Do not add `Requires=piwatcher-inference.service`.

### Makefile direction

Recommended target split:

* `base-db-up`: unchanged.
* `base-llama-setup`: host install/config/model preparation.
* `base-llama-up`: starts `piwatcher-inference.service` or runs `llama-swap` in the foreground for development.
* `base-up`: starts DB, optionally starts inference when `ENABLE_INFERENCE=true`, applies migrations, and runs the base server.

The important behavior is that a direct `make base-llama-up` can be strict, while `make base-up` should not make inference a hidden mandatory dependency when `ENABLE_INFERENCE=false`.

### Configuration additions

Consider these `.env` variables for the setup layer, not the Python app:

```text
ENABLE_INFERENCE=true
LLAMA_SWAP_URL=http://127.0.0.1:8080/v1
LLAMA_SWAP_MODEL=lfm2-vl-450m
LLAMA_SWAP_MODELS_DIR=/mnt/nvme/piwatcher/models
LLAMA_SWAP_MODEL_FILE=LFM2.5-VL-450M-Q4_0.gguf
LLAMA_SWAP_MMPROJ_FILE=
LLAMA_CPP_REF=<pinned-tag-or-commit>
LLAMA_SWAP_VERSION=v230
LLAMA_SERVER_BIN=/home/bostdiek/Projects/llama.cpp/build/bin/llama-server
LLAMA_SWAP_BIN=/home/bostdiek/.local/bin/llama-swap
LLAMA_SWAP_LISTEN=127.0.0.1:8080
FORCE_REBUILD_LLAMA_CPP=false
FORCE_INSTALL_LLAMA_SWAP=false
```

The app does not need `LLAMA_CPP_REF`, binary paths, or model file paths.

### Validation checklist

* `uname -m` returns `aarch64` on the Pi 5.
* `command -v llama-server` returns the expected stable path.
* `llama-server --version` works.
* `command -v llama-swap` returns the expected stable path, or `LLAMA_SWAP_BIN` points to an existing executable.
* `llama-swap --help` works.
* Generated config uses absolute host paths, not `/models`.
* Model and mmproj files exist and are readable by user `pi`.
* `systemctl start piwatcher-inference.service` succeeds when model files are present.
* `curl -fsS http://127.0.0.1:8080/health` returns `OK`.
* `curl -fsS http://127.0.0.1:8080/v1/models` returns the configured model.
* With inference disabled or service stopped, PiWatcher still accepts uploads and serves the dashboard.
* With `ENABLE_INFERENCE=true` and the service healthy, a test event classification updates event metadata.

### Manual Pi 5 validation commands

Validate the current host state before building full setup automation:

```bash
uname -m
"$HOME/.local/bin/llama-swap" --help
"$HOME/.local/bin/llama-swap" --version || true
command -v llama-server || true
llama-server --version || true
find "$HOME" /usr/local/bin /opt -name llama-server -type f 2>/dev/null
```

Observed result on the Pi 5: `uname -m` reports `aarch64`, `/home/bostdiek/.local/bin/llama-swap` works and reports version `230`, and `go` is missing. This validates the installed llama-swap binary but not the repeatable `go install` path. Install Go only if the setup script needs to update or reinstall llama-swap from source.

Given the user-provided existing config, validate the current candidate `llama-server` path directly:

```bash
test -x /home/bostdiek/Projects/llama.cpp/build/bin/llama-server
/home/bostdiek/Projects/llama.cpp/build/bin/llama-server --version
```

If both succeed, setup can reuse that binary as `LLAMA_SERVER_BIN`. Then validate the local GGUF file that should be used with `--model`:

```bash
test -r "$LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MODEL_FILE"
```

Expected result: the model file exists locally and is readable by the service user. If not, place or download the GGUF file before starting the systemd service.

Validate whether `go install` is sufficient for llama-swap after Go is installed:

```bash
set -euo pipefail
uname -m
go version
GOBIN="$HOME/.local/bin" go install github.com/mostlygeek/llama-swap@v230
"$HOME/.local/bin/llama-swap" --help
"$HOME/.local/bin/llama-swap" --version || true
```

Expected result: `uname -m` reports `aarch64`, `go version` is present, `go install` exits successfully, and `llama-swap --help` prints usage. If `--version` is unsupported, that is acceptable as long as help and runtime start work.

If Raspberry Pi Connect disconnects during `go install`, treat that as an operational validation issue rather than a llama-swap result. Run long install/build commands inside `tmux` over SSH, or redirect them to a log with `nohup`, so the command survives UI disconnects and leaves output for diagnosis.

Do not run `set -euo pipefail` directly in an interactive zsh session. zsh supports strict-mode equivalents, but `set -e` / `errexit` can exit the current interactive shell on the first failed command, which makes the terminal appear to stop. Use strict mode inside a script or subshell, or run validation commands interactively without `set -e`.

Safer SSH/tmux validation:

```bash
ssh pi@pi5.local
tmux new -s piwatcher-inference
```

Inside `tmux`:

```bash
uname -m
go version
mkdir -p "$HOME/.local/bin"
GOBIN="$HOME/.local/bin" go install github.com/mostlygeek/llama-swap@v230 2>&1 | tee "$HOME/llama-swap-go-install.log"
"$HOME/.local/bin/llama-swap" --help
"$HOME/.local/bin/llama-swap" --version || true
```

If strict mode is wanted, wrap the validation in a script with an explicit shell instead of applying it to the current terminal:

```bash
cat > "$HOME/validate-llama-swap.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
uname -m
go version
mkdir -p "$HOME/.local/bin"
GOBIN="$HOME/.local/bin" go install github.com/mostlygeek/llama-swap@v230 2>&1 | tee "$HOME/llama-swap-go-install.log"
"$HOME/.local/bin/llama-swap" --help
"$HOME/.local/bin/llama-swap" --version || true
SH
chmod +x "$HOME/validate-llama-swap.sh"
"$HOME/validate-llama-swap.sh"
```

If the session drops, reconnect and inspect:

```bash
tmux attach -t piwatcher-inference
tail -100 "$HOME/llama-swap-go-install.log"
journalctl -b -p warning..alert --no-pager | tail -100
dmesg -T | tail -100
```

If the Pi rebooted or killed the process, check for out-of-memory, thermal, or network messages before retrying. If only Pi Connect disconnected but `tmux` kept running, the install approach is still viable.

Validate whether the binary can start with a minimal config:

```bash
mkdir -p "$HOME/piwatcher-inference-test"
cat > "$HOME/piwatcher-inference-test/config.yaml" <<'YAML'
models:
  test:
    cmd: python3 -m http.server ${PORT} --bind 127.0.0.1
    ttl: 5
YAML
"$HOME/.local/bin/llama-swap" --config "$HOME/piwatcher-inference-test/config.yaml" --listen 127.0.0.1:8080
```

Expected result: llama-swap starts and listens on `127.0.0.1:8080`. This does not prove real inference works, but it proves the Go-installed binary can parse config, start, and bind locally.

Validate host `llama-server` separately after installing or building llama.cpp:

```bash
command -v llama-server
llama-server --version
```

Expected result: both commands succeed and the binary path is stable, preferably `/usr/local/bin/llama-server` or `/opt/piwatcher-inference/bin/llama-server`.

Validate the final generated PiWatcher config only after model files are present:

```bash
test -r "$LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MODEL_FILE"
test -r "$LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MMPROJ_FILE"
grep -n '/models\|llama-server' deploy/llama-swap/config.yaml
```

Expected result: model files are readable and `deploy/llama-swap/config.yaml` references absolute host paths, not container-only `/models/...` paths.

## Follow-on Questions

* Does `go install github.com/mostlygeek/llama-swap@v230` produce a Pi 5 binary with the expected embedded UI and runtime behavior, or should the script prefer upstream release binaries/source `make clean all`?
* Which Raspberry Pi OS version and Go package version are installed on the target Pi 5?
* Should the default Pi 5 build use CPU with OpenBLAS/KleidiAI only, or should Vulkan be validated and enabled behind an explicit flag?
* Should PiWatcher expose llama-swap only on localhost, or is LAN access to llama-swap’s UI/logs desired for operations?
