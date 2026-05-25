"""
Определение ракурса (анфас / профиль / спина) и порядок [front, side, back] для Wan r2v.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Literal

from google.genai import types

from gemini_client import get_client

logger = logging.getLogger(__name__)

PhotoView = Literal["front", "side", "back"]
VIEWS_ORDER: tuple[PhotoView, ...] = ("front", "side", "back")

# Ожидаемая подпись в боте: 1=спереди, 2=сзади, 3=сбоку → front, back, side
_FALLBACK_INDICES = (0, 2, 1)


def _mime(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) > 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _normalize_view(raw: str) -> PhotoView | None:
    key = (raw or "").strip().lower()
    aliases: dict[str, PhotoView] = {
        "front": "front",
        "анфас": "front",
        "face": "front",
        "back": "back",
        "rear": "back",
        "сзади": "back",
        "spine": "back",
        "side": "side",
        "profile": "side",
        "профиль": "side",
        "сбоку": "side",
    }
    return aliases.get(key)


def _parse_classification_json(text: str) -> dict[int, PhotoView] | None:
    if not text:
        return None

    def _from_dict(data: dict) -> dict[int, PhotoView] | None:
        out: dict[int, PhotoView] = {}
        for k, v in data.items():
            try:
                idx = int(k)
            except (TypeError, ValueError):
                continue
            view = _normalize_view(str(v))
            if view and 0 <= idx <= 2:
                out[idx] = view
        return out if len(out) == 3 else None

    # Полный JSON
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                parsed = _from_dict(data)
                if parsed:
                    return parsed
        except json.JSONDecodeError:
            pass

    # Обрезанный ответ модели: {"0":"front без закрывающей скобки
    pairs = re.findall(r'["\']?(\d)["\']?\s*:\s*["\']?([a-zA-Zа-яА-ЯёЁ]+)', text)
    if pairs:
        out: dict[int, PhotoView] = {}
        for idx_s, raw in pairs:
            try:
                idx = int(idx_s)
            except ValueError:
                continue
            view = _normalize_view(raw)
            if view and 0 <= idx <= 2:
                out[idx] = view
        if len(out) == 3:
            return out
    return None


def _order_from_map(photos: list[bytes], mapping: dict[int, PhotoView]) -> list[bytes]:
    by_view: dict[PhotoView, bytes] = {mapping[i]: photos[i] for i in range(3)}
    return [by_view[v] for v in VIEWS_ORDER]


def _classify_sync(photos: list[bytes]) -> list[bytes]:
    parts: list[types.Part] = [
        types.Part.from_text(
            text=(
                "You see three full-body photos of the SAME person in upload order (index 0, 1, 2). "
                "Classify each index as exactly one view: front (face/chest toward camera), "
                "back (back toward camera), or side (profile). "
                'Reply with ONLY JSON like {"0":"front","1":"back","2":"side"} — no other text.'
            )
        ),
    ]
    for i, blob in enumerate(photos):
        parts.append(types.Part.from_text(text=f"Photo index {i}:"))
        parts.append(types.Part.from_bytes(data=blob, mime_type=_mime(blob)))

    client = get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(max_output_tokens=256, temperature=0),
    )
    text = (response.text or "").strip()
    mapping = _parse_classification_json(text)
    if not mapping:
        raise ValueError(f"bad classification JSON: {text[:200]}")
    ordered = _order_from_map(photos, mapping)
    logger.info("photo views classified: %s", {i: mapping[i] for i in sorted(mapping)})
    return ordered


async def order_photos_front_side_back(photos: list[bytes]) -> list[bytes]:
    """Возвращает [анфас, профиль, спина] для Image1 / Image2 / Image3 в Wan r2v."""
    if len(photos) != 3:
        return list(photos)
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _classify_sync, photos)
    except Exception as e:
        logger.warning("photo view classification failed, using upload labels 1=front 2=back 3=side: %s", e)
        return [photos[_FALLBACK_INDICES[0]], photos[_FALLBACK_INDICES[1]], photos[_FALLBACK_INDICES[2]]]
