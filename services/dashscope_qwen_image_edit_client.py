"""
Qwen Image Edit (Model Studio): один референс + текст → PNG по URL из ответа.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Mapping, Optional

import httpx

from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_HTTP_ORIGIN,
    DASHSCOPE_QWEN_AFTER_PROMPT_EXTEND,
    DASHSCOPE_QWEN_IMAGE_EDIT_AFTER_MODEL,
    DASHSCOPE_QWEN_IMAGE_EDIT_MODEL,
    DASHSCOPE_QWEN_IMAGE_EDIT_SIZE,
    HTTPS_PROXY,
)

logger = logging.getLogger(__name__)

_GEN_PATH = "/api/v1/services/aigc/multimodal-generation/generation"


def _data_url_from_image_bytes(image_bytes: bytes) -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif image_bytes.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif image_bytes.startswith(b"RIFF") and len(image_bytes) > 12 and image_bytes[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


def _first_image_url(data: Mapping[str, Any]) -> Optional[str]:
    out = data.get("output")
    if not isinstance(out, Mapping):
        return None
    choices = out.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    ch0 = choices[0]
    if not isinstance(ch0, Mapping):
        return None
    msg = ch0.get("message")
    if not isinstance(msg, Mapping):
        return None
    content = msg.get("content")
    if not isinstance(content, list):
        return None
    for part in content:
        if not isinstance(part, Mapping):
            continue
        u = part.get("image")
        if isinstance(u, str) and u.startswith("http"):
            return u
    return None


async def _qwen_image_edit(
    image_bytes: bytes,
    prompt: str,
    *,
    model: str,
    max_retries: int = 2,
    prompt_extend: bool = True,
) -> Optional[bytes]:
    if not DASHSCOPE_API_KEY:
        logger.error("DASHSCOPE_API_KEY / ALIBABA_MODEL_STUDIO_API_KEY is not set")
        return None

    data_url = _data_url_from_image_bytes(image_bytes)

    body: dict[str, Any] = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": data_url},
                        {"text": prompt},
                    ],
                }
            ]
        },
        "parameters": {
            "n": 1,
            "negative_prompt": " ",
            "watermark": False,
            "prompt_extend": prompt_extend,
        },
    }
    if DASHSCOPE_QWEN_IMAGE_EDIT_SIZE:
        body["parameters"]["size"] = DASHSCOPE_QWEN_IMAGE_EDIT_SIZE

    url = f"{DASHSCOPE_HTTP_ORIGIN}{_GEN_PATH}"
    proxy = HTTPS_PROXY if HTTPS_PROXY else None
    timeout = httpx.Timeout(connect=30, read=300, write=120, pool=30)

    logger.info(
        "Qwen image edit request model=%s prompt_len=%s input_bytes=%s prompt_extend=%s",
        model,
        len(prompt),
        len(image_bytes),
        prompt_extend,
    )

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, proxy=proxy) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()

            if not isinstance(data, dict):
                return None
            if data.get("code"):
                logger.error(
                    "Qwen image edit API error: %s %s",
                    data.get("code"),
                    data.get("message"),
                )
                return None

            img_url = _first_image_url(data)
            if not img_url:
                logger.error("Qwen image edit: no image URL in response keys=%s", list(data.keys()))
                return None

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=20, read=120, write=20, pool=20),
                proxy=proxy,
            ) as dl:
                dr = await dl.get(img_url)
                dr.raise_for_status()
                out = dr.content
                logger.info(
                    "Qwen image edit ok model=%s output_bytes=%s",
                    model,
                    len(out),
                )
                return out
        except httpx.TransportError as e:
            last_exc = e
        except httpx.HTTPStatusError as e:
            last_exc = e
            status = getattr(e.response, "status_code", None)
            try:
                logger.warning(
                    "Qwen image edit HTTP %s: %s",
                    status,
                    (e.response.text[:800] if e.response else ""),
                )
            except Exception:
                pass
            if status not in (429, 500, 502, 503, 504):
                break

        await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("Qwen image edit failed: %r", last_exc)
    return None


async def edit_after_body_image_qwen(
    image_bytes: bytes,
    prompt: str,
    *,
    max_retries: int = 2,
    prompt_extend: bool | None = None,
) -> Optional[bytes]:
    """Кадр «после»: модель DASHSCOPE_QWEN_IMAGE_EDIT_AFTER_MODEL."""
    pe = DASHSCOPE_QWEN_AFTER_PROMPT_EXTEND if prompt_extend is None else prompt_extend
    return await _qwen_image_edit(
        image_bytes,
        prompt,
        model=DASHSCOPE_QWEN_IMAGE_EDIT_AFTER_MODEL,
        max_retries=max_retries,
        prompt_extend=pe,
    )


async def edit_measurements_overlay_qwen(
    image_bytes: bytes,
    prompt: str,
    *,
    max_retries: int = 2,
    prompt_extend: bool = False,
) -> Optional[bytes]:
    """Оверлей замеров на фото: модель DASHSCOPE_QWEN_IMAGE_EDIT_MODEL."""
    return await _qwen_image_edit(
        image_bytes,
        prompt,
        model=DASHSCOPE_QWEN_IMAGE_EDIT_MODEL,
        max_retries=max_retries,
        prompt_extend=prompt_extend,
    )
