"""
fal.ai — Kling O3 image-to-video (подмена старого Hailuo-клиента).
https://fal.ai/models/fal-ai/kling-video/o3/standard/image-to-video
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

from config import (
    FAL_HAILUO_DUAL_MODEL,
    FAL_HAILUO_MODEL,
    _fal_hailuo_duration,
)
from services.fal_common import (
    download_fal_media,
    extract_video_url,
    run_fal_queue_job,
    upload_bytes_to_fal_cdn,
)
from prompts import HAILUO_I2V_PROMPT_MAX
from services.image_fit import fit_image_for_hailuo

logger = logging.getLogger(__name__)


async def generate_hailuo_fal_video(
    prompt: str,
    start_image: bytes,
    end_image: bytes | None = None,
    *,
    max_retries: int = 2,
) -> tuple[Optional[bytes], str]:
    """i2v: стартовый кадр (анфас); опционально end_image_url (спина) для поворота 180°."""
    start_image = fit_image_for_hailuo(start_image)
    if end_image:
        end_image = fit_image_for_hailuo(end_image)

    if end_image:
        start_url, end_url = await asyncio.gather(
            upload_bytes_to_fal_cdn(start_image, log_label="hailuo-start"),
            upload_bytes_to_fal_cdn(end_image, log_label="hailuo-end"),
        )
    else:
        start_url = await upload_bytes_to_fal_cdn(start_image, log_label="hailuo-start")
        end_url = None

    if not start_url:
        return None, "upload"
    if end_image and not end_url:
        return None, "upload"

    duration = str(_fal_hailuo_duration())
    start_sha = hashlib.sha256(start_image).hexdigest()[:12]
    model_id = FAL_HAILUO_MODEL
    input_payload: dict = {
        "prompt": (prompt or "")[:HAILUO_I2V_PROMPT_MAX],
        "image_url": start_url,
        "duration": duration,
    }

    if end_image:
        model_id = FAL_HAILUO_DUAL_MODEL or FAL_HAILUO_MODEL
        input_payload["end_image_url"] = end_url
        end_sha = hashlib.sha256(end_image).hexdigest()[:12]
        logger.info(
            "fal Kling submit model=%s duration=%s start_sha=%s end_sha=%s dual_frame=1",
            model_id,
            duration,
            start_sha,
            end_sha,
        )
    else:
        logger.info(
            "fal Kling submit model=%s duration=%s start_sha=%s bytes=%s",
            model_id,
            duration,
            start_sha,
            len(start_image),
        )

    result, reason = await run_fal_queue_job(
        model_id=model_id,
        input_payload=input_payload,
        log_label="hailuo-i2v",
        max_retries=max_retries,
    )
    if reason == "aspect_ratio":
        logger.warning("hailuo-i2v aspect_ratio — retry with strict pad")
        start_image = fit_image_for_hailuo(start_image, strict=True)
        if end_image:
            end_image = fit_image_for_hailuo(end_image, strict=True)
            start_url, end_url = await asyncio.gather(
                upload_bytes_to_fal_cdn(start_image, log_label="hailuo-start-retry"),
                upload_bytes_to_fal_cdn(end_image, log_label="hailuo-end-retry"),
            )
        else:
            start_url = await upload_bytes_to_fal_cdn(
                start_image, log_label="hailuo-start-retry"
            )
            end_url = None
        if not start_url or (end_image and not end_url):
            return None, "aspect_ratio"
        input_payload["image_url"] = start_url
        if end_image:
            input_payload["end_image_url"] = end_url
        result, reason = await run_fal_queue_job(
            model_id=model_id,
            input_payload=input_payload,
            log_label="hailuo-i2v",
            max_retries=1,
        )
    if reason:
        return None, reason
    if not result:
        return None, "unknown"

    url = extract_video_url(result)
    if not url:
        return None, "unknown"

    out = await download_fal_media(url, log_label="hailuo-mp4")
    if out:
        return out, ""
    return None, "unknown"
