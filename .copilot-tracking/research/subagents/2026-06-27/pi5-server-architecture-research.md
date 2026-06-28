# Pi 5 Inference Server Architecture Research

## Research Topics

1. Liquid AI LFM2-VL-450M model specifications
2. llama-swap with vision models
3. PydanticAI for structured outputs
4. Grammar files / constrained output (GBNF)
5. FastAPI server design for image burst reception
6. PostgreSQL for event storage
7. Image storage strategy on NVMe SSD
8. Inference pipeline design

---

## 1. Liquid AI LFM2-VL-450M Model

### Key Specifications

- **Full name**: LFM2-VL-450M
- **Parameters**: ~450M (built on LFM2-350M language backbone + 86M SigLIP2 NaFlex vision encoder)
- **Architecture**: Three components — language model backbone (LFM2-350M), vision encoder (SigLIP2 NaFlex Base 86M), and multimodal projector (2-layer MLP with pixel unshuffle)
- **Input resolution**: Native resolution processing up to **512×512 pixels**. Larger images are split into non-overlapping 512×512 patches. No upscaling — handles smaller images natively
- **Aspect ratios**: Supports non-standard aspect ratios without distortion
- **Token generation from images**:
  - 256×384 image → 96 image tokens
  - 384×680 image → 240 image tokens
  - 1000×3000 image → 1,020 image tokens
- **Tunable parameters**: Max number of image tokens and number of image patches are user-tunable at inference time (speed-quality tradeoff without retraining)
- **License**: Open license based on Apache 2.0 — free for academic/research and commercial use under $10M revenue
- **Compatibility**: Currently compatible with Hugging Face transformers and TRL. Community integrations in progress for other frameworks
- **Design**: Optimized for on-device/edge deployment, low-latency inference
- **Inference speed**: Up to 2× faster than comparable VLMs on GPU

### Input Format

The model accepts:
- Text input (standard language model input)
- Image input at native resolution up to 512×512
- For larger images: automatic patch-based splitting into 512×512 non-overlapping patches

### Relevance for Wildlife Classification

- 450M parameters is ideal for Pi 5 with limited RAM/compute
- Native 512×512 resolution is perfect for wildlife camera frames (can downscale from higher res)
- Fast inference speed is critical for processing bursts of frames
- The model can describe scenes in natural language, which can be constrained to classification labels

---

## 2. llama-swap with Vision Models

### Overview

**Repository**: [mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap) (4,800+ stars)
**Language**: Go
**Purpose**: Reliable model swapping for any local OpenAI/Anthropic compatible server (llama.cpp, vllm, etc.)

### Supported API Endpoints

llama-swap proxies requests to underlying inference servers and supports:
- `v1/chat/completions` (OpenAI format)
- `v1/responses` (OpenAI responses format)
- `v1/completions`
- `v1/messages` (Anthropic format)
- `v1/messages/count_tokens`
- `v1/embeddings`
- `v1/rerank` / `v1/reranking`
- `v1/audio/transcriptions`
- `v1/images/generations`
- `/sdapi/v1/txt2img` / `img2img`

### Vision Model Configuration

In llama-swap config, vision capabilities are declared via the `capabilities` field:

```yaml
models:
  "lfm2-vl-450m":
    name: "LFM2-VL-450M Wildlife Classifier"
    cmd: |
      llama-server --port ${PORT}
      --model /path/to/lfm2-vl-450m.gguf
      --ctx-size 4096
      -ngl 99
    capabilities:
      in: ["text", "image"]
      out: ["text"]
      context: 4096
    ttl: 0  # never unload (always-on for wildlife classification)
```

When `in` contains `"image"`, llama-swap reports `"vision": true` in the `/v1/models` capabilities response.

### Sending Images via OpenAI-Compatible API

The llama-swap UI and API use the standard OpenAI chat completions vision format:

```json
{
  "model": "lfm2-vl-450m",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "Classify the animal in this image. Respond with JSON."
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
          }
        }
      ]
    }
  ],
  "max_tokens": 256,
  "temperature": 0.1
}
```

The image is sent as a **base64-encoded data URL** within the `content` array of the user message. This is the standard OpenAI vision API format that llama-swap passes through to the underlying llama-server.

### Key Configuration Options

- `ttl: 0` — Never unload the model (keep it always loaded for fast inference)
- `proxy` — URL where the underlying inference server listens
- `checkEndpoint` — Health check path (default: `/health`)
- `concurrencyLimit` — Limit concurrent requests to the model

---

## 3. PydanticAI for Structured Outputs

### Overview

PydanticAI is a Python agent framework by the Pydantic team for building production-grade applications with generative AI. It provides:

- Model-agnostic design (supports OpenAI, Anthropic, Google, Ollama, and any OpenAI-compatible API)
- Type-safe structured outputs using Pydantic models
- Validation with automatic retries
- Tool/function calling support

### Using with OpenAI-Compatible APIs

PydanticAI works with any OpenAI-compatible endpoint (like llama-swap) via `OpenAIChatModel`:

```python
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# Point to llama-swap's OpenAI-compatible endpoint
model = OpenAIChatModel(
    'lfm2-vl-450m',
    provider=OpenAIProvider(
        base_url='http://localhost:8080/v1',
        api_key='sk-unused'  # llama-swap may not require auth
    )
)

agent = Agent(model, output_type=ClassificationResult)
```

### Defining Structured Output Schemas

```python
from pydantic import BaseModel, Field
from typing import Literal

class AnimalClassification(BaseModel):
    """Classification of an animal detected in a wildlife camera image."""
    label: Literal[
        "deer", "bear", "coyote", "fox", "raccoon", "skunk",
        "rabbit", "squirrel", "bird", "turkey", "cat", "dog",
        "human", "vehicle", "unknown", "empty"
    ] = Field(description="The primary animal detected")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    description: str = Field(description="Brief description of what's in the image")

agent = Agent(
    model,
    output_type=AnimalClassification,
    instructions='Classify the animal in this wildlife camera image.',
)
```

### Output Modes

PydanticAI supports three output modes:

1. **Tool Output** (default): Uses the model's tool calling capability. The JSON schema is provided as a tool parameter schema. Works with most models.

2. **Native Output** (`NativeOutput`): Uses the model's native "Structured Outputs" / "JSON Schema response format" feature. The model is forced to only output text matching the JSON schema. Best for models that support it.

3. **Prompted Output** (`PromptedOutput`): Injects the schema into instructions and relies on the model to follow it. Uses JSON mode if available. Least reliable but works with all models.

For llama.cpp-backed models, **Prompted Output** may be the most practical since tool calling support varies:

```python
from pydantic_ai import Agent, PromptedOutput

agent = Agent(
    model,
    output_type=PromptedOutput(AnimalClassification),
    instructions='Classify the animal in this wildlife camera image.',
)
```

### Validation and Retries

PydanticAI automatically:
- Validates model output against the Pydantic schema
- Re-prompts the model if validation fails (configurable retry count)
- Supports custom output validators for additional logic

```python
from pydantic_ai import Agent, ModelRetry, RunContext

agent = Agent(model, output_type=AnimalClassification, retries={'output': 3})

@agent.output_validator
async def validate_classification(ctx: RunContext, output: AnimalClassification) -> AnimalClassification:
    if output.confidence < 0.1 and output.label != "unknown":
        raise ModelRetry("Very low confidence should use 'unknown' label")
    return output
```

### Grammar File Generation

PydanticAI does **not** directly generate GBNF grammar files. However, the approach of using `json_schema` with llama.cpp's server achieves similar constrained output at the token level (see section 4).

---

## 4. Grammar Files / Constrained Output (GBNF)

### What is GBNF?

GBNF (GGML BNF) is a format for defining formal grammars to constrain model outputs in llama.cpp. It forces the model to generate only text matching a defined pattern at the **token level** — tokens that would violate the grammar are masked out during sampling.

### Using with llama.cpp Server (and llama-swap)

llama.cpp's server supports two ways to constrain output:

1. **Direct grammar** — pass a GBNF grammar string as the `grammar` body field
2. **JSON schema** — pass a JSON schema as `json_schema` body field or in `response_format`

Since llama-swap proxies requests directly to llama-server, both methods work.

### JSON Schema Approach (Recommended)

llama.cpp automatically converts JSON schemas to GBNF grammars. This is the simplest approach:

```json
{
  "model": "lfm2-vl-450m",
  "messages": [...],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "schema": {
        "type": "object",
        "properties": {
          "label": {
            "type": "string",
            "enum": ["deer", "bear", "coyote", "fox", "raccoon", "skunk",
                     "rabbit", "squirrel", "bird", "turkey", "cat", "dog",
                     "human", "vehicle", "unknown", "empty"]
          },
          "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
          },
          "description": {
            "type": "string",
            "maxLength": 200
          }
        },
        "required": ["label", "confidence"],
        "additionalProperties": false
      }
    }
  }
}
```

### Custom GBNF Grammar for Wildlife Classification

```gbnf
root ::= "{" ws "\"label\":" ws label "," ws "\"confidence\":" ws confidence ("," ws "\"description\":" ws string)? ws "}"

label ::= "\"deer\"" | "\"bear\"" | "\"coyote\"" | "\"fox\"" | "\"raccoon\"" | "\"skunk\"" | "\"rabbit\"" | "\"squirrel\"" | "\"bird\"" | "\"turkey\"" | "\"cat\"" | "\"dog\"" | "\"human\"" | "\"vehicle\"" | "\"unknown\"" | "\"empty\""

confidence ::= "0" ("." [0-9]{1,3})? | "1" (".0"{0,3})?

string ::= "\"" [^"\\]* "\""

ws ::= [ \t\n]*
```

### Performance Impact

- **Minimal overhead** — grammar-constrained sampling adds negligible latency since it only masks logits
- **Faster generation** — constrained output is often shorter and more deterministic, reducing total tokens generated
- **No hallucinated keys** — the model cannot produce malformed JSON or unexpected fields

### Grammar vs JSON Mode vs Structured Outputs

| Approach | Reliability | Speed | Flexibility |
|----------|-------------|-------|-------------|
| GBNF Grammar / JSON Schema | Highest — token-level enforcement | Fastest — shorter output | Fixed schema only |
| JSON Mode | Medium — valid JSON but may not match schema | Medium | Any JSON structure |
| Prompted Output | Lowest — model may ignore instructions | Slowest — verbose output | Most flexible |

**Recommendation**: Use `response_format` with `json_schema` when calling llama-swap. This gives token-level constraint enforcement with no grammar authoring needed.

### Important Note from llama.cpp Docs

> The JSON schema is only used to constrain the model output and is NOT injected into the prompt. The model has no visibility into the schema, so if you want it to understand the expected structure, describe it explicitly in your prompt.

This means the prompt must still explain what labels to use and what the fields mean.

---

## 5. FastAPI Server Design

### Proposed API Endpoints

```python
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

app = FastAPI(title="PiWatcher Inference Server", version="0.1.0")

# --- Models ---

class EventMetadata(BaseModel):
    camera_id: str
    timestamp: datetime
    battery_level: Optional[float] = None  # 0.0-1.0
    trigger_type: str = "motion"  # motion, scheduled, manual

class FrameClassification(BaseModel):
    label: str
    confidence: float
    description: Optional[str] = None
    model_name: str = "lfm2-vl-450m"

class EventResponse(BaseModel):
    event_id: str
    timestamp: datetime
    frame_count: int
    status: str  # "pending", "processing", "complete", "failed"
    classifications: Optional[list[FrameClassification]] = None

class EventListResponse(BaseModel):
    events: list[EventResponse]
    total: int
    page: int
    page_size: int

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    disk_usage_percent: float
    uptime_seconds: float
    pending_classifications: int


# --- Endpoints ---

@app.post("/events", response_model=EventResponse, status_code=201)
async def create_event(
    background_tasks: BackgroundTasks,
    frames: list[UploadFile] = File(...),
    camera_id: str = Form(...),
    timestamp: str = Form(...),
    battery_level: Optional[float] = Form(None),
    trigger_type: str = Form("motion"),
):
    """
    Receive a burst of JPEG frames from a camera with metadata.
    Saves frames to disk and queues for classification.
    """
    event_id = str(uuid.uuid4())
    # Save frames, create DB record, queue classification
    background_tasks.add_task(classify_event, event_id)
    return EventResponse(
        event_id=event_id,
        timestamp=datetime.fromisoformat(timestamp),
        frame_count=len(frames),
        status="pending",
    )


@app.get("/events", response_model=EventListResponse)
async def list_events(
    camera_id: Optional[str] = None,
    label: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20,
):
    """List events with optional filtering."""
    ...


@app.get("/events/{event_id}", response_model=EventResponse)
async def get_event(event_id: str):
    """Get event details including classification results."""
    ...


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Server health status."""
    ...
```

### Async Patterns — Background Task vs Synchronous

**Recommended: Background Tasks with FastAPI**

```python
from fastapi import BackgroundTasks
import asyncio
from collections import deque

# Simple in-process queue
classification_queue: deque = deque()

async def classify_event(event_id: str):
    """Background task to classify all frames in an event."""
    frames = await get_event_frames(event_id)
    results = []
    for frame in frames:
        classification = await call_llama_swap(frame.file_path)
        results.append(classification)
    await save_classifications(event_id, results)
    await update_event_status(event_id, "complete")
```

**Why not Celery?**

- Overkill for a single Pi 5 with one inference model
- Adds Redis/RabbitMQ dependency
- FastAPI's `BackgroundTasks` or `asyncio.Queue` is sufficient
- If needed later, can upgrade to `arq` (async Redis queue) which is lighter than Celery

**Recommended approach**:
- Use `BackgroundTasks` for fire-and-forget classification after upload
- Use `asyncio.Semaphore` to limit concurrent inference calls (since the model can only handle one at a time on Pi 5)
- Return immediately to the camera with a 201 + event_id
- Camera can poll or use webhook for results

```python
# Semaphore to ensure only one inference at a time
inference_semaphore = asyncio.Semaphore(1)

async def call_llama_swap(image_path: str) -> AnimalClassification:
    async with inference_semaphore:
        async with httpx.AsyncClient() as client:
            # Read and encode image
            image_b64 = base64.b64encode(open(image_path, 'rb').read()).decode()
            response = await client.post(
                "http://localhost:8080/v1/chat/completions",
                json={
                    "model": "lfm2-vl-450m",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": CLASSIFICATION_PROMPT},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                        ]
                    }],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"schema": CLASSIFICATION_SCHEMA}
                    },
                    "max_tokens": 128,
                    "temperature": 0.1,
                },
                timeout=60.0,
            )
            # Parse and validate
            ...
```

---

## 6. PostgreSQL for Event Storage

### Schema Design

```sql
-- Events table
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    duration_seconds FLOAT,
    frame_count INTEGER NOT NULL,
    battery_level FLOAT,
    trigger_type VARCHAR(32) DEFAULT 'motion',
    status VARCHAR(32) DEFAULT 'pending',  -- pending, processing, complete, failed
    primary_label VARCHAR(64),  -- Dominant classification for quick filtering
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX idx_events_camera_id ON events(camera_id);
CREATE INDEX idx_events_primary_label ON events(primary_label);
CREATE INDEX idx_events_status ON events(status);

-- Frames table
CREATE TABLE frames (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size_bytes INTEGER,
    width INTEGER,
    height INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_frames_event_id ON frames(event_id);

-- Classifications table
CREATE TABLE classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    frame_id UUID NOT NULL REFERENCES frames(id) ON DELETE CASCADE,
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(64),
    label VARCHAR(64) NOT NULL,
    confidence FLOAT NOT NULL,
    description TEXT,
    raw_output JSONB,  -- Full model response for debugging/retraining
    inference_time_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_classifications_frame_id ON classifications(frame_id);
CREATE INDEX idx_classifications_label ON classifications(label);
CREATE INDEX idx_classifications_confidence ON classifications(confidence);
```

### PostgreSQL vs SQLite Analysis

| Factor | PostgreSQL | SQLite |
|--------|-----------|--------|
| Concurrent access | Excellent — multiple readers/writers | Limited — single writer lock |
| JSON support | JSONB with indexing, querying | JSON1 extension, limited |
| Full-text search | Built-in `tsvector` | FTS5 extension |
| Async support | Native with asyncpg | Needs aiosqlite wrapper |
| Memory footprint | ~50-100MB idle | ~0 (embedded) |
| Future scaling | Easy to migrate to remote DB | Would require rewrite |
| Backup | pg_dump, streaming replication | Just copy the file |
| Complex queries | Full SQL, CTEs, window functions | Full SQL but slower |
| Operational burden | Needs service management | Zero administration |

### Recommendation: Start with PostgreSQL

For a Pi 5 with NVMe SSD, PostgreSQL is justified because:

1. **Concurrent access** — The FastAPI server writes events while background tasks write classifications. SQLite's write lock would create contention.
2. **JSONB columns** — Store raw model output efficiently, with ability to query into it later.
3. **Future-proof** — If you add a web dashboard, multiple cameras, or remote access, PostgreSQL handles it without migration.
4. **Pi 5 has resources** — With 8GB RAM and NVMe SSD, PostgreSQL's overhead (~50MB RAM) is negligible.

**However**: If simplicity is paramount and there's only one camera with low event rate, SQLite is perfectly fine. You can always migrate later.

### Using with Python (asyncpg + SQLAlchemy)

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import JSON
import uuid
from datetime import datetime

engine = create_async_engine("postgresql+asyncpg://piwatcher:password@localhost/piwatcher")

class Base(DeclarativeBase):
    pass

class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[str]
    timestamp: Mapped[datetime]
    frame_count: Mapped[int]
    status: Mapped[str] = mapped_column(default="pending")
    primary_label: Mapped[str | None]

class Classification(Base):
    __tablename__ = "classifications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    frame_id: Mapped[uuid.UUID]
    model_name: Mapped[str]
    label: Mapped[str]
    confidence: Mapped[float]
    raw_output: Mapped[dict] = mapped_column(JSON)
```

---

## 7. Image Storage Strategy

### Filesystem Layout

Recommended: **Date-based hierarchy with event subdirectories**

```
/mnt/nvme/piwatcher/
├── frames/
│   ├── 2026/
│   │   ├── 06/
│   │   │   ├── 27/
│   │   │   │   ├── {event_id}/
│   │   │   │   │   ├── frame_001.jpg
│   │   │   │   │   ├── frame_002.jpg
│   │   │   │   │   └── ...
│   │   │   │   └── {event_id}/
│   │   │   │       └── ...
│   │   │   └── 28/
│   │   └── 07/
│   └── ...
├── thumbnails/  # Optional: downscaled versions for quick browsing
│   └── (same structure)
└── exports/  # For training data exports
```

**Why this layout?**
- Easy to find events by date
- Easy to archive/delete old data by date
- No single directory gets too large
- Event grouping preserves burst context

### Storage Estimates

| Parameter | Value |
|-----------|-------|
| Frame resolution (Pi Zero camera) | 1920×1080 JPEG |
| Average JPEG size (outdoor scene) | ~150-250 KB |
| Frames per event (1 fps × 60s) | 60 frames |
| Events per day (moderate activity) | 5-15 events |
| Daily storage (10 events × 60 frames × 200KB) | ~120 MB/day |
| Monthly storage | ~3.6 GB/month |
| Yearly storage | ~43 GB/year |

**With lower resolution (640×480 for inference):**

| Parameter | Value |
|-----------|-------|
| Frame size at 640×480 JPEG | ~30-50 KB |
| Daily storage (10 events × 60 frames × 40KB) | ~24 MB/day |
| Monthly | ~720 MB/month |
| Yearly | ~8.6 GB/year |

### NVMe SSD Fill Time

| SSD Size | At full res (120 MB/day) | At 640×480 (24 MB/day) | At full res (high activity, 30 events/day) |
|----------|--------------------------|--------------------------|---------------------------------------------|
| 256 GB | ~5.8 years | ~29 years | ~1.9 years |
| 500 GB | ~11.4 years | ~57 years | ~3.8 years |
| 1 TB | ~22.8 years | ~114 years | ~7.6 years |

### Recommendation

1. **Store originals at full resolution** — disk is cheap, retraining data is valuable
2. **Create 512×512 resized copies for inference** (matches LFM2-VL native resolution)
3. **Implement retention policy** — keep originals for 90 days, keep classified "interesting" frames indefinitely
4. **Database tracks file paths** — never rely on filesystem traversal for lookups

### Retention Cron

```python
# Delete frames older than 90 days for "empty" classifications
# Keep frames with animal detections indefinitely
async def cleanup_old_frames():
    cutoff = datetime.now() - timedelta(days=90)
    # Delete frames where all classifications are "empty" and older than cutoff
    ...
```

---

## 8. Inference Pipeline Design

### Flow Diagram

```
Camera (Pi Zero) → POST /events (multipart) → FastAPI Server (Pi 5)
                                                    │
                                                    ├── 1. Save frames to disk
                                                    ├── 2. Create DB event record (status: "pending")
                                                    ├── 3. Return 201 with event_id
                                                    │
                                                    └── 4. Background task triggered
                                                            │
                                                            ├── 5. Update status → "processing"
                                                            ├── 6. For each frame (or sampled subset):
                                                            │       ├── Resize to 512×512
                                                            │       ├── Base64 encode
                                                            │       ├── Call llama-swap /v1/chat/completions
                                                            │       ├── Parse JSON response
                                                            │       └── Save classification to DB
                                                            ├── 7. Determine primary_label (majority vote)
                                                            └── 8. Update status → "complete"
```

### Synchronous vs Async Inference

**Recommendation: Asynchronous (background task)**

Reasons:
- Camera should not block waiting for classification (battery-powered, needs to return to sleep)
- Inference takes 2-10 seconds per frame on Pi 5 (60 frames × 5s = 5 minutes per event)
- Camera upload should complete in seconds, not minutes
- Allows queuing multiple events if camera triggers rapidly

### Frame Sampling Strategy

Processing all 60 frames is expensive. Recommended approach:

```python
async def classify_event(event_id: str):
    frames = await get_event_frames(event_id)

    # Strategy: classify a subset of frames
    # - First frame, last frame, and every Nth frame
    # - Or: first 3 frames + frames at 25%, 50%, 75% marks
    sample_indices = get_sample_indices(len(frames), max_samples=5)

    classifications = []
    for idx in sample_indices:
        frame = frames[idx]
        result = await call_llama_swap(frame.file_path)
        classifications.append(result)

    # Determine primary label by majority vote / highest confidence
    primary = max(classifications, key=lambda c: c.confidence)
    await update_event(event_id, primary_label=primary.label, status="complete")
```

### Batching Consideration

llama.cpp (and by extension llama-swap) processes requests **sequentially** for vision models — there's no batch endpoint. Each image requires a separate API call. However, you can:

1. **Pipeline sequential calls** — send the next request as soon as the previous completes
2. **Limit samples** — classify 3-5 representative frames instead of all 60
3. **Early termination** — if first 3 frames all agree on a label with high confidence, skip the rest

### Complete Pipeline Code Example

```python
import asyncio
import base64
import httpx
from pathlib import Path

LLAMA_SWAP_URL = "http://localhost:8080/v1/chat/completions"
MODEL_NAME = "lfm2-vl-450m"

CLASSIFICATION_PROMPT = """Analyze this wildlife camera image. Identify the primary subject.
Respond with a JSON object containing:
- "label": one of [deer, bear, coyote, fox, raccoon, skunk, rabbit, squirrel, bird, turkey, cat, dog, human, vehicle, unknown, empty]
- "confidence": a number between 0 and 1
- "description": a brief description (max 100 chars)"""

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {
            "type": "string",
            "enum": ["deer", "bear", "coyote", "fox", "raccoon", "skunk",
                     "rabbit", "squirrel", "bird", "turkey", "cat", "dog",
                     "human", "vehicle", "unknown", "empty"]
        },
        "confidence": {"type": "number"},
        "description": {"type": "string"}
    },
    "required": ["label", "confidence"],
    "additionalProperties": False
}

inference_semaphore = asyncio.Semaphore(1)  # One inference at a time

async def classify_frame(client: httpx.AsyncClient, image_path: Path) -> dict:
    """Classify a single frame using the vision model."""
    async with inference_semaphore:
        image_bytes = image_path.read_bytes()
        image_b64 = base64.b64encode(image_bytes).decode()

        response = await client.post(
            LLAMA_SWAP_URL,
            json={
                "model": MODEL_NAME,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": CLASSIFICATION_PROMPT},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }}
                    ]
                }],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"schema": CLASSIFICATION_SCHEMA}
                },
                "max_tokens": 128,
                "temperature": 0.1,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)


async def classify_event(event_id: str):
    """Classify sampled frames from an event."""
    frames = await get_event_frames(event_id)
    await update_event_status(event_id, "processing")

    # Sample 5 frames evenly distributed
    indices = get_sample_indices(len(frames), max_samples=5)

    async with httpx.AsyncClient() as client:
        for idx in indices:
            frame = frames[idx]
            try:
                result = await classify_frame(client, Path(frame.file_path))
                await save_classification(frame.id, result)
            except Exception as e:
                logging.error(f"Classification failed for frame {frame.id}: {e}")

    # Determine primary label
    classifications = await get_classifications_for_event(event_id)
    if classifications:
        primary = max(classifications, key=lambda c: c.confidence)
        await update_event(event_id, primary_label=primary.label, status="complete")
    else:
        await update_event_status(event_id, "failed")
```

---

## Key Recommendations Summary

1. **Model**: LFM2-VL-450M is well-suited — 450M params, native 512×512 resolution, edge-optimized
2. **Serving**: llama-swap with `ttl: 0` (always loaded), vision capability declared in config
3. **API Format**: OpenAI chat completions with base64 images in content array
4. **Constrained Output**: Use `response_format.json_schema` for token-level enforcement of classification schema
5. **Structured Parsing**: PydanticAI with `PromptedOutput` mode, or parse JSON directly with Pydantic validation
6. **Server**: FastAPI with async background tasks, `asyncio.Semaphore(1)` for inference serialization
7. **Database**: PostgreSQL with JSONB for raw outputs, indexed classification labels
8. **Storage**: Date/event hierarchy on NVMe, full-resolution originals, 512×512 inference copies
9. **Pipeline**: Async classification with frame sampling (5 representative frames per event)
10. **Retention**: 90-day default, indefinite for interesting detections

---

## Follow-On Questions

- What GGUF quantization of LFM2-VL-450M is available? (Q4_K_M would be ideal for Pi 5 with 8GB RAM)
- Does llama.cpp have full support for the LFM2-VL architecture, or is a custom build needed?
- What is the actual inference latency per frame on Pi 5 (ARM Cortex-A76) with this model?
- Should the Pi Zero send all frames or pre-filter (motion detection) before sending?

## References

- Liquid AI LFM2-VL blog post: https://www.liquid.ai/blog/lfm2-vl-efficient-vision-language-models
- llama-swap repository: https://github.com/mostlygeek/llama-swap
- llama-swap configuration docs: https://github.com/mostlygeek/llama-swap/blob/main/docs/configuration.md
- PydanticAI documentation: https://pydantic.dev/docs/ai/overview/
- PydanticAI output modes: https://pydantic.dev/docs/ai/core-concepts/output/
- PydanticAI models overview: https://pydantic.dev/docs/ai/models/overview/
- GBNF grammar guide: https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- Liquid AI Hugging Face: https://huggingface.co/LiquidAI
