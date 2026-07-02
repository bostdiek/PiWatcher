"""Main PiWatcher camera loop for motion detection, capture, and upload."""

import logging
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from .battery import get_battery_level
from .capture import CaptureSession, CaptureState
from .config import CameraConfig, load_config
from .heartbeat import HeartbeatManager
from .motion import detect_motion
from .queue import EventBundle, create_event_bundle, load_due_event_bundles
from .transfer import upload_event, upload_event_result, wifi_off, wifi_on

logger = logging.getLogger("piwatcher")
_shutdown_requested = False


class Camera(Protocol):
    """Camera operations used by the watcher loop."""

    def capture_array(self, name: str) -> NDArray[np.integer]: ...

    def capture_file(self, path: str, *, name: str) -> None: ...


class HeartbeatLike(Protocol):
    """Minimal heartbeat interface used by transfer/drain helpers."""

    def send(self, battery_pct: int | None = None) -> bool: ...


def setup_logging() -> None:
    """Configure camera runtime logging."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def request_shutdown(_signum: int, _frame: object) -> None:
    """Signal handler that asks the main loop to stop."""
    global _shutdown_requested
    _shutdown_requested = True


def main() -> int:
    """Run the camera watcher until stopped by systemd or the user."""
    setup_logging()
    config = load_config()
    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)

    from picamera2 import Picamera2  # ty: ignore[unresolved-import]

    picam = Picamera2()
    camera_config = picam.create_still_configuration(
        main={"size": (config.main_width, config.main_height), "format": "RGB888"},
        lores={"size": (config.lores_width, config.lores_height), "format": "YUV420"},
    )
    picam.configure(camera_config)
    picam.start()

    try:
        run_loop(picam, config)
    finally:
        picam.stop()

    return 0


def run_loop(camera: Camera, config: CameraConfig) -> None:
    """Coordinate motion checks, capture sessions, transfers, and heartbeat sends."""
    startup_time = time.monotonic()
    if config.wifi_power_save:
        logger.info(
            "keeping WiFi on for %.0f seconds after startup",
            config.wifi_startup_grace_seconds,
        )
        wifi_on()
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
        frame_queue_dir=config.frame_queue_dir,
        wifi_power_save=config.wifi_power_save,
    )
    previous_frame: NDArray[np.integer] | None = None
    active_bundle: EventBundle | None = None

    while not _shutdown_requested:
        current_frame = _capture_lores_gray(camera)
        motion_detected = False
        if previous_frame is not None:
            motion = detect_motion(
                current_frame,
                previous_frame,
                threshold=config.motion_threshold,
                min_changed_pct=config.min_changed_pct,
            )
            motion_detected = motion.detected
            logger.debug(
                "motion detected=%s changed_pct=%.2f mean_diff=%.2f",
                motion.detected,
                motion.changed_pct,
                motion.mean_diff,
            )

        previous_frame = current_frame
        if motion_detected:
            if session.state is CaptureState.IDLE:
                event_start = datetime.now(UTC)
                active_bundle = create_event_bundle(
                    frame_queue_dir=config.frame_queue_dir,
                    camera_id=config.camera_id,
                    event_start=event_start,
                )
                logger.info("motion detected, starting capture")
            session.on_motion()

        if session.should_capture_frame():
            frame_path = _capture_main_frame(camera, config.frame_queue_dir, active_bundle)
            session.on_frame_captured(frame_path)
            if active_bundle is not None:
                active_bundle.record_frame(frame_path)

        state = session.tick()
        if state is CaptureState.TRANSFERRING:
            frames = session.finish()
            if active_bundle is not None and frames:
                event_end = datetime.now(UTC)
                active_bundle.mark_ready(event_end=event_end)
            elif active_bundle is not None:
                active_bundle.delete()
            _transfer_frames(frames, config, heartbeat, active_bundle, startup_time)
            _drain_pending_bundles(config, heartbeat, startup_time)
            active_bundle = None

        if session.state is CaptureState.IDLE and heartbeat.is_due():
            battery_pct = get_battery_level()
            logger.info("sending standalone heartbeat")
            heartbeat.send_standalone(
                battery_pct,
                manage_wifi=_should_manage_wifi(config, startup_time),
            )
            _drain_pending_bundles(config, heartbeat, startup_time)

        time.sleep(0.1)


def _capture_lores_gray(camera: Camera) -> NDArray[np.integer]:
    frame = camera.capture_array("lores")
    if frame.ndim == 2:
        return frame
    return frame[:, :, 0]


def _capture_main_frame(
    camera: Camera,
    frame_queue_dir: Path,
    bundle: EventBundle | None,
) -> Path:
    if bundle is not None:
        path = bundle.allocate_frame_path()
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        frame_queue_dir.mkdir(parents=True, exist_ok=True)
        path = frame_queue_dir / f"frame_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.jpg"
    camera.capture_file(str(path), name="main")
    return path


def _transfer_frames(
    frames: list[Path],
    config: CameraConfig,
    heartbeat: HeartbeatLike,
    bundle: EventBundle | None,
    startup_time: float,
) -> None:
    if not frames:
        return

    battery_pct = get_battery_level()
    logger.info("uploading %d captured frames", len(frames))
    manage_wifi = _should_manage_wifi(config, startup_time)
    if manage_wifi:
        wifi_on()
    try:
        uploaded = upload_event(
            frames=frames,
            camera_id=config.camera_id,
            server_url=config.server_url,
            api_key=config.api_key,
            battery_pct=battery_pct,
            event_start=bundle.event_start if bundle is not None else None,
            event_end=bundle.event_end if bundle is not None else None,
            camera_event_id=bundle.event_id if bundle is not None else None,
        )
        if uploaded:
            heartbeat.send(battery_pct)
            if bundle is not None:
                bundle.delete()
            else:
                for frame in frames:
                    frame.unlink(missing_ok=True)
        else:
            logger.warning("upload failed; leaving %d frames queued", len(frames))
    finally:
        if manage_wifi:
            wifi_off()


def _drain_pending_bundles(
    config: CameraConfig,
    heartbeat: HeartbeatLike,
    startup_time: float,
) -> None:
    """Drain due durable bundles during idle windows with configured limits."""
    max_events = max(0, config.queue_drain_max_events)
    max_seconds = max(0, config.queue_drain_max_seconds)
    if max_events == 0 or max_seconds == 0:
        return

    started = time.monotonic()
    drained = 0
    while drained < max_events and (time.monotonic() - started) < max_seconds:
        due_bundles = load_due_event_bundles(
            config.frame_queue_dir,
            lease_seconds=config.queue_upload_lease_seconds,
        )
        if not due_bundles:
            return

        bundle = due_bundles[0]
        frame_paths = [path for path in bundle.frame_paths() if path.exists()]
        if not frame_paths:
            bundle.mark_terminal_failure(error_message="bundle has no uploadable frames")
            drained += 1
            continue

        bundle.mark_uploading()
        manage_wifi = _should_manage_wifi(config, startup_time)
        if manage_wifi:
            wifi_on()
        try:
            battery_pct = get_battery_level()
            attempt = upload_event_result(
                frames=frame_paths,
                camera_id=config.camera_id,
                server_url=config.server_url,
                api_key=config.api_key,
                battery_pct=battery_pct,
                event_start=bundle.event_start,
                event_end=bundle.event_end,
                camera_event_id=bundle.event_id,
            )
            if attempt.success:
                heartbeat.send(battery_pct)
                bundle.mark_uploaded()
                bundle.delete()
            else:
                classification = attempt.classification
                if classification is None or classification.retryable:
                    bundle.mark_retryable_failure(
                        error_message=(
                            classification.reason
                            if classification is not None
                            else "upload returned unsuccessful status"
                        ),
                        retry_after_seconds=_retry_delay_seconds(config, bundle.attempt_count),
                    )
                else:
                    bundle.mark_terminal_failure(error_message=classification.reason)
        finally:
            if manage_wifi:
                wifi_off()
        drained += 1


def _retry_delay_seconds(config: CameraConfig, attempt_count: int) -> int:
    """Compute bounded exponential backoff for queue drain retries."""
    initial = max(1, config.queue_retry_initial_seconds)
    maximum = max(initial, config.queue_retry_max_seconds)
    exponent = max(0, attempt_count - 1)
    return min(maximum, initial * (2**exponent))


def _should_manage_wifi(
    config: CameraConfig,
    startup_time: float,
    now: float | None = None,
) -> bool:
    if not config.wifi_power_save:
        return False
    current_time = time.monotonic() if now is None else now
    return current_time - startup_time >= config.wifi_startup_grace_seconds


if __name__ == "__main__":
    sys.exit(main())
