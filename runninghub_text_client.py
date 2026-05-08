import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Optional

import httpx

from config import (
    HTTPS_PROXY,
    RH_TEXT_MAX_WAIT_SEC,
    RH_TEXT_PROMPT_FIELD_NAME,
    RH_TEXT_PROMPT_NODE_ID,
    RH_TEXT_WEBAPP_ID,
    WAN_API_KEY,
    WAN_BASE_URL,
)

logger = logging.getLogger(__name__)

RUN_PATH = "/task/openapi/ai-app/run"
OUTPUTS_PATH = "/task/openapi/outputs"
POLL_INTERVAL = 2


def _extract_text(payload: Mapping) -> Optional[str]:
    data = payload.get("data")
    if isinstance(data, str):
        text = data.strip()
        return text or None

    candidate_keys = (
        "text",
        "output_text",
        "outputText",
        "content",
        "answer",
        "result",
        "message",
    )

    def from_mapping(item: Mapping) -> Optional[str]:
        for key in candidate_keys:
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None

    if isinstance(data, Mapping):
        text = from_mapping(data)
        if text:
            return text
        nested = data.get("data")
        if isinstance(nested, Mapping):
            return from_mapping(nested)

    if isinstance(data, list):
        parts: list[str] = []
        for item in data:
            if not isinstance(item, Mapping):
                continue
            text = from_mapping(item)
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts).strip()

    return None


def _run_text_sync(prompt: str) -> Optional[str]:
    if not WAN_API_KEY:
        logger.error("WAN_API_KEY is not set")
        return None
    if not RH_TEXT_WEBAPP_ID:
        logger.error("RH_TEXT_WEBAPP_ID is not set")
        return None

    proxy = HTTPS_PROXY if HTTPS_PROXY else None
    payload = {
        "webappId": RH_TEXT_WEBAPP_ID,
        "apiKey": WAN_API_KEY,
        "nodeInfoList": [
            {
                "nodeId": RH_TEXT_PROMPT_NODE_ID,
                "fieldName": RH_TEXT_PROMPT_FIELD_NAME,
                "fieldValue": prompt,
            }
        ],
    }

    try:
        with httpx.Client(
            base_url=WAN_BASE_URL,
            proxy=proxy,
            timeout=httpx.Timeout(connect=30, read=120, write=30, pool=30),
            headers={"Content-Type": "application/json"},
        ) as client:
            submit = client.post(RUN_PATH, json=payload)
            submit.raise_for_status()
            body = submit.json()
            if not isinstance(body, Mapping):
                logger.error("RH text run: unexpected response: %r", body)
                return None
            if body.get("code") not in (0, "0"):
                logger.error("RH text run failed: %r", body)
                return None

            data = body.get("data")
            task_id = data.get("taskId") if isinstance(data, Mapping) else None
            if not task_id:
                logger.error("RH text run: taskId missing: %r", body)
                return None

            started = time.time()
            while True:
                elapsed = int(time.time() - started)
                if elapsed > RH_TEXT_MAX_WAIT_SEC:
                    logger.error("RH text poll timeout after %ss", elapsed)
                    return None

                resp = client.post(OUTPUTS_PATH, json={"apiKey": WAN_API_KEY, "taskId": task_id})
                resp.raise_for_status()
                poll = resp.json()
                if not isinstance(poll, Mapping):
                    poll = {"raw": str(poll)}
                code = poll.get("code")

                if code in (0, "0"):
                    text = _extract_text(poll)
                    if text:
                        return text
                    logger.error("RH text: no text in payload: %r", poll)
                    return None

                if code in (804, "804", 813, "813"):
                    time.sleep(POLL_INTERVAL)
                    continue

                logger.error("RH text poll failed: %r", poll)
                return None
    except Exception as e:
        logger.error("RH text client error: %s", e, exc_info=True)
        return None


async def ask_runninghub_text(prompt: str, *, max_output_tokens: int | None = None) -> Optional[str]:
    _ = max_output_tokens
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_text_sync, prompt)
