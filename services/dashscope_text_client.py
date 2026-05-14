import asyncio
import logging
from typing import Optional

import httpx

from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_CHAT_COMPLETIONS_URL,
    DASHSCOPE_TEXT_MODEL,
    HTTPS_PROXY,
)

logger = logging.getLogger(__name__)


async def ask_dashscope_text(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.6,
    max_tokens: int | None = None,
    max_retries: int = 2,
) -> Optional[str]:
    if not DASHSCOPE_API_KEY:
        logger.error("DASHSCOPE_API_KEY / ALIBABA_MODEL_STUDIO_API_KEY is not set")
        return None

    payload: dict = {
        "model": model or DASHSCOPE_TEXT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    proxy = HTTPS_PROXY if HTTPS_PROXY else None
    timeout = httpx.Timeout(connect=20, read=120, write=20, pool=20)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, proxy=proxy) as client:
                resp = await client.post(
                    DASHSCOPE_CHAT_COMPLETIONS_URL,
                    headers={
                        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            choices = data.get("choices") if isinstance(data, dict) else None
            if not choices:
                return None

            first = choices[0] if isinstance(choices, list) and choices else None
            if not isinstance(first, dict):
                return None

            msg = first.get("message")
            if not isinstance(msg, dict):
                return None

            content = msg.get("content")
            return content.strip() if isinstance(content, str) and content.strip() else None
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
        except httpx.HTTPStatusError as e:
            last_error = e
            status = getattr(e.response, "status_code", None)
            if status not in (429, 500, 502, 503, 504):
                try:
                    logger.warning(
                        "DashScope chat HTTP %s: %s",
                        status,
                        (e.response.text[:500] if e.response else ""),
                    )
                except Exception:
                    pass
                break

        await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("DashScope chat request failed: %r", last_error)
    return None
