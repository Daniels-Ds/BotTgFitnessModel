"""
Wan image-to-video (DashScope async): первый кадр + промпт → MP4.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Mapping, Optional

import httpx

from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_HTTP_ORIGIN,
    DASHSCOPE_WAN_I2V_MODEL,
    DASHSCOPE_WAN_I2V_NEGATIVE_PROMPT,
    DASHSCOPE_WAN_I2V_PROMPT_EXTEND,
    DASHSCOPE_WAN_I2V_RESOLUTION,
    DASHSCOPE_VIDEO_MAX_WAIT_SEC,
    DASHSCOPE_VIDEO_POLL_INTERVAL_SEC,
    HTTPS_PROXY,
)

logger = logging.getLogger(__name__)

_VIDEO_SYNTH = "/api/v1/services/aigc/video-generation/video-synthesis"


def _task_url(task_id: str) -> str:
    return f"{DASHSCOPE_HTTP_ORIGIN}/api/v1/tasks/{task_id}"


def _video_url_from_task(body: Mapping[str, Any]) -> Optional[str]:
    out = body.get("output")
    if not isinstance(out, Mapping):
        return None
    u = out.get("video_url")
    if isinstance(u, str) and u.startswith("http"):
        return u
    return None


def _task_status(body: Mapping[str, Any]) -> str:
    out = body.get("output")
    if isinstance(out, Mapping):
        s = out.get("task_status")
        if isinstance(s, str):
            return s
    return ""


async def generate_wan_i2v_video(
    prompt: str,
    image_bytes: bytes,
    *,
    max_retries: int = 2,
) -> tuple[Optional[bytes], str]:
    """
    Возвращает (mp4_bytes, reason). reason пустая строка при успехе;
    при отказе модерации — 'safety', иначе короткий тег (quota, network, unknown).
    """
    if not DASHSCOPE_API_KEY:
        logger.error("DASHSCOPE_API_KEY / ALIBABA_MODEL_STUDIO_API_KEY is not set")
        return None, "config"

    b64 = base64.b64encode(image_bytes).decode("ascii")
    img_url = f"data:image/jpeg;base64,{b64}"

    body: dict[str, Any] = {
        "model": DASHSCOPE_WAN_I2V_MODEL,
        "input": {
            "prompt": prompt,
            "img_url": img_url,
        },
        "parameters": {
            "resolution": DASHSCOPE_WAN_I2V_RESOLUTION,
            "prompt_extend": DASHSCOPE_WAN_I2V_PROMPT_EXTEND,
        },
    }
    if DASHSCOPE_WAN_I2V_NEGATIVE_PROMPT:
        body["input"]["negative_prompt"] = DASHSCOPE_WAN_I2V_NEGATIVE_PROMPT

    submit_url = f"{DASHSCOPE_HTTP_ORIGIN}{_VIDEO_SYNTH}"
    proxy = HTTPS_PROXY if HTTPS_PROXY else None
    submit_timeout = httpx.Timeout(connect=30, read=60, write=120, pool=30)
    poll_timeout = httpx.Timeout(connect=20, read=60, write=20, pool=20)

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=submit_timeout, proxy=proxy) as client:
                r = await client.post(
                    submit_url,
                    headers={
                        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                        "Content-Type": "application/json",
                        "X-DashScope-Async": "enable",
                    },
                    json=body,
                )
                r.raise_for_status()
                created = r.json()

            if not isinstance(created, dict):
                return None, "unknown"
            if created.get("code"):
                msg = str(created.get("message") or "")
                logger.error("Wan i2v create error: %s %s", created.get("code"), msg)
                low = msg.lower()
                if any(x in low for x in ("safety", "policy", "moderation", "content", "filtered")):
                    return None, "safety"
                if "quota" in low or "balance" in low or "limit" in low:
                    return None, "quota"
                return None, "unknown"

            out0 = created.get("output")
            task_id: str | None = None
            if isinstance(out0, Mapping):
                tid = out0.get("task_id")
                if isinstance(tid, str):
                    task_id = tid
            if not task_id:
                tid2 = created.get("task_id")
                if isinstance(tid2, str):
                    task_id = tid2
            if not task_id:
                logger.error("Wan i2v: no task_id: %r", created)
                return None, "unknown"

            started = time.monotonic()
            while True:
                if time.monotonic() - started > DASHSCOPE_VIDEO_MAX_WAIT_SEC:
                    logger.error("Wan i2v: timeout task=%s", task_id)
                    return None, "timeout"

                await asyncio.sleep(DASHSCOPE_VIDEO_POLL_INTERVAL_SEC)

                async with httpx.AsyncClient(timeout=poll_timeout, proxy=proxy) as pc:
                    pr = await pc.get(
                        _task_url(task_id),
                        headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
                    )
                    pr.raise_for_status()
                    payload = pr.json()

                if not isinstance(payload, dict):
                    continue

                status = _task_status(payload)
                if status == "SUCCEEDED":
                    vurl = _video_url_from_task(payload)
                    if not vurl:
                        logger.error("Wan i2v: SUCCEEDED but no video_url: %r", payload)
                        return None, "unknown"
                    async with httpx.AsyncClient(
                        timeout=httpx.Timeout(connect=30, read=300, write=30, pool=30),
                        proxy=proxy,
                    ) as dl:
                        dr = await dl.get(vurl)
                        dr.raise_for_status()
                        return dr.content, ""

                if status in ("FAILED", "CANCELED"):
                    out = payload.get("output")
                    code = msg = ""
                    if isinstance(out, Mapping):
                        code = str(out.get("code") or "")
                        msg = str(out.get("message") or "")
                    joined = f"{code} {msg}".lower()
                    logger.error("Wan i2v task %s: %s %s", status, code, msg)
                    if any(x in joined for x in ("safety", "policy", "moderation", "content", "filtered")):
                        return None, "safety"
                    if "quota" in joined or "balance" in joined:
                        return None, "quota"
                    return None, "unknown"

        except httpx.TransportError as e:
            # TransportError включает Timeout/Network/RemoteProtocolError (обрыв без ответа) и ProxyError.
            last_exc = e
        except httpx.HTTPStatusError as e:
            last_exc = e
            status = getattr(e.response, "status_code", None)
            try:
                logger.warning(
                    "Wan i2v HTTP %s: %s",
                    status,
                    (e.response.text[:600] if e.response else ""),
                )
            except Exception:
                pass
            if status == 429:
                return None, "quota"
            if status in {401, 403}:
                return None, "auth"
            if status not in (500, 502, 503, 504):
                break

        await asyncio.sleep(2.0 * (attempt + 1))

    logger.error("Wan i2v failed: %r", last_exc)
    return None, "network"
