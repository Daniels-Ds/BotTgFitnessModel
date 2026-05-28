"""
fal.ai — кадр «после» (FAL_FLUX_MODEL).
По умолчанию Hunyuan Image 3 Instruct Edit:
https://fal.ai/models/fal-ai/hunyuan-image/v3/instruct/edit
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from config import (
    FAL_FLUX_ASPECT_RATIO,
    FAL_FLUX_ENABLE_PROMPT_EXPANSION,
    FAL_FLUX_ENABLE_SAFETY_CHECKER,
    FAL_FLUX_GUIDANCE_SCALE,
    FAL_FLUX_MODEL,
    FAL_FLUX_OUTPUT_FORMAT,
    FAL_FLUX_SAFETY_TOLERANCE,
    FAL_FLUX_SEED,
    FAL_WAN_AFTER_SEED_10,
    FAL_WAN_AFTER_SEED_30,
    FAL_WAN_AFTER_SEED_50,
)
from services.fal_common import (
    download_fal_media,
    extract_image_url,
    run_fal_queue_job,
    upload_bytes_to_fal_cdn,
)

logger = logging.getLogger(__name__)

_PROMPT_MAX = 5000

# image_size enum — Seedream, Hunyuan и др.
_ASPECT_TO_IMAGE_SIZE: dict[str, str] = {
    "9:16": "portrait_16_9",
    "16:9": "landscape_16_9",
    "4:3": "landscape_4_3",
    "3:4": "portrait_4_3",
    "1:1": "square",
}


def _is_flux_model(model_id: str) -> bool:
    low = model_id.lower()
    return "flux" in low and "seedream" not in low and "hunyuan" not in low


def _is_hunyuan_model(model_id: str) -> bool:
    return "hunyuan" in model_id.lower()


def _is_seedream_model(model_id: str) -> bool:
    return "seedream" in model_id.lower()


def _uses_fal_image_size(model_id: str) -> bool:
    return _is_hunyuan_model(model_id) or _is_seedream_model(model_id)


def _is_wan_edit_model(model_id: str) -> bool:
    low = model_id.lower()
    return "wan/v2.7/edit" in low or ("wan" in low and "edit" in low)


def _fal_image_size(aspect_ratio: str) -> str:
    return _ASPECT_TO_IMAGE_SIZE.get(aspect_ratio.strip(), "portrait_16_9")


def _after_edit_log_label(model_id: str) -> str:
    if _is_wan_edit_model(model_id):
        return "wan-edit"
    if _is_hunyuan_model(model_id):
        return "hunyuan"
    if _is_seedream_model(model_id):
        return "seedream"
    return "flux-2"


def _seed_for_after_tier(tier: int | None) -> int | None:
    if tier == 10 and FAL_WAN_AFTER_SEED_10 is not None:
        return FAL_WAN_AFTER_SEED_10
    if tier == 30 and FAL_WAN_AFTER_SEED_30 is not None:
        return FAL_WAN_AFTER_SEED_30
    if tier == 50 and FAL_WAN_AFTER_SEED_50 is not None:
        return FAL_WAN_AFTER_SEED_50
    return FAL_FLUX_SEED


def _build_after_edit_payload(prompt: str, image_url: str, *, seed: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": (prompt or "")[:_PROMPT_MAX],
        "image_urls": [image_url],
    }
    if seed is not None:
        payload["seed"] = seed

    if _is_wan_edit_model(FAL_FLUX_MODEL):
        payload.update(
            {
                "image_size": _fal_image_size(FAL_FLUX_ASPECT_RATIO),
                "num_images": 1,
                "enable_prompt_expansion": FAL_FLUX_ENABLE_PROMPT_EXPANSION,
                "enable_safety_checker": FAL_FLUX_ENABLE_SAFETY_CHECKER,
                "output_format": FAL_FLUX_OUTPUT_FORMAT,
            }
        )
        return payload

    if _is_hunyuan_model(FAL_FLUX_MODEL):
        payload.update(
            {
                "image_size": _fal_image_size(FAL_FLUX_ASPECT_RATIO),
                "num_images": 1,
                "guidance_scale": FAL_FLUX_GUIDANCE_SCALE,
                "enable_prompt_expansion": FAL_FLUX_ENABLE_PROMPT_EXPANSION,
                "enable_safety_checker": FAL_FLUX_ENABLE_SAFETY_CHECKER,
                "output_format": FAL_FLUX_OUTPUT_FORMAT,
            }
        )
        return payload

    if _is_seedream_model(FAL_FLUX_MODEL):
        payload.update(
            {
                "image_size": _fal_image_size(FAL_FLUX_ASPECT_RATIO),
                "enable_safety_checker": FAL_FLUX_ENABLE_SAFETY_CHECKER,
                "num_images": 1,
                "max_images": 1,
            }
        )
        return payload

    if _uses_fal_image_size(FAL_FLUX_MODEL):
        payload["image_size"] = _fal_image_size(FAL_FLUX_ASPECT_RATIO)
        payload["enable_safety_checker"] = FAL_FLUX_ENABLE_SAFETY_CHECKER
        payload["num_images"] = 1
        return payload

    payload.update(
        {
            "aspect_ratio": FAL_FLUX_ASPECT_RATIO,
            "output_format": FAL_FLUX_OUTPUT_FORMAT,
            "enable_safety_checker": FAL_FLUX_ENABLE_SAFETY_CHECKER,
            "safety_tolerance": FAL_FLUX_SAFETY_TOLERANCE,
        }
    )
    return payload


async def edit_after_body_image_flux(
    image_bytes: bytes,
    prompt: str,
    *,
    intensity_tier: int | None = None,
    max_retries: int = 2,
) -> Optional[bytes]:
    log_label = _after_edit_log_label(FAL_FLUX_MODEL)
    image_url = await upload_bytes_to_fal_cdn(image_bytes, log_label=f"{log_label}-input")
    if not image_url:
        return None

    seed = _seed_for_after_tier(intensity_tier)
    input_payload = _build_after_edit_payload(prompt, image_url, seed=seed)
    if seed is not None:
        logger.info("%s after-edit: seed=%s tier=%s", log_label, seed, intensity_tier)

    result, reason = await run_fal_queue_job(
        model_id=FAL_FLUX_MODEL,
        input_payload=input_payload,
        log_label=log_label,
        max_retries=max_retries,
    )
    if reason == "safety" or not result:
        return None

    url = extract_image_url(result)
    if not url:
        return None

    return await download_fal_media(url, log_label=log_label)
