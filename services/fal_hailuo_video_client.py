"""
fal.ai — MiniMax Hailuo 2.3 image-to-video.
https://fal.ai/models/fal-ai/minimax/hailuo-2.3/standard/image-to-video
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from config import (
    FAL_HAILUO_DUAL_MODEL,
    FAL_HAILUO_MODEL,
    FAL_HAILUO_PROMPT_OPTIMIZER,
    FAL_HAILUO_RESOLUTION,
    _fal_hailuo_duration,
)
from services.fal_common import (
    bytes_to_data_uri,
    download_fal_media,
    extract_video_url,
    run_fal_queue_job,
)

logger = logging.getLogger(__name__)


async def generate_hailuo_fal_video(
    prompt: str,
    start_image: bytes,
    end_image: bytes | None = None,
    *,
    max_retries: int = 2,
) -> tuple[Optional[bytes], str]:
    """i2v: стартовый кадр (анфас); опционально end_image_url (спина) для поворота 180°."""
    duration = str(_fal_hailuo_duration())
    start_sha = hashlib.sha256(start_image).hexdigest()[:12]
    model_id = FAL_HAILUO_MODEL
    input_payload: dict = {
        "prompt": (prompt or "")[:5000],
        "image_url": bytes_to_data_uri(start_image),
        "duration": duration,
        "prompt_optimizer": FAL_HAILUO_PROMPT_OPTIMIZER,
    }

    if end_image:
        model_id = FAL_HAILUO_DUAL_MODEL or FAL_HAILUO_MODEL
        input_payload["end_image_url"] = bytes_to_data_uri(end_image)
        end_sha = hashlib.sha256(end_image).hexdigest()[:12]
        logger.info(
            "fal Hailuo submit model=%s duration=%s start_sha=%s end_sha=%s dual_frame=1",
            model_id,
            duration,
            start_sha,
            end_sha,
        )
    else:
        logger.info(
            "fal Hailuo submit model=%s duration=%s start_sha=%s bytes=%s",
            model_id,
            duration,
            start_sha,
            len(start_image),
        )

    res = (FAL_HAILUO_RESOLUTION or "768P").upper()
    if res in ("512P", "768P", "1080P"):
        input_payload["resolution"] = res

    result, reason = await run_fal_queue_job(
        model_id=model_id,
        input_payload=input_payload,
        log_label="hailuo-i2v",
        max_retries=max_retries,
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
