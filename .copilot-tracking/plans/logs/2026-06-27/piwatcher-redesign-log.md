<!-- markdownlint-disable-file -->
# Planning Log: PiWatcher Architecture Redesign

## Discrepancy Log

Gaps and differences identified between research findings and the implementation plan.

### Unaddressed Research Items

* DR-01: Cloudflare Tunnel setup for remote access
  * Source: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 290-295)
  * Reason: User stated "no Cloudflare needed initially" — LAN access via pi5.local is sufficient for v1
  * Impact: low — can be added later without architectural changes

* DR-02: External battery wiring (parallel LiPo to PiSugar S)
  * Source: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 67-69)
  * Reason: Hardware modification, not a software concern
  * Impact: low — software handles whatever battery capacity exists

* DR-03: Pi Zero W vs Pi Zero 2 W performance investigation
  * Source: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 62-64)
  * Reason: User confirmed Pi Zero W Rev 1.1 (single-core). Research validated 2fps @ 1024x1024 is achievable.
  * Impact: low — confirmed feasible on single-core

* DR-04: Pi 5 fan diagnosis
  * Source: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 57-59)
  * Reason: Hardware debugging separate from software implementation. Thermal management code handles broken fan scenario.
  * Impact: low — thermal gating in inference.py handles this regardless

* DR-05: React SPA alternative for frontend
  * Source: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 275-280)
  * Reason: User agreed htmx + Jinja2 is sufficient for solo dev. React adds npm build step complexity.
  * Impact: low — htmx can be replaced later without backend changes

* DR-06: Research `consecutive_frames` parameter for false-positive reduction
  * Source: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Scenario 4 — MotionConfig dataclass, `consecutive_frames: int = 2`)
  * Reason: Plan's motion.py performs single-frame comparison. Consecutive-frame gating could be added at the watcher.py loop level but is not explicitly planned as a step or config parameter.
  * Impact: minor — reduces false positives from transient pixel noise; can be added to watcher loop logic and CameraConfig without architectural changes

* DR-07: Research `night_multiplier` and `roi` tuning parameters
  * Source: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Scenario 4 — MotionConfig dataclass)
  * Reason: Nice-to-have tuning features beyond minimum viable system. Plan's CameraConfig includes core threshold/pct but omits these advanced parameters.
  * Impact: minor — daytime-only system (no IR), so night_multiplier has limited current value; ROI is a convenience feature for excluding tree canopies or fixed objects

### Plan Deviations from Research

* DD-01: Package structure uses packages/camera/ instead of research's piwatcher/zero/
  * Research recommends: `piwatcher/zero/` and `piwatcher/server/` flat structure
  * Plan implements: `packages/camera/src/piwatcher_camera/` and `packages/base/src/piwatcher_base/` uv workspace
  * Rationale: uv workspace convention uses packages/ directory with src layout. Better separation for rsync deployment (only need to sync the src directory).

* DD-02: Camera package uses python-dotenv instead of dataclass-based TOML config
  * Research recommends: dataclass with TOML or .env
  * Plan implements: python-dotenv with dataclass wrapper
  * Rationale: .env is simpler to edit on headless Pi Zero via SSH. Single flat file, no TOML parser needed.

* DD-03: No docker-compose for full stack (only PostgreSQL)
  * Research recommends: docker-compose.yml for PostgreSQL + server + cloudflared
  * Plan implements: Docker only for PostgreSQL; server runs natively via systemd
  * Rationale: Native uvicorn via systemd is simpler for development and debugging on Pi 5. Docker adds unnecessary layer for the Python app.

* DD-04: Research internal inconsistencies on resolution and fps (outdated sections)
  * Research recommends: Key Discoveries #2 and Power Budget #7 specify 1024x1024 @ 2fps; however, Scenario 1 diagram still shows "640x480 @ 1fps", and the Considered Alternatives table lists "640x480" as "Selected" capture resolution
  * Plan implements: 1024x1024 @ 2fps consistently across all steps (config defaults, power budget assumptions, transfer calculations)
  * Rationale: Research was updated mid-session. Key Discoveries and Power Budget represent the final agreed values. Scenario 1 diagram and Alternatives table are stale pre-decision text within the research document itself. Plan correctly follows the final conclusion.

* DD-05: Phase 0 now updates pre-commit tooling before project scaffold
  * Plan originally specified: Commit planning artifacts, then remove the legacy RTSP/Poetry architecture
  * Implementation differs: Phase 0 also replaces black/isort/flake8 hooks with uv-run ruff and ty hooks
  * Rationale: User requested pre-commit be updated as part of Phase 0 so the clean-slate repo stops enforcing legacy formatting and linting tools before new code is scaffolded.

* DD-06: Root project depends on workspace packages for import validation
  * Plan specifies: Root `pyproject.toml` defines the uv workspace members
  * Implementation differs: Root `pyproject.toml` also declares `piwatcher-camera` and `piwatcher-base` dependencies with `[tool.uv.sources]` pointing to the workspace
  * Rationale: `uv sync` resolved the workspace without these dependencies, but the required root import validation could not import either package until they were installed into the root environment.

* DD-07: Base package adds `aiosqlite` for hardware-free async tests
  * Plan specifies: Server tests should use SQLite in-memory for test DBs
  * Implementation differs: `aiosqlite` was added as a base package dependency to support SQLAlchemy async SQLite tests
  * Rationale: Async SQLAlchemy requires an async SQLite driver for the planned no-PostgreSQL test strategy.

* DD-08: Dashboard serves frame files with a request-time route
  * Plan specifies: FastAPI app mounts static files for dashboard assets/frame access
  * Implementation differs: Dashboard uses `/frames/{frame_path:path}` handled at request time instead of mounting `StaticFiles` at import time
  * Rationale: Static mounting required environment-backed settings during module import, which broke the app import validation before `.env` existed. Request-time serving preserves importability and still gates paths to the configured frame storage directory.

* DD-09: Removed test package markers to avoid duplicate top-level `tests` packages
  * Plan specifies: Add `packages/base/tests/__init__.py` and `packages/camera/tests/__init__.py` during scaffold
  * Implementation differs: Phase 6 removed those files and configured pytest import mode in `pyproject.toml`
  * Rationale: Keeping both files made pytest collect both package test trees as the same top-level `tests` package, causing import collisions during full validation.

## Implementation Paths Considered

### Selected: uv Workspace with rsync Deployment

* Approach: uv workspace on Mac for development. Two packages (camera, base). rsync camera source to Pi Zeros via Makefile. Run base station natively on Pi 5 with systemd.
* Rationale: Minimal tooling on field devices. Camera package has zero build step — just Python files rsynced. Pi 5 can optionally use uv (aarch64 supported) but doesn't need it for systemd operation.
* Evidence: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md, conversation decisions

### IP-01: Git-Based Deployment (SSH + git pull on each Pi)

* Approach: Keep git repo on all Pis. SSH in, run `git pull` to update.
* Trade-offs: Familiar workflow, automatic history. But requires git + GitHub SSH keys on every Pi Zero. Pi Zeros need full repo cloned (wasted space, security risk).
* Rejection rationale: User agreed rsync is cleaner — no git needed on field devices. Reduces attack surface (no SSH keys to GitHub on outdoor devices).

### IP-02: Docker-Based Deployment (build image, docker pull on Pis)

* Approach: Build Docker images for camera and base. Pi Zeros run container.
* Trade-offs: Reproducible environment, easy rollback. But Pi Zero W has very limited RAM (512MB), slow image pulls, Docker overhead significant.
* Rejection rationale: Docker on Pi Zero W is impractical — 512MB RAM leaves almost nothing for the container. Native Python with apt-installed picamera2 is the only viable path.

### IP-03: Ansible/Fabric-Based Deployment

* Approach: Use Ansible or Fabric for orchestrated multi-Pi deployment.
* Trade-offs: Proper infra-as-code, idempotent, handles multiple devices elegantly.
* Rejection rationale: Over-engineered for 2-4 cameras. A Makefile with a for loop achieves the same result in 10 lines vs 50+ lines of Ansible YAML.

## Suggested Follow-On Work

Items identified during planning that fall outside current scope.

* WI-01: Cloudflare Tunnel integration — Remote access to dashboard from outside LAN (low priority)
  * Source: Research document, rejected for v1
  * Dependency: Phase 4 dashboard must be complete

* WI-02: Training data export pipeline — Export labeled frames for fine-tuning custom model (medium priority)
  * Source: User requirement "keep all images for future training"
  * Dependency: Phase 3 DB schema + frame storage must be complete

* WI-03: Night mode / IR LED integration — Extend to 24hr monitoring (low priority)
  * Source: Research scope note "daytime only"
  * Dependency: Hardware (IR camera module + LEDs)

* WI-04: Multiple model support — Try different VLMs via llama-swap model switching (low priority)
  * Source: llama-swap supports multiple models
  * Dependency: Phase 3 inference pipeline must be complete

* WI-05: Self-hosted ntfy — Run ntfy on Pi 5 for privacy instead of ntfy.sh cloud (low priority)
  * Source: Research noted self-hosting option
  * Dependency: Phase 3 notifications must be complete

* WI-06: Battery low-power shutdown — Gracefully stop capture when battery <10% (medium priority)
  * Source: Derived from power budget analysis
  * Dependency: Phase 2 battery module must be complete

* WI-07: Web-based configuration UI — Edit motion threshold, heartbeat interval from dashboard (medium priority)
  * Source: Research MotionConfig dataclass
  * Dependency: Phase 4 dashboard must be complete

* WI-08: Pi 5 fan repair/replacement — Diagnose and fix thermal management hardware (high priority, non-software)
  * Source: Research "Potential Next Research" section
  * Dependency: None (hardware task)

* WI-09: Pi Zero W hardware smoke test — Validate `picamera2`, rfkill sudoers, PiSugar I2C, and actual capture loop on device (high priority)
  * Source: Phase 2 validation report
  * Dependency: Phase 2 camera package must be deployed to a Pi Zero W

* WI-10: PostgreSQL-backed Alembic validation — Run upgrade/downgrade against a real PostgreSQL instance (medium priority)
  * Source: Phase 3 validation report
  * Dependency: Phase 5 Docker Compose PostgreSQL setup

* WI-11: Browser-level dashboard smoke test — Verify CDN-loaded htmx/Chart.js behavior and visual layout with sample images (low priority)
  * Source: Phase 4 validation report
  * Dependency: Phase 4 dashboard and sample frame data

* WI-12: Base station installation Makefile targets — Add repeatable targets to install Pi 5 systemd units and enable the TTL timer (low priority)
  * Source: Phase 5 validation report
  * Dependency: Phase 5 deployment files

* WI-13: Production PostgreSQL credential handling — Move default Compose credentials into environment-specific overrides before field deployment (medium priority)
  * Source: Phase 5 validation report
  * Dependency: Phase 5 Docker Compose setup

* WI-14: CI-safe camera deployment dry-run target — Add a Makefile target that expands rsync/ssh commands without connecting (low priority)
  * Source: Phase 6 validation report
  * Dependency: Existing Makefile deployment target
