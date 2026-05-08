"""
OpenRouter: image-to-image «после» через модель с output modality image.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Any, Optional

import httpx

from config import (
    HTTPS_PROXY,
    OPENROUTER_API_KEY,
    OPENROUTER_CHAT_COMPLETIONS_URL,
    OPENROUTER_IMAGE_FALLBACK_MODEL,
    OPENROUTER_IMAGE_MODEL,
)

logger = logging.getLogger(__name__)


def _payload_modalities_and_image_config(model_id: str) -> tuple[list[str], dict[str, str] | None]:
    """Gemini: image+text + size; Flux/BFL: modality image + aspect 9:16 (иначе часто уезжает в 16:9)."""
    mid = (model_id or "").lower()
    if mid.startswith("google/") or "gemini" in mid:
        return ["image", "text"], {"aspect_ratio": "9:16", "image_size": "1K"}
    return ["image"], {"aspect_ratio": "9:16"}


_DATA_URL_RE = re.compile(
    r"^data:(?P<mime>image/[\w+.-]+);base64,(?P<b64>[A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)


def _data_url_to_bytes(url: str) -> Optional[bytes]:
    m = _DATA_URL_RE.match(url.strip())
    if not m:
        return None
    raw = re.sub(r"\s+", "", m.group("b64"))
    try:
        return base64.b64decode(raw, validate=False)
    except Exception:
        return None


def _first_generated_image_bytes(message: dict[str, Any]) -> Optional[bytes]:
    images = message.get("images")
    if not isinstance(images, list):
        return None
    for item in images:
        if not isinstance(item, dict):
            continue
        inner = item.get("image_url") or item.get("imageUrl")
        if isinstance(inner, dict):
            u = inner.get("url")
            if isinstance(u, str) and u.startswith("data:"):
                out = _data_url_to_bytes(u)
                if out:
                    return out
        if isinstance(inner, str) and inner.startswith("data:"):
            out = _data_url_to_bytes(inner)
            if out:
                return out
    return None


async def _generate_with_model(
    model_id: str,
    image_bytes: bytes,
    user_prompt: str,
    *,
    max_retries: int = 2,
) -> Optional[bytes]:
    """Один model slug + ретраи сети."""
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set")
        return None

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    modalities, image_config = _payload_modalities_and_image_config(model_id)

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "modalities": modalities,
    }
    if image_config is not None:
        payload["image_config"] = image_config

    proxy = HTTPS_PROXY if HTTPS_PROXY else None
    timeout = httpx.Timeout(connect=30, read=180, write=60, pool=30)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, proxy=proxy) as client:
                resp = await client.post(
                    OPENROUTER_CHAT_COMPLETIONS_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            choices = data.get("choices") if isinstance(data, dict) else None
            if not isinstance(choices, list) or not choices:
                logger.error("OpenRouter image (%s): no choices in response", model_id)
                return None

            first = choices[0]
            if not isinstance(first, dict):
                return None
            msg = first.get("message")
            if not isinstance(msg, dict):
                return None

            out = _first_generated_image_bytes(msg)
            if out:
                return out
            logger.warning(
                "OpenRouter image (%s): no images in assistant message (policy/refusal?)",
                model_id,
            )
            return None
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
        except httpx.HTTPStatusError as e:
            last_error = e
            status = getattr(e.response, "status_code", None)
            try:
                logger.warning(
                    "OpenRouter image (%s) HTTP %s: %s",
                    model_id,
                    status,
                    (e.response.text[:500] if e.response else ""),
                )
            except Exception:
                pass
            if status not in (429, 500, 502, 503, 504):
                break

        await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("OpenRouter image (%s) failed after retries: %r", model_id, last_error)
    return None


async def generate_after_reference_image(
    image_bytes: bytes,
    user_prompt: str,
    *,
    model: str | None = None,
    max_retries: int = 2,
) -> Optional[bytes]:
    """
    Отправляет референс + текст в модель с image output (modalities подбираются под id модели).
    Если основная модель не возвращает картинку (Flux часто режет реальных людей), пробует OPENROUTER_IMAGE_FALLBACK_MODEL.
    """
    primary = (model or OPENROUTER_IMAGE_MODEL).strip()
    chain = [primary]
    fb = OPENROUTER_IMAGE_FALLBACK_MODEL
    if fb and fb != primary:
        chain.append(fb)

    for mid in chain:
        logger.info("OpenRouter image: trying model %s", mid)
        out = await _generate_with_model(mid, image_bytes, user_prompt, max_retries=max_retries)
        if out:
            return out
        if len(chain) > 1 and mid == primary:
            logger.warning("OpenRouter image: primary model failed, trying fallback")

    return None
