import asyncio
import logging
from typing import Optional

import httpx
from google import genai
from google.genai import types

from config import GOOGLE_AI_API_KEY, GEMINI_MODEL, HTTPS_PROXY

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CLIENT SINGLETON (ВАЖНО)
# ─────────────────────────────────────────────

_httpx_client = None
_gemini_client = None


def get_client():
    global _httpx_client, _gemini_client

    if _gemini_client:
        return _gemini_client

    if HTTPS_PROXY:
        transport = httpx.HTTPTransport(proxy=HTTPS_PROXY)

        _httpx_client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(30, 120, 30, 30),
        )

        _gemini_client = genai.Client(
            api_key=GOOGLE_AI_API_KEY,
            http_options={"httpx_client": _httpx_client},
        )
    else:
        _gemini_client = genai.Client(api_key=GOOGLE_AI_API_KEY)

    return _gemini_client


# ─────────────────────────────────────────────
# RETRY LOGIC (ASYNC BACKOFF)
# ─────────────────────────────────────────────

class GeminiRetry:
    def __init__(self, max_retries: int = 5):
        self.max_retries = max_retries

    async def run(self, prompt: str, *, max_output_tokens: int | None = None) -> Optional[str]:
        delay = 2
        config = (
            types.GenerateContentConfig(max_output_tokens=max_output_tokens)
            if max_output_tokens is not None
            else None
        )

        for attempt in range(1, self.max_retries + 1):
            try:
                client = get_client()

                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )

                return response.text

            except Exception as e:
                msg = str(e).lower()

                is_rate_limit = "429" in msg or "quota" in msg or "resource_exhausted" in msg
                is_network = any(x in msg for x in ["ssl", "connect", "timeout", "eof"])

                if attempt == self.max_retries:
                    logger.error(f"Gemini failed: {e}", exc_info=True)
                    return None

                if is_rate_limit:
                    wait = delay * attempt
                    logger.warning(f"Rate limit hit → retry in {wait}s")
                    await asyncio.sleep(wait)
                    continue

                if is_network:
                    wait = delay * attempt
                    logger.warning(f"Network error → retry in {wait}s")
                    await asyncio.sleep(wait)
                    continue

                logger.error(f"Gemini unexpected error: {e}")
                return None

        return None


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

_retry = GeminiRetry()


async def ask_gemini(prompt: str, *, max_output_tokens: int | None = None) -> Optional[str]:
    return await _retry.run(prompt, max_output_tokens=max_output_tokens)