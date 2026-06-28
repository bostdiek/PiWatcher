<!-- markdownlint-disable-file -->
# Planning Log: Pi 5 Host Inference Ownership

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Unaddressed Research Items

* DR-01: Actual Pi 5 `llama-server` binary and local GGUF file were not validated in this planning session.
  * Source: .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 31-34)
  * Reason: The plan can define validation and setup behavior, but the remote Pi 5 path requires device access and the prior SSH attempt failed.
  * Impact: medium
* DR-02: Go-based repeatable `llama-swap` installation is not validated because Go is missing on the Pi 5.
  * Source: .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 89-97)
  * Reason: The user already has a working `llama-swap` binary, so the implementation plan reuses `LLAMA_SWAP_BIN` and defers reinstall/update automation.
  * Impact: low
* DR-03: Exact host service user remains deployment-specific.
  * Source: .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 101-109)
  * Reason: User paths indicate `bostdiek`, while existing base service examples use `/home/pi`; the plan requires absolute paths and environment overrides instead of hard-coding only one user.
  * Impact: medium

### Plan Deviations from Research

* DD-01: Plan keeps Docker llama-swap as a development/local path instead of removing it entirely.
  * Research recommends: Do not default to the current llama-swap unified image on Pi 5 because it is not arm64 usable.
  * Plan implements: Host inference becomes the Pi 5 owned path while Docker llama-swap remains available for local development or validated architectures.
  * Rationale: The app and Makefile still have useful local Docker behavior; removing it would be unrelated churn and could break non-Pi development.
* DD-02: Plan does not implement Hugging Face `--hf-repo` and `--hf-file` in generated PiWatcher config.
  * Research recommends: Use explicit local `--model` paths as the project-owned standard after user clarification.
  * Plan implements: Generated config uses `LLAMA_SERVER_BIN --model $LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MODEL_FILE` and setup downloads the file only when `LLAMA_SWAP_MODEL_URL` is configured.
  * Rationale: Deterministic local model files make boot behavior predictable under systemd and match the user’s preference.
* DD-03: Plan preserves optional inference instead of making base service require inference.
  * Research recommends: PiWatcher should own inference lifecycle but not make inference a hard dependency of event ingestion.
  * Plan implements: A separate `piwatcher-inference.service` and soft systemd ordering; `make base-up` should not hard-require inference when disabled.
  * Rationale: The base app already handles disabled and unavailable inference gracefully, and forcing inference startup would regress reliability.

## Implementation Paths Considered

### Selected: Host llama-swap launching host llama-server

* Approach: Add host inference setup to generate absolute-path llama-swap config, validate/download local GGUF files, add a dedicated `piwatcher-inference.service`, and keep the base app endpoint-only.
* Rationale: This matches the selected architecture after the current llama-swap Docker image failed Pi 5 arm64 validation while the host `llama-swap` binary already works.
* Evidence: .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md (Lines 111-142)

### IP-01: Current llama-swap Docker container as production Pi 5 inference

* Approach: Keep `ghcr.io/mostlygeek/llama-swap:unified-vulkan` as the owned inference runtime for Pi 5.
* Trade-offs: Simple because Compose already exists, but the tested image does not provide `linux/arm64/v8` and reports x86_64 contents.
* Rejection rationale: It does not satisfy the Pi 5 production target without building or finding a different arm64 image.

### IP-02: Direct host llama-server without llama-swap

* Approach: Start `llama-server` directly with systemd and point PiWatcher at its OpenAI-compatible endpoint.
* Trade-offs: Fewer layers and simpler service graph, but loses llama-swap model switching, TTL unload, and the user’s already-working llama-swap binary.
* Rejection rationale: The selected path preserves future model switching and reuses validated host llama-swap with limited additional complexity.

### IP-03: Application-managed inference process lifecycle

* Approach: Add Python code in `piwatcher_base` to start and monitor `llama-swap` or `llama-server` directly.
* Trade-offs: Centralizes behavior in the app, but mixes web app runtime with system process supervision and model-file management.
* Rejection rationale: systemd is the better owner for process restart, boot ordering, environment files, and host binaries; app code should remain endpoint-based.

## Suggested Follow-On Work

Items identified during planning that fall outside current scope.

* WI-01: Validate Pi 5 host binaries and model file — Run `llama-server --version`, `llama-swap --version`, and local GGUF readability checks on the actual Pi 5. (high)
  * Source: DR-01
  * Dependency: Pi 5 shell access
* WI-02: Add repeatable llama.cpp build/install automation — Create a separate script to clone or update llama.cpp at a pinned ref and install `llama-server` to a stable path. (medium)
  * Source: DR-01 and DR-02
  * Dependency: Confirmed Pi 5 build requirements and desired install prefix
* WI-03: Add repeatable llama-swap install/update automation — Install Go or fetch release binaries when the existing `LLAMA_SWAP_BIN` is missing or forced to update. (medium)
  * Source: DR-02
  * Dependency: Decision on Go install versus binary release retrieval
* WI-04: Validate an arm64 Docker alternative — Research or build a Pi 5-compatible llama-swap or direct llama.cpp image if host builds become too heavy. (low)
  * Source: IP-01 and IP-02
  * Dependency: Need to preserve Docker-owned inference as a production option
* WI-05: Resolve repository formatting drift — Run or stage a separate formatting cleanup for the 19 pre-existing Python files reported by `uv run --no-sync ruff format --check .`. (low)
  * Source: Phase 4 validation
  * Dependency: Decide whether to include unrelated formatting-only changes in a separate branch or cleanup commit
