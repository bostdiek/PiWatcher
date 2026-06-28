---
applyTo: ".copilot-tracking/changes/2026-06-27/piwatcher-redesign-changes.md"
---

<!-- markdownlint-disable-file -->

# Implementation Plan: PiWatcher Architecture Redesign

## Overview

Redesign PiWatcher as a motion-triggered wildlife camera system with Pi Zero W battery-powered cameras sending JPEG frames to a Pi 5 base station running local AI inference (LFM2-VL-450M) via llama-swap, with an htmx dashboard and PostgreSQL storage.

## Objectives

### User Requirements

- Pi Zero W cameras detect motion via picamera2 frame differencing, capture 1024x1024 @ 2fps bursts, batch-upload to Pi 5 over WiFi — Source: conversation
- Pi 5 base station runs FastAPI server, receives frames, runs LFM2-VL-450M inference via llama-swap with PydanticAI, stores results in PostgreSQL — Source: conversation + research
- htmx + Jinja2 + TailwindCSS + Chart.js dashboard accessible on LAN — Source: conversation
- Makefile + rsync deployment from Mac to Pi Zeros (no git on field devices) — Source: conversation
- uv workspace for development on Mac, dev tooling (ruff/ty) stays on Mac only — Source: conversation
- 15-minute heartbeat from cameras to base, piggyback on event uploads, stored in PostgreSQL with 90-day TTL — Source: conversation
- Pre-shared bearer token authentication between cameras and base — Source: research
- Keep existing repo, clean slate the code — Source: conversation

### Derived Objectives

- Alembic migrations from day one for schema evolution — Derived from: multi-camera support + future training data needs
- systemd services on both Pi Zero and Pi 5 for reliability — Derived from: headless outdoor deployment
- PiSugar S I2C battery monitoring reported with each upload — Derived from: battery-powered operation needs visibility
- Thermal management for Pi 5 inference (check temp, gap between calls) — Derived from: user-reported fan issues
- ntfy.sh push notifications on detection events — Derived from: research recommendation, user did not reject
- Frame storage on NVMe SSD organized by date for future model training — Derived from: user stated "keep all images for future training"

## Context Summary

### Project Files

- pyproject.toml - Current Poetry-based root (will be replaced with uv workspace)
- piwatcher/base/pyproject.toml - Old RTSP architecture (will be removed)
- piwatcher/camera/ - Old camera code (will be removed)

### References

- .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md - Primary architecture research
- .copilot-tracking/research/subagents/2026-06-27/pi-zero-architecture-research.md - Pi Zero motion detection details
- .copilot-tracking/research/subagents/2026-06-27/pi5-server-architecture-research.md - Pi 5 server + inference pipeline
- .copilot-tracking/research/subagents/2026-06-27/frontend-remote-access-research.md - Dashboard + remote access

### Standards References

- Pre-shared bearer token for LAN auth (OWASP: sufficient for trusted network, no user accounts)
- PostgreSQL with parameterized queries via SQLAlchemy (SQL injection prevention)
- secrets.token_hex(32) for API key generation (cryptographically secure)

## Implementation Checklist

### [x] Implementation Phase 0: Commit & Clear Repo

<!-- parallelizable: false -->

- [x] Step 0.1: Commit planning artifacts
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 15-30)
  - Commit .copilot-tracking/ directory with message: "docs: add architecture research and implementation plan"
- [x] Step 0.2: Remove old code and commit
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 32-55)
  - Remove: piwatcher/, piwatcher.egg-info/, test/, tmp/, generate_diffs.sh, old pyproject.toml
  - Keep: LICENSE, README.md, .copilot-tracking/
  - Commit with message: "chore: remove legacy RTSP architecture for clean slate redesign"
- [x] Step 0.3: Update pre-commit hooks for redesign tooling
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 57-75)
  - Replace legacy black/isort/flake8 hooks with uv-run ruff and ty hooks

### [x] Implementation Phase 1: Project Scaffold

<!-- parallelizable: false -->

- [x] Step 1.1: Create uv workspace root pyproject.toml
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 60-100)
- [x] Step 1.2: Create packages/camera/ package structure
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 102-140)
- [x] Step 1.3: Create packages/base/ package structure
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 142-190)
- [x] Step 1.4: Create Makefile with deployment targets
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 192-240)
- [x] Step 1.5: Create configuration files (.env.example, .gitignore, ruff.toml)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 242-295)
- [x] Step 1.6: Validate scaffold
  - Run `uv sync` to verify workspace resolves
  - Run `ruff check .` to verify config

### [x] Implementation Phase 2: Camera Package

<!-- parallelizable: true -->

- [x] Step 2.1: Implement motion detection module (motion.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 280-340)
- [x] Step 2.2: Implement capture state machine (capture.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 342-410)
- [x] Step 2.3: Implement network transfer module (transfer.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 412-470)
- [x] Step 2.4: Implement battery monitor (battery.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 472-520)
- [x] Step 2.5: Implement heartbeat module (heartbeat.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 522-560)
- [x] Step 2.6: Implement main watcher loop (watcher.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 562-620)
- [x] Step 2.7: Implement config loading (config.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 622-670)
- [x] Step 2.8: Create systemd unit file and setup script
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 672-720)
- [x] Step 2.9: Write camera package tests
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 722-760)

### [x] Implementation Phase 3: Base Station Server

<!-- parallelizable: true -->

- [x] Step 3.1: Database schema + SQLAlchemy models (models.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 770-840)
- [x] Step 3.2: Alembic setup + initial migration
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 842-880)
- [x] Step 3.3: FastAPI app with auth middleware (main.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 882-940)
- [x] Step 3.4: Event ingest endpoint (routes/events.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 942-1000)
- [x] Step 3.5: Frame storage service (storage.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1002-1040)
- [x] Step 3.6: Inference pipeline with thermal management (inference.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1042-1120)
- [x] Step 3.7: Heartbeat endpoint + TTL cleanup (routes/heartbeat.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1122-1170)
- [x] Step 3.8: Push notifications via ntfy.sh (notifications.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1172-1210)
- [x] Step 3.9: Server config and DB connection (config.py, db.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1212-1260)
- [x] Step 3.10: Write server tests
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1262-1310)

### [x] Implementation Phase 4: Dashboard

<!-- parallelizable: false -->

- [x] Step 4.1: Base template with TailwindCSS + htmx (base.html)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1320-1370)
- [x] Step 4.2: Events list page with real-time updates (events.html)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1372-1420)
- [x] Step 4.3: Event detail page with frame gallery (event_detail.html)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1422-1460)
- [x] Step 4.4: Camera health page with battery sparklines (health.html)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1462-1510)
- [x] Step 4.5: Dashboard route handlers (routes/dashboard.py)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1512-1560)
- [x] Step 4.6: WebSocket for real-time event stream
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1562-1600)

### [x] Implementation Phase 5: Deployment & Operations

<!-- parallelizable: false -->

- [x] Step 5.1: Pi 5 systemd service for piwatcher-base
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1610-1650)
- [x] Step 5.2: Docker Compose for PostgreSQL
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1652-1690)
- [x] Step 5.3: Pi Zero setup script (deploy/setup-camera.sh)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1692-1740)
- [x] Step 5.4: Heartbeat TTL cron job (pg_cron or systemd timer)
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1742-1770)
- [x] Step 5.5: Update README.md with setup instructions
  - Details: .copilot-tracking/details/2026-06-27/piwatcher-redesign-details.md (Lines 1772-1810)

### [x] Implementation Phase 6: Validation

<!-- parallelizable: false -->

- [x] Step 6.1: Run full project validation
  - Execute `uv run ruff check .` for linting
  - Execute `uv run ty check` for type checking
  - Execute `uv run pytest` for all tests
- [x] Step 6.2: Fix minor validation issues
  - Iterate on lint errors, type errors, and test failures
  - Apply fixes directly when corrections are straightforward
- [x] Step 6.3: Verify Makefile targets work
  - Test `make lint`, `make typecheck`, `make test`
  - Verify `make update-cameras` rsync syntax (dry-run mode)
- [x] Step 6.4: Report blocking issues
  - Document issues requiring Pi hardware for testing
  - Provide user with deployment testing steps

## Planning Log

See .copilot-tracking/plans/logs/2026-06-27/piwatcher-redesign-log.md for discrepancy tracking, implementation paths considered, and suggested follow-on work.

## Dependencies

- Python 3.11+ (Pi 5 and Mac)
- Python 3.9+ (Pi Zero W — Bookworm ships 3.11)
- uv (Mac development, optional on Pi 5)
- ruff + ty (Mac development only)
- PostgreSQL 15+ (Pi 5 via Docker)
- picamera2 (Pi Zero — system apt package)
- llama-swap + llama.cpp (Pi 5 — pre-installed, not managed by this project)
- rsync + SSH (Mac → Pi Zero deployment)

## Success Criteria

- `uv sync` resolves workspace without errors — Traces to: uv workspace requirement
- `ruff check .` passes with zero errors — Traces to: dev tooling on Mac
- `pytest` passes for both packages — Traces to: code correctness
- Camera watcher.py can be rsync'd to Pi Zero and run via systemd — Traces to: deployment strategy
- FastAPI server starts and accepts POST /api/events with bearer auth — Traces to: Pi-to-Pi communication
- Alembic migrations apply cleanly to fresh PostgreSQL — Traces to: database requirement
- Dashboard renders at http://localhost:8000 with event list — Traces to: frontend requirement
- Makefile `update-cameras` target performs rsync to configured hosts — Traces to: deployment automation
