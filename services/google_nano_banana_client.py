"""
Google Gemini Image (Nano Banana) — редактирование фото «после».
Модели: gemini-2.5-flash-image, gemini-3.1-flash-image-preview, gemini-3-pro-image-preview.
https://ai.google.dev/gemini-api/docs/image-generation
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

from google.genai import types

from config import (
    GOOGLE_AI_API_KEY,
    GOOGLE_NANO_BANANA_ASPECT_RATIO,
    GOOGLE_NANO_BANANA_MODEL,
)
from gemini_client import get_client
from prompts import after_body_image_negative_prompt

logger = logging.getLogger(__name__)


def _mime_and_name(image_bytes: bytes) -> tuple[str, str]:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "input.png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "input.jpg"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) > 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp", "input.webp"
    return "image/jpeg", "input.jpg"


def _extract_image_bytes(response) -> Optional[bytes]:
    parts = getattr(response, "parts", None)
    if parts:
        iterable = parts
    else:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        content = getattr(candidates[0], "content", None)
        if not content:
            return None
        iterable = getattr(content, "parts", None) or []

    for part in iterable:
        inline = getattr(part, "inline_data", None)
        if not inline:
            continue
        raw = getattr(inline, "data", None)
        if not raw:
            continue
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, str):
            return base64.b64decode(raw)
    return None


def _edit_after_body_sync(image_bytes: bytes, prompt: str) -> Optional[bytes]:
    if not GOOGLE_AI_API_KEY:
        logger.error("GOOGLE_AI_API_KEY is not set")
        return None

    mime, _ = _mime_and_name(image_bytes)
    full_prompt = f"{prompt}\n\nAvoid: {after_body_image_negative_prompt()}"

    client = get_client()
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(aspect_ratio=GOOGLE_NANO_BANANA_ASPECT_RATIO),
    )
    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type=mime),
        types.Part.from_text(text=full_prompt),
    ]

    response = client.models.generate_content(
        model=GOOGLE_NANO_BANANA_MODEL,
        contents=contents,
        config=config,
    )

    out = _extract_image_bytes(response)
    if out:
        logger.info(
            "Google Nano Banana ok model=%s output_bytes=%s",
            GOOGLE_NANO_BANANA_MODEL,
            len(out),
        )
    else:
        logger.error(
            "Google Nano Banana: no image in response model=%s",
            GOOGLE_NANO_BANANA_MODEL,
        )
    return out


async def edit_after_body_image_google(
    image_bytes: bytes,
    prompt: str,
    *,
    max_retries: int = 2,
) -> Optional[bytes]:
    """Кадр «после» через Gemini Image (Nano Banana)."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            loop = asyncio.get_running_loop()
            out = await loop.run_in_executor(
                None,
                _edit_after_body_sync,
                image_bytes,
                prompt,
            )
            if out:
                return out
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            retryable = any(
                x in msg
                for x in ("429", "quota", "resource_exhausted", "ssl", "timeout", "connect", "eof", "503", "500")
            )
            logger.warning(
                "Google Nano Banana attempt %s failed (retryable=%s): %s",
                attempt + 1,
                retryable,
                e,
            )
            if not retryable and attempt >= max_retries:
                break
        await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("Google Nano Banana edit failed: %r", last_exc)
    return None
