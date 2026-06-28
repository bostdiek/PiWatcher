# Pi Zero W Wildlife Camera Architecture Research

## Research Topics

1. picamera2 motion detection
2. Duty-cycle power management
3. WiFi toggling from Python
4. Auto-start on boot (systemd service)
5. Capture parameters for VL model
6. Motion detection configuration
7. Pi Zero W camera module options
8. HTTP POST of JPEG frames

---

## 1. picamera2 Motion Detection

### Overview

picamera2 is the libcamera-based replacement for the legacy picamera library. It works on all Raspberry Pi boards including Pi Zero W (though performance is limited on the BCM2835 single-core ARM11). Version 0.3.36 is the latest release.

### Dual-Stream Architecture (lores + main)

picamera2 supports simultaneous dual-stream capture — a low-resolution "lores" stream for motion detection and a high-resolution "main" stream for actual capture. This is the key to efficient motion detection on Pi Zero.

```python
from picamera2 import Picamera2

lsize = (320, 240)  # Low-res for motion detection
picam2 = Picamera2()
main = {"size": (1280, 720), "format": "RGB888"}
lores = {"size": lsize, "format": "YUV420"}
video_config = picam2.create_video_configuration(main, lores=lores)
picam2.configure(video_config)
picam2.start()
```

### Frame Differencing with NumPy (Low CPU)

The official motion detection example uses Mean Squared Error (MSE) between consecutive frames from the lores stream:

```python
import numpy as np

w, h = lsize
prev = None

while True:
    cur = picam2.capture_array("lores")[:h, :w]
    if prev is not None:
        mse = np.square(np.subtract(cur, prev)).mean()
        if mse > 7:  # Threshold
            print("Motion detected!", mse)
    prev = cur
```

**Key points:**
- Uses only the Y (luminance) channel from YUV420 format — the `[:h, :w]` slice extracts just the Y plane
- At 320x240, the frame is only 76,800 pixels — very fast even on Pi Zero's single ARM11 core
- MSE computation is vectorized via NumPy, reducing Python overhead
- No OpenCV dependency required for basic motion detection

### MappedArray for Zero-Copy Access

`MappedArray` provides direct access to camera buffers without copying:

```python
with picam2.captured_array("lores") as arr:
    # arr is a numpy array mapped directly to the camera buffer
    mse = np.square(np.subtract(arr[:h, :w], prev)).mean()
```

This avoids memory allocation on each frame, reducing GC pressure on the memory-constrained Pi Zero (512MB RAM).

### Circular Buffer / Pre-Motion Capture

picamera2 does not have a built-in circular buffer like the legacy picamera's `PiCameraCircularIO`. However, you can implement a simple ring buffer:

```python
from collections import deque

pre_frames = deque(maxlen=5)  # Keep last 5 frames before motion

while True:
    cur = picam2.capture_array("lores")[:h, :w]
    if prev is not None:
        mse = np.square(np.subtract(cur, prev)).mean()
        if mse > threshold:
            # Motion! Capture high-res frame
            frame = picam2.capture_array("main")
            # pre_frames contains frames before motion
            break
    pre_frames.append(cur)
    prev = cur
```

For still capture (our use case), this is less relevant since we just need to capture the current high-res frame when motion triggers.

### Resolution Recommendations

| Stream | Resolution | Purpose | Frame Size (YUV420) |
|--------|-----------|---------|-------------------|
| lores | 320x240 | Motion detection | ~115 KB |
| lores | 160x120 | Ultra-low-power motion | ~29 KB |
| main | 1280x720 | Capture for VL model | ~2.7 MB (RGB) |
| main | 640x480 | Reduced capture | ~900 KB (RGB) |

**Recommendation:** Use 320x240 lores for motion detection (good balance of sensitivity and CPU), and capture stills from the main stream at 640x480 or 1280x720 (to be downsized by the Pi 5).

### Still Capture API

For our wildlife camera, we want stills, not video:

```python
# Configure for still capture with lores motion stream
still_config = picam2.create_still_configuration(
    main={"size": (1280, 720), "format": "RGB888"},
    lores={"size": (320, 240), "format": "YUV420"}
)
picam2.configure(still_config)
picam2.start()

# When motion detected:
picam2.capture_file("capture.jpg")
# Or capture to memory:
image = picam2.capture_image("main")  # Returns PIL Image
```

---

## 2. Duty-Cycle Power Management

### Pi Zero W Power Consumption

From official Raspberry Pi documentation:

| State | Current Draw | Power (at 5V) |
|-------|-------------|---------------|
| Idle (no WiFi, no camera) | ~100 mA | ~0.5 W |
| Idle with WiFi | ~150 mA | ~0.75 W |
| Active (camera + processing) | ~200-250 mA | ~1.0-1.25 W |
| Boot (max) | ~200 mA | ~1.0 W |
| Camera Module v2 active | +~250 mA | +~1.25 W |

### Camera Start/Stop Strategy

**Option A: Keep camera running, duty-cycle captures**

```python
picam2 = Picamera2()
picam2.configure(still_config)
picam2.start()

while True:
    # Camera ISP is running, consuming power
    cur = picam2.capture_array("lores")[:h, :w]
    if motion_detected(cur, prev):
        handle_motion()
    prev = cur
    time.sleep(0.5)  # Poll interval
```

- Camera draws power continuously (~250 mA)
- No startup delay for captures
- Simplest implementation

**Option B: Start/stop camera between polls**

```python
while True:
    picam2.start()
    time.sleep(0.3)  # Camera warmup
    frame = picam2.capture_array("lores")[:h, :w]
    picam2.stop()
    
    if motion_detected(frame, prev):
        picam2.start()
        time.sleep(0.3)
        capture_and_send()
        picam2.stop()
    
    prev = frame
    time.sleep(poll_interval)  # e.g., 5 seconds
```

- Camera power saved during sleep (~250 mA saved)
- 300ms startup penalty per poll
- Risk: may miss fast-moving animals during sleep

**Option C (Recommended): Keep camera running with low-res polling**

For a wildlife camera, Option A is recommended because:
1. The camera startup time (300ms+) could miss fast-moving animals
2. Continuous low-res polling at 320x240 is minimal additional CPU load
3. The lores stream hardware scaling is done by the ISP, not the CPU
4. Power savings from Option B are marginal compared to WiFi toggling savings

### Optimal Poll Intervals

| Scenario | Poll Interval | Rationale |
|----------|--------------|-----------|
| Active monitoring | 0.5s | Catches most wildlife movement |
| Power-saving mode | 2-5s | For battery operation |
| Night mode | 5-10s | Less activity expected |

### Power Budget for Battery Operation

With a typical 10,000 mAh USB battery pack at 5V:
- Camera always on, WiFi toggled: ~200 mA average → ~50 hours
- Camera duty-cycled (5s interval), WiFi toggled: ~120 mA average → ~83 hours

---

## 3. WiFi Toggling from Python

### Method 1: rfkill (Recommended)

`rfkill` is the most reliable way to fully disable the WiFi radio:

```python
import subprocess

def wifi_off():
    """Disable WiFi radio completely — lowest power state"""
    subprocess.run(["sudo", "rfkill", "block", "wifi"], check=True)

def wifi_on():
    """Enable WiFi radio"""
    subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
```

**Pros:**
- Fully powers down the radio chip
- Saves ~50 mA when WiFi is blocked
- Clean interface, no risk of partial state

**Cons:**
- Reconnection takes 3-8 seconds depending on DHCP
- Requires sudo (can be fixed with udev rules or sudoers)

### Method 2: ip link set (Faster Reconnect)

```python
def wifi_off():
    """Disable WiFi interface but keep radio powered"""
    subprocess.run(["sudo", "ip", "link", "set", "wlan0", "down"], check=True)

def wifi_on():
    """Re-enable WiFi interface"""
    subprocess.run(["sudo", "ip", "link", "set", "wlan0", "up"], check=True)
```

**Pros:**
- Faster reconnection (1-3 seconds)
- Less wear on the radio

**Cons:**
- Radio may still draw some power in soft-off state
- Less power savings than rfkill

### Static IP Configuration (Minimize Reconnect Delay)

Static IP eliminates DHCP negotiation, reducing reconnect from ~5s to ~2s:

**/etc/dhcpcd.conf:**
```
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1
```

Or with NetworkManager (newer Pi OS):

**/etc/NetworkManager/system-connections/your-network.nmconnection:**
```ini
[ipv4]
method=manual
addresses=192.168.1.100/24
gateway=192.168.1.1
dns=192.168.1.1
```

### Reconnection Time Comparison

| Method | Static IP | DHCP |
|--------|----------|------|
| rfkill block/unblock | ~2-3s | ~5-8s |
| ip link down/up | ~1-2s | ~3-5s |

### Connectivity Verification Before POST

```python
import socket
import time

def wait_for_connectivity(host, port=80, timeout=10):
    """Wait until the Pi 5 server is reachable"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            sock = socket.create_connection((host, port), timeout=2)
            sock.close()
            return True
        except (OSError, socket.timeout):
            time.sleep(0.5)
    return False

def wifi_on_and_wait(server_host, server_port=8000):
    """Enable WiFi and wait for server connectivity"""
    subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
    time.sleep(1)  # Give radio time to associate
    return wait_for_connectivity(server_host, server_port)
```

### Sudoers Configuration (No Password for rfkill)

Add to `/etc/sudoers.d/piwatcher`:
```
piwatcher ALL=(ALL) NOPASSWD: /usr/sbin/rfkill block wifi
piwatcher ALL=(ALL) NOPASSWD: /usr/sbin/rfkill unblock wifi
```

---

## 4. Auto-Start on Boot (systemd Service)

### Service File

**/etc/systemd/system/piwatcher.service:**

```ini
[Unit]
Description=PiWatcher Wildlife Camera Motion Detector
After=local-fs.target
# No network dependency — WiFi is toggled manually by the script

[Service]
Type=simple
User=piwatcher
Group=video
ExecStart=/usr/bin/python3 /home/piwatcher/piwatcher/watcher.py
WorkingDirectory=/home/piwatcher/piwatcher
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security hardening
ProtectSystem=strict
ReadWritePaths=/home/piwatcher/piwatcher/frames
PrivateTmp=true

# Camera access
SupplementaryGroups=video

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Installation Commands

```bash
# Copy service file
sudo cp piwatcher.service /etc/systemd/system/

# Create service user (optional, can use pi user)
sudo useradd -r -s /bin/false -G video piwatcher

# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable piwatcher.service

# Start now
sudo systemctl start piwatcher.service

# Check status
sudo systemctl status piwatcher.service

# View logs
journalctl -u piwatcher.service -f
```

### Key Design Decisions

1. **No network dependency** (`After=local-fs.target` only) — WiFi is toggled manually by the watcher script
2. **`User=piwatcher`** — run as unprivileged user
3. **`Group=video`** — required for camera access via libcamera
4. **`Restart=on-failure`** — automatic restart if the script crashes
5. **`RestartSec=10`** — 10-second delay before restart (prevents rapid restart loops)

### Dependencies

The service needs:
- `video` group membership for camera access
- Sudoers entry for rfkill (if using WiFi toggling)
- Write access to a frames directory (for queueing)

---

## 5. Capture Parameters for VL Model

### Liquid AI VL Model Input

The Liquid AI Vision-Language models (like LFM-3B or similar 450M parameter variants) typically accept standard vision transformer input resolutions:

| Resolution | Pixels | Typical Use |
|-----------|--------|-------------|
| 224x224 | 50,176 | ViT-B/16, CLIP |
| 336x336 | 112,896 | LLaVA-1.5 |
| 384x384 | 147,456 | ViT-L/14, many VLMs |
| 448x448 | 200,704 | InternVL, some Liquid models |
| 512x512 | 262,144 | Higher-res VLMs |

**Most likely input for a 450M VL model: 384x384 or 448x448**

### Pi Zero Camera Capture Resolutions

The Pi Camera Module v2 (IMX219) native modes:
- 3280x2464 (full resolution, 8MP)
- 1920x1080 (1080p crop)
- 1640x1232 (2x2 binned)
- 640x480 (cropped/binned)

### Strategy: Capture Higher, Downsize on Pi 5

**Recommended approach:** Capture at 640x480 on Pi Zero, downsize to model resolution on Pi 5.

Rationale:
- 640x480 is a native camera mode — no software scaling needed on Pi Zero
- JPEG compression at 640x480 yields small files (~30-60 KB at quality 85)
- Pi 5 has plenty of CPU/GPU to resize to 384x384 or 448x448
- Higher capture res (e.g., 1280x720) wastes bandwidth for minimal benefit

### JPEG File Sizes at Different Resolutions

Measured with quality=85 (typical outdoor scene):

| Resolution | JPEG Size (Q85) | JPEG Size (Q70) |
|-----------|----------------|----------------|
| 320x240 | ~15-25 KB | ~10-18 KB |
| 640x480 | ~40-70 KB | ~25-45 KB |
| 1280x720 | ~100-180 KB | ~60-120 KB |
| 1920x1080 | ~200-400 KB | ~130-250 KB |

### Transfer Time Over WiFi

Pi Zero W has 802.11n single-band (2.4 GHz) with ~35 Mbps theoretical, ~10-15 Mbps real-world throughput:

| File Size | Transfer Time (10 Mbps) | Transfer Time (15 Mbps) |
|----------|------------------------|------------------------|
| 30 KB | ~24 ms | ~16 ms |
| 60 KB | ~48 ms | ~32 ms |
| 120 KB | ~96 ms | ~64 ms |
| 300 KB | ~240 ms | ~160 ms |

**At 640x480 Q85 (~50 KB), transfer takes ~40ms — negligible compared to WiFi reconnection time.**

### Recommendation

```python
# Capture configuration for wildlife camera
capture_config = {
    "main": {"size": (640, 480), "format": "RGB888"},
    "lores": {"size": (320, 240), "format": "YUV420"}
}

# JPEG encoding settings
jpeg_quality = 85  # Good balance of quality and size
```

---

## 6. Motion Detection Configuration

### Configurable Parameters

```python
MOTION_CONFIG = {
    # Pixel change threshold (MSE between frames)
    # Lower = more sensitive, Higher = less sensitive
    "threshold": 7.0,  # Default from picamera2 example
    
    # Minimum number of changed pixels (percentage of frame)
    # Filters out noise — requires contiguous changed area
    "min_changed_pct": 2.0,  # 2% of pixels must change
    
    # Cooldown between motion events (seconds)
    # Prevents rapid-fire captures of the same animal
    "cooldown_seconds": 5.0,
    
    # Region of interest (ROI) — normalized coordinates
    # Ignore motion outside this region
    "roi": {
        "x": 0.0, "y": 0.0,  # Top-left
        "w": 1.0, "h": 1.0   # Full frame (default)
    },
    
    # Number of consecutive motion frames required
    # Reduces false positives from single-frame noise
    "consecutive_frames": 2,
    
    # Night mode (higher threshold due to noise)
    "night_threshold_multiplier": 1.5,
}
```

### Reasonable Defaults for Outdoor Wildlife

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| threshold (MSE) | 5-10 | 7 works well for moderate sensitivity |
| min_changed_pct | 1-3% | Filters wind/leaf movement |
| cooldown_seconds | 3-10s | Prevents duplicate captures |
| consecutive_frames | 2 | Eliminates single-frame noise |
| ROI | full frame or custom | Exclude known movement areas (trees) |

### Advanced: Pixel-Level Thresholding

For better noise rejection than global MSE:

```python
def detect_motion_advanced(cur, prev, threshold=25, min_area_pct=2.0):
    """Advanced motion detection with area filtering"""
    diff = np.abs(cur.astype(np.int16) - prev.astype(np.int16))
    # Count pixels that changed more than threshold
    changed = (diff > threshold).sum()
    total = cur.shape[0] * cur.shape[1]
    pct_changed = (changed / total) * 100
    return pct_changed > min_area_pct
```

### Environmental Considerations

- **Wind:** Increases false positives from swaying vegetation. Use higher threshold (10-15) or ROI masking
- **Rain:** Causes widespread pixel change. Detect rain by checking if >50% of frame changes
- **Dawn/Dusk:** Gradual lighting changes. Use frame-to-frame diff, not absolute threshold
- **Shadows:** Moving clouds create slow, large-area changes. consecutive_frames=2 helps
- **Insects:** Very close to lens, cause large pixel changes. min_area_pct helps (insects appear very large but blur)

---

## 7. Pi Zero W Camera Module Options

### Compatible Camera Modules

| Module | Sensor | Resolution | Focus | Night | Pi Zero Compatible |
|--------|--------|-----------|-------|-------|-------------------|
| Camera Module v2 | IMX219 | 8MP | Fixed | No | Yes (via ribbon) |
| Camera Module v2 NoIR | IMX219 | 8MP | Fixed | Yes (no IR filter) | Yes |
| Camera Module v3 | IMX708 | 12MP | Autofocus | No | Yes |
| Camera Module v3 NoIR | IMX708 | 12MP | Autofocus | Yes | Yes |
| HQ Camera | IMX477 | 12.3MP | C/CS mount | Depends on lens | Yes |

### Pi Zero W Camera Connector

Pi Zero W uses a **mini 22-pin, 0.5mm (fine) pitch, 11.5mm width CSI connector** (smaller than the standard Pi connector). You need:
- A Pi Zero camera ribbon cable (shorter, different connector width)
- Or an adapter cable from standard to mini CSI

### Recommended: Camera Module v2 (NoIR for Wildlife)

For wildlife:
- **Camera Module v2 NoIR** — best for wildlife (night vision with IR LEDs)
- Fixed focus eliminates autofocus delay/noise
- IMX219 is well-supported and power-efficient
- 8MP is more than enough (we're capturing at 640x480)

### Night Vision Setup

For night wildlife photography:
1. Camera Module v2 NoIR (lacks IR-cut filter)
2. 850nm IR LED array (invisible to most animals)
3. The NoIR module sees IR illumination as visible light

### picamera2 vs Legacy picamera

| Feature | picamera (legacy) | picamera2 |
|---------|-------------------|-----------|
| Backend | MMAL (Broadcom proprietary) | libcamera (open-source) |
| Pi Zero support | Yes | Yes |
| Dual streams | Limited | Full support (main + lores) |
| Still capture | `capture()` | `capture_file()` / `capture_array()` |
| Motion detection | PiCameraCircularIO | Manual with NumPy |
| Maintained | No (deprecated) | Yes (active development) |
| Python version | Python 2/3 | Python 3 only |
| Installation | pip | apt (recommended) |

**picamera2 is the only supported option for new projects.** The legacy camera stack is disabled by default on Bookworm and later.

### Installation on Pi Zero

```bash
# Pi Zero with Raspberry Pi OS Lite (Bookworm)
sudo apt install python3-picamera2 --no-install-recommends
```

The `--no-install-recommends` flag avoids pulling in GUI dependencies, saving ~200MB on a headless Pi Zero.

---

## 8. HTTP POST of JPEG Frames

### Library Comparison

| Library | Size | Async | Connection Pooling | Pi Zero Suitability |
|---------|------|-------|-------------------|-------------------|
| urllib3 | Built-in (via urllib) | No | Yes | Good (no deps) |
| requests | ~150 KB | No | Yes (via urllib3) | Good (standard) |
| httpx | ~1 MB | Yes (optional) | Yes | Overkill for sync |

**Recommendation: `requests`** — it's already available on Raspberry Pi OS, simple API, and sufficient for our sync-only use case.

### Basic HTTP POST Implementation

```python
import requests
import io
from pathlib import Path

def post_frame(jpeg_bytes: bytes, server_url: str, timeout: float = 10.0) -> bool:
    """POST a JPEG frame to the Pi 5 server"""
    try:
        response = requests.post(
            server_url,
            files={"frame": ("capture.jpg", jpeg_bytes, "image/jpeg")},
            timeout=timeout
        )
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False
```

### Multipart Upload of Multiple Frames

```python
def post_multiple_frames(frames: list[bytes], server_url: str, timeout: float = 30.0) -> bool:
    """POST multiple JPEG frames in a single request"""
    files = [
        ("frames", (f"frame_{i}.jpg", frame, "image/jpeg"))
        for i, frame in enumerate(frames)
    ]
    try:
        response = requests.post(server_url, files=files, timeout=timeout)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False
```

### Retry with Exponential Backoff

```python
import time
import random

def post_with_retry(jpeg_bytes: bytes, server_url: str, max_retries: int = 3) -> bool:
    """POST with exponential backoff retry"""
    for attempt in range(max_retries):
        try:
            response = requests.post(
                server_url,
                files={"frame": ("capture.jpg", jpeg_bytes, "image/jpeg")},
                timeout=10.0
            )
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        
        if attempt < max_retries - 1:
            # Exponential backoff with jitter
            delay = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
    
    return False
```

### Filesystem Queue for Failed Uploads

```python
import json
from pathlib import Path
from datetime import datetime

QUEUE_DIR = Path("/home/piwatcher/piwatcher/frame_queue")

def queue_frame(jpeg_bytes: bytes, metadata: dict):
    """Save frame to disk when network is unavailable"""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    
    # Save JPEG
    frame_path = QUEUE_DIR / f"{timestamp}.jpg"
    frame_path.write_bytes(jpeg_bytes)
    
    # Save metadata
    meta_path = QUEUE_DIR / f"{timestamp}.json"
    meta_path.write_text(json.dumps(metadata))

def flush_queue(server_url: str) -> int:
    """Attempt to upload all queued frames"""
    sent = 0
    for frame_path in sorted(QUEUE_DIR.glob("*.jpg")):
        meta_path = frame_path.with_suffix(".json")
        jpeg_bytes = frame_path.read_bytes()
        
        if post_frame(jpeg_bytes, server_url):
            frame_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            sent += 1
        else:
            break  # Stop on first failure
    return sent
```

### Complete Upload Flow

```python
def handle_motion_event(picam2, server_url: str, server_host: str):
    """Full flow: capture → WiFi on → upload → WiFi off"""
    # 1. Capture frame immediately
    jpeg_buffer = io.BytesIO()
    picam2.capture_file(jpeg_buffer, format="jpeg")
    jpeg_bytes = jpeg_buffer.getvalue()
    
    # 2. Enable WiFi
    wifi_on()
    
    # 3. Wait for connectivity
    if wait_for_connectivity(server_host, port=8000, timeout=10):
        # 4. Flush any queued frames first
        flush_queue(server_url)
        
        # 5. Upload current frame
        if not post_with_retry(jpeg_bytes, server_url):
            queue_frame(jpeg_bytes, {"timestamp": time.time()})
    else:
        # Network unavailable — queue to disk
        queue_frame(jpeg_bytes, {"timestamp": time.time()})
    
    # 6. Disable WiFi
    wifi_off()
```

---

## Summary of Recommendations

| Topic | Recommendation |
|-------|---------------|
| Motion detection | picamera2 dual-stream, 320x240 YUV420 lores, NumPy MSE |
| Power management | Keep camera running, toggle WiFi only |
| WiFi control | `rfkill` + static IP (2-3s reconnect) |
| Boot service | systemd simple service, no network dependency |
| Capture resolution | 640x480 JPEG Q85 (~50 KB), resize on Pi 5 |
| Motion config | threshold=7, cooldown=5s, consecutive_frames=2 |
| Camera module | Camera Module v2 NoIR + IR LEDs for wildlife |
| HTTP upload | `requests` library, multipart POST, filesystem queue fallback |

---

## References

- picamera2 repository: https://github.com/raspberrypi/picamera2
- picamera2 manual: https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf
- Official motion detection example: `examples/capture_motion.py`
- Improved motion example: `examples/capture_motion_improved.py`
- Raspberry Pi hardware documentation: https://www.raspberrypi.com/documentation/computers/raspberry-pi.html
- Pi Zero W specs: BCM2835, 512MB RAM, 802.11n WiFi (35 Mbps), 150mA idle
- Camera Module documentation: https://www.raspberrypi.com/documentation/accessories/camera.html

## Follow-On Questions

- What is the exact input resolution for the specific Liquid AI VL 450M model being used? (Need model card/documentation)
- What is the Pi 5 server API endpoint format? (Affects POST implementation)
- Will the Pi Zero be battery-powered or wall-powered? (Affects power management strategy)
- Is there a specific IR LED module being used? (Affects NoIR camera configuration)

## Clarifying Questions

- The Pi Zero W (original) has a single-core BCM2835 at 1GHz with 512MB RAM. The Pi Zero 2 W has a quad-core BCM2710A1. Which model is being used? The Pi Zero 2 W would significantly improve motion detection performance.
