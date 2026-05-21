"""
Kie.ai Market — Seedream 4.5 Edit (кадр «после»).
Документация: https://docs.kie.ai/market/seedream/4-5-edit
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Mapping, Optional

import httpx

from config import (
    HTTPS_PROXY,
    KIE_API_KEY,
    KIE_BASE_URL,
    KIE_SEEDREAM_ASPECT_RATIO,
    KIE_SEEDREAM_EDIT_MODEL,
    KIE_SEEDREAM_NSFW_CHECKER,
    KIE_SEEDREAM_QUALITY,
    KIE_TASK_MAX_WAIT_SEC,
    KIE_TASK_POLL_INTERVAL_SEC,
    KIE_UPLOAD_BASE_URL,
    KIE_UPLOAD_PATH,
)

logger = logging.getLogger(__name__)

_CREATE_TASK_PATH = "/api/v1/jobs/createTask"
_RECORD_INFO_PATH = "/api/v1/jobs/recordInfo"
_STREAM_UPLOAD_PATH = "/api/file-stream-upload"


def _mime_and_name(image_bytes: bytes) -> tuple[str, str]:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "input.png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "input.jpg"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) > 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp", "input.webp"
    return "image/jpeg", "input.jpg"


def _upload_file_url(data: Mapping[str, Any]) -> Optional[str]:
    if not isinstance(data, Mapping):
        return None
    for key in ("fileUrl", "downloadUrl", "url"):
        val = data.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    return None


def _result_urls_from_task(data: Mapping[str, Any]) -> list[str]:
    raw = data.get("resultJson")
    parsed: Any = raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Kie recordInfo: invalid resultJson: %s", raw[:200])
            return []
    if isinstance(parsed, Mapping):
        urls = parsed.get("resultUrls")
        if isinstance(urls, list):
            return [u for u in urls if isinstance(u, str) and u.startswith("http")]
    return []


async def _upload_image_bytes(
    client: httpx.AsyncClient,
    image_bytes: bytes,
) -> Optional[str]:
    mime, filename = _mime_and_name(image_bytes)
    files = {"file": (filename, image_bytes, mime)}
    data = {"uploadPath": KIE_UPLOAD_PATH, "fileName": filename}
    resp = await client.post(
        f"{KIE_UPLOAD_BASE_URL}{_STREAM_UPLOAD_PATH}",
        files=files,
        data=data,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, Mapping):
        return None
    code = payload.get("code")
    if payload.get("success") is False or (code is not None and code not in (200, "200")):
        logger.error("Kie upload failed: %r", payload)
        return None
    inner = payload.get("data")
    if isinstance(inner, Mapping):
        url = _upload_file_url(inner)
        if url:
            return url
    logger.error("Kie upload: no file URL in response: %r", payload)
    return None


async def _create_edit_task(
    client: httpx.AsyncClient,
    *,
    prompt: str,
    image_url: str,
) -> Optional[str]:
    body = {
        "model": KIE_SEEDREAM_EDIT_MODEL,
        "input": {
            "prompt": prompt[:3000],
            "image_urls": [image_url],
            "aspect_ratio": KIE_SEEDREAM_ASPECT_RATIO,
            "quality": KIE_SEEDREAM_QUALITY,
            "nsfw_checker": KIE_SEEDREAM_NSFW_CHECKER,
        },
    }
    resp = await client.post(f"{KIE_BASE_URL}{_CREATE_TASK_PATH}", json=body)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, Mapping) or payload.get("code") != 200:
        logger.error("Kie createTask failed: %r", payload)
        return None
    data = payload.get("data")
    if isinstance(data, Mapping) and data.get("taskId"):
        return str(data["taskId"])
    logger.error("Kie createTask: missing taskId: %r", payload)
    return None


async def _poll_task_result_url(
    client: httpx.AsyncClient,
    task_id: str,
) -> Optional[str]:
    deadline = time.monotonic() + KIE_TASK_MAX_WAIT_SEC
    while time.monotonic() < deadline:
        resp = await client.get(
            f"{KIE_BASE_URL}{_RECORD_INFO_PATH}",
            params={"taskId": task_id},
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, Mapping) or payload.get("code") != 200:
            logger.error("Kie recordInfo failed: %r", payload)
            return None
        data = payload.get("data")
        if not isinstance(data, Mapping):
            await asyncio.sleep(KIE_TASK_POLL_INTERVAL_SEC)
            continue

        state = str(data.get("state") or "").lower()
        if state == "success":
            urls = _result_urls_from_task(data)
            if urls:
                return urls[0]
            logger.error("Kie task success but no resultUrls: %r", data)
            return None
        if state == "fail":
            logger.error(
                "Kie task failed taskId=%s failCode=%s failMsg=%s",
                task_id,
                data.get("failCode"),
                data.get("failMsg"),
            )
            return None

        await asyncio.sleep(KIE_TASK_POLL_INTERVAL_SEC)

    logger.error("Kie task timeout taskId=%s wait_sec=%s", task_id, KIE_TASK_MAX_WAIT_SEC)
    return None


async def _download_bytes(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    resp = await client.get(url)
    resp.raise_for_status()
    if resp.content:
        return resp.content
    return None


async def edit_after_body_image_seedream(
    image_bytes: bytes,
    prompt: str,
    *,
    max_retries: int = 2,
) -> Optional[bytes]:
    """
    Seedream 4.5 Edit через Kie.ai: загрузка референса → createTask → poll → скачать PNG/JPEG.
    """
    if not KIE_API_KEY:
        logger.error("KIE_API_KEY is not set")
        return None

    proxy = HTTPS_PROXY if HTTPS_PROXY else None
    timeout = httpx.Timeout(connect=30, read=300, write=120, pool=30)
    headers = {"Authorization": f"Bearer {KIE_API_KEY}"}

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, proxy=proxy, headers=headers) as client:
                image_url = await _upload_image_bytes(client, image_bytes)
                if not image_url:
                    return None
                logger.info(
                    "Kie Seedream edit: uploaded ref_bytes=%s image_url_len=%s",
                    len(image_bytes),
                    len(image_url),
                )

                task_id = await _create_edit_task(
                    client,
                    prompt=prompt,
                    image_url=image_url,
                )
                if not task_id:
                    return None
                logger.info(
                    "Kie Seedream edit: task created model=%s taskId=%s prompt_len=%s",
                    KIE_SEEDREAM_EDIT_MODEL,
                    task_id,
                    len(prompt),
                )

                result_url = await _poll_task_result_url(client, task_id)
                if not result_url:
                    return None

                out = await _download_bytes(client, result_url)
                if out:
                    logger.info(
                        "Kie Seedream edit ok taskId=%s output_bytes=%s",
                        task_id,
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
                    "Kie Seedream HTTP %s: %s",
                    status,
                    (e.response.text[:800] if e.response else ""),
                )
            except Exception:
                pass
            if status not in (429, 500, 502, 503, 504):
                break

        await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("Kie Seedream edit failed: %r", last_exc)
    return None
