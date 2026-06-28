<!-- markdownlint-disable-file -->
# Implementation Details: Pi 5 Host Inference Ownership

## Context Reference

Sources: user request to create the plan, `.copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md`, and `.copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md`.

## Implementation Phase 1: Host Inference Setup Script

<!-- parallelizable: false -->

### Step 1.1: Add host inference configuration variables

Update `deploy/setup-llama-swap.sh` so it can generate a host-installed Pi 5 config in addition to the current Docker-oriented config. Add or consume these variables: `LLAMA_SWAP_BIN`, `LLAMA_SERVER_BIN`, `LLAMA_SWAP_LISTEN`, `LLAMA_SWAP_MODEL`, `LLAMA_SWAP_MODELS_DIR`, `LLAMA_SWAP_MODEL_FILE`, `LLAMA_SWAP_MODEL_URL`, `LLAMA_SWAP_MMPROJ_FILE`, `LLAMA_SWAP_MMPROJ_URL`, and `LLAMA_SWAP_MEDIA_PATH`.

Files:
* deploy/setup-llama-swap.sh - Primary setup script for model placement and generated llama-swap config
* .env.example - Example values for host inference variables

Discrepancy references:
* Addresses DD-01 by making host inference the Pi 5 owned path instead of the unsupported arm64 Docker image.

Success criteria:
* Script reads root `.env` and environment overrides for all host inference settings.
* Script validates `LLAMA_SERVER_BIN` as executable when host mode is selected.
* Script validates `LLAMA_SWAP_BIN` as executable when it will print or install host service commands.
* Defaults match the researched Pi 5 values unless explicitly overridden.

Context references:
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 111-142) - Host binary and explicit model path requirements
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 23-65) - Current setup script is Docker-oriented and uses PATH lookup

Dependencies:
* Existing `deploy/setup-llama-swap.sh` behavior must be preserved for local Docker development unless the implementor intentionally splits host and Docker scripts.
* Bash implementation instructions apply to this shell script.

### Step 1.2: Add deterministic model download and placement checks

Modify setup so explicit `--model` usage is backed by a real local GGUF file. If `LLAMA_SWAP_MODEL_URL` is set and the final model file is missing, download into `LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MODEL_FILE` using resumable and atomic behavior. If no URL is set and the file is missing, print manual placement instructions and fail only the inference setup/start path, not the base application startup path.

Files:
* deploy/setup-llama-swap.sh - Download, resume, atomic rename, and missing-file guidance
* .env.example - Model URL and file placement examples

Discrepancy references:
* Addresses DR-01 by making local model-file presence explicit even though the actual Pi 5 file is not yet validated.

Success criteria:
* Setup creates `LLAMA_SWAP_MODELS_DIR` when needed.
* Partial downloads cannot be mistaken for complete model files.
* Existing model files are not re-downloaded unless a force variable or explicit user action is introduced.
* Missing model files produce the exact target path and a copy/download command the user can run manually.

Context references:
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 137-142) - `--model` does not download and setup must own placement
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 52-65) - Current script only prints guidance for missing files

Dependencies:
* Step 1.1 configuration variables are available.
* Network access is needed only when `LLAMA_SWAP_MODEL_URL` or `LLAMA_SWAP_MMPROJ_URL` is set.

### Step 1.3: Generate host llama-swap config with explicit `--model`

Update generated `deploy/llama-swap/config.yaml` content for host mode so the model command uses the absolute `LLAMA_SERVER_BIN` path and explicit local model paths. Do not generate `--hf-repo` or `--hf-file` for the standard PiWatcher-owned config. Include `--mmproj` only when `LLAMA_SWAP_MMPROJ_FILE` is non-empty and exists or has been downloaded. Keep the model ID aligned with `LLAMA_SWAP_MODEL`.

Files:
* deploy/setup-llama-swap.sh - Config generation logic
* deploy/llama-swap/config.yaml - Generated config checked into the workspace when setup is run

Discrepancy references:
* Addresses DD-02 by replacing the exploratory Hugging Face-backed config with deterministic local model paths.

Success criteria:
* Generated command starts with `/home/bostdiek/Projects/llama.cpp/build/bin/llama-server` by default for Pi 5 host mode.
* Generated command includes `--model /mnt/nvme/piwatcher/models/LFM2.5-VL-450M-Q4_0.gguf` by default for the selected model.
* Generated command binds upstream llama-server to `127.0.0.1` and `${PORT}`.
* Generated config remains valid YAML.

Context references:
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 160-198) - Target host-generated config example and old exploratory config
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 67-77) - Current committed config is container-oriented

Dependencies:
* Steps 1.1 and 1.2 complete.

### Step 1.4: Validate setup script behavior

Run focused checks after script changes. Prefer shell syntax and a dry-run or temporary-output invocation if the script exposes one; otherwise run the script with local test variables pointed at a temporary model directory and no network URL.

Validation commands:
* `bash -n deploy/setup-llama-swap.sh` - Shell syntax validation
* `LLAMA_SWAP_MODEL_URL= LLAMA_SWAP_MODELS_DIR=$TMPDIR/piwatcher-models bash deploy/setup-llama-swap.sh` - No-network missing-file behavior, adjusted if the script requires host paths
* `python - <<'PY'` with `yaml.safe_load` if PyYAML is already available, or another repo-standard YAML validation command - Generated config validation

## Implementation Phase 2: Host Service And Startup Orchestration

<!-- parallelizable: false -->

### Step 2.1: Add a host `piwatcher-inference.service`

Create a dedicated systemd unit for host-installed inference. The service should run `llama-swap` with an absolute binary path, the generated config path, and a localhost listen address. Use `EnvironmentFile` for overrides and avoid requiring inference for base ingestion.

Files:
* deploy/piwatcher-inference.service - New systemd unit for host llama-swap
* deploy/setup-llama-swap.sh - Optional install guidance or generated service-path output

Discrepancy references:
* Addresses DR-01 by documenting the expected validated paths while keeping Pi hardware validation as a deployment step.

Success criteria:
* `ExecStart` uses `${LLAMA_SWAP_BIN}` materialized as an absolute path or a known absolute default.
* Service listens on `127.0.0.1:8080` by default.
* Service uses the generated config path and restarts on failure.
* Service is separate from base API startup.

Context references:
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 225-259) - Host-installed llama.cpp and llama-swap selected scenario
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 79-97) - Current base service does not own inference

Dependencies:
* Phase 1 generated config path and binary defaults are stable.

### Step 2.2: Soft-link base service to inference without requiring it

Update `deploy/piwatcher-base.service` only if needed to add `Wants=piwatcher-inference.service` and `After=piwatcher-inference.service`. Do not add `Requires=piwatcher-inference.service` because missing inference must not block event ingestion, dashboard, heartbeat handling, or storage.

Files:
* deploy/piwatcher-base.service - Optional soft ordering relationship to inference

Discrepancy references:
* Addresses DD-03 by preserving optional inference semantics at systemd boundaries.

Success criteria:
* Base service remains startable when inference service is missing, disabled, or failed.
* Systemd ordering prefers inference before base when both are enabled.
* Existing PostgreSQL startup behavior is preserved.

Context references:
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 280-286) - Selected approach requires soft `Wants`/`After`, not `Requires`
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 79-97) - Current service starts only PostgreSQL and FastAPI

Dependencies:
* Step 2.1 defines the inference service name.

### Step 2.3: Split Make targets so `base-up` is not a hidden inference dependency

Update `Makefile` so `make base-up` starts PostgreSQL, migrations, and the server without hard-requiring llama-swap when `ENABLE_INFERENCE` is false or absent. Keep a direct inference target such as `base-llama-up` or add a host target such as `base-inference-up` that is strict when explicitly invoked.

Files:
* Makefile - Local and host startup orchestration targets

Discrepancy references:
* Addresses DD-03 by aligning local startup with app-level optional inference.

Success criteria:
* `make base-up` no longer fails because llama-swap or model files are unavailable when inference is disabled.
* Explicit inference targets still fail clearly when binaries or model files are missing.
* Existing `base-db-up` and migration behavior remains intact.

Context references:
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 98-111) - Current Makefile makes llama-swap a hard prerequisite of base-up
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 274-286) - Base app remains healthy when inference is disabled or unavailable

Dependencies:
* Phase 1 setup script exposes strict inference setup behavior.

## Implementation Phase 3: Documentation, Environment Examples, And Tests

<!-- parallelizable: true -->

### Step 3.1: Update environment examples and README configuration

Document the selected Pi 5 host inference path and keep Docker llama-swap framed as local/development or architecture-dependent. Add `ENABLE_INFERENCE`, `LLAMA_SERVER_BIN`, `LLAMA_SWAP_BIN`, model directory, model file, model URL, and localhost endpoint examples. Make clear that `--model` does not download and that setup downloads only when a URL is configured.

Files:
* .env.example - Complete example variables for optional host inference
* README.md - Pi 5 inference setup and troubleshooting documentation

Discrepancy references:
* Addresses DR-01 and DD-02 by documenting manual validation and local model placement.

Success criteria:
* README shows the selected Pi 5 architecture: base to localhost llama-swap to host llama-server to local GGUF.
* README states that inference is disabled by default until `ENABLE_INFERENCE=true` is set.
* README includes validation commands for `llama-server --version`, readable model file, `/v1/models`, and a basic chat-completions smoke test.
* `.env.example` includes `ENABLE_INFERENCE=false` by default.

Context references:
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 113-124) - `.env.example` currently omits `ENABLE_INFERENCE`
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 145-198) - Complete examples and explicit local model paths

Dependencies:
* Can proceed in parallel with Phase 2 after Phase 1 defaults are chosen.

### Step 3.2: Add or update tests for optional inference orchestration

Update tests only where repo behavior changes. Focus on the base application remaining healthy when inference is disabled, generated settings accepting the model ID, and any script behavior that can be tested without Pi hardware. Avoid brittle tests that require real `llama-server` or network downloads.

Files:
* packages/base/tests/test_inference.py - Existing inference failure isolation and enablement behavior
* packages/base/tests/test_events.py - Event upload should remain independent of inference availability
* New shell-script test location if the repository already has one, otherwise document manual validation in README instead of adding a new framework

Discrepancy references:
* Addresses DD-03 by validating optional runtime behavior stays intact.

Success criteria:
* Existing inference tests still pass.
* New tests, if added, do not require Pi hardware, Docker image availability, or network access.
* Script validation covers config generation with local model paths when practical.

Context references:
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md (Lines 126-173) - Current app and tests already isolate inference failures
* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 280-286) - Missing inference must not block storage or dashboard behavior

Dependencies:
* Phase 1 or Phase 2 changes define the exact behavior under test.

## Implementation Phase 4: Final Validation

<!-- parallelizable: false -->

### Step 4.1: Run full project validation

Execute the repository validation commands after all implementation phases complete.

Validation commands:
* `uv run --all-packages pytest`
* `uv run --no-sync ruff check .`
* `uv run --no-sync ruff format --check .`
* `uv run --no-sync ty check`
* `bash -n deploy/setup-llama-swap.sh`

### Step 4.2: Run focused inference setup validation

Run focused checks that do not require actual Pi 5 hardware. Use temporary directories and empty URLs to validate missing-file behavior. If the implementor has Pi 5 access, run the Pi-specific commands separately over a resilient terminal session.

Validation commands:
* `LLAMA_SWAP_MODEL_URL= LLAMA_SWAP_MODELS_DIR=$TMPDIR/piwatcher-models bash deploy/setup-llama-swap.sh`
* `test -x /home/bostdiek/Projects/llama.cpp/build/bin/llama-server` on Pi 5
* `/home/bostdiek/Projects/llama.cpp/build/bin/llama-server --version` on Pi 5
* `test -r /mnt/nvme/piwatcher/models/LFM2.5-VL-450M-Q4_0.gguf` on Pi 5
* `curl http://127.0.0.1:8080/v1/models` on Pi 5 after service start

### Step 4.3: Fix minor validation issues and report blockers

Fix isolated lint, type, script syntax, and documentation issues discovered by validation. Report blockers instead of attempting large unplanned work when failures require Pi hardware, model downloads, llama.cpp rebuilds, or system package installation.

## Dependencies

* Bash shell and standard Unix utilities for deploy scripts
* Docker Compose for existing PostgreSQL and local Docker llama-swap development path
* uv for Python validation
* Existing Pi 5 host binaries or manual validation for `/home/bostdiek/.local/bin/llama-swap` and `/home/bostdiek/Projects/llama.cpp/build/bin/llama-server`
* Network access only when downloading model files from `LLAMA_SWAP_MODEL_URL`

## Success Criteria

* PiWatcher has a documented host-installed Pi 5 inference path using host llama-swap and host llama-server.
* Generated llama-swap config uses explicit local `--model` paths and absolute host binaries.
* Setup downloads or clearly validates the local GGUF file before inference startup.
* Base startup remains independent of inference when inference is disabled or unavailable.
* README and `.env.example` explain how to enable, validate, and troubleshoot Pi 5 inference.
