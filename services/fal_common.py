"""fal.ai через официальный fal-client (subscribe_async)."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any, Mapping, Optional

import httpx

from config import (
    FAL_DOWNLOAD_CONNECT_SEC,
    FAL_DOWNLOAD_READ_SEC,
    FAL_DOWNLOAD_RETRIES,
    FAL_DOWNLOAD_TRY_DIRECT,
    FAL_KEY,
    FAL_MAX_WAIT_SEC,
    HTTPS_PROXY,
)

logger = logging.getLogger(__name__)


def mime_and_name(image_bytes: bytes) -> tuple[str, str]:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "input.png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "input.jpg"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) > 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp", "input.webp"
    return "image/jpeg", "input.jpg"


def bytes_to_data_uri(image_bytes: bytes) -> str:
    mime, _ = mime_and_name(image_bytes)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _is_safety_error(text: str) -> bool:
    low = (text or "").lower()
    return any(
        m in low
        for m in (
            "content_policy",
            "content policy",
            "nsfw",
            "safety",
            "moderation",
            "blocked",
            "inappropriate",
            "violat",
        )
    )


def _unwrap_fal_result(raw: Any) -> Mapping[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    if "images" in raw or "video" in raw or "image" in raw:
        return raw
    for key in ("response", "data", "payload", "output"):
        inner = raw.get(key)
        if isinstance(inner, Mapping) and (
            "images" in inner or "video" in inner or "image" in inner
        ):
            return inner
    return raw


def extract_image_url(result: Mapping[str, Any]) -> Optional[str]:
    body = _unwrap_fal_result(result) or result
    images = body.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, Mapping) and isinstance(first.get("url"), str):
            return first["url"]
        if isinstance(first, str) and first.startswith("http"):
            return first
    for key in ("image", "output"):
        val = body.get(key)
        if isinstance(val, Mapping) and isinstance(val.get("url"), str):
            return val["url"]
    return None


def extract_video_url(result: Mapping[str, Any]) -> Optional[str]:
    body = _unwrap_fal_result(result) or result
    video = body.get("video")
    if isinstance(video, Mapping) and isinstance(video.get("url"), str):
        return video["url"]
    if isinstance(video, str) and video.startswith("http"):
        return video
    return None


async def run_fal_queue_job(
    *,
    model_id: str,
    input_payload: dict[str, Any],
    log_label: str,
    max_retries: int = 2,
) -> tuple[Optional[dict[str, Any]], str]:
    if not FAL_KEY:
        logger.error("FAL_KEY is not set")
        return None, "config"

    os.environ["FAL_KEY"] = FAL_KEY

    import fal_client

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            logger.info("fal %s: subscribe model=%s", log_label, model_id)

            def on_queue_update(status: Any) -> None:
                name = type(status).__name__
                if name in ("Queued", "InProgress"):
                    logger.debug("fal %s queue: %s", log_label, name)

            result = await fal_client.subscribe_async(
                model_id,
                arguments=input_payload,
                with_logs=False,
                on_queue_update=on_queue_update,
                client_timeout=float(FAL_MAX_WAIT_SEC),
            )

            if isinstance(result, Mapping):
                return dict(result), ""
            logger.error("fal %s unexpected result type: %s", log_label, type(result))
            return None, "unknown"
        except Exception as e:
            last_exc = e
            msg = str(e)
            logger.warning("fal %s attempt %s: %s", log_label, attempt + 1, msg[:500])
            if _is_safety_error(msg):
                return None, "safety"
            await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("fal %s failed: %r", log_label, last_exc)
    return None, "unknown"


def _download_proxy_plan() -> list[Optional[str]]:
    """Порядок попыток: сначала HTTPS_PROXY, на последней — без прокси (если включено)."""
    n = FAL_DOWNLOAD_RETRIES
    if not HTTPS_PROXY:
        return [None] * n
    plan = [HTTPS_PROXY] * n
    if FAL_DOWNLOAD_TRY_DIRECT and n >= 2:
        plan[-1] = None
    return plan


def _fal_download_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=FAL_DOWNLOAD_CONNECT_SEC,
        read=FAL_DOWNLOAD_READ_SEC,
        write=120.0,
        pool=30.0,
    )


async def download_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.content or None


async def download_fal_media(url: str, *, log_label: str = "media") -> Optional[bytes]:
    """Скачать результат с CDN: ретраи, длинный connect/read, fallback без прокси."""
    host = url.split("/")[2] if "://" in url else "?"
    last_exc: Exception | None = None
    for attempt, proxy in enumerate(_download_proxy_plan(), start=1):
        via = "direct" if proxy is None else "proxy"
        try:
            logger.info(
                "fal download %s attempt %s/%s via=%s host=%s",
                log_label,
                attempt,
                FAL_DOWNLOAD_RETRIES,
                via,
                host,
            )
            async with httpx.AsyncClient(timeout=_fal_download_timeout(), proxy=proxy) as client:
                data = await download_bytes(client, url)
            if data:
                logger.info("fal download %s ok bytes=%s via=%s", log_label, len(data), via)
                return data
        except httpx.HTTPStatusError as e:
            last_exc = e
            logger.warning(
                "fal download %s attempt %s HTTP %s via=%s",
                log_label,
                attempt,
                e.response.status_code,
                via,
            )
            if e.response.status_code in (403, 404, 410):
                break
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError, httpx.RemoteProtocolError) as e:
            last_exc = e
            logger.warning(
                "fal download %s attempt %s %s via=%s: %s",
                log_label,
                attempt,
                type(e).__name__,
                via,
                str(e)[:200],
            )
        except Exception as e:
            last_exc = e
            logger.warning(
                "fal download %s attempt %s via=%s: %s",
                log_label,
                attempt,
                via,
                str(e)[:200],
            )
        if attempt < FAL_DOWNLOAD_RETRIES:
            await asyncio.sleep(min(2.0 * attempt, 10.0))

    logger.error("fal download %s failed after %s tries: %r", log_label, FAL_DOWNLOAD_RETRIES, last_exc)
    return None
