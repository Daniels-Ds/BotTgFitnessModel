"""Подгонка кадров под ограничения i2v (Hailuo: aspect ratio 0.4–2.5)."""
from __future__ import annotations

import io
import logging
import math

logger = logging.getLogger(__name__)

# fal Hailuo — https://docs.fal.ai/errors#image_aspect_ratio_error
_MIN_AR = 0.4
_MAX_AR = 2.5
_MIN_AR_TARGET = 0.401
_MAX_AR_TARGET = 2.49
_PAD_RGB = (255, 255, 255)

_WARN_TOO_NARROW = 0.35
_WARN_TOO_WIDE = 2.8


def _open_rgb(image_bytes: bytes):
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(image_bytes))
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def _jpeg_bytes(im) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


def image_aspect_ratio(image_bytes: bytes) -> tuple[float, int, int] | None:
    """width/height после EXIF; None если не удалось прочитать."""
    try:
        im = _open_rgb(image_bytes)
    except Exception:
        return None
    w, h = im.size
    if w < 1 or h < 1:
        return None
    return w / h, w, h


def photo_aspect_hint(image_bytes: bytes) -> str | None:
    """Короткое предупреждение при загрузке экстремальных пропорций."""
    info = image_aspect_ratio(image_bytes)
    if not info:
        return None
    ratio, _w, _h = info
    if ratio < _WARN_TOO_NARROW:
        return (
            "⚠️ Кадр очень узкий (похоже на сильный кроп). Для видео лучше фото "
            "<b>в полный рост</b> в портретном режиме телефона (9:16), без обрезки по бокам. "
            "Я попробую подогнать кадр автоматически."
        )
    if ratio > _WARN_TOO_WIDE:
        return (
            "⚠️ Кадр слишком широкий (панорама). Для видео лучше вертикальное фото "
            "<b>в полный рост</b>. Попробую подогнать кадр автоматически."
        )
    return None


def fit_image_for_hailuo(image_bytes: bytes, *, strict: bool = False) -> bytes:
    """EXIF + паддинг (без кропа) до ratio ∈ [0.4, 2.5], JPEG без EXIF."""
    min_target = 0.42 if strict else _MIN_AR_TARGET
    max_target = 2.45 if strict else _MAX_AR_TARGET

    try:
        from PIL import Image

        im = _open_rgb(image_bytes)
    except ImportError:
        logger.warning("Pillow not installed — Hailuo frames not normalized")
        return image_bytes
    except Exception as e:
        logger.warning("fit_image_for_hailuo: open failed: %s", e)
        return image_bytes

    w, h = im.size
    if w < 1 or h < 1:
        return image_bytes

    ratio = w / h
    mode: str | None = None

    if ratio < min_target:
        new_w = max(w, math.ceil(h * min_target))
        pad_left = (new_w - w) // 2
        canvas = Image.new("RGB", (new_w, h), _PAD_RGB)
        canvas.paste(im, (pad_left, 0))
        im = canvas
        mode = "sides"
    elif ratio > max_target:
        new_h = max(h, math.ceil(w / max_target))
        pad_top = (new_h - h) // 2
        canvas = Image.new("RGB", (w, new_h), _PAD_RGB)
        canvas.paste(im, (0, pad_top))
        im = canvas
        mode = "top_bottom"

    if mode is None:
        return _jpeg_bytes(im)

    nw, nh = im.size
    out_ar = nw / nh
    out = _jpeg_bytes(im)
    logger.info(
        "hailuo frame: pad-%s %sx%s ar=%.3f -> %sx%s ar=%.3f",
        mode,
        w,
        h,
        ratio,
        nw,
        nh,
        out_ar,
    )
    if out_ar < _MIN_AR or out_ar > _MAX_AR:
        logger.warning(
            "hailuo frame: padded ar=%.4f still outside fal limits",
            out_ar,
        )
    return out
