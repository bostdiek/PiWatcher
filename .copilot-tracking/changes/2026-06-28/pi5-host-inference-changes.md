<!-- markdownlint-disable-file -->
# Release Changes: Pi 5 Host Inference Ownership

**Related Plan**: .copilot-tracking/plans/2026-06-28/pi5-host-inference-plan.instructions.md
**Implementation Date**: 2026-06-28

## Summary

Implementation in progress for optional Pi 5 host inference lifecycle using host llama-swap and host llama-server with local GGUF model files.

## Changes

### Added

* deploy/piwatcher-inference.service - Added a dedicated host llama-swap systemd unit with absolute binary/config defaults, localhost listen address, optional environment overrides, and restart-on-failure behavior.

### Modified

* deploy/setup-llama-swap.sh - Added host inference configuration variables, root `.env` loading, executable validation, deterministic model and mmproj download or placement checks, and host llama-swap config generation with explicit local `--model` paths.
* deploy/llama-swap/config.yaml - Updated the checked-in generated config to use host `llama-server`, the Pi 5 model ID, and the local NVMe GGUF model path.
* deploy/piwatcher-base.service - Added soft `Wants=` and `After=` ordering for `piwatcher-inference.service` without making inference required for base startup.
* Makefile - Split base startup from inference by default while preserving explicit `base-inference-up` and `base-llama-up` inference targets.
* .env.example - Added optional host inference defaults and variables for host binaries, localhost endpoint, model storage, model download URL, media path, and disabled-by-default inference.
* README.md - Documented Pi 5 host inference architecture, setup behavior, Docker development framing, and validation commands.
* packages/base/tests/test_inference.py - Replaced a test-only settings stub with the existing `Settings` fixture so type checking passes while preserving the temperature-cooldown behavior under test.

### Removed

## Additional or Deviating Changes

* Phase 1 YAML validation used `uv run python` after the default `python` environment lacked PyYAML.
	* Reason: The repository-managed environment had PyYAML available and successfully validated the generated config.
* Phase 2 systemd unit verification was skipped locally.
	* Reason: `systemd-analyze` is not available on this macOS host; verification should run on the Pi 5 or another systemd host.
* Phase 3 did not add new Python tests.
	* Reason: Existing inference and event tests already cover disabled inference and event upload independence without Pi hardware; this phase changed docs and environment examples only.
* Repo-wide `ruff format --check .` still reports 19 files that would be reformatted.
	* Reason: These files were already dirty outside this implementation slice; only the touched inference test was formatted to avoid sweeping unrelated changes.
* Pi 5 systemd and hardware smoke checks were not run locally.
	* Reason: This macOS host lacks `systemd-analyze` and the earlier Pi SSH attempt failed; target-device validation remains a deployment step.

## Release Summary

Implemented optional Pi 5 host inference ownership across setup, service orchestration, local startup, documentation, and validation. Added one new service file: `deploy/piwatcher-inference.service`. Modified `deploy/setup-llama-swap.sh`, `deploy/llama-swap/config.yaml`, `deploy/piwatcher-base.service`, `Makefile`, `.env.example`, `README.md`, and `packages/base/tests/test_inference.py`.

Validation passed for `uv run --all-packages pytest`, `uv run --no-sync ruff check .`, `uv run --no-sync ty check`, `bash -n deploy/setup-llama-swap.sh`, checked-in YAML parsing, temporary host setup generation, and expected no-network missing-model failure guidance. Repo-wide format check remains blocked by pre-existing formatting drift in unrelated dirty files.
