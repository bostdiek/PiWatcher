<!-- markdownlint-disable-file -->
# Implementation Details: PiWatcher Architecture Redesign

## Context Reference

Sources: .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md, conversation decisions (heartbeat, monitoring, deployment, tooling)

## Implementation Phase 0: Commit & Clear Repo

<!-- parallelizable: false -->

### Step 0.1: Commit planning artifacts

Stage and commit the `.copilot-tracking/` directory so the research and planning work is preserved in git history before any code changes.

```bash
git add .copilot-tracking/
git commit -m "docs: add architecture research and implementation plan"
```

Files:
* .copilot-tracking/ - All research, plans, details, and logs

Success criteria:
* Planning artifacts are in git history
* Working tree is clean for .copilot-tracking/

Dependencies:
* None (first step)

### Step 0.2: Remove old code and commit

Remove all legacy code in a single commit. This preserves the old architecture in git history while providing a clean slate for the new implementation.

```bash
git rm -r piwatcher/ piwatcher.egg-info/ test/ tmp/ generate_diffs.sh pyproject.toml
git commit -m "chore: remove legacy RTSP architecture for clean slate redesign"
```

Remove:
* `piwatcher/` - Old base + camera packages (Poetry-based RTSP architecture)
* `piwatcher.egg-info/` - Build artifact from old package
* `test/` - Empty old test directory
* `tmp/` - Temporary diff files
* `generate_diffs.sh` - No longer needed
* `pyproject.toml` - Old Poetry root (will be replaced by uv workspace)

Keep:
* `LICENSE` - Unchanged
* `README.md` - Will be rewritten later but keep for continuity
* `.copilot-tracking/` - Planning files (just committed)

Files:
* Remove all listed above

Success criteria:
* Repo contains only LICENSE, README.md, and .copilot-tracking/
* Full old code is accessible via `git log` / `git show`
* Clean working tree ready for new scaffold

Dependencies:
* Step 0.1 (planning artifacts committed first)

### Step 0.3: Update pre-commit hooks for redesign tooling

Replace the old Python formatting and linting hooks with the redesign tooling used by the uv workspace.

Remove:
* black hook
* isort hook
* flake8 hook

Add:
* ruff check via `uv run ruff check --fix`
* ruff format via `uv run ruff format`
* ty type checking via `uv run ty check`

Files:
* .pre-commit-config.yaml - Development hook configuration

Success criteria:
* `pre-commit validate-config` passes
* `.pre-commit-config.yaml` validates with the `check-yaml` hook

Dependencies:
* Step 0.2 (legacy Poetry tooling removed first)

## Implementation Phase 1: Project Scaffold

<!-- parallelizable: false -->

### Step 1.1: Create uv workspace root pyproject.toml

Create the uv workspace configuration as the new project root.

```toml
[project]
name = "piwatcher"
version = "0.1.0"
description = "Wildlife camera system with Pi Zero W cameras and Pi 5 AI inference"
requires-python = ">=3.11"
readme = "README.md"
license = "MIT"

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv]
dev-dependencies = [
    "ruff>=0.11",
    "ty>=0.0.1a1",
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",  # FastAPI test client
    "pytest-cov>=6.0",
]
```

Files:
* pyproject.toml - Replace entirely with uv workspace config

Success criteria:
* `uv sync` resolves without errors
* Workspace members are discovered

Dependencies:
* None (first step)

### Step 1.2: Create packages/camera/ package structure

Minimal camera package with only the dependencies that will run on Pi Zero W. picamera2 is installed via apt (not pip) so it's not listed as a dependency.

```toml
# packages/camera/pyproject.toml
[project]
name = "piwatcher-camera"
version = "0.1.0"
description = "PiWatcher camera motion detection and capture"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "python-dotenv>=1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Directory structure:
```
packages/camera/
├── pyproject.toml
├── src/
│   └── piwatcher_camera/
│       └── __init__.py
└── tests/
    └── __init__.py
```

Files:
* packages/camera/pyproject.toml - Package metadata and minimal deps
* packages/camera/src/piwatcher_camera/__init__.py - Package init (version only)
* packages/camera/tests/__init__.py - Test package init

Success criteria:
* Package is discovered by uv workspace
* `uv run --package piwatcher-camera python -c "import piwatcher_camera"` works

Dependencies:
* Step 1.1 (workspace root must exist)

### Step 1.3: Create packages/base/ package structure

Base station server package with all Pi 5 dependencies.

```toml
# packages/base/pyproject.toml
[project]
name = "piwatcher-base"
version = "0.1.0"
description = "PiWatcher base station server with AI inference"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "pydantic-ai>=0.1",
    "jinja2>=3.1",
    "python-multipart>=0.0.18",
    "httpx>=0.27",
    "aiofiles>=24.1",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project.scripts]
piwatcher-server = "piwatcher_base.main:run"
```

Directory structure:
```
packages/base/
├── pyproject.toml
├── src/
│   └── piwatcher_base/
│       ├── __init__.py
│       ├── routes/
│       │   └── __init__.py
│       └── templates/
│           └── .gitkeep
├── alembic/
│   └── .gitkeep
└── tests/
    └── __init__.py
```

Files:
* packages/base/pyproject.toml - Full server dependency list
* packages/base/src/piwatcher_base/__init__.py - Package init
* packages/base/src/piwatcher_base/routes/__init__.py - Routes subpackage
* packages/base/src/piwatcher_base/templates/.gitkeep - Template directory placeholder
* packages/base/alembic/.gitkeep - Alembic directory placeholder
* packages/base/tests/__init__.py - Test package init

Success criteria:
* Package resolves all dependencies via `uv sync`
* `uv run --package piwatcher-base python -c "import piwatcher_base"` works

Dependencies:
* Step 1.1 (workspace root must exist)

### Step 1.4: Create Makefile with deployment targets

```makefile
# Makefile — PiWatcher development and deployment
.PHONY: lint typecheck test update-cameras setup-camera

# Configuration
CAMERAS ?= feeder-cam.local pond-cam.local
CAMERA_SRC := packages/camera/src/piwatcher_camera/
CAMERA_DEST := ~/piwatcher/
CAMERA_USER ?= pi
CAMERA_SERVICE := piwatcher-camera

# Development
lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run ty check

test:
	uv run pytest

test-cov:
	uv run pytest --cov=packages/camera/src --cov=packages/base/src --cov-report=term-missing

# Deployment
update-cameras:
	@for cam in $(CAMERAS); do \
		echo ">>> Deploying to $$cam..."; \
		rsync -avz --delete \
			$(CAMERA_SRC) \
			$(CAMERA_USER)@$$cam:$(CAMERA_DEST); \
		rsync -avz \
			packages/camera/.env.camera \
			$(CAMERA_USER)@$$cam:$(CAMERA_DEST).env; \
		ssh $(CAMERA_USER)@$$cam "sudo systemctl restart $(CAMERA_SERVICE)"; \
		echo ">>> $$cam updated."; \
	done

# First-time camera setup (run once per new Pi Zero)
setup-camera:
	@if [ -z "$(CAM)" ]; then echo "Usage: make setup-camera CAM=feeder-cam.local"; exit 1; fi
	scp deploy/setup-camera.sh $(CAMERA_USER)@$(CAM):~/setup-camera.sh
	ssh $(CAMERA_USER)@$(CAM) "chmod +x ~/setup-camera.sh && sudo ~/setup-camera.sh"
```

Files:
* Makefile - Development and deployment automation

Success criteria:
* `make lint` runs ruff
* `make test` runs pytest
* `make update-cameras` performs rsync (verifiable with --dry-run)

Dependencies:
* Steps 1.1-1.3 (packages must exist for lint/test targets)

### Step 1.5: Create configuration files

**.env.example** (root — Pi 5 server):
```env
# PiWatcher Base Station Configuration
PIWATCHER_API_KEY=change-me-use-python-c-import-secrets-print-secrets-token-hex-32
DATABASE_URL=postgresql+asyncpg://piwatcher:piwatcher@localhost:5432/piwatcher
FRAME_STORAGE_PATH=/mnt/nvme/piwatcher/frames
LLAMA_SWAP_URL=http://localhost:8080/v1
LLAMA_SWAP_MODEL=lfm2-vl-450m
NTFY_TOPIC=piwatcher
NTFY_URL=https://ntfy.sh
MAX_INFERENCE_TEMP_C=72.0
COOLDOWN_TEMP_C=60.0
INFERENCE_GAP_SECONDS=15
HEARTBEAT_TTL_DAYS=90
```

**packages/camera/.env.example**:
```env
# PiWatcher Camera Configuration
CAMERA_ID=change-me
SERVER_URL=http://pi5.local:8000
PIWATCHER_API_KEY=change-me-match-server
MOTION_THRESHOLD=7.0
MIN_CHANGED_PCT=2.0
CAPTURE_FPS=2.0
CAPTURE_MIN_DURATION=60.0
COOLDOWN_SECONDS=5.0
HEARTBEAT_INTERVAL=900
LORES_WIDTH=160
LORES_HEIGHT=120
MAIN_WIDTH=1024
MAIN_HEIGHT=1024
```

**.gitignore**:
```
# Environments
.env
*.env.camera

# uv
.venv/
uv.lock

# Python
__pycache__/
*.egg-info/
dist/
build/
```

**ruff.toml**:
```toml
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "TCH"]

[lint.isort]
known-first-party = ["piwatcher_camera", "piwatcher_base"]
```

Files:
* .env.example - Server environment template
* packages/camera/.env.example - Camera environment template
* .gitignore - Updated ignore patterns
* ruff.toml - Linter configuration

Success criteria:
* .env files document all configurable parameters
* ruff.toml validates with `ruff check --config ruff.toml`

Dependencies:
* Steps 1.1-1.3

### Step 1.6: Validate scaffold

Run validation commands to ensure the workspace is properly configured.

Commands:
* `uv sync` - Verify all dependencies resolve
* `uv run ruff check .` - Verify ruff config works (expect no files to lint yet)
* `uv run python -c "import piwatcher_camera; import piwatcher_base"` - Verify imports

Success criteria:
* All commands pass with zero errors

Dependencies:
* Steps 1.1-1.6

## Implementation Phase 2: Camera Package

<!-- parallelizable: true -->

### Step 2.1: Implement motion detection module (motion.py)

Pure NumPy frame differencing on lores stream. No OpenCV dependency.

```python
# packages/camera/src/piwatcher_camera/motion.py
"""Frame differencing motion detection using NumPy on lores stream."""
import numpy as np
from dataclasses import dataclass

@dataclass
class MotionResult:
    detected: bool
    changed_pct: float
    mean_diff: float

def detect_motion(
    current_frame: np.ndarray,
    previous_frame: np.ndarray,
    threshold: float = 7.0,
    min_changed_pct: float = 2.0,
) -> MotionResult:
    """Compare two grayscale lores frames for motion.

    Args:
        current_frame: Current lores frame (H, W) uint8
        previous_frame: Previous lores frame (H, W) uint8
        threshold: Per-pixel difference threshold
        min_changed_pct: Minimum percentage of changed pixels to trigger

    Returns:
        MotionResult with detection status and metrics
    """
    diff = np.abs(current_frame.astype(np.int16) - previous_frame.astype(np.int16))
    changed_pixels = np.sum(diff > threshold)
    total_pixels = diff.size
    changed_pct = (changed_pixels / total_pixels) * 100.0
    mean_diff = float(np.mean(diff))

    return MotionResult(
        detected=changed_pct >= min_changed_pct,
        changed_pct=changed_pct,
        mean_diff=mean_diff,
    )
```

Files:
* packages/camera/src/piwatcher_camera/motion.py - Motion detection logic

Success criteria:
* Function accepts two NumPy arrays, returns MotionResult
* No OpenCV or picamera2 dependency (pure NumPy)
* Testable without hardware

Context references:
* .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 101-108) - lores stream config
* .copilot-tracking/research/subagents/2026-06-27/pi-zero-architecture-research.md - frame differencing approach

Dependencies:
* Step 1.2 (camera package must exist)

### Step 2.2: Implement capture state machine (capture.py)

State machine: IDLE → CAPTURING → COOLDOWN → TRANSFERRING → IDLE

```python
# packages/camera/src/piwatcher_camera/capture.py
"""Adaptive capture state machine for burst image collection."""
import enum
import time
from dataclasses import dataclass, field
from pathlib import Path

class CaptureState(enum.Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    COOLDOWN = "cooldown"
    TRANSFERRING = "transferring"

@dataclass
class CaptureSession:
    state: CaptureState = CaptureState.IDLE
    frames: list[Path] = field(default_factory=list)
    start_time: float = 0.0
    last_motion_time: float = 0.0
    cooldown_start: float = 0.0

    # Config
    min_duration: float = 60.0
    cooldown_duration: float = 5.0
    fps: float = 2.0

    def start(self) -> None: ...
    def on_frame_captured(self, path: Path) -> None: ...
    def on_motion(self) -> None: ...
    def tick(self) -> CaptureState: ...
    def should_capture_frame(self) -> bool: ...
    def finish(self) -> list[Path]: ...
```

The state machine tracks:
- Minimum 60s capture duration
- 5s cooldown after last motion (resets if motion resumes)
- Frame timing for 2fps rate limiting
- Returns accumulated frame paths when transitioning to TRANSFERRING

Files:
* packages/camera/src/piwatcher_camera/capture.py - Capture state machine

Success criteria:
* State transitions follow: IDLE → CAPTURING → COOLDOWN → TRANSFERRING → IDLE
* Cooldown resets on new motion
* Minimum duration enforced
* Testable without hardware (time-based logic only)

Context references:
* .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 73-88) - Adaptive capture state machine

Dependencies:
* Step 1.2

### Step 2.3: Implement network transfer module (transfer.py)

Handles WiFi toggling (rfkill) and batch HTTP upload to base station.

```python
# packages/camera/src/piwatcher_camera/transfer.py
"""WiFi management and frame batch upload to base station."""
import subprocess
import time
from pathlib import Path

def wifi_on() -> None:
    """Enable WiFi radio via rfkill."""
    subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
    # Wait for association
    time.sleep(5)

def wifi_off() -> None:
    """Disable WiFi radio via rfkill."""
    subprocess.run(["sudo", "rfkill", "block", "wifi"], check=True)

def upload_event(
    frames: list[Path],
    camera_id: str,
    server_url: str,
    api_key: str,
    battery_pct: int | None = None,
) -> bool:
    """Upload captured frames as multipart POST to base station.

    Returns True on success, False on failure (frames kept for retry).
    """
    ...
```

Upload strategy:
- WiFi ON → wait for association (5s) → POST multipart with all frames → WiFi OFF
- On failure: keep frames in queue, retry on next event or heartbeat
- Includes camera_id, event timestamp, battery_pct in form fields

Files:
* packages/camera/src/piwatcher_camera/transfer.py - WiFi + upload logic

Success criteria:
* WiFi toggle via subprocess (rfkill)
* Multipart POST with bearer auth header
* Failure returns False (frames preserved)
* Retry queue for failed uploads

Context references:
* .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 195-210) - WiFi toggling approach
* .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 220-240) - Auth token pattern

Dependencies:
* Step 1.2

### Step 2.4: Implement battery monitor (battery.py)

I2C interface to PiSugar S for battery percentage and charging status.

```python
# packages/camera/src/piwatcher_camera/battery.py
"""PiSugar S battery monitor via I2C."""

PISUGAR_I2C_ADDR = 0x57  # PiSugar S I2C address

def get_battery_level() -> int | None:
    """Read battery percentage from PiSugar S via I2C.

    Returns percentage (0-100) or None if PiSugar not available.
    """
    try:
        # SMBus read from PiSugar S register
        ...
    except (OSError, FileNotFoundError):
        return None

def is_charging() -> bool | None:
    """Check if battery is currently charging."""
    ...
```

Graceful fallback: returns None if I2C not available (development without hardware).

Files:
* packages/camera/src/piwatcher_camera/battery.py - PiSugar I2C battery reading

Success criteria:
* Returns int percentage or None on failure
* No crash if I2C bus unavailable
* Testable with mock (no hardware needed)

Dependencies:
* Step 1.2

### Step 2.5: Implement heartbeat module (heartbeat.py)

Periodic heartbeat to base station, piggybacks on event uploads when WiFi is already active.

```python
# packages/camera/src/piwatcher_camera/heartbeat.py
"""Periodic heartbeat reporting to base station."""
import time
import requests

class HeartbeatManager:
    def __init__(self, interval: int, server_url: str, api_key: str, camera_id: str):
        self.interval = interval  # seconds (default 900 = 15 min)
        self.server_url = server_url
        self.api_key = api_key
        self.camera_id = camera_id
        self.last_sent: float = 0.0

    def is_due(self) -> bool:
        """Check if heartbeat interval has elapsed."""
        return (time.time() - self.last_sent) >= self.interval

    def send(self, battery_pct: int | None = None) -> bool:
        """Send heartbeat to base station. Called when WiFi is active."""
        ...

    def piggyback(self, battery_pct: int | None = None) -> None:
        """Record that heartbeat was sent alongside an event upload."""
        self.last_sent = time.time()
```

Key behavior:
- If WiFi is already on (during event upload), piggyback heartbeat
- If interval elapsed and no events, trigger standalone WiFi ON → heartbeat → WiFi OFF
- Reports: camera_id, battery_pct, uptime, timestamp

Files:
* packages/camera/src/piwatcher_camera/heartbeat.py - Heartbeat timing and sending

Success criteria:
* 15-minute default interval (configurable)
* Piggyback resets timer without extra WiFi cycle
* Standalone heartbeat triggers WiFi toggle if needed

Dependencies:
* Step 2.3 (uses wifi_on/wifi_off from transfer module)

### Step 2.6: Implement main watcher loop (watcher.py)

Main entry point that orchestrates all camera modules.

```python
# packages/camera/src/piwatcher_camera/watcher.py
"""Main PiWatcher camera loop — motion detection, capture, upload."""
import logging
import signal
import sys

from .config import load_config
from .motion import detect_motion
from .capture import CaptureSession, CaptureState
from .transfer import wifi_on, wifi_off, upload_event
from .battery import get_battery_level
from .heartbeat import HeartbeatManager

logger = logging.getLogger("piwatcher")

def main() -> None:
    """Main watcher loop."""
    config = load_config()
    setup_logging(config)

    # picamera2 setup (only import at runtime — not available on Mac)
    from picamera2 import Picamera2

    picam = Picamera2()
    # Configure dual-stream: lores for motion, main for capture
    camera_config = picam.create_still_configuration(
        main={"size": (config.main_width, config.main_height), "format": "RGB888"},
        lores={"size": (config.lores_width, config.lores_height), "format": "YUV420"},
    )
    picam.configure(camera_config)
    picam.start()

    session = CaptureSession(
        min_duration=config.capture_min_duration,
        cooldown_duration=config.cooldown_seconds,
        fps=config.capture_fps,
    )
    heartbeat = HeartbeatManager(
        interval=config.heartbeat_interval,
        server_url=config.server_url,
        api_key=config.api_key,
        camera_id=config.camera_id,
    )

    previous_frame = None
    # Main loop: check motion, manage state, handle heartbeat
    ...
```

Loop structure:
1. Grab lores frame
2. If IDLE: check motion → transition to CAPTURING
3. If CAPTURING: grab main frame, save JPEG, check motion continues
4. If COOLDOWN: check timer, reset if motion resumes
5. If TRANSFERRING: wifi_on, upload, piggyback heartbeat, wifi_off
6. Check heartbeat timer (standalone send if due and no recent event)

Files:
* packages/camera/src/piwatcher_camera/watcher.py - Main orchestration loop

Success criteria:
* Orchestrates all modules correctly
* Graceful shutdown on SIGTERM (systemd stop)
* Logging at INFO level for events, DEBUG for frame-by-frame

Dependencies:
* Steps 2.1-2.5 (all camera modules)

### Step 2.7: Implement config loading (config.py)

Load configuration from .env file using python-dotenv.

```python
# packages/camera/src/piwatcher_camera/config.py
"""Camera configuration from environment variables."""
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

@dataclass
class CameraConfig:
    camera_id: str
    server_url: str
    api_key: str
    motion_threshold: float = 7.0
    min_changed_pct: float = 2.0
    capture_fps: float = 2.0
    capture_min_duration: float = 60.0
    cooldown_seconds: float = 5.0
    heartbeat_interval: int = 900  # 15 minutes
    lores_width: int = 160
    lores_height: int = 120
    main_width: int = 1024
    main_height: int = 1024
    frame_queue_dir: Path = Path("/tmp/piwatcher/frames")

def load_config() -> CameraConfig:
    """Load config from .env file and environment."""
    load_dotenv()
    return CameraConfig(
        camera_id=os.environ["CAMERA_ID"],
        server_url=os.environ["SERVER_URL"],
        api_key=os.environ["PIWATCHER_API_KEY"],
        motion_threshold=float(os.getenv("MOTION_THRESHOLD", "7.0")),
        ...
    )
```

Files:
* packages/camera/src/piwatcher_camera/config.py - Config dataclass + loader

Success criteria:
* Required vars (CAMERA_ID, SERVER_URL, PIWATCHER_API_KEY) raise clear error if missing
* Optional vars have sensible defaults
* Frame queue directory created if not exists

Dependencies:
* Step 1.2

### Step 2.8: Create systemd unit file and setup script

**systemd unit** (`deploy/piwatcher-camera.service`):
```ini
[Unit]
Description=PiWatcher Camera Service
After=local-fs.target

[Service]
Type=simple
User=pi
Group=video
ExecStart=/usr/bin/python3 -m piwatcher_camera.watcher
WorkingDirectory=/home/pi/piwatcher
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**Setup script** (`deploy/setup-camera.sh`):
- Install apt dependencies (python3-picamera2, python3-numpy, python3-requests, python3-dotenv)
- Configure sudoers for rfkill
- Install systemd service
- Create frame queue directory
- Enable and start service

Files:
* deploy/piwatcher-camera.service - systemd unit file
* deploy/setup-camera.sh - First-time Pi Zero setup script

Success criteria:
* Service auto-starts on boot
* Restarts on failure with 10s delay
* Runs as pi user with video group access

Dependencies:
* Step 2.6 (watcher must exist as entry point)

### Step 2.9: Write camera package tests

Test motion detection, capture state machine, and config loading without hardware.

```python
# packages/camera/tests/test_motion.py
def test_no_motion_identical_frames(): ...
def test_motion_detected_significant_change(): ...
def test_threshold_boundary(): ...

# packages/camera/tests/test_capture.py
def test_state_idle_to_capturing_on_motion(): ...
def test_cooldown_resets_on_new_motion(): ...
def test_minimum_duration_enforced(): ...
def test_finish_returns_frame_paths(): ...

# packages/camera/tests/test_config.py
def test_load_config_required_vars(monkeypatch): ...
def test_load_config_defaults(monkeypatch): ...
def test_missing_required_var_raises(): ...

# packages/camera/tests/test_heartbeat.py
def test_heartbeat_due_after_interval(): ...
def test_piggyback_resets_timer(): ...
```

Files:
* packages/camera/tests/test_motion.py - Motion detection unit tests
* packages/camera/tests/test_capture.py - State machine tests
* packages/camera/tests/test_config.py - Config loading tests
* packages/camera/tests/test_heartbeat.py - Heartbeat timing tests

Success criteria:
* All tests pass without picamera2 or Pi hardware
* Motion detection tested with synthetic NumPy arrays
* State machine tested with time mocking

Dependencies:
* Steps 2.1-2.7 (modules to test must exist)

## Implementation Phase 3: Base Station Server

<!-- parallelizable: true -->

### Step 3.1: Database schema + SQLAlchemy models (models.py)

```python
# packages/base/src/piwatcher_base/models.py
"""SQLAlchemy models for PiWatcher database."""
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(50), index=True)
    event_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    frame_count: Mapped[int] = mapped_column(Integer)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Classification results
    label: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    raw_classification: Mapped[dict | None] = mapped_column(JSONB)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    frames: Mapped[list["Frame"]] = relationship(back_populates="event")

class Frame(Base):
    __tablename__ = "frames"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    sequence_num: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    event: Mapped["Event"] = relationship(back_populates="frames")

class Heartbeat(Base):
    __tablename__ = "heartbeats"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[str] = mapped_column(String(50), index=True)
    battery_pct: Mapped[int | None] = mapped_column(Integer)
    uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Files:
* packages/base/src/piwatcher_base/models.py - All SQLAlchemy models

Success criteria:
* Models define events, frames, and heartbeats tables
* JSONB column for raw classification output
* Indexes on camera_id and created_at for queries

Dependencies:
* Step 1.3

### Step 3.2: Alembic setup + initial migration

```bash
cd packages/base
uv run alembic init alembic
```

Configure `alembic/env.py` to import models and use async engine. Create initial migration with `alembic revision --autogenerate -m "initial schema"`.

Files:
* packages/base/alembic.ini - Alembic configuration
* packages/base/alembic/env.py - Async migration environment
* packages/base/alembic/versions/001_initial_schema.py - First migration

Success criteria:
* `alembic upgrade head` creates all tables on fresh PostgreSQL
* `alembic downgrade base` cleanly removes all tables

Dependencies:
* Step 3.1 (models must exist for autogenerate)

### Step 3.3: FastAPI app with auth middleware (main.py)

```python
# packages/base/src/piwatcher_base/main.py
"""FastAPI application for PiWatcher base station."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .db import init_db
from .routes import events, heartbeat, dashboard

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="PiWatcher", lifespan=lifespan)

# Mount routes
app.include_router(events.router, prefix="/api")
app.include_router(heartbeat.router, prefix="/api")
app.include_router(dashboard.router)

def run():
    import uvicorn
    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

Auth dependency:
```python
# packages/base/src/piwatcher_base/auth.py
from fastapi import Depends, HTTPException, Header
from .config import get_settings

async def verify_api_key(authorization: str = Header(...)) -> None:
    settings = get_settings()
    expected = f"Bearer {settings.api_key}"
    if not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
```

Files:
* packages/base/src/piwatcher_base/main.py - FastAPI app + lifespan
* packages/base/src/piwatcher_base/auth.py - Bearer token verification

Success criteria:
* App starts with `uvicorn`
* All /api/ routes require bearer auth
* Dashboard routes are public (LAN access)
* Uses constant-time comparison for auth

Dependencies:
* Step 1.3

### Step 3.4: Event ingest endpoint (routes/events.py)

```python
# packages/base/src/piwatcher_base/routes/events.py
"""Event upload and query endpoints."""
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks
from ..auth import verify_api_key
from ..storage import store_frames
from ..inference import classify_event_background

router = APIRouter(tags=["events"])

@router.post("/events", dependencies=[Depends(verify_api_key)])
async def create_event(
    background_tasks: BackgroundTasks,
    camera_id: str = Form(...),
    event_start: str = Form(...),
    battery_pct: int | None = Form(None),
    frames: list[UploadFile] = File(...),
):
    """Receive frames from camera, store, and queue inference."""
    # 1. Store frames to NVMe
    # 2. Create Event record in DB
    # 3. Queue background inference task
    ...

@router.get("/events")
async def list_events(camera_id: str | None = None, limit: int = 50):
    """List events, optionally filtered by camera."""
    ...

@router.get("/events/{event_id}")
async def get_event(event_id: int):
    """Get event detail with classification results."""
    ...
```

Files:
* packages/base/src/piwatcher_base/routes/events.py - Event CRUD endpoints

Success criteria:
* POST accepts multipart with frames + metadata
* Frames stored to configured path on NVMe
* Background inference queued without blocking response
* GET endpoints support filtering and pagination

Dependencies:
* Steps 3.1, 3.3, 3.5 (models, app, storage)

### Step 3.5: Frame storage service (storage.py)

```python
# packages/base/src/piwatcher_base/storage.py
"""Frame file storage organized by date."""
from pathlib import Path
from datetime import datetime
from fastapi import UploadFile

async def store_frames(
    frames: list[UploadFile],
    camera_id: str,
    event_start: datetime,
    storage_path: Path,
) -> list[Path]:
    """Store uploaded frames to NVMe organized as YYYY/MM/DD/camera_id/event_timestamp/.

    Returns list of stored file paths.
    """
    date_dir = storage_path / event_start.strftime("%Y/%m/%d") / camera_id
    event_dir = date_dir / event_start.strftime("%H%M%S")
    event_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for i, frame in enumerate(frames):
        dest = event_dir / f"frame_{i:04d}.jpg"
        content = await frame.read()
        dest.write_bytes(content)
        paths.append(dest)
    return paths
```

Storage layout: `/mnt/nvme/piwatcher/frames/2026/06/27/feeder-cam/143201/frame_0000.jpg`

Files:
* packages/base/src/piwatcher_base/storage.py - Frame file management

Success criteria:
* Frames stored in date/camera/event hierarchy
* Returns paths for DB recording
* Directory creation is idempotent

Dependencies:
* Step 1.3

### Step 3.6: Inference pipeline with thermal management (inference.py)

```python
# packages/base/src/piwatcher_base/inference.py
"""PydanticAI + llama-swap inference with thermal management."""
import asyncio
import base64
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from typing import Literal

class WildlifeClassification(BaseModel):
    label: Literal[
        "deer", "bear", "coyote", "fox", "raccoon", "skunk",
        "rabbit", "squirrel", "bird", "turkey", "cat", "dog",
        "human", "vehicle", "unknown", "empty"
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    description: str = Field(max_length=200)

def get_cpu_temp() -> float:
    """Read Pi 5 CPU temperature from thermal zone."""
    temp_str = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
    return float(temp_str) / 1000.0

async def classify_event_background(event_id: int, frame_paths: list[Path]) -> None:
    """Classify sampled frames with thermal management.

    Samples 5 frames evenly spaced, waits between inference calls,
    pauses if temperature exceeds threshold.
    """
    ...
```

Key implementation:
- Sample 5 frames evenly across the event
- Check temperature before each call
- 15s gap between inference calls
- Pause if >72°C until <60°C
- Store best/majority classification in event record
- Use JSON schema response_format for constrained output

Files:
* packages/base/src/piwatcher_base/inference.py - Full inference pipeline

Success criteria:
* Samples frames rather than classifying all
* Thermal gating prevents throttling
* PydanticAI validates model output
* Results stored in events table JSONB column

Context references:
* .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 152-175) - Thermal management code
* .copilot-tracking/research/2026-06-27/piwatcher-architecture-redesign-research.md (Lines 440-470) - PydanticAI + classification model

Dependencies:
* Steps 3.1, 3.3 (models and app must exist)

### Step 3.7: Heartbeat endpoint + TTL cleanup (routes/heartbeat.py)

```python
# packages/base/src/piwatcher_base/routes/heartbeat.py
"""Heartbeat reception and health query endpoints."""
from fastapi import APIRouter, Depends
from ..auth import verify_api_key
from ..models import Heartbeat

router = APIRouter(tags=["heartbeat"])

@router.post("/heartbeat", dependencies=[Depends(verify_api_key)])
async def receive_heartbeat(camera_id: str, battery_pct: int | None = None, uptime: int | None = None):
    """Record heartbeat from camera."""
    ...

@router.get("/health/cameras")
async def camera_health():
    """Return last heartbeat and battery for each camera."""
    ...
```

TTL cleanup: scheduled DELETE of heartbeats older than 90 days. Implemented as either:
- pg_cron (if available): `DELETE FROM heartbeats WHERE created_at < now() - interval '90 days'`
- systemd timer running SQL via psql
- FastAPI startup task running daily

Files:
* packages/base/src/piwatcher_base/routes/heartbeat.py - Heartbeat endpoints

Success criteria:
* POST stores heartbeat with timestamp
* GET returns per-camera health summary (last seen, battery trend)
* TTL cleanup removes old heartbeats

Dependencies:
* Steps 3.1, 3.3

### Step 3.8: Push notifications via ntfy.sh (notifications.py)

```python
# packages/base/src/piwatcher_base/notifications.py
"""Push notifications via ntfy.sh."""
import httpx
from pathlib import Path

async def notify_detection(
    label: str,
    confidence: float,
    camera_id: str,
    thumbnail_path: Path | None = None,
    ntfy_url: str = "https://ntfy.sh",
    ntfy_topic: str = "piwatcher",
) -> None:
    """Send push notification with detection result."""
    async with httpx.AsyncClient() as client:
        headers = {"Title": f"{label} detected ({confidence:.0%})", "Tags": "camera"}
        if thumbnail_path and thumbnail_path.exists():
            # Attach image
            ...
        else:
            await client.post(
                f"{ntfy_url}/{ntfy_topic}",
                content=f"{label} spotted on {camera_id}",
                headers=headers,
            )
```

Files:
* packages/base/src/piwatcher_base/notifications.py - ntfy.sh integration

Success criteria:
* Sends notification with label, confidence, camera
* Optional image attachment
* Non-blocking (doesn't fail event pipeline on notification error)

Dependencies:
* Step 1.3

### Step 3.9: Server config and DB connection (config.py, db.py)

```python
# packages/base/src/piwatcher_base/config.py
"""Server configuration via pydantic-settings."""
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    api_key: str
    database_url: str
    frame_storage_path: str = "/mnt/nvme/piwatcher/frames"
    llama_swap_url: str = "http://localhost:8080/v1"
    llama_swap_model: str = "lfm2-vl-450m"
    ntfy_topic: str = "piwatcher"
    ntfy_url: str = "https://ntfy.sh"
    max_inference_temp_c: float = 72.0
    cooldown_temp_c: float = 60.0
    inference_gap_seconds: int = 15
    heartbeat_ttl_days: int = 90

    model_config = {"env_prefix": "PIWATCHER_", "env_file": ".env"}

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# packages/base/src/piwatcher_base/db.py
"""Database connection and session management."""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .config import get_settings

engine = None
SessionLocal = None

async def init_db():
    global engine, SessionLocal
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session
```

Files:
* packages/base/src/piwatcher_base/config.py - Pydantic settings
* packages/base/src/piwatcher_base/db.py - Async DB engine + session

Success criteria:
* Settings loaded from environment with PIWATCHER_ prefix
* Async engine created on startup
* Session dependency for FastAPI routes

Dependencies:
* Step 1.3

### Step 3.10: Write server tests

```python
# packages/base/tests/test_events.py - Event endpoint integration tests
# packages/base/tests/test_inference.py - Inference pipeline tests (mocked llama-swap)
# packages/base/tests/test_auth.py - Auth middleware tests
# packages/base/tests/test_storage.py - Frame storage tests
# packages/base/tests/test_heartbeat.py - Heartbeat endpoint tests
# packages/base/tests/conftest.py - Shared fixtures (test DB, test client, mock settings)
```

Test approach:
- Use httpx AsyncClient with FastAPI TestClient
- SQLite in-memory for test DB (asyncpg not needed for tests)
- Mock llama-swap responses for inference tests
- Mock thermal readings

Files:
* packages/base/tests/conftest.py - Shared test fixtures
* packages/base/tests/test_events.py - Event endpoint tests
* packages/base/tests/test_inference.py - Inference tests
* packages/base/tests/test_auth.py - Auth tests
* packages/base/tests/test_storage.py - Storage tests
* packages/base/tests/test_heartbeat.py - Heartbeat tests

Success criteria:
* All tests pass without PostgreSQL or llama-swap running
* Auth tests verify token validation and rejection
* Storage tests verify directory creation and file writing

Dependencies:
* Steps 3.1-3.9

## Implementation Phase 4: Dashboard

<!-- parallelizable: false -->

### Step 4.1: Base template with TailwindCSS + htmx (base.html)

```html
<!-- packages/base/src/piwatcher_base/templates/base.html -->
<!DOCTYPE html>
<html>
<head>
    <title>PiWatcher - {% block title %}{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body class="bg-gray-900 text-gray-100">
    <nav><!-- Camera selector, nav links --></nav>
    {% block content %}{% endblock %}
</body>
</html>
```

Files:
* packages/base/src/piwatcher_base/templates/base.html - Layout template

Success criteria:
* TailwindCSS + htmx + Chart.js loaded from CDN
* Dark theme, responsive layout
* Navigation between pages

Dependencies:
* Step 3.3 (FastAPI app with Jinja2 configured)

### Step 4.2: Events list page with real-time updates (events.html)

Grid of recent events with labels, thumbnails, timestamps. htmx polling or WebSocket for new events.

Files:
* packages/base/src/piwatcher_base/templates/events.html - Events list
* packages/base/src/piwatcher_base/templates/partials/event_card.html - Single event card partial

Success criteria:
* Shows recent events with thumbnail, label, confidence, camera
* Auto-updates via htmx (hx-trigger="every 10s" or WebSocket)
* Filterable by camera_id

Dependencies:
* Step 4.1, Step 3.4

### Step 4.3: Event detail page with frame gallery (event_detail.html)

Full frame gallery for a single event with classification details.

Files:
* packages/base/src/piwatcher_base/templates/event_detail.html - Event detail with gallery

Success criteria:
* Shows all frames in grid/carousel
* Displays classification: label, confidence, description, raw JSON
* Links to frame files served as static

Dependencies:
* Step 4.1, Step 3.4

### Step 4.4: Camera health page with battery sparklines (health.html)

Per-camera health dashboard with battery level chart (Chart.js sparkline) and last-seen timestamps.

Files:
* packages/base/src/piwatcher_base/templates/health.html - Camera health dashboard

Success criteria:
* Chart.js sparkline showing battery % over last 24h per camera
* Last heartbeat timestamp with "X minutes ago" display
* Color coding: green (recent), yellow (>30 min), red (>2hr)

Dependencies:
* Step 4.1, Step 3.7

### Step 4.5: Dashboard route handlers (routes/dashboard.py)

```python
# packages/base/src/piwatcher_base/routes/dashboard.py
"""Dashboard HTML routes (no auth — LAN access)."""
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="templates")

@router.get("/")
async def index(request: Request): ...

@router.get("/events")
async def events_page(request: Request, camera_id: str | None = None): ...

@router.get("/events/{event_id}")
async def event_detail(request: Request, event_id: int): ...

@router.get("/health")
async def health_page(request: Request): ...
```

Files:
* packages/base/src/piwatcher_base/routes/dashboard.py - Dashboard routes

Success criteria:
* HTML responses for browser access
* No auth required (LAN-only dashboard)
* Passes query context to templates

Dependencies:
* Steps 4.1-4.4 (templates must exist)

### Step 4.6: WebSocket for real-time event stream

Optional: htmx WebSocket extension for live event updates on the events page.

Files:
* packages/base/src/piwatcher_base/routes/ws.py - WebSocket endpoint

Success criteria:
* New events broadcast to connected dashboard clients
* Graceful disconnect handling

Dependencies:
* Step 3.4 (event creation triggers broadcast)

## Implementation Phase 5: Deployment & Operations

<!-- parallelizable: false -->

### Step 5.1: Pi 5 systemd service for piwatcher-base

```ini
# deploy/piwatcher-base.service
[Unit]
Description=PiWatcher Base Station
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=pi
ExecStart=/home/pi/.local/bin/uv run --package piwatcher-base piwatcher-server
WorkingDirectory=/home/pi/PiWatcher
Restart=on-failure
RestartSec=10
EnvironmentFile=/home/pi/PiWatcher/.env

[Install]
WantedBy=multi-user.target
```

Files:
* deploy/piwatcher-base.service - Pi 5 systemd unit

Success criteria:
* Starts after PostgreSQL
* Reads .env for configuration
* Restarts on crash

Dependencies:
* Phase 3 complete

### Step 5.2: Docker Compose for PostgreSQL

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: piwatcher
      POSTGRES_PASSWORD: piwatcher
      POSTGRES_DB: piwatcher
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Files:
* docker-compose.yml - PostgreSQL service

Success criteria:
* `docker compose up -d` starts PostgreSQL
* Data persists across restarts
* Accessible on localhost:5432

Dependencies:
* None (can be created early)

### Step 5.3: Pi Zero setup script (deploy/setup-camera.sh)

One-time setup script run via `make setup-camera CAM=hostname`:
- Install apt deps (python3-picamera2, python3-numpy, python3-requests, python3-dotenv, python3-smbus)
- Configure sudoers for rfkill
- Create working directory
- Install systemd service
- Enable I2C for PiSugar

Files:
* deploy/setup-camera.sh - First-time Pi Zero provisioning

Success criteria:
* Idempotent (safe to run twice)
* All apt installs with --no-install-recommends
* Service enabled but not started (needs .env first)

Dependencies:
* Step 2.8 (systemd unit must exist)

### Step 5.4: Heartbeat TTL cron job

systemd timer that runs daily to purge old heartbeats:

```ini
# deploy/piwatcher-ttl.timer
[Unit]
Description=PiWatcher heartbeat TTL cleanup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

```ini
# deploy/piwatcher-ttl.service
[Unit]
Description=Delete old heartbeat records

[Service]
Type=oneshot
ExecStart=/usr/bin/psql -U piwatcher -d piwatcher -c "DELETE FROM heartbeats WHERE created_at < now() - interval '90 days';"
```

Files:
* deploy/piwatcher-ttl.timer - Timer unit
* deploy/piwatcher-ttl.service - Oneshot cleanup service

Success criteria:
* Runs daily
* Deletes heartbeats older than 90 days
* Logs deletion count

Dependencies:
* Step 3.7 (heartbeats table must exist)

### Step 5.5: Update README.md with setup instructions

Rewrite README.md with:
- Project overview and architecture diagram (ASCII)
- Prerequisites (hardware, software)
- Quick start: Mac development setup (`uv sync`, `make test`)
- Pi 5 setup: Docker Compose, Alembic migration, systemd service
- Pi Zero setup: `make setup-camera`, rsync deployment
- Configuration reference (all .env variables)
- Development workflow (lint, test, deploy)

Files:
* README.md - Complete project documentation

Success criteria:
* New user can set up full system following README
* All make targets documented
* Architecture diagram matches implementation

Dependencies:
* All previous phases

## Implementation Phase 6: Validation

<!-- parallelizable: false -->

### Step 6.1: Run full project validation

Execute all validation commands:
* `uv sync` - Verify dependencies resolve
* `uv run ruff check .` - Linting
* `uv run ruff format --check .` - Format check
* `uv run ty check` - Type checking
* `uv run pytest --cov` - Tests with coverage

### Step 6.2: Fix minor validation issues

Iterate on lint errors, type errors, and test failures. Apply fixes when straightforward.

### Step 6.3: Verify Makefile targets work

* `make lint` - Runs without error
* `make typecheck` - Passes
* `make test` - All green
* `make update-cameras CAMERAS=test.local` - Rsync command formed correctly (dry-run)

### Step 6.4: Report blocking issues

Document issues requiring:
* Pi hardware for integration testing
* PostgreSQL for migration testing
* llama-swap for inference testing
Provide deployment test steps for user.

## Dependencies

* Python 3.11+
* uv (development)
* ruff + ty (linting/typing — Mac only)
* PostgreSQL 16 (Docker on Pi 5)
* picamera2 (apt on Pi Zero — not a pip dependency)
* llama-swap + LFM2-VL-450M GGUF (pre-installed on Pi 5)

## Success Criteria

* Complete uv workspace with two packages resolving cleanly
* All tests pass (camera + base) without hardware
* Makefile automates lint, test, and deployment
* FastAPI server starts and serves dashboard + API
* Camera watcher deployable via rsync
