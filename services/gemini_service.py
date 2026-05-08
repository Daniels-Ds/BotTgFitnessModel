from typing import Optional

from services.openrouter_text_client import ask_openrouter_text


async def generate_workout(prompt: str) -> Optional[str]:
    # Тренировочный план обычно длиннее, чем рекомендации по питанию.
    return await ask_openrouter_text(prompt, max_tokens=2000)
