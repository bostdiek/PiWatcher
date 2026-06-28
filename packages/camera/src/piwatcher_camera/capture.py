"""Adaptive capture state machine for burst image collection."""

import enum
import time
from dataclasses import dataclass, field
from pathlib import Path


class CaptureState(enum.Enum):
    """Capture lifecycle states."""

    IDLE = "idle"
    CAPTURING = "capturing"
    COOLDOWN = "cooldown"
    TRANSFERRING = "transferring"


@dataclass
class CaptureSession:
    """Track motion-triggered burst capture timing and frame paths."""

    state: CaptureState = CaptureState.IDLE
    frames: list[Path] = field(default_factory=list)
    start_time: float = 0.0
    last_motion_time: float = 0.0
    cooldown_start: float = 0.0
    last_frame_time: float = 0.0
    min_duration: float = 60.0
    cooldown_duration: float = 5.0
    fps: float = 2.0
    _finished_frames: list[Path] = field(default_factory=list, init=False, repr=False)

    def start(self, now: float | None = None) -> None:
        """Start a new capture session."""
        current_time = time.time() if now is None else now
        self.state = CaptureState.CAPTURING
        self.frames = []
        self.start_time = current_time
        self.last_motion_time = current_time
        self.cooldown_start = 0.0
        self.last_frame_time = 0.0
        self._finished_frames = []

    def on_frame_captured(self, path: Path, now: float | None = None) -> None:
        """Record a captured frame path."""
        self.frames.append(path)
        self.last_frame_time = time.time() if now is None else now

    def on_motion(self, now: float | None = None) -> None:
        """Record motion and restart capture if needed."""
        current_time = time.time() if now is None else now
        if self.state is CaptureState.IDLE:
            self.start(current_time)
            return

        self.last_motion_time = current_time
        if self.state is CaptureState.COOLDOWN:
            self.state = CaptureState.CAPTURING
            self.cooldown_start = 0.0

    def tick(self, now: float | None = None) -> CaptureState:
        """Advance time-based transitions and return the current state."""
        current_time = time.time() if now is None else now
        if self.state is CaptureState.CAPTURING:
            elapsed = current_time - self.start_time
            quiet = current_time - self.last_motion_time
            if elapsed >= self.min_duration and quiet >= self.cooldown_duration:
                self.state = CaptureState.COOLDOWN
                self.cooldown_start = current_time
        elif self.state is CaptureState.COOLDOWN:
            if current_time - self.last_motion_time < self.cooldown_duration:
                self.state = CaptureState.CAPTURING
                self.cooldown_start = 0.0
            elif current_time - self.cooldown_start >= self.cooldown_duration:
                self._finished_frames = list(self.frames)
                self.state = CaptureState.TRANSFERRING

        return self.state

    def should_capture_frame(self, now: float | None = None) -> bool:
        """Return True when the capture rate allows another frame."""
        if self.state is not CaptureState.CAPTURING:
            return False
        if self.fps <= 0:
            return False

        current_time = time.time() if now is None else now
        interval = 1.0 / self.fps
        return self.last_frame_time == 0.0 or current_time - self.last_frame_time >= interval

    def finish(self) -> list[Path]:
        """Return accumulated frame paths and reset to idle."""
        frames = list(self._finished_frames or self.frames)
        self.state = CaptureState.IDLE
        self.frames = []
        self.start_time = 0.0
        self.last_motion_time = 0.0
        self.cooldown_start = 0.0
        self.last_frame_time = 0.0
        self._finished_frames = []
        return frames
