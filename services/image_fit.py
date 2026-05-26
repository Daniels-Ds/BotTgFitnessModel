"""Подгонка кадров под ограничения i2v (Hailuo: aspect ratio 0.4–2.5)."""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# fal Hailuo 02 / 2.3 — https://docs.fal.ai/errors#image_aspect_ratio_error
_MIN_AR = 0.4
_MAX_AR = 2.5
_PAD_RGB = (255, 255, 255)


def fit_image_for_hailuo(image_bytes: bytes) -> bytes:
    """
    Паддинг до допустимого aspect ratio (без кропа — тело не обрезается).
    9:16 и прочие кадры в [0.4, 2.5] возвращаются как есть.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed — Hailuo frames not normalized")
        return image_bytes

    try:
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        logger.warning("fit_image_for_hailuo: open failed: %s", e)
        return image_bytes

    w, h = im.size
    if w < 1 or h < 1:
        return image_bytes

    ratio = w / h
    if _MIN_AR <= ratio <= _MAX_AR:
        return image_bytes

    if ratio < _MIN_AR:
        new_w = int(h * _MIN_AR)
        pad_left = (new_w - w) // 2
        canvas = Image.new("RGB", (new_w, h), _PAD_RGB)
        canvas.paste(im, (pad_left, 0))
        mode = "sides"
    else:
        new_h = int(w / _MAX_AR)
        pad_top = (new_h - h) // 2
        canvas = Image.new("RGB", (w, new_h), _PAD_RGB)
        canvas.paste(im, (0, pad_top))
        mode = "top_bottom"

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=90, optimize=True)
    out = buf.getvalue()
    nw, nh = canvas.size
    logger.info(
        "hailuo frame: pad-%s %sx%s ar=%.3f -> %sx%s ar=%.3f",
        mode,
        w,
        h,
        ratio,
        nw,
        nh,
        nw / nh,
    )
    return out
