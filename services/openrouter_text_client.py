import asyncio
import logging
from typing import Optional

import httpx

from config import (
    HTTPS_PROXY,
    OPENROUTER_API_KEY,
    OPENROUTER_CHAT_COMPLETIONS_URL,
    OPENROUTER_MODEL,
)

logger = logging.getLogger(__name__)


async def ask_openrouter_text(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.6,
    max_tokens: int | None = None,
    max_retries: int = 2,
) -> Optional[str]:
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set")
        return None

    payload: dict = {
        "model": model or OPENROUTER_MODEL,
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
                    OPENROUTER_CHAT_COMPLETIONS_URL,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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
            # Повторяем только на временных ошибках.
            status = getattr(e.response, "status_code", None)
            if status not in (429, 500, 502, 503, 504):
                break

        # Небольшая пауза перед ретраем
        await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("OpenRouter request failed: %r", last_error)
    return None

