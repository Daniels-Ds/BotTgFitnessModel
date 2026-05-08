"""
RunningHub consumer workflow client (ai-app mode).
"""
import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from typing import Optional

import httpx

from config import (
    HTTPS_PROXY,
    KIE_API_KEY,
    KIE_BASE_URL,
    KIE_IMAGE_ASPECT_RATIO,
    KIE_IMAGE_MAX_WAIT_SEC,
    KIE_IMAGE_MODEL,
    WAN_AFTER_IMAGE_DURATION_NODE_ID,
    WAN_AFTER_IMAGE_FIELD_IMAGE,
    WAN_AFTER_IMAGE_FIELD_PROMPT,
    WAN_AFTER_IMAGE_NODE_IMAGE,
    WAN_AFTER_IMAGE_NODE_PROMPT,
    WAN_AFTER_IMAGE_WEBAPP_ID,
    WAN_API_KEY,
    WAN_ASPECT_FIELD_NAME,
    WAN_ASPECT_FIELD_VALUE,
    WAN_ASPECT_NODE_ID,
    WAN_BASE_URL,
    WAN_UPLOAD_URL,
    WAN_WEBAPP_ID,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
POLL_INTERVAL = 5
MAX_WAIT = 600

RUN_PATH = "/task/openapi/ai-app/run"
OUTPUTS_PATH = "/task/openapi/outputs"
KIE_GENERATE_PATH = "/api/v1/flux/kontext/generate"
KIE_RECORD_INFO_PATH = "/api/v1/flux/kontext/record-info"

# Node bindings from exported workflow api json.
NODE_IMAGE = "109"      # LoadImage.image
NODE_PROMPT = "176"     # CR Text.text
NODE_DURATION = "186"   # JWInteger.value
DEFAULT_DURATION = "5"


def _normalize_reason(payload: Mapping) -> str:
    text = " ".join(
        [
            str(payload.get("msg") or ""),
            str(payload.get("message") or ""),
            str(payload.get("errorMessage") or ""),
            str(payload.get("failedReason") or ""),
            str(payload),
        ]
    ).lower()
    if "node_not_found" in text or "node_info_mismatch" in text:
        return "node_mismatch"
    if "safety" in text or "policy" in text or "moderation" in text or "filtered" in text:
        return "safety"
    if "quota" in text or "insufficient" in text or "balance" in text or "coin" in text:
        return "quota"
    if "timeout" in text:
        return "timeout"
    if "api key" in text or "denied" in text or "forbidden" in text:
        return "auth"
    return "unknown"


def _is_kie_sensitive_error(reason: str) -> bool:
    text = (reason or "").lower()
    return ("sensitive" in text) or ("flagged" in text) or ("e005" in text) or ("safety" in text)


def _build_kie_text2image_prompt(summary_text: str) -> str:
    return (
        "Create a realistic full-body fitness model in sportswear, front view, neutral pose, plain studio background. "
        "Apply the following body measurements to the generated model proportions (in centimeters). "
        "Natural anatomy, non-sexual, no nudity, no exaggerated features.\n\n"
        f"{summary_text}"
    )


def _upload_image(image_bytes: bytes, proxy: Optional[str]) -> Optional[str]:
    files = {"file": ("input.jpg", image_bytes, "image/jpeg")}
    data = {"apiKey": WAN_API_KEY, "fileType": "image"}
    with httpx.Client(
        proxy=proxy,
        timeout=httpx.Timeout(connect=30, read=120, write=120, pool=30),
        follow_redirects=True,
    ) as upload_client:
        resp = upload_client.post(WAN_UPLOAD_URL, data=data, files=files)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, Mapping):
        logger.error("WAN upload: unexpected response type: %s", type(payload).__name__)
        return None
    if payload.get("code") not in (0, "0"):
        logger.error("WAN upload failed: %r", payload)
        return None
    item = payload.get("data")
    if not isinstance(item, Mapping):
        logger.error("WAN upload: bad data payload: %r", payload)
        return None
    # ai-app flow wants fileName for LoadImage node.
    file_name = item.get("fileName")
    if file_name:
        return str(file_name)
    # Fallback for alternative payload shapes.
    download_url = item.get("download_url")
    return str(download_url) if download_url else None


def _submit_ai_app(client: httpx.Client, webapp_id: str, nodes: list[dict[str, str]]) -> tuple[Optional[str], str]:
    payload = {"webappId": webapp_id, "apiKey": WAN_API_KEY, "nodeInfoList": nodes}
    resp = client.post(RUN_PATH, json=payload)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, Mapping):
        logger.error("WAN run: unexpected response type: %s", type(body).__name__)
        return None, "unknown"
    code = body.get("code")
    if code not in (0, "0"):
        logger.error("WAN run failed: %r", body)
        return None, _normalize_reason(body)
    data = body.get("data")
    if not isinstance(data, Mapping):
        logger.error("WAN run: missing data: %r", body)
        return None, "unknown"
    task_id = data.get("taskId")
    if not task_id:
        logger.error("WAN run: missing taskId: %r", body)
        return None, "unknown"
    return str(task_id), ""


def _submit_task(client: httpx.Client, prompt: str, uploaded_file: str, webapp_id: str) -> tuple[Optional[str], str]:
    nodes: list[dict[str, str]] = [
        {"nodeId": NODE_IMAGE, "fieldName": "image", "fieldValue": uploaded_file},
        {"nodeId": NODE_PROMPT, "fieldName": "text", "fieldValue": prompt},
        {"nodeId": NODE_DURATION, "fieldName": "value", "fieldValue": DEFAULT_DURATION},
    ]
    if WAN_ASPECT_NODE_ID:
        nodes.append(
            {
                "nodeId": WAN_ASPECT_NODE_ID,
                "fieldName": WAN_ASPECT_FIELD_NAME,
                "fieldValue": WAN_ASPECT_FIELD_VALUE,
            }
        )
    return _submit_ai_app(client, webapp_id, nodes)


def _after_image_node_list(prompt: str, uploaded_file: str) -> list[dict[str, str]]:
    nodes: list[dict[str, str]] = [
        {"nodeId": WAN_AFTER_IMAGE_NODE_IMAGE, "fieldName": WAN_AFTER_IMAGE_FIELD_IMAGE, "fieldValue": uploaded_file},
    ]
    if WAN_AFTER_IMAGE_NODE_PROMPT:
        nodes.append(
            {
                "nodeId": WAN_AFTER_IMAGE_NODE_PROMPT,
                "fieldName": WAN_AFTER_IMAGE_FIELD_PROMPT,
                "fieldValue": prompt,
            }
        )
    if WAN_AFTER_IMAGE_DURATION_NODE_ID:
        nodes.append(
            {
                "nodeId": WAN_AFTER_IMAGE_DURATION_NODE_ID,
                "fieldName": "value",
                "fieldValue": DEFAULT_DURATION,
            }
        )
    if WAN_ASPECT_NODE_ID:
        nodes.append(
            {
                "nodeId": WAN_ASPECT_NODE_ID,
                "fieldName": WAN_ASPECT_FIELD_NAME,
                "fieldValue": WAN_ASPECT_FIELD_VALUE,
            }
        )
    return nodes


def _extract_url_from_outputs_payload(payload: Mapping) -> Optional[str]:
    data = payload.get("data")
    if isinstance(data, str) and data.startswith("http"):
        return data
    if isinstance(data, Mapping):
        for key in ("fileUrl", "url"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, Mapping):
                continue
            file_type = str(item.get("fileType") or "").lower()
            file_url = item.get("fileUrl") or item.get("url")
            if isinstance(file_url, str) and file_url:
                if file_type in {"mp4", "mov", "avi", "video"}:
                    return file_url
        for item in data:
            if isinstance(item, Mapping):
                file_url = item.get("fileUrl") or item.get("url")
                if isinstance(file_url, str) and file_url:
                    return file_url
    return None


def _extract_image_url_from_outputs_payload(payload: Mapping) -> Optional[str]:
    """Первый артефакт-картинка (не видео)."""
    data = payload.get("data")
    if isinstance(data, str) and data.startswith("http"):
        return data
    if isinstance(data, Mapping):
        ft = str(data.get("fileType") or "").lower()
        if ft in {"jpeg", "jpg", "png", "webp", "image"}:
            for key in ("fileUrl", "url"):
                val = data.get(key)
                if isinstance(val, str) and val:
                    return val
    if isinstance(data, list):
        image_types = {"jpeg", "jpg", "png", "webp", "image"}
        for item in data:
            if not isinstance(item, Mapping):
                continue
            file_type = str(item.get("fileType") or "").lower()
            file_url = item.get("fileUrl") or item.get("url")
            if not isinstance(file_url, str) or not file_url:
                continue
            if file_type in image_types:
                return file_url
        for item in data:
            if not isinstance(item, Mapping):
                continue
            file_type = str(item.get("fileType") or "").lower()
            if file_type in {"mp4", "mov", "avi", "video"}:
                continue
            file_url = item.get("fileUrl") or item.get("url")
            if isinstance(file_url, str) and file_url:
                return file_url
    return None


def _extract_kie_result_url(task_data: Mapping) -> Optional[str]:
    def _collect_urls(value) -> list[str]:
        urls: list[str] = []
        if isinstance(value, str):
            if value.startswith("http"):
                urls.append(value)
            return urls
        if isinstance(value, Mapping):
            for v in value.values():
                urls.extend(_collect_urls(v))
            return urls
        if isinstance(value, list):
            for item in value:
                urls.extend(_collect_urls(item))
            return urls
        return urls

    response_data = task_data.get("response")
    if isinstance(response_data, Mapping):
        direct = response_data.get("resultImageUrl")
        if isinstance(direct, str) and direct:
            return direct
        nested_info = response_data.get("info")
        if isinstance(nested_info, Mapping):
            nested = nested_info.get("resultImageUrl")
            if isinstance(nested, str) and nested:
                return nested
    info_data = task_data.get("info")
    if isinstance(info_data, Mapping):
        info_url = info_data.get("resultImageUrl")
        if isinstance(info_url, str) and info_url:
            return info_url
    direct_task = task_data.get("resultImageUrl")
    if isinstance(direct_task, str) and direct_task:
        return direct_task

    # Fallback: sometimes KIE returns image URLs in other nested fields
    # (e.g. images/results/output/downloadUrl/url).
    for candidate_url in _collect_urls(task_data):
        lower = candidate_url.lower()
        if any(token in lower for token in (".jpg", ".jpeg", ".png", ".webp", "/images/", "image")):
            return candidate_url
    return None


def _poll_outputs(
    client: httpx.Client,
    task_id: str,
    *,
    url_extractor: Callable[[Mapping], Optional[str]] = _extract_url_from_outputs_payload,
) -> tuple[Optional[str], str, Mapping]:
    started = time.time()
    last_payload: Mapping = {}
    while True:
        elapsed = int(time.time() - started)
        if elapsed > MAX_WAIT:
            return None, "timeout", last_payload

        resp = client.post(OUTPUTS_PATH, json={"apiKey": WAN_API_KEY, "taskId": task_id})
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, Mapping):
            payload = {"raw": str(payload)}
        last_payload = payload

        code = payload.get("code")
        logger.info("WAN poll (%ss) code=%s", elapsed, code)

        if code in (0, "0"):
            file_url = url_extractor(payload)
            if file_url:
                return file_url, "", payload
            return None, "unknown", payload

        # Known statuses from docs/sample code:
        # 804 running, 813 queued, 805 failed.
        if code in (804, "804", 813, "813"):
            time.sleep(POLL_INTERVAL)
            continue
        if code in (805, "805"):
            return None, _normalize_reason(payload), payload

        # Fallback: keep polling for transient unknown status codes.
        time.sleep(POLL_INTERVAL)


def _download_file(video_url: str, proxy: Optional[str]) -> Optional[bytes]:
    with httpx.Client(
        proxy=proxy,
        timeout=httpx.Timeout(connect=30, read=180, write=30, pool=30),
        follow_redirects=True,
    ) as dl_client:
        resp = dl_client.get(video_url)
    if resp.status_code != 200:
        logger.error("WAN download failed: status=%s url=%s", resp.status_code, video_url)
        return None
    return resp.content


def _generate_one_video_sync(prompt: str, image_bytes: bytes, webapp_id: str) -> tuple[Optional[bytes], str]:
    if not WAN_API_KEY:
        logger.error("WAN_API_KEY is not set")
        return None, "config"
    if not webapp_id:
        logger.error("WAN webapp id is not set")
        return None, "config"

    proxy = HTTPS_PROXY if HTTPS_PROXY else None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Submitting WAN job...")
            uploaded_file = _upload_image(image_bytes, proxy)
            if not uploaded_file:
                return None, "network"
            logger.info("WAN image uploaded")

            with httpx.Client(
                base_url=WAN_BASE_URL,
                proxy=proxy,
                timeout=httpx.Timeout(connect=30, read=120, write=30, pool=30),
                headers={"Content-Type": "application/json"},
            ) as client:
                task_id, reason = _submit_task(client, prompt, uploaded_file, webapp_id)
                if not task_id:
                    return None, reason or "unknown"
                logger.info("WAN task submitted: %s", task_id)

                video_url, reason, payload = _poll_outputs(client, task_id)
                if not video_url:
                    logger.error("WAN generation failed, reason=%s payload=%r", reason, payload)
                    return None, reason or "unknown"

            data = _download_file(video_url, proxy)
            if not data:
                return None, "network"
            return data, ""
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else None
            body = ""
            try:
                body = e.response.text if e.response is not None else ""
            except Exception:
                pass
            logger.error("WAN HTTP error (status=%s): %s", code, body)
            if code == 429:
                return None, "quota"
            if code in {401, 403}:
                return None, "auth"
            return None, "network"
        except Exception as e:
            logger.warning("WAN attempt %s/%s failed: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
            else:
                return None, "network"

    return None, "unknown"


def _generate_after_body_image_sync(prompt: str, image_bytes: bytes) -> tuple[Optional[bytes], str]:
    """Референс + текст → картинка «после» (отдельный ai-app), без видео."""
    if not WAN_API_KEY:
        logger.error("WAN_API_KEY is not set")
        return None, "config"
    if not WAN_AFTER_IMAGE_WEBAPP_ID:
        logger.error("WAN_AFTER_IMAGE_WEBAPP_ID is not set")
        return None, "config"
    if not WAN_AFTER_IMAGE_NODE_IMAGE:
        logger.error("WAN_AFTER_IMAGE_NODE_IMAGE is empty")
        return None, "config"

    proxy = HTTPS_PROXY if HTTPS_PROXY else None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Submitting WAN after-image job (webapp=%s)...", WAN_AFTER_IMAGE_WEBAPP_ID)
            uploaded_file = _upload_image(image_bytes, proxy)
            if not uploaded_file:
                return None, "network"
            logger.info("WAN after-image: reference uploaded")

            with httpx.Client(
                base_url=WAN_BASE_URL,
                proxy=proxy,
                timeout=httpx.Timeout(connect=30, read=120, write=30, pool=30),
                headers={"Content-Type": "application/json"},
            ) as client:
                nodes = _after_image_node_list(prompt, uploaded_file)
                task_id, reason = _submit_ai_app(client, WAN_AFTER_IMAGE_WEBAPP_ID, nodes)
                if not task_id:
                    return None, reason or "unknown"
                logger.info("WAN after-image task submitted: %s", task_id)

                image_url, reason, payload = _poll_outputs(
                    client,
                    task_id,
                    url_extractor=_extract_image_url_from_outputs_payload,
                )
                if not image_url:
                    logger.error("WAN after-image failed, reason=%s payload=%r", reason, payload)
                    return None, reason or "unknown"

            data = _download_file(image_url, proxy)
            if not data:
                return None, "network"
            return data, ""
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else None
            body = ""
            try:
                body = e.response.text if e.response is not None else ""
            except Exception:
                pass
            logger.error("WAN after-image HTTP error (status=%s): %s", code, body)
            if code == 429:
                return None, "quota"
            if code in {401, 403}:
                return None, "auth"
            return None, "network"
        except Exception as e:
            logger.warning("WAN after-image attempt %s/%s failed: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)
            else:
                return None, "network"

    return None, "unknown"


def _submit_measurements_app_sync(summary_text: str, image_bytes: bytes) -> tuple[Optional[str], Optional[str], str]:
    _ = image_bytes  # text-to-image mode for measurements
    if not KIE_API_KEY:
        logger.error("KIE_API_KEY is not set")
        return None, None, "config"

    proxy = HTTPS_PROXY if HTTPS_PROXY else None
    try:
        with httpx.Client(
            base_url=KIE_BASE_URL,
            proxy=proxy,
            timeout=httpx.Timeout(connect=30, read=60, write=30, pool=30),
            headers={
                "Authorization": f"Bearer {KIE_API_KEY}",
                "Content-Type": "application/json",
            },
        ) as client:
            prompts_to_try = [
                _build_kie_text2image_prompt(summary_text),
                "Create a realistic healthy adult fitness model, front view, neutral sportswear, studio light.\n\n"
                + summary_text,
            ]
            last_task_id = ""
            last_reason = "unknown"
            for attempt_idx, prompt_text in enumerate(prompts_to_try, start=1):
                submit = client.post(
                    KIE_GENERATE_PATH,
                    json={
                        "prompt": prompt_text,
                        "aspectRatio": KIE_IMAGE_ASPECT_RATIO,
                        "model": KIE_IMAGE_MODEL,
                        "enableTranslation": True,
                        "outputFormat": "jpeg",
                        "safetyTolerance": 2,
                    },
                )
                submit.raise_for_status()
                submit_payload = submit.json()
                if not isinstance(submit_payload, Mapping):
                    logger.error("KIE generate unexpected response: %r", submit_payload)
                    return None, None, "unknown"
                if submit_payload.get("code") != 200:
                    logger.error("KIE generate failed: %r", submit_payload)
                    last_reason = _normalize_reason(submit_payload)
                    if attempt_idx == 1 and _is_kie_sensitive_error(last_reason):
                        continue
                    return None, None, last_reason

                data = submit_payload.get("data")
                task_id = data.get("taskId") if isinstance(data, Mapping) else None
                if not task_id:
                    logger.error("KIE generate: taskId missing: %r", submit_payload)
                    return None, None, "unknown"
                last_task_id = str(task_id)

                started = time.time()
                while True:
                    elapsed = int(time.time() - started)
                    if elapsed > KIE_IMAGE_MAX_WAIT_SEC:
                        return str(task_id), None, "timeout"

                    poll = client.get(KIE_RECORD_INFO_PATH, params={"taskId": str(task_id)})
                    poll.raise_for_status()
                    poll_payload = poll.json()
                    if not isinstance(poll_payload, Mapping):
                        logger.error("KIE poll bad payload: %r", poll_payload)
                        return str(task_id), None, "unknown"
                    if poll_payload.get("code") != 200:
                        logger.error("KIE poll failed: %r", poll_payload)
                        return str(task_id), None, _normalize_reason(poll_payload)

                    task_data = poll_payload.get("data")
                    if not isinstance(task_data, Mapping):
                        logger.error("KIE poll missing data: %r", poll_payload)
                        return str(task_id), None, "unknown"

                    success_flag_raw = task_data.get("successFlag")
                    try:
                        success_flag = int(success_flag_raw)
                    except (TypeError, ValueError):
                        success_flag = success_flag_raw
                    if success_flag == 1:
                        result_url = _extract_kie_result_url(task_data)
                        if result_url:
                            return str(task_id), result_url, ""
                        return str(task_id), None, "unknown"

                    if success_flag == 0:
                        time.sleep(max(2, POLL_INTERVAL))
                        continue

                    if success_flag in (2, 3):
                        reason = _normalize_reason(task_data)
                        if reason == "unknown":
                            reason = str(task_data.get("errorMessage") or task_data.get("message") or "unknown")
                        last_reason = reason
                        if attempt_idx == 1 and _is_kie_sensitive_error(reason):
                            logger.warning("KIE sensitive flag on first attempt, retrying with safe prompt")
                            break
                        return str(task_id), None, reason

                    logger.warning("KIE poll unknown successFlag=%r payload=%r", success_flag, poll_payload)
                    time.sleep(max(2, POLL_INTERVAL))
            return last_task_id or None, None, last_reason
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else None
        body = ""
        try:
            body = e.response.text if e.response is not None else ""
        except Exception:
            pass
        logger.error("KIE HTTP error (status=%s): %s", code, body)
        if code == 429:
            return None, None, "quota"
        if code == 402:
            return None, None, "quota"
        if code in {401, 403}:
            return None, None, "auth"
        return None, None, "network"
    except Exception as e:
        logger.warning("KIE measurements submit failed: %s", e)
        return None, None, "network"


async def generate_video(prompt: str, image_bytes: bytes) -> tuple[Optional[bytes], str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_one_video_sync, prompt, image_bytes, WAN_WEBAPP_ID)


async def generate_video_after(prompt: str, image_bytes: bytes) -> tuple[Optional[bytes], str]:
    """360° видео: тот же ai-app, что и «сейчас»; вход — картинка после WAN_AFTER_IMAGE_WEBAPP_ID."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_one_video_sync, prompt, image_bytes, WAN_WEBAPP_ID)


async def generate_after_body_image_via_rh(prompt: str, image_bytes: bytes) -> tuple[Optional[bytes], str]:
    """Кадр «после»"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_after_body_image_sync, prompt, image_bytes)


async def submit_measurements_to_rh(summary_text: str, image_bytes: bytes) -> tuple[Optional[str], Optional[str], str]:
    """Генерирует фото по замерам через KIE.ai (оставлено старое имя для совместимости)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _submit_measurements_app_sync, summary_text, image_bytes)
