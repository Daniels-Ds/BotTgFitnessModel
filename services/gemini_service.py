from typing import Optional

from services.dashscope_text_client import ask_dashscope_text


async def generate_workout(prompt: str, *, max_tokens: int = 2000) -> Optional[str]:
    return await ask_dashscope_text(prompt, max_tokens=max_tokens)
