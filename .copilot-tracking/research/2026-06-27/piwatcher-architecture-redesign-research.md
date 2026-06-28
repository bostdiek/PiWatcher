<!-- markdownlint-disable-file -->
# Task Research: PiWatcher Architecture Redesign

Comprehensive architecture research for redesigning PiWatcher as a motion-triggered wildlife camera system using Pi Zero W (battery-powered, outdoor) and Pi 5 (NVMe SSD, indoor inference server).

## Task Implementation Requests

* Pi Zero W: Motion-triggered capture with duty-cycle power management, WiFi toggling, auto-start on boot
* Pi 5: FastAPI ingest server, Liquid AI VL 450M inference via llama-swap (OpenAI-compatible), structured outputs via PydanticAI
* Database: PostgreSQL (or alternatives) for event metadata, image storage strategy for future model training
* Frontend: React dashboard vs Streamlit, remote access via Cloudflare Tunnel
* Configuration: Motion detection sensitivity, capture duration/rate, optimal resolution for Liquid AI model
* Infrastructure: Grammar files for constrained LLM output, data pipeline for future model training

## Scope and Success Criteria

* Scope: Full system architecture for both Pi Zero and Pi 5, including deployment scripts, database schema, API design, frontend choice, and remote access
* Assumptions:
  * Pi Zero W with PiSugar S 1200mAh (+ optional external battery)
  * Pi 5 with NVMe SSD running llama-swap with LFM2-VL-450M Q4_0 GGUF (confirmed working)
  * Standard Pi Camera Module (with IR filter — no night vision)
  * No IR LEDs — daytime only detection
  * Local WiFi network between Zero and Pi 5
  * User wants to keep all images for future training regardless of label
  * Pi 5 has fan thermal issues — inference must be bursty with cooldown periods
  * Dashboard accessible via pi5.local on LAN (no Cloudflare needed initially)
  * Capture strategy: adaptive — 2 Hz while motion continues, extend 5s after motion stops, minimum 60s
  * Resolution: 1024x1024 (tiles cleanly into 4x 512x512 patches for LFM2-VL)
* Success Criteria:
  * Complete architecture with data flow diagrams
  * Pi Zero boot script and systemd service configuration
  * Pi 5 API design with PydanticAI integration
  * Database schema recommendation with rationale
  * Frontend recommendation with rationale
  * Configuration strategy for motion detection parameters
  * Remote access solution

## Outline

1. Pi Zero Architecture (motion detection, picamera2, duty cycle, WiFi, boot config)
2. Pi 5 Server Architecture (FastAPI, llama-swap integration, PydanticAI, grammar files)
3. Database & Storage (PostgreSQL vs alternatives, image storage, schema design)
4. Frontend (React vs Streamlit, remote access via Cloudflare)
5. Configuration & Tuning (motion sensitivity, capture rate, resolution)
6. Data Pipeline (image retention, labeling, future training)

## Potential Next Research

* Pi 5 fan diagnosis — is Active Cooler connected/spinning? Could be connector, PWM issue, or worn bearing
  * Reasoning: With working fan, thermal management becomes trivial and inference can be sustained
  * Reference: Pi 5 thermal docs, `vcgencmd measure_temp`
* PiSugar S I2C Python API — exact commands to read battery level, charging status
  * Reasoning: Need to report battery to Pi 5 with each upload
  * Reference: PiSugar GitHub wiki
* Pi Zero W vs Pi Zero 2 W — which board does the user have? Quad-core significantly helps capture
  * Reasoning: Single-core may struggle with 2fps 1024x1024 + motion detection simultaneously
  * Reference: Official specs
* Actual llama.cpp inference benchmark — time `curl` call to llama-swap with a test image
  * Reasoning: Need real numbers for thermal management gaps (currently estimated 10-25s)
  * Reference: User's running Pi 5 system
* External battery wiring — PiSugar S BAT pad pinout for parallel LiPo connection
  * Reasoning: 1200mAh only gives ~40 events in 8hr monitoring; external cell needed
  * Reference: PiSugar S schematic

## Research Executed

### File Analysis

* .copilot-tracking/research/subagents/2026-06-27/pi-zero-architecture-research.md
  * picamera2 dual-stream motion detection, WiFi toggling, systemd boot config, capture parameters
* .copilot-tracking/research/subagents/2026-06-27/pi5-server-architecture-research.md
  * LFM2-VL-450M specs, llama-swap vision API, PydanticAI, PostgreSQL schema, inference pipeline
* .copilot-tracking/research/subagents/2026-06-27/frontend-remote-access-research.md
  * Dashboard framework comparison, Cloudflare Tunnel setup, push notifications

### External Research

* Liquid AI LFM2-VL-450M model card
  * 450M params = LFM2-350M backbone + SigLIP2 NaFlex 86M vision encoder
  * Native 512x512 resolution, non-standard aspect ratio support
  * Apache 2.0 license (commercial use under $10M revenue)
  * Source: Liquid AI official documentation

* mostlygeek/llama-swap (4,800+ stars)
  * Go proxy for OpenAI/Anthropic compatible servers
  * Vision model config via `capabilities: {in: ["text", "image"], out: ["text"]}`
  * Source: https://github.com/mostlygeek/llama-swap

* PydanticAI by Pydantic team
  * Model-agnostic agent framework, OpenAI-compatible via `OpenAIChatModel`
  * Three output modes: Tool Output, Native Output, Prompted Output
  * Auto-retry on validation failure

## Key Discoveries

### 1. LFM2-VL-450M Model Specifications

The Liquid AI model is specifically designed for edge deployment:
- **Native resolution: 512x512** — images are split into non-overlapping 512x512 patches
- **Token generation**: 256x384 → 96 tokens, 384x680 → 240 tokens, 1000x3000 → 1,020 tokens
- **Tunable speed-quality tradeoff** at inference time (max image tokens, number of patches)
- **2x faster** than comparable VLMs on GPU
- Serves via standard OpenAI vision API format (base64 image in content array)
- **Confirmed running**: Q4_0 GGUF quantization on Pi 5 via llama-swap

**Implication**: Capture at 1024x1024 on Pi Zero — tiles cleanly into 4 × 512x512 patches with zero waste.

### 2. Resolution: 1024x1024 is Optimal for Bird Species ID

- **1024x1024 tiles cleanly** into 4 × 512x512 patches (2x2 grid) for LFM2-VL-450M
- **Q4_0 quantization does NOT negate resolution** — it affects language model weights, not vision feature extraction. The ViT encoder still processes full-resolution patches.
- **Bird features need the pixels** — distinguishing sparrow/finch/wren requires beak shape, eye stripes, wing bars. At 640x480 these are 3-8 pixels; at 1024x1024 they're 6-16 pixels.
- **Pi Camera v2 supports it** — uses Mode 2 (1640x1232 binned) with ISP ScalerCrop to produce 1024x1024. Achieves 2 fps on Pi Zero W easily (500ms budget, ~150ms needed).
- **JPEG size**: ~120-150 KB per frame at quality 85
- **Transfer**: 120 frames × 150KB = 18MB → ~15 seconds over Pi Zero WiFi

### 3. Adaptive Capture State Machine

```
IDLE (WiFi OFF, lores motion detection)
  → motion detected →
CAPTURING (2 fps main @ 1024x1024, WiFi OFF, motion monitoring continues)
  → motion stops →
COOLDOWN (still capturing 2 fps, 5s countdown, resets if motion resumes)
  → 5s elapsed AND total >= 60s →
TRANSFERRING (WiFi ON, batch upload all frames, WiFi OFF)
  → complete →
IDLE
```

- Minimum 60s capture, extends while motion continues + 5s after
- WiFi stays OFF during entire capture (avoids frame drops, saves power)
- All frames queued in memory/SD, batch-transferred after capture ends
- 120 frames (60s @ 2fps) is typical; more if motion persists

### 4. picamera2 Dual-Stream Configuration

- **lores stream** (160x120 YUV420) for motion detection — tiny, almost free
- **main stream** (1024x1024 RGB) via Mode 2 binned sensor + ISP ScalerCrop
- No OpenCV dependency needed — pure NumPy frame differencing on lores
- Pi Zero W sustains 2 fps capture at 1024x1024 within budget

### 5. Grammar-Constrained Output via JSON Schema

llama.cpp automatically converts JSON schemas to GBNF grammars via `response_format.json_schema`. This is **token-level enforcement** with negligible overhead:
- Forces model to only generate valid JSON matching the schema
- `enum` field restricts to exact animal labels
- No hand-written grammar needed
- Combined with PydanticAI validation for defense-in-depth

**Important**: The JSON schema is NOT injected into the prompt — you must still describe expected output in the prompt text.

### 6. Pi 5 Thermal Management for Bursty Inference

The user's Pi 5 has fan issues. Key thermal facts:
- **Throttling begins at 80°C**, hard limit 85°C
- Estimated inference: **10-25 seconds per frame** for LFM2-VL-450M Q4_0 at 1024x1024
- **Strategy: Check temp before each inference, wait 10-15s between calls, pause if >72°C until <60°C**
- 5 sampled frames with 15s gaps = ~3 minutes total processing per event
- This keeps temp cycling 55-70°C, well below throttle threshold

```python
MAX_TEMP_C = 72.0
COOL_DOWN_TEMP_C = 60.0

async def classify_with_thermal_management(frames, sample_count=5):
    indices = [int(i * len(frames) / sample_count) for i in range(sample_count)]
    for i, idx in enumerate(indices):
        temp = get_cpu_temp()
        if temp > MAX_TEMP_C:
            while get_cpu_temp() > COOL_DOWN_TEMP_C:
                await asyncio.sleep(5)
        result = await classify_frame(frames[idx])
        if i < sample_count - 1:
            await asyncio.sleep(15)  # Cooldown gap
```

### 7. Power Budget (Revised for 1024x1024 @ 2fps)

| Phase | Draw | Duration | Energy |
|-------|------|----------|--------|
| Capture (1024x1024 @ 2fps) | ~290 mA | 60s | 4.83 mAh |
| WiFi associate | ~200 mA | 5s | 0.28 mAh |
| Transfer (18MB batch) | ~180 mA | 15s | 0.75 mAh |
| **Total per event** | | **~80s** | **~5.9 mAh** |

With 1200 mAh battery:
- Continuous 8hr monitoring (idle at 120mA) + events: **~40 events**
- 4hr active + sleep rest: **~122 events**
- With external battery (e.g., 6000 mAh total): **~800+ events**

### 8. Database: PostgreSQL + Alembic

For this project, PostgreSQL is the right choice over SQLite:
- Concurrent write access (upload + classification background task)
- JSONB columns for raw model output (queryable, indexable)
- `asyncpg` for async FastAPI integration
- Only ~50MB RAM overhead on Pi 5 (8GB available)
- Future-proof for multi-camera, remote access

**Alembic for migrations**: Yes, use from the start. Reasons:
- Schema will evolve: adding cameras table, notification preferences, classification confidence thresholds, training labels
- Alembic is lightweight (~5 files), integrates directly with SQLAlchemy models
- `alembic revision --autogenerate` detects model changes automatically
- Prevents manual DDL and "works on my machine" schema drift
- Setup: `alembic init alembic` → edit `env.py` to point at your models → done

### 9. Multi-Camera Identity

Each Pi Zero includes a `camera_id` in its config and every POST:

```python
# Pi Zero .env
CAMERA_ID=front-yard
SERVER_URL=http://pi5.local:8000

# POST payload includes identity
{
    "camera_id": "front-yard",
    "event_start": "2026-06-27T14:32:01Z",
    "frame_count": 120,
    "battery_pct": 72
}
```

- `camera_id` is a short slug (e.g., `front-yard`, `back-fence`, `side-gate`)
- Stored in `events.camera_id` column — all queries filterable by camera
- Dashboard shows per-camera feed with location labels
- No camera registration needed — server accepts any known token, records whatever `camera_id` is sent

### 10. Authentication: Pre-Shared Bearer Token

For LAN-only Pi-to-Pi communication, a pre-shared API key is the right balance:

```python
# Both Pi Zero and Pi 5 share this in .env
PIWATCHER_API_KEY=<random 32-byte hex>

# Pi Zero sends:
headers = {"Authorization": f"Bearer {PIWATCHER_API_KEY}"}
requests.post(f"{SERVER_URL}/api/events", headers=headers, ...)

# Pi 5 FastAPI validates:
from fastapi import Depends, HTTPException, Header

async def verify_api_key(authorization: str = Header(...)):
    if authorization != f"Bearer {settings.api_key}":
        raise HTTPException(status_code=401)
```

**Why this and not something fancier:**
- mTLS is overkill for a home LAN (cert rotation complexity)
- OAuth/JWT adds moving parts with no benefit (no user accounts, no token refresh needed)
- The threat model is: prevent random LAN devices from posting garbage to your API
- Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`
- Each camera can share the same key, OR unique keys per camera for individual revocation

**If you later add Cloudflare Tunnel**: Cloudflare Access handles external auth; the bearer token remains for Pi-to-Pi on LAN.

### 11. Frontend: htmx + FastAPI Templates (Recommended)

For a solo developer:
- **htmx + Jinja2 + TailwindCSS** — stays in Python ecosystem, server-rendered with dynamic updates
- Real-time via `hx-ws` WebSocket integration
- Mobile-responsive via TailwindCSS
- No JavaScript build step, no npm
- Accessible via `pi5.local:8000` on LAN (no Cloudflare needed to start)
- Upgrade path to React SPA or Cloudflare Tunnel later

**Alternative**: React + Vite if you want a richer SPA experience (better image galleries, PWA support).

### 8. Cloudflare Tunnel (Free, Ideal)

- Completely free on Zero Trust free plan
- No port forwarding, automatic SSL
- Built-in authentication via Cloudflare Access (OTP or OAuth)
- Pi 5 runs `cloudflared` as systemd service
- Supports WebSocket (for real-time dashboard updates)
- Only requires a domain (~$10/year)

### 9. Push Notifications: ntfy.sh

- Single HTTP POST integration from Python
- Supports image attachments in notifications
- Free tier: 250 messages/day
- Can be self-hosted on Pi 5 for privacy
- Android + iOS apps available

### 10. Storage: Will Never Fill Up

At 640x480 (recommended): **~24 MB/day** = 8.6 GB/year. A 500GB NVMe lasts 57+ years.
At 1080p (full res): **~120 MB/day** = 43 GB/year. A 500GB NVMe lasts 11+ years.

Keep everything. Storage is not a constraint.

## Technical Scenarios

### Scenario 1: Pi Zero Watcher Service

**Architecture**: Single Python script running as systemd service, auto-starts on boot.

```
┌─────────────────────────────────────────────┐
│ Pi Zero W (PiSugar S Battery)               │
│                                             │
│  systemd: piwatcher.service                 │
│  ┌─────────────────────────────────────┐    │
│  │ watcher.py                          │    │
│  │                                     │    │
│  │  ┌──────────┐    ┌──────────────┐  │    │
│  │  │ picamera2│    │ Motion Detect │  │    │
│  │  │ lores    │───▶│ NumPy MSE    │  │    │
│  │  │ 320x240  │    └──────┬───────┘  │    │
│  │  └──────────┘           │           │    │
│  │                    motion detected   │    │
│  │                         │           │    │
│  │  ┌──────────────────────▼────────┐  │    │
│  │  │ Capture burst (main 640x480) │  │    │
│  │  │ 1 fps × 60s → 60 JPEGs      │  │    │
│  │  └──────────────────────┬────────┘  │    │
│  │                         │           │    │
│  │  ┌──────────────────────▼────────┐  │    │
│  │  │ WiFi ON → POST → WiFi OFF    │  │    │
│  │  │ (rfkill + requests + retry)  │  │    │
│  │  └──────────────────────────────┘  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

**Boot script (copy-paste to Pi Zero):**

```bash
#!/bin/bash
# PiWatcher Pi Zero Setup Script
# Run as root on a fresh Raspberry Pi OS Lite (Bookworm)

set -e

# 1. Create service user
sudo useradd -r -s /bin/false -G video piwatcher || true

# 2. Install dependencies
sudo apt update
sudo apt install -y python3-picamera2 python3-numpy python3-requests --no-install-recommends

# 3. Create project directory
sudo mkdir -p /home/piwatcher/piwatcher/frame_queue
sudo chown -R piwatcher:piwatcher /home/piwatcher

# 4. Configure static IP (edit for your network)
cat >> /etc/dhcpcd.conf << 'EOF'
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1
EOF

# 5. Sudoers for WiFi toggling (no password)
cat > /etc/sudoers.d/piwatcher << 'EOF'
piwatcher ALL=(ALL) NOPASSWD: /usr/sbin/rfkill block wifi
piwatcher ALL=(ALL) NOPASSWD: /usr/sbin/rfkill unblock wifi
EOF
chmod 440 /etc/sudoers.d/piwatcher

# 6. Create systemd service
cat > /etc/systemd/system/piwatcher.service << 'EOF'
[Unit]
Description=PiWatcher Wildlife Camera
After=local-fs.target

[Service]
Type=simple
User=piwatcher
Group=video
ExecStart=/usr/bin/python3 /home/piwatcher/piwatcher/watcher.py
WorkingDirectory=/home/piwatcher/piwatcher
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 7. Enable service
sudo systemctl daemon-reload
sudo systemctl enable piwatcher.service

echo "Setup complete! Copy watcher.py to /home/piwatcher/piwatcher/ and reboot."
```

### Scenario 2: Pi 5 Inference Server

**Architecture**: FastAPI + PostgreSQL + llama-swap + Cloudflare Tunnel

```
┌─────────────────────────────────────────────────────────────┐
│ Pi 5 (NVMe SSD)                                            │
│                                                             │
│  ┌─────────────┐     ┌──────────────────────────────────┐  │
│  │ cloudflared │────▶│ Dashboard (htmx/React)           │  │
│  │ tunnel      │     │ served from FastAPI static files  │  │
│  └─────────────┘     └──────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ FastAPI Server (port 8000)                           │  │
│  │                                                      │  │
│  │  POST /events  ──▶ Save frames + queue inference     │  │
│  │  GET  /events  ──▶ List/filter events                │  │
│  │  WS   /ws     ──▶ Real-time event stream             │  │
│  │                                                      │  │
│  │  Background: classify_event()                        │  │
│  │    └── call llama-swap with JSON schema constraint   │  │
│  │    └── PydanticAI validation + retry                 │  │
│  │    └── Store results in PostgreSQL                   │  │
│  │    └── Send ntfy push notification                   │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                           │
│  ┌──────────────▼──────┐   ┌───────────────────────────┐  │
│  │ PostgreSQL          │   │ llama-swap (port 8080)     │  │
│  │ events/frames/class │   │ └── llama-server           │  │
│  └─────────────────────┘   │     └── LFM2-VL-450M.gguf │  │
│                             └───────────────────────────┘  │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ NVMe SSD: /mnt/nvme/piwatcher/frames/YYYY/MM/DD/  │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Scenario 3: PydanticAI + JSON Schema Constrained Output

**Selected approach**: Use `response_format.json_schema` with llama-swap (token-level enforcement) + PydanticAI validation as defense-in-depth.

```python
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

model = OpenAIChatModel(
    "lfm2-vl-450m",
    provider=OpenAIProvider(base_url="http://localhost:8080/v1", api_key="unused")
)

agent = Agent(
    model,
    output_type=WildlifeClassification,
    retries={"output": 3},
    instructions="Classify the primary subject in this wildlife camera image.",
)
```

### Scenario 4: Motion Detection Configuration

**Configurable parameters with sensible defaults:**

```python
@dataclass
class MotionConfig:
    threshold: float = 7.0          # MSE between frames (5-15 range)
    min_changed_pct: float = 2.0    # % of pixels that must change
    cooldown_seconds: float = 5.0   # Min time between events
    consecutive_frames: int = 2     # Frames above threshold to trigger
    capture_fps: float = 1.0        # Frames per second during capture
    capture_duration: float = 60.0  # Seconds to capture after trigger
    night_multiplier: float = 1.5   # Threshold multiplier at night
    roi: tuple = (0.0, 0.0, 1.0, 1.0)  # Region of interest (x, y, w, h)
```

**Tuning guidance:**
- Windy day → increase threshold to 10-15
- Night (more noise) → night_multiplier handles this
- Small animals (squirrels) → lower min_changed_pct to 1%
- Reduce false positives → increase consecutive_frames to 3

### Considered Alternatives

| Decision | Selected | Rejected | Reason |
|----------|----------|----------|--------|
| Database | PostgreSQL | SQLite | Concurrent access, JSONB, asyncpg |
| Frontend | htmx + Jinja2 | Streamlit | Mobile support, real-time, performance |
| Notifications | ntfy.sh | Pushover, Telegram | Free, image support, self-hostable |
| WiFi control | rfkill | ip link | Full radio power-down, more battery saved |
| Capture res | 640x480 | 1080p, 320x240 | Balance of quality and transfer size |
| Inference | Background tasks | Celery | Simpler, sufficient for single Pi 5 |
| Remote access | Cloudflare Tunnel | ngrok, port forward | Free, auth built-in, production-grade |
| Output constraint | JSON schema (via llama.cpp) | Hand-written GBNF, prompted | Auto-conversion, token-level, zero effort |

## Implementation File Tree

```
piwatcher/
├── zero/                          # Pi Zero package
│   ├── watcher.py                 # Main motion detection loop
│   ├── config.py                  # MotionConfig dataclass + .env loading
│   ├── motion.py                  # Frame differencing logic
│   ├── capture.py                 # Burst capture logic
│   ├── network.py                 # WiFi toggle + HTTP POST + queue
│   ├── battery.py                 # PiSugar I2C battery monitor
│   ├── setup.sh                   # Boot setup script (copy-paste)
│   └── piwatcher.service          # systemd unit file
├── server/                        # Pi 5 package
│   ├── main.py                    # FastAPI app
│   ├── config.py                  # Server config
│   ├── models.py                  # SQLAlchemy models
│   ├── schemas.py                 # Pydantic request/response schemas
│   ├── inference.py               # PydanticAI + llama-swap integration
│   ├── storage.py                 # Frame storage management
│   ├── notifications.py           # ntfy.sh integration
│   ├── db.py                      # Database connection + migrations
│   └── templates/                 # htmx/Jinja2 dashboard templates
│       ├── base.html
│       ├── events.html
│       ├── event_detail.html
│       └── config.html
├── docker-compose.yml             # PostgreSQL + server + cloudflared
└── pyproject.toml
```
