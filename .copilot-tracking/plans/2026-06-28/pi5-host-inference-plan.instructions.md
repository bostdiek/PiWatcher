---
applyTo: '.copilot-tracking/changes/2026-06-28/pi5-host-inference-changes.md'
---
<!-- markdownlint-disable-file -->
# Implementation Plan: Pi 5 Host Inference Ownership

## Overview

Implement an optional Pi 5 host inference path where PiWatcher owns startup and configuration for host `llama-swap` launching host `llama-server` against a local GGUF file on NVMe, while keeping the base app healthy when inference is disabled or unavailable.

## Objectives

### User Requirements

* Make the plan for PiWatcher-owned Pi 5 inference lifecycle — Source: user request, “now make the plan” after inference research.
* Use host-installed `llama-swap` and host `llama-server` instead of the current unsupported Pi 5 llama-swap Docker image — Source: user preference and research findings.
* Require an explicit `LLAMA_SERVER_BIN` path because systemd should not rely on interactive shell `PATH` — Source: user request, “I think we need the path to the llama server binary too.”
* Generate llama-swap commands with explicit local `--model` paths, not `--hf-repo` or `--hf-file` — Source: user clarification, “I want it to use the --model.”
* Download or validate the GGUF model file on NVMe before inference startup — Source: user question about whether `--model` downloads automatically.
* Keep inference protected and optional so base storage, heartbeat, dashboard, and event ingestion still work without inference — Source: prior user request that inference “should be protected / optional.”

### Derived Objectives

* Preserve app-level endpoint-only inference settings and keep model paths in deployment setup — Derived from: `piwatcher_base.config` and `piwatcher_base.inference` already use endpoint URL/model only.
* Split local startup so `make base-up` does not hide a hard inference dependency when `ENABLE_INFERENCE` is false — Derived from: current `Makefile` makes `base-up` depend on `base-llama-up` even though app inference defaults disabled.
* Add a dedicated `piwatcher-inference.service` with soft base ordering instead of process management inside the Python app — Derived from: systemd is the right owner for host process restart and boot ordering.
* Keep Docker llama-swap available as local/development infrastructure, but stop treating it as the Pi 5 production path — Derived from: current `ghcr.io/mostlygeek/llama-swap:unified-vulkan` image lacks `linux/arm64/v8` support.
* Update README and `.env.example` so enabling inference is explicit, reproducible, and testable — Derived from: current environment examples omit `ENABLE_INFERENCE` while code supports it.

## Context Summary

### Project Files

* deploy/setup-llama-swap.sh - Current setup script prepares model files and generates Docker-oriented llama-swap config.
* deploy/llama-swap/config.yaml - Current generated config uses container paths and `llama-server` by PATH lookup.
* docker-compose.yml - Current local Compose file defines PostgreSQL and Docker llama-swap.
* Makefile - Current `base-up` depends on `base-llama-up`, making inference a hidden startup dependency.
* deploy/piwatcher-base.service - Current base systemd service starts PostgreSQL and FastAPI but does not own inference.
* packages/base/src/piwatcher_base/config.py - Base app settings include endpoint/model/enabled inference controls.
* packages/base/src/piwatcher_base/inference.py - Base app posts OpenAI-compatible requests and handles disabled or failed inference without crashing.
* README.md - Documentation needs host Pi 5 inference setup, validation, and troubleshooting updates.
* .env.example - Environment example needs `ENABLE_INFERENCE` and host inference variables.

### References

* .copilot-tracking/research/2026-06-28/llama-swap-vs-llama-server-research.md - Primary inference architecture research and selected approach.
* .copilot-tracking/research/subagents/2026-06-28/pi5-host-inference-current-surfaces-research.md - Current repository implementation surfaces and missing files.
* .copilot-tracking/research/subagents/2026-06-28/host-installed-llama-inference-research.md - Host-installed llama.cpp and llama-swap research from earlier investigation.

### Standards References

* /Users/bryanostdiek/.vscode-insiders/extensions/ise-hve-essentials.hve-core-all-3.3.101/.github/instructions/coding-standards/bash/bash.instructions.md - Applies when editing `deploy/setup-llama-swap.sh`.
* /Users/bryanostdiek/.vscode-insiders/extensions/ise-hve-essentials.hve-core-all-3.3.101/.github/instructions/hve-core/markdown.instructions.md - Applies when editing README and tracking Markdown.
* /Users/bryanostdiek/.vscode-insiders/extensions/ise-hve-essentials.hve-core-all-3.3.101/.github/instructions/hve-core/writing-style.instructions.md - Applies when editing README and user-facing Markdown.

## Implementation Checklist

### [x] Implementation Phase 1: Host Inference Setup Script

<!-- parallelizable: false -->

* [x] Step 1.1: Add host inference configuration variables
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 12-36)
* [x] Step 1.2: Add deterministic model download and placement checks
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 37-61)
* [x] Step 1.3: Generate host llama-swap config with explicit `--model`
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 62-85)
* [x] Step 1.4: Validate setup script behavior
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 86-94)

### [x] Implementation Phase 2: Host Service And Startup Orchestration

<!-- parallelizable: false -->

* [x] Step 2.1: Add a host `piwatcher-inference.service`
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 99-122)
* [x] Step 2.2: Soft-link base service to inference without requiring it
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 123-144)
* [x] Step 2.3: Split Make targets so `base-up` is not a hidden inference dependency
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 145-166)

### [x] Implementation Phase 3: Documentation, Environment Examples, And Tests

<!-- parallelizable: true -->

* [x] Step 3.1: Update environment examples and README configuration
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 171-194)
* [x] Step 3.2: Add or update tests for optional inference orchestration
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 195-218)

### [x] Implementation Phase 4: Final Validation

<!-- parallelizable: false -->

* [x] Step 4.1: Run full project validation
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 223-233)
* [x] Step 4.2: Run focused inference setup validation
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 234-244)
* [x] Step 4.3: Fix minor validation issues and report blockers
  * Details: .copilot-tracking/details/2026-06-28/pi5-host-inference-details.md (Lines 245-248)

## Planning Log

See `.copilot-tracking/plans/logs/2026-06-28/pi5-host-inference-log.md` for discrepancy tracking, implementation paths considered, and suggested follow-on work.

## Dependencies

* Bash shell and standard Unix utilities for deploy scripts.
* Existing Pi 5 host `llama-swap` binary at `/home/bostdiek/.local/bin/llama-swap`, or an override through `LLAMA_SWAP_BIN`.
* Existing Pi 5 host `llama-server` binary at `/home/bostdiek/Projects/llama.cpp/build/bin/llama-server`, or an override through `LLAMA_SERVER_BIN`.
* Local GGUF model file at `/mnt/nvme/piwatcher/models/LFM2.5-VL-450M-Q4_0.gguf`, or network access to download `LLAMA_SWAP_MODEL_URL` during setup.
* Docker Compose for existing PostgreSQL startup and local Docker llama-swap development path.
* uv, pytest, ruff, and ty for Python validation.

## Success Criteria

* `deploy/setup-llama-swap.sh` can generate a Pi 5 host llama-swap config using absolute `LLAMA_SERVER_BIN` and explicit local `--model` path — Traces to: user requirement for explicit `--model` and research selected approach.
* Setup either downloads `LLAMA_SWAP_MODEL_URL` into `LLAMA_SWAP_MODELS_DIR/$LLAMA_SWAP_MODEL_FILE` or clearly fails inference setup with manual placement instructions — Traces to: user question about model download behavior.
* A dedicated `deploy/piwatcher-inference.service` starts host llama-swap on localhost without making base API startup depend on inference — Traces to: protected optional inference requirement.
* `make base-up` no longer hard-requires llama-swap when inference is disabled, while explicit inference startup remains strict — Traces to: current Makefile mismatch and optional inference objective.
* README and `.env.example` document `ENABLE_INFERENCE`, host binary paths, model file placement, and Pi 5 validation commands — Traces to: environment/documentation gaps in current-surface research.
* Full project validation and focused deploy-script validation pass or report Pi 5 hardware/model-download blockers explicitly — Traces to: final validation phase requirements.
