<!-- markdownlint-disable-file -->
# Release Changes: PiWatcher Architecture Redesign

**Related Plan**: piwatcher-redesign-plan.instructions.md
**Implementation Date**: 2026-06-27

## Summary

Implementation in progress for the PiWatcher clean-slate architecture redesign: uv workspace, Pi Zero W camera package, Pi 5 FastAPI base station, htmx dashboard, and deployment operations.

## Changes

### Added

* .copilot-tracking/changes/2026-06-27/piwatcher-redesign-changes.md - Tracks implementation changes and validation results for this plan
* pyproject.toml - Created uv workspace root and wired workspace packages for root import validation
* Makefile - Added development, test, coverage, and camera deployment targets
* .env.example - Added PiWatcher base station environment template
* ruff.toml - Added project lint and import sorting configuration
* packages/camera/pyproject.toml - Added Pi Zero camera package metadata and runtime dependencies
* packages/camera/.env.example - Added camera environment template
* packages/camera/src/piwatcher_camera/__init__.py - Added camera package init
* packages/base/pyproject.toml - Added Pi 5 base station package metadata, server dependencies, and script entry point
* packages/base/src/piwatcher_base/__init__.py - Added base package init
* packages/base/src/piwatcher_base/routes/__init__.py - Added base routes package init
* packages/base/src/piwatcher_base/templates/.gitkeep - Preserved base template directory
* packages/base/alembic/.gitkeep - Preserved Alembic directory
* packages/camera/src/piwatcher_camera/motion.py - Added NumPy frame differencing motion detection
* packages/camera/src/piwatcher_camera/capture.py - Added adaptive capture state machine
* packages/camera/src/piwatcher_camera/transfer.py - Added rfkill WiFi controls and multipart event upload
* packages/camera/src/piwatcher_camera/battery.py - Added PiSugar I2C battery helpers with graceful fallback
* packages/camera/src/piwatcher_camera/heartbeat.py - Added heartbeat timing, send, and piggyback logic
* packages/camera/src/piwatcher_camera/config.py - Added camera environment config loader and defaults
* packages/camera/src/piwatcher_camera/watcher.py - Added main Pi camera watcher loop with isolated runtime `picamera2` import
* deploy/piwatcher-camera.service - Added Pi Zero systemd service
* deploy/setup-camera.sh - Added executable first-time camera setup script
* packages/camera/tests/test_motion.py - Added motion detection tests
* packages/camera/tests/test_capture.py - Added capture state tests
* packages/camera/tests/test_config.py - Added camera config tests
* packages/camera/tests/test_heartbeat.py - Added heartbeat tests
* packages/base/src/piwatcher_base/models.py - Added Event, Frame, and Heartbeat SQLAlchemy models
* packages/base/src/piwatcher_base/config.py - Added base station settings loader
* packages/base/src/piwatcher_base/db.py - Added async SQLAlchemy engine and session helpers
* packages/base/src/piwatcher_base/auth.py - Added bearer token auth dependency
* packages/base/src/piwatcher_base/main.py - Added FastAPI app, lifespan, and route mounting
* packages/base/src/piwatcher_base/storage.py - Added date/camera/event frame storage service
* packages/base/src/piwatcher_base/inference.py - Added llama-swap inference adapter with thermal gating
* packages/base/src/piwatcher_base/notifications.py - Added best-effort ntfy notification helper
* packages/base/src/piwatcher_base/routes/events.py - Added event ingest and query API routes
* packages/base/src/piwatcher_base/routes/heartbeat.py - Added heartbeat ingest, health summary, and cleanup API support
* packages/base/alembic.ini - Added Alembic configuration
* packages/base/alembic/env.py - Added async Alembic migration environment
* packages/base/alembic/versions/001_initial_schema.py - Added initial schema migration
* packages/base/alembic/versions/.gitkeep - Preserved Alembic versions directory
* packages/base/tests/conftest.py - Added base test fixtures and DB overrides
* packages/base/tests/test_auth.py - Added auth tests
* packages/base/tests/test_events.py - Added event route tests
* packages/base/tests/test_heartbeat.py - Added heartbeat route tests
* packages/base/tests/test_inference.py - Added inference pipeline tests
* packages/base/tests/test_storage.py - Added storage tests
* packages/base/src/piwatcher_base/routes/dashboard.py - Added LAN-public dashboard HTML routes and frame serving
* packages/base/src/piwatcher_base/routes/ws.py - Added WebSocket connection manager and event broadcast endpoint
* packages/base/src/piwatcher_base/templates/base.html - Added responsive TailwindCSS, htmx, and Chart.js dashboard shell
* packages/base/src/piwatcher_base/templates/events.html - Added events list page with polling and camera filtering
* packages/base/src/piwatcher_base/templates/event_detail.html - Added event detail frame gallery and classification display
* packages/base/src/piwatcher_base/templates/health.html - Added camera health page with battery sparklines
* packages/base/src/piwatcher_base/templates/partials/event_card.html - Added reusable event card partial
* packages/base/tests/test_dashboard.py - Added dashboard route rendering tests
* deploy/piwatcher-base.service - Added Pi 5 systemd service for the base station server
* deploy/piwatcher-ttl.service - Added daily heartbeat TTL cleanup service
* deploy/piwatcher-ttl.timer - Added daily heartbeat TTL cleanup timer
* docker-compose.yml - Added PostgreSQL 16 service with persistent storage and healthcheck

### Modified

* .pre-commit-config.yaml - Replaced legacy black/isort/flake8 hooks with uv-run ruff check, ruff format, and ty check hooks
* .gitignore - Updated ignore patterns for uv, Python build artifacts, env files, and caches
* packages/camera/pyproject.toml - Added NumPy runtime dependency for motion detection
* packages/base/pyproject.toml - Added aiosqlite to support async SQLite tests
* pyproject.toml - Added pytest import mode and validation-oriented typing fixes in workspace configuration
* packages/base/src/piwatcher_base/config.py - Adjusted settings construction for type-check compatibility
* packages/base/src/piwatcher_base/routes/heartbeat.py - Tightened typed cleanup row count handling
* packages/base/src/piwatcher_base/inference.py - Applied formatting and type-check compatibility fixes
* packages/base/src/piwatcher_base/storage.py - Applied formatting fixes
* packages/base/tests/test_inference.py - Adjusted tests for type-check and pytest stability
* packages/camera/src/piwatcher_camera/battery.py - Added Pi-only hardware import typing fallback
* packages/camera/src/piwatcher_camera/watcher.py - Added camera protocol typing for runtime-only `picamera2`
* packages/base/src/piwatcher_base/main.py - Mounted dashboard and WebSocket routes without import-time settings requirements
* packages/base/src/piwatcher_base/routes/events.py - Broadcasts event creation messages to connected dashboard clients
* packages/base/tests/conftest.py - Extended base test fixtures for dashboard route tests
* deploy/setup-camera.sh - Made Pi Zero provisioning idempotent, added I2C/PiSugar dependencies, and enabled service without starting before `.env` exists
* README.md - Rewritten with current architecture, setup, deployment, configuration, and operations guidance
* .copilot-tracking/plans/2026-06-27/piwatcher-redesign-plan.instructions.md - Marked Phase 0 complete and added Step 0.3 for pre-commit redesign tooling
* .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md - Added Phase 0 Step 0.3 implementation details for pre-commit tooling
* .copilot-tracking/plans/logs/2026-06-27/piwatcher-redesign-log.md - Recorded the Phase 0 pre-commit tooling update and Phase 1 root dependency wiring as implementation deviations
* .copilot-tracking/plans/2026-06-27/piwatcher-redesign-plan.instructions.md - Marked Phase 1 scaffold steps complete

### Removed

* Legacy RTSP/Poetry code and generated artifacts were removed in Phase 0 commits: piwatcher/, piwatcher.egg-info/, test/, tmp/, generate_diffs.sh, root pyproject.toml, and stale poetry.lock
* packages/base/tests/__init__.py - Removed to avoid duplicate top-level pytest package collisions
* packages/camera/tests/__init__.py - Removed to avoid duplicate top-level pytest package collisions

## Additional or Deviating Changes

* Updated .pre-commit-config.yaml during Phase 0 at user request
	* Reason: The redesign uses uv, ruff, and ty; keeping black/isort/flake8 would make local hooks disagree with the new project tooling.
* Added `aiosqlite` to the base package dependency list
	* Reason: The plan requires server tests to run without PostgreSQL, and SQLAlchemy async SQLite requires this driver.
* Removed package test `__init__.py` markers and set pytest import mode
	* Reason: Full validation exposed duplicate `tests` package import collisions across the two workspace packages.

## Release Summary

Implemented the PiWatcher clean-slate redesign across 62 changed paths after the Phase 0 cleanup commits. The new repo contains a uv workspace with separate camera and base packages, Mac-only ruff/ty tooling, pre-commit hooks aligned to that toolchain, a Pi Zero W motion/capture/upload runtime, a Pi 5 FastAPI base station with PostgreSQL/Alembic models, thermal-gated llama-swap inference, htmx/Jinja2 dashboard pages, deployment units, Docker Compose PostgreSQL, and updated setup documentation.

Files created include the workspace root (`pyproject.toml`, `Makefile`, `.env.example`, `ruff.toml`), camera package modules and tests under `packages/camera/`, base station modules, Alembic migration, templates, routes, and tests under `packages/base/`, deployment assets under `deploy/`, and `docker-compose.yml`. Existing files modified include `.pre-commit-config.yaml`, `.gitignore`, `README.md`, package metadata, and tracking artifacts. Removed files include the legacy RTSP/Poetry architecture and duplicate test package markers.

Validation passed with `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check`, `uv run pytest --cov` (28 tests, 79% aggregate coverage, no threshold), `make lint`, `make typecheck`, `make test`, and `make -n update-cameras CAMERAS=test.local`. Local validation did not exercise Pi Zero camera hardware, PiSugar I2C, rfkill behavior, Pi 5 PostgreSQL migrations against a live database, llama-swap inference, or browser/device dashboard behavior; those are recorded as follow-on hardware and deployment validation items.