<!-- markdownlint-disable-file -->
# Task Research: llama-swap vs llama.cpp server for PiWatcher inference

Research whether PiWatcher should rely on a llama-swap container, include a separate llama.cpp server container, or treat inference as externally managed on the Pi 5.

## Task Implementation Requests

* Determine what the currently configured llama-swap container includes and whether it can perform inference by itself.
* Determine whether PiWatcher should add a llama.cpp/llama-server container, keep llama-swap only, or prefer external inference setup.
* Clarify whether PiWatcher needs a model path when using an already configured Pi 5 inference stack.
* Evaluate whether setup scripts should install host `llama-server` and host `llama-swap` on Pi 5 instead of relying on Docker inference images.

## Scope and Success Criteria

* Scope: PiWatcher base inference integration, docker-compose inference services, llama-swap and llama.cpp server deployment patterns.
* Assumptions:
  * The base app consumes an OpenAI-compatible `/v1/chat/completions` endpoint.
  * User already has some Pi 5 llama.cpp/llama-swap setup.
  * Local/dev compose may differ from Pi 5 production setup.
* Success Criteria:
  * Verify whether the selected llama-swap image includes a runnable `llama-server` or only routes/process-manages commands.
  * Identify one recommended PiWatcher inference architecture.
  * Document alternatives and model path responsibilities.

## Outline

* Current repo inference wiring
* llama-swap container capability research
* Standalone llama.cpp server option
* Alternatives analysis
* Recommended approach

## Potential Next Research

* Confirm the current Pi 5 `/home/bostdiek/Projects/llama.cpp/build/bin/llama-server --version` output and the local GGUF path to use with `--model` for LFM2.5.
  * Reasoning: binary path and model ID are now known, but the deterministic local model file path still needs validation.
  * Reference: User-provided `/home/bostdiek/llamaswapconfig.yaml` content.

## Research Executed

### File Analysis

* docker-compose.yml
  * Defines a `llama-swap` service using `ghcr.io/mostlygeek/llama-swap:unified-vulkan`, mounting `deploy/llama-swap/config.yaml` and model files into `/models`.
* deploy/llama-swap/config.yaml
  * Configures model `lfm2-vl-450m` with `cmd: llama-server --host 127.0.0.1 --port ${PORT} --model /models/lfm2-vl-450m.gguf --mmproj /models/lfm2-vl-450m-mmproj.gguf`.
  * This means the configured service expects `llama-server` to exist inside the runtime where llama-swap launches commands.
* deploy/setup-llama-swap.sh
  * Generates the same llama-swap command config and prepares/downloads model files.
  * It does not install llama.cpp on the host.
* packages/base/src/piwatcher_base/inference.py
  * Sends OpenAI-compatible chat-completions requests to `{LLAMA_SWAP_URL}/chat/completions`.
  * It uses only endpoint URL and model name. It does not read model paths.
* packages/base/src/piwatcher_base/config.py
  * Base app settings include `llama_swap_url`, `llama_swap_model`, and `inference_enabled`, but no local model path setting.
* .copilot-tracking/research/subagents/2026-06-28/llama-swap-container-capabilities-research.md
  * Subagent verified upstream docs and local image contents.
* .copilot-tracking/research/subagents/2026-06-28/host-installed-llama-inference-research.md
  * Subagent evaluated host-installed Pi 5 inference using setup-managed llama.cpp and llama-swap binaries.

### Code Search Results

* `LLAMA_SWAP_URL`
  * README documents endpoint configuration and currently frames llama-swap as the default inference service.
* `LLAMA_SWAP_MODEL_FILE` and `LLAMA_SWAP_MMPROJ_FILE`
  * README and setup script treat these as deployment/model-storage settings, not base application settings.

### External Research

* Researcher Subagent: llama-swap upstream documentation
  * llama-swap is a Go proxy/model-switching layer for OpenAI-compatible and Anthropic-compatible upstream servers.
  * It extracts the request `model`, starts/stops configured upstream commands, and proxies to the active provider.
  * Its unified Docker image family is documented as including `llama-server`, `ik-llama-server`, stable-diffusion.cpp, whisper.cpp, and llama-swap.
* Researcher Subagent: llama.cpp Docker/server documentation
  * `ghcr.io/ggml-org/llama.cpp:server` provides the `llama-server` executable and supports OpenAI-compatible `/v1/chat/completions` and `/v1/models`.
  * Direct llama-server can serve PiWatcher’s request shape without llama-swap when only one model is needed.
* Researcher Subagent: host-installed llama.cpp and llama-swap documentation
  * llama.cpp can be built on the Pi 5 from a pinned ref with CMake, producing a local `llama-server` binary.
  * llama-swap is a Go binary with a config file that launches upstream commands such as `llama-server`, injects `${PORT}`, proxies OpenAI-compatible endpoints, and supports TTL unload.
  * Host install preserves llama-swap behavior without relying on the unavailable Pi 5 arm64 Docker image.
  * Host setup should discover or require both `LLAMA_SWAP_BIN` and `LLAMA_SERVER_BIN`; generated configs and systemd units should use resolved absolute paths.

### User Verification

* Docker command: `docker run --rm --entrypoint sh ghcr.io/mostlygeek/llama-swap:unified-vulkan -c 'command -v llama-server && llama-server --version'`
  * Output included `/usr/local/bin/llama-server` and `version: 1 (27c8bb4)`.
  * Docker warned that the requested image platform was `linux/amd64` while the host was `linux/arm64/v8`.
  * The binary reported `built with GNU 13.3.0 for Linux x86_64`.
  * Conclusion: the tested amd64 unified image definitely includes `llama-server`; this does not yet prove the Pi 5 arm64 image variant includes a working arm64 `llama-server`.
* Pi 5 Docker command: `docker run --rm --platform linux/arm64/v8 --entrypoint sh ghcr.io/mostlygeek/llama-swap:unified-vulkan -c 'command -v llama-server && llama-server --version'`
  * Docker pulled the image digest but reported that the image platform was `linux/amd64` and does not provide `linux/arm64/v8`.
  * Conclusion: `ghcr.io/mostlygeek/llama-swap:unified-vulkan` is not a usable owned Pi 5 inference image for the current arm64 target.
* Pi 5 host command sequence: `uname -m`, `go version`, `GOBIN="$HOME/.local/bin" go install github.com/mostlygeek/llama-swap@v230`, `$HOME/.local/bin/llama-swap --help`, and `$HOME/.local/bin/llama-swap --version || true`
  * `uname -m` returned `aarch64`.
  * `go version` and `go install` failed with `zsh: command not found: go`, so repeatable source install/update via Go is not yet validated on this host.
  * `/home/bostdiek/.local/bin/llama-swap --help` succeeded.
  * `/home/bostdiek/.local/bin/llama-swap --version` succeeded and reported `version: 230 (32bc7813261000228ea5274d89a8c89e7cce2725), built at 2026-06-25T04:03:31Z`.
  * Conclusion: host llama-swap itself is validated on Pi 5 arm64 at `/home/bostdiek/.local/bin/llama-swap`. The next unknown is host `llama-server` availability and model-path configuration, not whether the existing llama-swap binary can run.
* User-provided Pi 5 config: `/home/bostdiek/llamaswapconfig.yaml`
  * Intended launch command: `llama-swap --config /home/bostdiek/llamaswapconfig.yaml --listen 127.0.0.1:8080`.
  * Defines `macros.llama_bin: /home/bostdiek/Projects/llama.cpp/build/bin/llama-server`, making that the current candidate `LLAMA_SERVER_BIN`.
  * Defines `macros.downloads_dir: /home/bostdiek/Downloads`, used as the vision model `--media-path`.
  * Preloads `lfm2.5-vl-450m-q4_0` on startup.
  * Includes `lfm2.5-vl-450m-q4_0` with `--hf-repo LiquidAI/LFM2.5-VL-450M-GGUF` and `--hf-file LFM2.5-VL-450M-Q4_0.gguf`, rather than explicit local GGUF paths.
  * Includes `gemma-4-e4b-it` with a local GGUF path under `/home/bostdiek/Projects/unsloth/...`.
  * User clarified that this exploratory config should not be treated as the target standard and that PiWatcher should generate commands using explicit `--model` paths.
  * Conclusion: PiWatcher should use `LLAMA_SWAP_MODEL=lfm2.5-vl-450m-q4_0`, validate `LLAMA_SERVER_BIN`, and generate deterministic llama-swap commands with local `--model` GGUF paths rather than `--hf-repo` and `--hf-file`.

### Project Conventions

* Standards referenced: Task Researcher mode constraints.
* Instructions followed: Research files under `.copilot-tracking/research/` only.

## Key Discoveries

### Project Structure

PiWatcher’s base application is already decoupled from model files. It speaks to an OpenAI-compatible HTTP endpoint and only needs `ENABLE_INFERENCE=true`, endpoint URL, and model name. Model paths are used by the infrastructure layer that launches inference, either llama-swap config or a direct llama-server container.

### Implementation Patterns

The current compose setup uses llama-swap as a single container that launches `llama-server` internally. This is only valid on platforms where the selected image bundles a compatible `llama-server`. User verification found `/usr/local/bin/llama-server` and version `1 (27c8bb4)` in the amd64 image, but Pi 5 verification showed `ghcr.io/mostlygeek/llama-swap:unified-vulkan` does not provide `linux/arm64/v8`. The current image is therefore unsuitable as PiWatcher's owned Pi 5 inference container.

The host-installed strategy fits PiWatcher better on Pi 5: setup installs or builds `llama-server`, installs `llama-swap`, writes a config with absolute host paths, and systemd starts llama-swap on boot. The base app still only knows about `LLAMA_SWAP_URL`, `LLAMA_SWAP_MODEL`, and `ENABLE_INFERENCE`.

User verification now narrows that further: an arm64 host llama-swap binary already runs on the Pi 5 and reports version `230`, but `go` is not installed. Setup should therefore reuse an existing executable `LLAMA_SWAP_BIN` when valid, and install Go only when updating or reinstalling llama-swap from source is explicitly requested.

The same explicit-binary approach should apply to `llama-server`. Setup should discover or require `LLAMA_SERVER_BIN`, verify that it is executable, and write that exact path into `deploy/llama-swap/config.yaml`. Relying on `llama-server` lookup through `PATH` is fragile under systemd and can differ from the user’s interactive zsh environment.

The user-provided Pi 5 config gives the current candidate values: `LLAMA_SWAP_BIN=/home/bostdiek/.local/bin/llama-swap`, `LLAMA_SERVER_BIN=/home/bostdiek/Projects/llama.cpp/build/bin/llama-server`, and `LLAMA_SWAP_MODEL=lfm2.5-vl-450m-q4_0`.

The selected PiWatcher standard is explicit local model files with llama.cpp `--model`, not `--hf-repo` and `--hf-file`. Hugging Face loading can remain a manual escape hatch, but project-owned setup should resolve the model into a local GGUF path and write that path into the generated llama-swap command.

Using `--model /path/to/file.gguf` does not download the model. The file must exist before `llama-server` starts. PiWatcher setup should either download `LLAMA_SWAP_MODEL_URL` into `LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MODEL_FILE`, or stop inference startup with clear instructions for manual placement. This keeps boot behavior deterministic while still allowing a one-command setup when a model URL is configured.

### Complete Examples

External Pi 5 inference stack already managed outside PiWatcher:

```dotenv
ENABLE_INFERENCE=true
LLAMA_SWAP_URL=http://pi5.local:8080/v1
LLAMA_SWAP_MODEL=lfm2.5-vl-450m-q4_0
```

PiWatcher does not need a model path in this mode.

The current llama-swap unified image fails this Pi 5 arm64 check:

```bash
docker run --rm --platform linux/arm64/v8 --entrypoint sh ghcr.io/mostlygeek/llama-swap:unified-vulkan -c 'command -v llama-server && llama-server --version'
```

Use an arm64-capable direct llama.cpp server image or a custom arm64 llama-swap image for PiWatcher-owned Pi 5 inference.

Host-installed Pi 5 inference stack:

```text
PiWatcher base app -> http://127.0.0.1:8080/v1 -> host llama-swap -> host llama-server -> local GGUF files
```

Host-generated llama-swap config must use absolute host paths, not container paths. It should also use an explicit `LLAMA_SERVER_BIN` executable path instead of relying on `PATH`:

```yaml
models:
  lfm2-vl-450m:
    cmd: /home/bostdiek/Projects/llama.cpp/build/bin/llama-server --host 127.0.0.1 --port ${PORT} --model /mnt/nvme/piwatcher/models/lfm2-vl-450m.gguf --mmproj /mnt/nvme/piwatcher/models/lfm2-vl-450m-mmproj.gguf
    ttl: 300
```

The existing Pi 5 config used llama.cpp Hugging Face loading for exploration:

```yaml
models:
  lfm2.5-vl-450m-q4_0:
    cmd: |
      ${llama_bin}
      --hf-repo LiquidAI/LFM2.5-VL-450M-GGUF
      --hf-file LFM2.5-VL-450M-Q4_0.gguf
      --host 127.0.0.1
      --port ${PORT}
      --ctx-size 1000
      --cache-ram 512
      --media-path ${downloads_dir}
```

That is not the target PiWatcher standard. The generated PiWatcher config should prefer explicit local `--model` paths:

```yaml
models:
  lfm2.5-vl-450m-q4_0:
    cmd: |
      /home/bostdiek/Projects/llama.cpp/build/bin/llama-server
      --model /mnt/nvme/piwatcher/models/LFM2.5-VL-450M-Q4_0.gguf
      --host 127.0.0.1
      --port ${PORT}
      --ctx-size 1000
      --cache-ram 512
      --media-path /home/bostdiek/Downloads
```

    Before starting that config, setup must ensure the target file exists:

    ```bash
    test -r /mnt/nvme/piwatcher/models/LFM2.5-VL-450M-Q4_0.gguf
    ```

Verify either llama-swap or direct llama-server exposes the expected API:

```bash
curl http://127.0.0.1:8080/v1/models
```

### API and Schema Documentation

PiWatcher calls an OpenAI-compatible endpoint:

```text
POST {LLAMA_SWAP_URL}/chat/completions
model: {LLAMA_SWAP_MODEL}
```

Direct llama.cpp server and llama-swap both satisfy this API shape when configured correctly.

### Configuration Examples

Direct llama.cpp server concept for one fixed model:

```yaml
services:
  llama-server:
    image: ghcr.io/ggml-org/llama.cpp:server
    ports:
      - "8080:8080"
    volumes:
      - /path/on/pi5/models:/models:ro
    command:
      - --host
      - 0.0.0.0
      - --port
      - "8080"
      - --model
      - /models/lfm2-vl-450m.gguf
      - --mmproj
      - /models/lfm2-vl-450m-mmproj.gguf
```

Exact backend/image/device flags still need Pi 5 validation.

## Technical Scenarios

### External Pi 5 Inference Stack

Use the user’s existing llama.cpp/llama-swap services and configure PiWatcher only with endpoint settings.

**Requirements:**

* Existing Pi 5 inference endpoint is reachable from the base app.
* Endpoint supports OpenAI-compatible `/v1/chat/completions`.
* Model name in PiWatcher matches the inference service’s model ID.

**Preferred Approach:**

* Best when inference is already installed and maintained on the Pi 5.
* PiWatcher does not need model paths.
* Operational boundaries are clear: PiWatcher stores events and asks an endpoint to classify.

```text
PiWatcher base -> LLAMA_SWAP_URL -> existing Pi 5 inference stack -> model files
```

**Implementation Details:**

```dotenv
ENABLE_INFERENCE=true
LLAMA_SWAP_URL=http://pi5.local:8080/v1
LLAMA_SWAP_MODEL=lfm2-vl-450m
```

#### Considered Alternatives

This is less self-contained for a new clone, but it is clean for the user’s current Pi 5 because the inference stack already exists.

### Current llama-swap Unified Container

Use the existing compose `llama-swap` service only on architectures where its image is supported. The unified image bundles `llama-server` on amd64, but the tested tag does not provide `linux/arm64/v8` for Pi 5.

**Requirements:**

* A Pi 5-compatible arm64 llama-swap image contains `llama-server`, or the project builds one.
* Model and mmproj files exist at the mounted `/models` paths.
* The Pi 5 container runtime supports the selected backend.

**Preferred Approach:**

* Good if PiWatcher should own inference locally and retain model TTL unload or future model switching.
* Not currently viable on Pi 5 with `ghcr.io/mostlygeek/llama-swap:unified-vulkan` because that tag does not provide `linux/arm64/v8`.
* Keep as optional/profiled infrastructure rather than mandatory `base-up` behavior.

```text
PiWatcher base -> llama-swap container -> bundled llama-server process -> mounted model files
```

**Implementation Details:**

```yaml
models:
  lfm2-vl-450m:
    cmd: llama-server --host 127.0.0.1 --port ${PORT} --model /models/lfm2-vl-450m.gguf --mmproj /models/lfm2-vl-450m-mmproj.gguf
    ttl: 300
```

#### Considered Alternatives

Adding a separate llama.cpp container behind llama-swap may become useful only if llama-swap itself is available on Pi 5 arm64 but needs to proxy to a hardware-specific provider image. It should not be the first owned-inference path.

### Direct llama.cpp llama-server Container

Run only `llama-server` when model swapping is not needed.

**Requirements:**

* One fixed wildlife VLM is enough.
* Need no llama-swap TTL/model switching behavior.
* Direct llama.cpp image supports target architecture and backend.

**Preferred Approach:**

* Simplest repo-owned inference option when not swapping models.
* Fewer layers: PiWatcher talks directly to llama-server.
* Model paths belong to the container command/volumes, not PiWatcher app config.

```text
PiWatcher base -> llama-server container -> mounted model files
```

#### Considered Alternatives

This loses llama-swap’s provider switching and idle unload behavior, but those are not necessary for one fixed model.

### Host-Installed llama.cpp and llama-swap

Install or build `llama-server` on the Pi 5 host and install `llama-swap` as a host Go binary. Manage startup with systemd.

**Requirements:**

* Setup script installs apt build/runtime dependencies or checks they exist.
* Setup script builds llama.cpp from a pinned `LLAMA_CPP_REF` and installs `llama-server` to a stable absolute path such as `/usr/local/bin/llama-server`.
* Setup script installs llama-swap from a pinned `LLAMA_SWAP_VERSION` to a stable absolute path such as `/usr/local/bin/llama-swap`.
* Generated config uses resolved absolute model paths.
* `piwatcher-inference.service` starts llama-swap on boot and is only a soft dependency of the base service.

**Preferred Approach:**

* Best match for PiWatcher-owned Pi 5 inference after the current llama-swap Docker image failed arm64 verification.
* Preserves llama-swap TTL unload and future model switching.
* Avoids relying on third-party multi-arch inference images.
* Keeps inference optional at the base app boundary.

```text
PiWatcher base -> host llama-swap -> host llama-server -> local GGUF files
```

**Implementation Details:**

```bash
GOBIN=/usr/local/bin go install github.com/mostlygeek/llama-swap@v230
```

Validate the `go install` path on the Pi 5. If it does not produce the expected binary behavior, use upstream release binaries or source build instead.

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS -DGGML_CPU_KLEIDIAI=ON
cmake --build build --config Release -j "$(nproc)"
install -m 0755 build/bin/llama-server /opt/piwatcher-inference/bin/llama-server
sudo ln -sfn /opt/piwatcher-inference/bin/llama-server /usr/local/bin/llama-server
```

#### Considered Alternatives

This requires on-device build time and pinned update management, but those are preferable to relying on an unavailable arm64 image. Direct host `llama-server` without llama-swap remains a fallback if `go install` or llama-swap source build is not reliable on Pi 5.

## Selected Approach

For the user’s current Pi 5, PiWatcher should own inference lifecycle as optional infrastructure because the base station needs to recover after reboot, unplugging, or reuse of the Pi 5. The base app should still talk only to an OpenAI-compatible endpoint and remain healthy when inference is disabled or unavailable.

For the repo’s owned Pi 5 inference path, prefer a setup-managed host inference stack: host-installed llama-swap launching host-installed llama.cpp `llama-server`. This best satisfies the requirement that PiWatcher can install, start, and recover inference on the Pi 5 without depending on the amd64-only `ghcr.io/mostlygeek/llama-swap:unified-vulkan` tag.

Use systemd to start `piwatcher-inference.service` on boot, and make `piwatcher-base.service` only softly order after it with `Wants`/`After`, not `Requires`. Missing inference must not prevent event ingestion, dashboard, heartbeat handling, or storage.

Keep direct Docker `llama-server` as a fallback if a known-good arm64 image is validated and host builds become too heavy. Keep llama-swap Docker only for amd64 development or when a Pi 5-compatible arm64 image is available.

Do not default to the current llama-swap unified image on Pi 5. Do not make inference a hard dependency of the base API.
