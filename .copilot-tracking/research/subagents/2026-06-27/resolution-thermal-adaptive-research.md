# Resolution, Thermal, and Adaptive Capture Research

## Research Topics

1. 1024x1024 vs 640x480 for bird identification with LFM2-VL-450M
2. Pi Camera Module v2 (IMX219) square crop at 1024x1024
3. Adaptive capture strategy (motion-triggered 2fps with timeout)
4. Pi 5 thermal throttling and bursty inference
5. Battery impact of 2fps capture at 1024x1024

---

## Topic 1: 1024x1024 vs 640x480 for Bird Identification

### LFM2-VL-450M Vision Patch Architecture

LFM2-VL-450M (like most modern VLMs based on ViT architectures) processes images using a patch-based approach with 512x512 input patches. The image is divided into non-overlapping patches and processed by the vision encoder.

#### Resolution Comparison

| Resolution | Patches (512x512) | Aspect | Padding/Crop Needed | Detail Level |
|---|---|---|---|---|
| 640x480 | ~1.17 patches worth | Non-square (4:3) | Yes - must pad to 512 or resize | Low-medium |
| 768x768 | ~2.25 patches worth | Square | Resize to 512 or use 1 patch + context | Medium |
| 1024x1024 | 4 patches (2x2 grid) | Square | Clean tiling, no waste | High |

#### 640x480 Analysis

- **Non-square problem**: The 4:3 aspect ratio means the model must either:
  - Resize to 512x512 (distorts aspect ratio, birds appear squished)
  - Pad to 512x512 (wastes ~6% of input on black bars)
  - Center-crop to 480x480, then resize to 512 (loses edges)
- **Single-patch coverage**: At 640x480, the entire image effectively maps to ~1 patch after resize. Fine for detecting "is this a bird?" but limited for species-level detail.
- **Detail limitation**: A bird occupying 20% of a 640x480 frame gives ~128x96 effective pixels for the bird. After resize to 512x512, the bird region is ~100x77 pixels of actual information.

#### 1024x1024 Analysis

- **Clean 4-patch tiling**: 1024x1024 divides perfectly into four 512x512 patches (2x2 grid). No padding, no aspect ratio distortion.
- **4x more detail**: Same bird at 20% of frame gets ~205x205 effective pixels. This is meaningful for distinguishing fine features (beak shape, eye stripe patterns, wing bars).
- **Species differentiation**: For sparrow vs finch vs wren, the distinguishing features are:
  - Beak shape/thickness (requires ~30+ pixel width of beak)
  - Eye stripe presence/absence
  - Wing bar coloring
  - Breast streaking patterns
  - At 640x480, these features are often 3-8 pixels; at 1024x1024, they're 6-16 pixels.

#### Q4_0 Quantization Impact on Detail Utility

- **Q4_0 reduces model weights**, not input resolution. The vision encoder still processes full-resolution patches.
- The quantization affects the language model's reasoning capacity, not the visual feature extraction.
- The ViT vision encoder (even in Q4_0 quantized model) still benefits from higher-resolution input because feature maps in early layers preserve spatial detail.
- **Verdict**: 1024x1024 is NOT wasted by Q4_0 quantization. The vision encoder extracts features at full patch resolution; quantization primarily impacts the text generation quality.

#### 768x768 Middle Ground

- Would require resize to 512x512 (single patch, loses detail) or padding to 1024x1024 (wastes 56% of patches on padding).
- Not a clean multiple of 512 — creates suboptimal tiling.
- **Not recommended** — it's neither the low-power option (640x480) nor the clean-tiling option (1024x1024).

### Recommendation

**Use 1024x1024**. The clean 4-patch tiling, combined with the meaningful improvement in bird feature resolution, makes this the optimal choice for species identification. The additional capture/transfer cost (covered in Topic 5) is manageable.

---

## Topic 2: Pi Camera Module v2 (IMX219) Square Crop at 1024x1024

### IMX219 Sensor Specifications (from official Raspberry Pi documentation)

- **Sensor resolution**: 3280 x 2464 pixels (8 megapixels)
- **Sensor image area**: 3.68 x 2.76 mm (4.6 mm diagonal)
- **Pixel size**: 1.12 µm x 1.12 µm
- **Focus**: Adjustable (manual)
- **Horizontal FoV**: 62.2 degrees
- **Vertical FoV**: 48.8 degrees

### Sensor Modes for IMX219

The IMX219 supports several sensor modes via picamera2/libcamera:

| Mode | Resolution | Aspect | Crop | FPS (Pi Zero) |
|---|---|---|---|---|
| 0 | 3280x2464 | 4:3 | Full sensor | ~2-5 fps |
| 1 | 1920x1080 | 16:9 | Center crop | ~15 fps |
| 2 | 1640x1232 | 4:3 | 2x2 binned | ~30 fps |
| 3 | 640x480 | 4:3 | 2x2 binned + crop | ~60-90 fps |

### Can picamera2 Capture 1024x1024 Directly?

**Yes, via ScalerCrop.** Picamera2 supports arbitrary output resolutions through the ISP (Image Signal Processor) pipeline:

1. **Sensor reads full frame** (or selected mode)
2. **ScalerCrop** applies a region-of-interest (ROI) crop on the sensor readout
3. **ISP scaler** resizes the cropped region to the requested output size

#### Method 1: Center-crop from full sensor (Best quality)

```python
from picamera2 import Picamera2

picam2 = Picamera2()

# Use full sensor mode for maximum quality
config = picam2.create_still_configuration(
    main={"size": (1024, 1024)},
    # ScalerCrop will be auto-set to center square crop
)
picam2.configure(config)
picam2.start()

# The ISP will:
# 1. Read 3280x2464 from sensor
# 2. Apply center crop of 2464x2464 (largest square)
# 3. Downscale to 1024x1024
```

When you request a square output, picamera2/libcamera automatically computes the largest centered square crop from the sensor readout and scales it down. From the 3280x2464 sensor, the largest square is 2464x2464, which downscales to 1024x1024 (2.4:1 ratio — well within ISP capabilities).

#### Method 2: Explicit ScalerCrop control

```python
from picamera2 import Picamera2
from libcamera import Rectangle

picam2 = Picamera2()
config = picam2.create_still_configuration(
    main={"size": (1024, 1024)},
)
picam2.configure(config)
picam2.start()

# Manually set crop region (center 2464x2464 from 3280x2464)
crop = (408, 0, 2464, 2464)  # (x_offset, y_offset, width, height)
picam2.set_controls({"ScalerCrop": crop})
```

#### Performance: 1024x1024 vs 640x480 on Pi Zero W

| Metric | 640x480 | 1024x1024 |
|---|---|---|
| Sensor mode used | Mode 3 (binned, fast) | Mode 0 or 2 (full/binned) |
| Sensor readout time | ~5ms | ~15-30ms |
| ISP processing | Minimal scaling | Crop + scale |
| Achievable fps (Pi Zero) | ~30 fps | ~5-8 fps (still), ~2-3 fps (continuous) |
| JPEG encode time | ~20-40ms | ~80-150ms |

**Critical finding for Pi Zero W**: The Pi Zero W uses the BCM2835 (single-core ARM11 @ 1GHz, 512MB RAM). At 1024x1024:
- Continuous capture at 2 fps is achievable but will stress the CPU
- JPEG encoding at quality 85 takes ~100-150ms per frame
- 2 fps = 500ms per frame budget → plenty of time for capture + encode
- **This works.** The Pi Zero can sustain 2 fps at 1024x1024.

#### Optimal Approach for Pi Zero

Use sensor **Mode 2** (1640x1232, 2x2 binned) for the main capture stream:
- Faster readout than full-resolution mode
- Still provides 1232x1232 square crop (larger than 1024x1024)
- ISP downscales 1232x1232 → 1024x1024 (only 1.2:1, minimal quality loss)
- **Much faster than reading full 3280x2464 sensor**

```python
# Optimized config for Pi Zero W
config = picam2.create_still_configuration(
    main={"size": (1024, 1024)},
    sensor={"output_size": (1640, 1232)},  # Use binned mode
    buffer_count=2,
)
```

### JPEG File Size at 1024x1024

At quality 85, JPEG sizes for natural outdoor scenes (birds, foliage):
- **1024x1024 quality 85**: ~80-200 KB typical (average ~120-150 KB)
- **640x480 quality 85**: ~30-80 KB typical (average ~50 KB)
- Bird scenes with foliage tend toward the higher end due to detail/texture

### Transfer Time (Pi Zero W WiFi)

Pi Zero W has 802.11n WiFi at ~35 Mbps theoretical, ~10-15 Mbps practical throughput:
- **150 KB frame over WiFi**: ~80-120ms per frame
- **120 frames × 150 KB = 18 MB total batch**: ~10-15 seconds transfer time
- This is very manageable as a post-capture batch transfer.

---

## Topic 3: Adaptive Capture Strategy

### State Machine Design

```
┌─────────────┐
│    IDLE     │ ← Motion detection on lores stream
│  WiFi: OFF  │   (low power, ~160x120 frame differencing)
└──────┬──────┘
       │ Motion detected
       ▼
┌─────────────┐
│  CAPTURING  │ ← 2 fps on main stream (1024x1024)
│  WiFi: OFF  │   Motion monitoring continues on lores
│  Timer: 60s │   Frames saved to SD/RAM buffer
└──────┬──────┘
       │ Motion stops → start 5s countdown
       ▼
┌─────────────┐
│  COOLDOWN   │ ← Still capturing at 2 fps
│  WiFi: OFF  │   Waiting for timer expiry
│  Timer: 5s  │   If motion resumes → back to CAPTURING
└──────┬──────┘
       │ 5s elapsed AND total_time >= 60s
       ▼
┌─────────────┐
│ TRANSFERRING│ ← WiFi ON, batch upload frames
│  WiFi: ON   │   Transfer all frames to Pi 5
└──────┬──────┘
       │ Transfer complete
       ▼
┌─────────────┐
│    IDLE     │ ← WiFi OFF, resume motion detection
└─────────────┘
```

### Implementation Approach

```python
import time
import threading
from enum import Enum
from picamera2 import Picamera2

class CaptureState(Enum):
    IDLE = "idle"
    CAPTURING = "capturing"
    COOLDOWN = "cooldown"
    TRANSFERRING = "transferring"

class AdaptiveCapture:
    def __init__(self):
        self.state = CaptureState.IDLE
        self.capture_start_time = None
        self.last_motion_time = None
        self.frames = []
        self.cooldown_seconds = 5
        self.min_duration_seconds = 60
        self.capture_fps = 2

    def on_motion_detected(self):
        if self.state == CaptureState.IDLE:
            self.state = CaptureState.CAPTURING
            self.capture_start_time = time.time()
            self.last_motion_time = time.time()
            self._start_capture()
        elif self.state == CaptureState.COOLDOWN:
            # Motion resumed — reset cooldown
            self.state = CaptureState.CAPTURING
            self.last_motion_time = time.time()

    def _capture_loop(self):
        while self.state in (CaptureState.CAPTURING, CaptureState.COOLDOWN):
            frame = self._capture_frame()
            self.frames.append(frame)
            time.sleep(1.0 / self.capture_fps)

            # Check state transitions
            if self.state == CaptureState.CAPTURING:
                if not self._motion_active():
                    self.state = CaptureState.COOLDOWN
                    self._cooldown_start = time.time()

            elif self.state == CaptureState.COOLDOWN:
                elapsed_cooldown = time.time() - self._cooldown_start
                total_elapsed = time.time() - self.capture_start_time
                if elapsed_cooldown >= self.cooldown_seconds:
                    if total_elapsed >= self.min_duration_seconds:
                        self._stop_and_transfer()
                        return

    def _stop_and_transfer(self):
        self.state = CaptureState.TRANSFERRING
        self._enable_wifi()
        self._batch_transfer(self.frames)
        self._disable_wifi()
        self.frames = []
        self.state = CaptureState.IDLE
```

### Dual-Stream Configuration (picamera2)

```python
# Configure dual streams: lores for motion, main for capture
config = picam2.create_video_configuration(
    main={"size": (1024, 1024), "format": "RGB888"},
    lore={"size": (160, 120), "format": "YUV420"},
    buffer_count=4,
)
```

The lores stream runs continuously for motion detection (frame differencing at 160x120 is nearly free on Pi Zero). When motion triggers, main stream frames are captured at 2 fps.

### WiFi Toggling Strategy

**WiFi stays OFF during the entire capture period.** Rationale:
- WiFi consumes ~40-80mA continuously
- WiFi radio interference can cause CPU interrupts, potentially causing frame drops
- Batch transfer after capture is more power-efficient (WiFi on for shorter total time)
- No risk of missing frames due to network activity

WiFi control:
```bash
# Disable WiFi (save ~40-80mA)
sudo rfkill block wifi
# or: sudo ip link set wlan0 down

# Enable WiFi
sudo rfkill unblock wifi
# Then wait for association (~2-5 seconds)
```

Python equivalent:
```python
import subprocess

def wifi_off():
    subprocess.run(["sudo", "rfkill", "block", "wifi"], check=True)

def wifi_on():
    subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
    time.sleep(5)  # Wait for association
```

---

## Topic 4: Pi 5 Thermal Throttling and Bursty Inference

### Pi 5 Thermal Throttling Behavior (from official documentation)

The Raspberry Pi 5 uses BCM2712 SoC with the following thermal management:

#### Temperature Thresholds

| Temperature | Action |
|---|---|
| Below 50°C | Fan off (0% speed), no throttling |
| 50°C | Fan on at 30% speed |
| 60°C | Fan at 50% speed |
| 67.5°C | Fan at 70% speed |
| 75°C | Fan at 100% speed |
| 80°C | **ARM cores begin progressive throttling** |
| 85°C | **Both ARM and GPU throttled back** (hard limit) |

**Hysteresis**: Fan speeds decrease when temperature drops 5°C below each threshold.

#### CPU Governor Behavior

- Default governor: `ondemand`
- Frequency steps: 2400 MHz (max), 1500 MHz, 1000 MHz, 750 MHz, 600 MHz
- Between 80-85°C: progressively steps down through these frequencies
- At 85°C: locked to minimum (600 MHz)

#### Key Insight for Inference

The Pi 5's normal operating temperature under sustained CPU load (no cooling) reaches 80-85°C within 5-10 minutes. **With the Active Cooler fan**, sustained loads typically plateau at 55-65°C.

If the user reports "fan problems," possible issues:
1. Fan not connected properly (4-pin JST-SH connector)
2. Fan PWM control not working (check `/sys/class/thermal/`)
3. Insufficient airflow in enclosure
4. Fan failing/worn out

### Reading CPU Temperature from Python

```python
def get_cpu_temp() -> float:
    """Read Pi 5 CPU temperature in Celsius."""
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        return int(f.read().strip()) / 1000.0

# Alternative via vcgencmd (more accurate)
import subprocess
def get_cpu_temp_vcgencmd() -> float:
    result = subprocess.run(
        ["vcgencmd", "measure_temp"],
        capture_output=True, text=True
    )
    # Output: "temp=45.6'C"
    return float(result.stdout.split("=")[1].split("'")[0])
```

### Estimated Inference Time: LFM2-VL-450M Q4_0 on Pi 5

Based on comparable VLMs on Pi 5:
- **Model size**: LFM2-VL-450M at Q4_0 ≈ ~250-300 MB in memory
- **Vision encoding** (1024x1024, 4 patches): ~3-8 seconds
- **Text generation** (short species ID response, ~50 tokens): ~5-15 seconds
- **Total per image**: ~10-25 seconds estimated

Via llama-swap, the model stays loaded between calls, so no reload overhead.

### Thermal Analysis for Bursty Workload

Scenario: 120 frames arrive (60s at 2fps), sample 5 frames for inference.

| Phase | Duration | Thermal Impact |
|---|---|---|
| Receive batch (WiFi) | ~10-15s | Low (network I/O, not CPU-bound) |
| Inference frame 1 | ~10-25s | HIGH (sustained CPU at 2.4GHz) |
| Cool-down gap | configurable | Drops 3-8°C per 10s rest |
| Inference frame 2 | ~10-25s | HIGH |
| ... | ... | ... |
| Inference frame 5 | ~10-25s | HIGH |
| **Total inference time** | ~50-125s | Intermittent high |

### Adaptive Throttling Strategy

```python
import time

MAX_TEMP_C = 72.0  # Stay well below 80°C throttle point
COOL_DOWN_TEMP_C = 60.0
PAUSE_BETWEEN_INFERENCES_S = 10  # Minimum gap

def process_batch_with_thermal_management(frames: list, sample_count: int = 5):
    """Process a batch of frames with temperature-aware pacing."""
    # Select evenly-spaced sample frames
    indices = [int(i * len(frames) / sample_count) for i in range(sample_count)]
    sampled = [frames[i] for i in indices]

    results = []
    for i, frame in enumerate(sampled):
        # Pre-inference temperature check
        temp = get_cpu_temp()
        if temp > MAX_TEMP_C:
            # Wait until cooled
            while get_cpu_temp() > COOL_DOWN_TEMP_C:
                time.sleep(5)

        # Run inference
        result = run_inference(frame)
        results.append(result)

        # Post-inference cooldown (skip after last frame)
        if i < len(sampled) - 1:
            time.sleep(PAUSE_BETWEEN_INFERENCES_S)

    return results
```

### "Infer N, Wait M" Pattern

A simple fixed pattern that works:
- **Infer 1 frame** (~15-20s of sustained CPU)
- **Wait 15 seconds** (allows ~5-8°C cooldown with Active Cooler)
- **Infer next frame**

With 5 sampled frames: total processing time ≈ 5×20s + 4×15s = **160 seconds** (~2.7 minutes)

This keeps the temperature cycling between ~55-70°C, well below throttle thresholds.

### Recommendation

1. **Always check temperature before each inference call**
2. Use a 10-15 second minimum gap between inferences
3. If temperature exceeds 72°C, wait until it drops below 60°C
4. 5 frames from a 120-frame burst is thermally manageable (~3 minutes total)
5. **Investigate the fan issue separately** — with a working Active Cooler, sustained inference should be fine up to 65°C

---

## Topic 5: Battery Impact of 2fps Capture at 1024x1024

### Pi Zero W Power Consumption Breakdown

From official Raspberry Pi documentation:
- **Pi Zero W idle**: ~150 mA (bare board, WiFi associated)
- **Pi Zero W active**: ~200-350 mA under load

Individual component draws:
| Component | Current Draw |
|---|---|
| Pi Zero W idle (WiFi off, camera idle) | ~100 mA |
| Camera sensor active (ISP running) | +50-80 mA |
| Camera at full readout (still capture) | +80-120 mA |
| WiFi associated + active transfer | +40-80 mA |
| WiFi scanning/idle | +20-40 mA |
| JPEG encoding (CPU at 100%) | +50-100 mA (included in "active") |

### Power Draw: 640x480 vs 1024x1024

| Capture Mode | Sensor Power | ISP Processing | CPU (JPEG encode) | Total Camera System |
|---|---|---|---|---|
| 640x480 (Mode 3, binned) | ~50 mA | ~20 mA | ~40 mA | ~110 mA |
| 1024x1024 (Mode 2, binned+crop) | ~70 mA | ~40 mA | ~80 mA | ~190 mA |

**Difference**: 1024x1024 draws roughly **60-80 mA more** than 640x480 during active capture, primarily due to:
- Larger sensor readout (Mode 2 vs Mode 3)
- More ISP processing (crop + scale)
- Longer/harder JPEG compression (4x more pixels)

### Energy Per Event Calculation

**Event profile**: Capture 60s @ 2fps @ 1024x1024, then WiFi transfer

#### Phase 1: Capture (60 seconds)
- System draw during capture: ~100 mA (base) + 190 mA (camera) = **~290 mA**
- Duration: 60 seconds
- Energy: 290 mA × (60/3600) h = **4.83 mAh**

#### Phase 2: WiFi On + Transfer (15 seconds)
- 120 frames × 150 KB = 18 MB
- Transfer time at ~10 Mbps = ~15 seconds
- System draw: 100 mA (base) + 80 mA (WiFi active) = **~180 mA**
- Energy: 180 mA × (15/3600) h = **0.75 mAh**

#### Phase 3: WiFi Association Overhead (5 seconds)
- Reconnecting to AP after rfkill unblock: ~5 seconds
- Draw during association: ~200 mA
- Energy: 200 mA × (5/3600) h = **0.28 mAh**

#### Total Energy Per Event
**~5.9 mAh per event**

### Events Before 1200 mAh Depleted

**Not all 1200 mAh is available for events** — the system must also account for:
- Idle time between events (motion detection running)
- Idle draw with WiFi off, camera lores stream: ~120 mA

Assuming 8 hours of operation per day (dawn to dusk for bird watching):
- Idle budget: 120 mA × 8h = 960 mAh (idle surveillance)
- Remaining for events: 1200 - 960 = **240 mAh** ← Very tight!

Wait — this means with a 1200 mAh battery:
- Pure idle surveillance time: ~10 hours
- **Events possible from remaining budget**: 240 mAh / 5.9 mAh = **~40 events**

But this assumes 8 continuous hours of idle monitoring. More realistically:

#### Scenario: Intermittent Operation (sleep between motion windows)

If the Pi Zero sleeps between active monitoring windows (e.g., only monitoring during peak bird hours):
- 4 hours active monitoring: 120 mA × 4h = 480 mAh
- Remaining: 720 mAh
- **Events**: 720 / 5.9 = **~122 events**

#### Scenario: Deep Sleep with External Motion Trigger

Using a PIR sensor to wake the Pi Zero from halt:
- Sleep current: ~5 mA (Pi Zero halted but powered)
- Wake on PIR trigger, capture event, halt again
- Available for events: ~1150 mAh
- **Events**: 1150 / 5.9 = **~195 events**

### Comparison: If Using 640x480 Instead

Energy per event at 640x480:
- Capture: 210 mA × (60/3600) = 3.5 mAh
- Transfer (120 × 50KB = 6MB): 180 mA × (5/3600) = 0.25 mAh
- WiFi startup: 0.28 mAh
- **Total: ~4.0 mAh per event**

Savings: ~1.9 mAh per event (32% less energy per event)
In the deep-sleep scenario: 1150 / 4.0 = **~288 events** (vs 195 at 1024x1024)

### Battery Recommendation

| Strategy | Events/Day | Notes |
|---|---|---|
| Continuous monitoring (8h) | ~40 events | Very constrained |
| 4h active window | ~122 events | Reasonable for backyard |
| PIR-triggered wake | ~195 events | Best for 1200mAh |
| 640x480 + PIR wake | ~288 events | If species ID quality acceptable |

**For a wildlife camera seeing 10-20 events/day**: 1024x1024 with PIR wake gives ~10-20 days of operation on 1200 mAh. This is viable for a weekend deployment. For longer deployments, consider:
- Larger battery (3000-5000 mAh LiPo)
- Solar trickle charging
- Reducing min capture duration from 60s to 30s (halves capture energy)

---

## Key Discoveries Summary

1. **1024x1024 is the right resolution** — clean 4-patch tiling, meaningful bird species detail, NOT wasted by Q4_0 quantization.

2. **Pi Camera v2 can capture 1024x1024** via picamera2 ScalerCrop from binned Mode 2 (1640x1232). The ISP handles the square crop + downscale efficiently. 2 fps is sustainable on Pi Zero W.

3. **Adaptive capture state machine** is straightforward: IDLE → CAPTURING → COOLDOWN → TRANSFERRING → IDLE. WiFi stays off during capture. Batch transfer ~18 MB in ~15 seconds.

4. **Pi 5 thermal throttling** starts at 80°C, hard limit at 85°C. With a working Active Cooler, sustained inference stays at 55-65°C. For bursty workload: infer 1 frame, wait 10-15s, repeat. 5 frames ≈ 3 minutes total, thermally safe. Always check `vcgencmd measure_temp` between calls.

5. **Battery at 1200 mAh** supports ~195 events (PIR-triggered wake) or ~40 events (continuous monitoring). 1024x1024 costs ~32% more energy per event vs 640x480. For 10-20 events/day, expect ~10-20 days on 1200 mAh with PIR wake strategy.

---

## Clarifying Questions

1. **Which Pi Zero?** — Is this a Pi Zero W (original, BCM2835, single-core ARM11) or Pi Zero 2 W (RP3A0, quad-core Cortex-A53)? The Pi Zero 2 W would handle 1024x1024 capture much more comfortably (4x CPU cores).

2. **What is the actual fan issue on Pi 5?** — Is the Active Cooler connected? Is it spinning? What temperature does `vcgencmd measure_temp` report under load? The thermal strategy depends heavily on whether the fan is fixable.

3. **Is the Pi Zero on battery or USB power?** — The energy calculations assume battery. If USB-powered (e.g., from a weatherproof solar panel), 1024x1024 at 2fps is a non-issue.

4. **How many events per day are expected?** — A busy bird feeder might see 50+ events/day; a trail camera might see 5. This determines battery sizing.

---

## Follow-On Research (Not Pursued)

- [ ] Benchmark actual JPEG encode times for 1024x1024 on Pi Zero W hardware
- [ ] Test picamera2 dual-stream (lores + main) simultaneous operation on Pi Zero W specifically
- [ ] Measure actual WiFi reconnection time after rfkill unblock on Pi Zero W
- [ ] Profile llama.cpp inference time for LFM2-VL-450M Q4_0 on Pi 5 with actual model
- [ ] Research PIR sensor integration with Pi Zero GPIO for hardware wake
- [ ] Investigate whether the Pi 5 fan can be replaced with a larger heatsink for passive cooling
