"""Inference adapter and thermal management for llama-swap classification."""

import asyncio
import base64
import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from .config import Settings, get_settings
from .db import session_scope
from .models import Event
from .notifications import notify_detection

logger = logging.getLogger(__name__)

ALLOWED_LABELS: tuple[str, ...] = (
    "deer",
    "bear",
    "coyote",
    "fox",
    "raccoon",
    "skunk",
    "rabbit",
    "squirrel",
    "bird",
    "turkey",
    "cat",
    "dog",
    "human",
    "vehicle",
    "unknown",
    "empty",
)

WildlifeLabel = Literal[
    "deer",
    "bear",
    "coyote",
    "fox",
    "raccoon",
    "skunk",
    "rabbit",
    "squirrel",
    "bird",
    "turkey",
    "cat",
    "dog",
    "human",
    "vehicle",
    "unknown",
    "empty",
]

LABEL_ALIASES: dict[str, WildlifeLabel] = {
    "animal": "unknown",
    "animals": "unknown",
    "birds": "bird",
    "car": "vehicle",
    "cars": "vehicle",
    "human being": "human",
    "man": "human",
    "none": "empty",
    "no animal": "empty",
    "no wildlife": "empty",
    "nothing": "empty",
    "person": "human",
    "people": "human",
    "truck": "vehicle",
    "vehicle": "vehicle",
    "wildlife": "unknown",
}


class WildlifeClassification(BaseModel):
    """Validated wildlife classification result."""

    label: WildlifeLabel
    confidence: float = Field(ge=0.0, le=1.0)
    description: str = Field(max_length=200)


def classification_prompt_text() -> str:
    """Return the frame-classification instruction sent to the local model."""

    return (
        "What is the main thing visible in this image? "
        "Choose the closest label from the schema and describe only what you actually see. "
        "Use unknown if the subject is unclear and empty if nothing relevant is visible."
    )


def response_format_json_schema() -> dict[str, Any]:
    """Return a strict schema payload for llama.cpp structured outputs."""

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "frame_classification",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "enum": list(ALLOWED_LABELS),
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "description": {
                        "type": "string",
                        "maxLength": 200,
                    },
                },
                "required": ["label", "confidence", "description"],
                "additionalProperties": False,
            },
        },
    }


def summarize_response_body(response: httpx.Response, limit: int = 500) -> str:
    """Return a bounded response body summary for inference diagnostics."""

    text = response.text.strip()
    if not text:
        return "<empty>"
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<truncated>"


def strip_json_fences(content: str) -> str:
    """Remove Markdown code fences around JSON model output."""

    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if not lines:
        return stripped

    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def normalize_label(label: str) -> WildlifeLabel:
    """Map model labels into the constrained dashboard taxonomy."""

    normalized = label.strip().lower()
    if normalized in ALLOWED_LABELS:
        return cast("WildlifeLabel", normalized)
    if normalized in LABEL_ALIASES:
        return LABEL_ALIASES[normalized]
    return "unknown"


def parse_classification_content(content: str) -> WildlifeClassification:
    """Parse model output, tolerating fenced JSON and loose labels."""

    parsed = json.loads(strip_json_fences(content))
    parsed["label"] = normalize_label(str(parsed.get("label", "unknown")))
    return WildlifeClassification.model_validate(parsed)


class LlamaSwapClassifier:
    """Thin OpenAI-compatible llama-swap classifier adapter."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def classify_frame(self, frame_path: Path) -> WildlifeClassification:
        """Classify one frame through llama-swap's OpenAI-compatible endpoint."""

        image_data = base64.b64encode(frame_path.read_bytes()).decode("ascii")
        payload = {
            "model": self.settings.llama_swap_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": classification_prompt_text(),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                        },
                    ],
                }
            ],
            "response_format": response_format_json_schema(),
            "temperature": 0,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.llama_swap_url.rstrip('/')}/chat/completions",
                json=payload,
            )
        try:
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return parse_classification_content(content)
        except httpx.HTTPStatusError:
            logger.warning(
                "Inference endpoint returned HTTP %s: %s",
                response.status_code,
                summarize_response_body(response),
            )
            raise
        except (KeyError, ValidationError, json.JSONDecodeError) as exc:
            logger.warning(
                "Inference endpoint returned an unusable response: %s; body=%s",
                exc,
                summarize_response_body(response),
            )
            raise


def get_cpu_temp() -> float:
    """Read Pi CPU temperature in Celsius, returning 0.0 when unavailable."""

    temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if not temp_path.exists():
        return 0.0
    return float(temp_path.read_text(encoding="utf-8").strip()) / 1000.0


def sample_frame_paths(frame_paths: list[Path], sample_count: int = 5) -> list[Path]:
    """Sample frames evenly across an event."""

    if len(frame_paths) <= sample_count:
        return frame_paths
    last_index = len(frame_paths) - 1
    return [
        frame_paths[round(index * last_index / (sample_count - 1))] for index in range(sample_count)
    ]


async def wait_for_safe_temperature(settings: Settings) -> None:
    """Pause inference while CPU temperature is above the configured ceiling."""

    if get_cpu_temp() <= settings.max_inference_temp_c:
        return
    while get_cpu_temp() > settings.cooldown_temp_c:
        await asyncio.sleep(5)


def choose_classification(
    results: list[WildlifeClassification],
) -> WildlifeClassification:
    """Choose the majority label, using confidence as the tie-breaker."""

    if not results:
        return WildlifeClassification(
            label="unknown",
            confidence=0.0,
            description="No frames classified",
        )

    label_counts = Counter(result.label for result in results)
    top_count = label_counts.most_common(1)[0][1]
    candidate_labels = {label for label, count in label_counts.items() if count == top_count}
    return max(
        (result for result in results if result.label in candidate_labels),
        key=lambda result: result.confidence,
    )


async def classify_event_background(event_id: int, frame_paths: list[Path]) -> None:
    """Classify sampled event frames and store the aggregate result."""

    settings = get_settings()
    if not settings.inference_enabled:
        logger.info("Inference disabled; skipping classification for event %s", event_id)
        return

    classifier = LlamaSwapClassifier(settings)
    sampled_paths = sample_frame_paths(frame_paths)
    results: list[WildlifeClassification] = []
    logger.info(
        "Starting inference for event %s with %s sampled frames via %s",
        event_id,
        len(sampled_paths),
        settings.llama_swap_url,
    )

    for index, frame_path in enumerate(sampled_paths):
        await wait_for_safe_temperature(settings)
        try:
            results.append(await classifier.classify_frame(frame_path))
        except httpx.ConnectError as exc:
            logger.warning(
                "Inference endpoint unavailable; skipping classification for event %s: %s",
                event_id,
                exc,
            )
            break
        except (
            httpx.HTTPError,
            OSError,
            KeyError,
            ValidationError,
            json.JSONDecodeError,
        ):
            logger.warning("Failed to classify frame %s for event %s", frame_path, event_id)
        if index < len(sampled_paths) - 1 and settings.inference_gap_seconds > 0:
            await asyncio.sleep(settings.inference_gap_seconds)

    classification = choose_classification(results)
    logger.info(
        "Finished inference for event %s with label=%s confidence=%.3f from %s successful samples",
        event_id,
        classification.label,
        classification.confidence,
        len(results),
    )
    raw_classification = {
        "samples": [result.model_dump() for result in results],
        "selected": classification.model_dump(),
    }

    async with session_scope() as session:
        event = await session.scalar(select(Event).where(Event.id == event_id))
        if event is None:
            logger.warning("Event %s disappeared before classification could be stored", event_id)
            return
        event.label = classification.label
        event.confidence = classification.confidence
        event.raw_classification = raw_classification
        event.classified_at = datetime.now(UTC)
        await session.commit()

        if classification.label not in {"empty", "unknown"}:
            await notify_detection(
                classification.label,
                classification.confidence,
                event.camera_id,
                thumbnail_path=sampled_paths[0] if sampled_paths else None,
                ntfy_url=settings.ntfy_url,
                ntfy_topic=settings.ntfy_topic,
            )
