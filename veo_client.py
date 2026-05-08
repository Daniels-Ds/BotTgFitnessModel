"""
Google VEO 3.1 client — with retry logic for unstable proxy connections
"""
import asyncio
import base64
import logging
import time
from collections.abc import Mapping
from google import genai
from typing import Optional
from config import GOOGLE_AI_API_KEY, VEO_MODEL, HTTPS_PROXY

logger = logging.getLogger(__name__)

MAX_RETRIES = 5       # сколько раз повторять при SSL ошибке
POLL_INTERVAL = 15    # секунд между проверками (больше = меньше нагрузка на прокси)
MAX_WAIT = 600        # максимум 10 минут
_last_failure_reason = "unknown"


def _set_failure_reason(reason: str) -> None:
    global _last_failure_reason
    _last_failure_reason = reason


def _get_failure_reason() -> str:
    return _last_failure_reason


def _make_client():
    from google import genai

    return genai.Client(
        api_key=GOOGLE_AI_API_KEY,
        vertexai=False
    )


def _poll_with_retry(client, operation, start_time: float) -> Optional[object]:
    """Poll operation with retry on SSL/connection errors."""
    while True:
        elapsed = int(time.time() - start_time)
        if elapsed > MAX_WAIT:
            logger.error("VEO timeout after 10 minutes")
            _set_failure_reason("timeout")
            return None

        time.sleep(POLL_INTERVAL)
        elapsed = int(time.time() - start_time)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                operation = client.operations.get(operation)
                logger.info(f"Poll ({elapsed}s) done={operation.done}")
                break  # success
            except Exception as e:
                err_str = str(e)
                is_ssl = "SSL" in err_str or "EOF" in err_str or "ConnectError" in err_str
                if is_ssl and attempt < MAX_RETRIES:
                    wait = attempt * 5  # 5, 10, 15, 20 сек
                    logger.warning(f"SSL error on poll (attempt {attempt}/{MAX_RETRIES}), retry in {wait}s: {e}")
                    time.sleep(wait)
                    # Пересоздаём клиент при SSL ошибке
                    try:
                        client = _make_client()
                    except Exception:
                        pass
                    continue
                else:
                    logger.error(f"Poll failed after {attempt} attempts: {e}")
                    _set_failure_reason("network")
                    return None
        else:
            # All retries exhausted
            return None

        if operation.done:
            return operation


def _extract_generated_videos(operation) -> list:
    """
    Robust extraction for different SDK response shapes.
    Returns [] when operation has no videos.
    """
    if operation is None:
        _set_failure_reason("unknown")
        return []

    op_error = getattr(operation, "error", None)
    if op_error:
        err_text = str(op_error).lower()
        if "safety" in err_text or "policy" in err_text or "blocked" in err_text or "censor" in err_text:
            _set_failure_reason("safety")
        elif "quota" in err_text or "resource_exhausted" in err_text or "429" in err_text:
            _set_failure_reason("quota")
        else:
            _set_failure_reason("unknown")
        logger.error("VEO operation finished with error: %s", op_error)
        return []

    response = getattr(operation, "response", None)
    if response is None:
        logger.error("VEO operation has no response (done=%s)", getattr(operation, "done", None))
        _set_failure_reason("unknown")
        return []

    # SDK object form: response.generated_videos
    videos = getattr(response, "generated_videos", None)
    if videos:
        return list(videos)

    # Dict-like form from some SDK/runtime combinations
    if isinstance(response, Mapping):
        for key in ("generated_videos", "generatedVideos", "videos"):
            val = response.get(key)
            if val:
                return list(val)

    # Some SDKs may nest payload under "result"
    result = getattr(response, "result", None)
    if isinstance(result, Mapping):
        for key in ("generated_videos", "generatedVideos", "videos"):
            val = result.get(key)
            if val:
                return list(val)
    elif result is not None:
        result_videos = getattr(result, "generated_videos", None)
        if result_videos:
            return list(result_videos)

    logger.error(
        "No generated videos in response. response_type=%s response=%r",
        type(response).__name__,
        response,
    )
    _set_failure_reason("unknown")
    return []


def _generate_one_video_sync(prompt: str, image_bytes: bytes) -> Optional[bytes]:
    try:
        from google.genai import types
        _set_failure_reason("unknown")

        client = _make_client()

        logger.info(f"Submitting VEO job...")
        operation = client.models.generate_videos(
            model=VEO_MODEL,
            prompt=prompt,
            image=types.Image(image_bytes=image_bytes, mime_type="image/jpeg"),
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",
                number_of_videos=1,
            ),
        )

        start_time = time.time()
        logger.info("Job submitted, polling...")

        operation = _poll_with_retry(client, operation, start_time)
        if operation is None:
            return None

        # Extract video
        videos = _extract_generated_videos(operation)
        if not videos:
            return None

        first = videos[0]
        video = getattr(first, "video", None)
        if video is None and isinstance(first, Mapping):
            video = first.get("video")
        if video is None:
            logger.error("First generated item has no video payload: %r", first)
            _set_failure_reason("unknown")
            return None

        logger.info(f"Got video object, attrs: {[a for a in dir(video) if not a.startswith('_')]}")

        # Case 1: direct bytes
        if hasattr(video, "video_bytes") and video.video_bytes:
            data = video.video_bytes
            logger.info(f"Got video_bytes: {len(data)} bytes")
            _set_failure_reason("")
            return bytes(data)

        # Case 2: URI — download
        if hasattr(video, "uri") and video.uri:
            logger.info(f"Downloading from URI: {video.uri}")
            
            # Try SDK download first
            try:
                client.files.download(file=video)
                if hasattr(video, "video_bytes") and video.video_bytes:
                    _set_failure_reason("")
                    return bytes(video.video_bytes)
            except Exception as e:
                logger.warning(f"SDK download failed: {e}")

            # Fallback: direct httpx download
            import httpx
            headers = {"x-goog-api-key": GOOGLE_AI_API_KEY}
            proxies = {"https://": HTTPS_PROXY} if HTTPS_PROXY else None
            
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    with httpx.Client(
                        proxy=HTTPS_PROXY if HTTPS_PROXY else None,
                        timeout=httpx.Timeout(connect=30, read=120, write=30, pool=30),
                        follow_redirects=True
                    ) as http:
                        resp = http.get(video.uri, headers=headers)
                    if resp.status_code == 200:
                        logger.info(f"Downloaded {len(resp.content)} bytes")
                        _set_failure_reason("")
                        return resp.content
                    logger.error(f"URI download status: {resp.status_code}")
                    _set_failure_reason("network")
                    return None
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        logger.warning(f"Download attempt {attempt} failed: {e}, retrying...")
                        time.sleep(attempt * 3)
                    else:
                        logger.error(f"Download failed after {MAX_RETRIES} attempts: {e}")
                        _set_failure_reason("network")
                        return None

        logger.error("No video_bytes and no uri")
        _set_failure_reason("unknown")
        return None

    except Exception as e:
        logger.error(f"VEO error: {e}", exc_info=True)
        _set_failure_reason("unknown")
        return None


async def generate_video(prompt: str, image_bytes: bytes) -> tuple[Optional[bytes], str]:
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _generate_one_video_sync, prompt, image_bytes)
    return data, _get_failure_reason()
