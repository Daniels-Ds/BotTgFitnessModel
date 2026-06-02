"""
Хендлеры бота: онбординг, кадры «после» (fal Hunyuan), два видео (fal Kling O3).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
import hashlib
import logging
import re
import time
from pathlib import Path
from aiogram import Dispatcher, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, InputMediaVideo, Message

from core.callbacks import CB
from core.tasks import task_manager
from db import (
    delete_workout_day,
    get_latest_body_measurement,
    get_workout_day_body,
    save_body_measurement,
    save_workout_day_body,
)
from keyboards import (
    activity_kb,
    cycle_kb,
    edit_menu_kb,
    gender_kb,
    muscle_kb,
    photo_aspect_kb,
    post_gen_kb,
    video_fallback_kb,
    water_footer_kb,
    welcome_kb,
    workout_today_kb,
)
from messages import (
    ASK_ACTIVITY,
    ASK_CYCLE,
    ASK_AGE,
    ASK_GENDER,
    ASK_HEIGHT,
    ASK_MEAS_BICEPS,
    ASK_MEAS_CALF,
    ASK_MEAS_CHEST,
    ASK_MEAS_FRONT_PHOTO,
    ASK_MEAS_HIPS,
    ASK_MEAS_SHOULDERS,
    ASK_MEAS_THIGH,
    ASK_MEAS_WAIST,
    ASK_PHOTOS,
    ASK_WEIGHT,
    ERROR_MEAS_PHOTO,
    ERROR_NOT_NUMBER,
    ERROR_NOT_PHOTO,
    ERROR_RANGE,
    MUSCLE_HINT,
    PHOTO_1_OK,
    PHOTO_2_OK,
    PHOTO_3_OK,
    photo_resend_prompt,
    POST_GEN_MENU,
    VIDEOS_READY,
    WELCOME,
    MEASUREMENTS_START,
    WORKOUT_FAIL,
    ask_muscles,
    profile_summary,
    progress_msg,
    workout_generating_html,
    workout_today_header_html,
)
from prompts import (
    after_intensity_tier,
    after_body_edit_prompt,
    body_measurements_overlay_prompt,
    nutrition_prompt,
    hailuo_after_turn_prompt,
    hailuo_before_turn_prompt,
    water_hint_text,
    workout_prompt_today,
)
from services.image_fit import fit_image_for_hailuo, photo_aspect_hint
from services.photo_order import VIEWS_ORDER, order_photos_front_side_back
from services.dashscope_qwen_image_edit_client import edit_measurements_overlay_qwen
from services.fal_flux_edit_client import edit_after_body_image_flux
from services.fal_hailuo_video_client import generate_hailuo_fal_video
from services.dashscope_text_client import ask_dashscope_text
from services.gemini_service import generate_workout
from config import (
    DASHSCOPE_API_KEY,
    FAL_KEY,
    TELEGRAM_REQUEST_TIMEOUT_SEC,
    pipeline_after_views,
)
from states import Measurements, Onboarding, PostGen
from utils import init_ui, remove_all_html
router = Router()
logger = logging.getLogger(__name__)

_active_tasks: dict[int, str] = {}
veo_lock = asyncio.Semaphore(1)


def is_busy(user_id: int) -> bool:
    return user_id in _active_tasks or task_manager.is_busy(user_id)


async def reject_if_busy(cb: CallbackQuery) -> bool:
    """True — колбэк уже отвечен, обработку прервать (идёт видео/Gemini)."""
    if is_busy(cb.from_user.id):
        await safe_answer(cb, "Сейчас идёт генерация. Подождите.", alert=True)
        return True
    return False


async def safe_answer(cb: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    try:
        await cb.answer(text, show_alert=alert)
    except Exception:
        pass


def _hide_service_names(text: str) -> str:
    """Убрать из текста ошибок названия провайдеров и env-переменных."""
    cleaned = (text or "").strip()
    for token in (
        "RunningHub",
        "runninghub",
        "DashScope",
        "dashscope",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE",
        "ALIBABA_MODEL_STUDIO_API_KEY",
        "ALIBABA_MODEL_STUDIO",
        "Model Studio",
        "MODEL_STUDIO",
        "Alibaba",
        "Gemini",
        "google.genai",
        "google",
        "fal.ai",
        "fal_client",
        "fal",
        "FAL_KEY",
        "FAL_",
        "Kie",
        "kie",
        "Qwen",
        "qwen",
        "Seedream",
        "seedream",
        "Hunyuan",
        "hunyuan",
        "Hailuo",
        "hailuo",
        "Kling",
        "kling",
        "Minimax",
        "Flux",
        "flux",
        "ByteDance",
        "OpenRouter",
        "Vertex",
        "aliyuncs",
        "minimax",
        ".env",
    ):
        cleaned = cleaned.replace(token, "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;—-")
    return cleaned or "временная ошибка"


def _user_error_appendix(reason: str) -> str:
    """Строка «Причина: …» для пользователя; без технических деталей конфига."""
    if not reason:
        return ""
    low = reason.lower()
    if any(
        x in low
        for x in (
            "api_key",
            "не задан",
            "not set",
            ".env",
            "fal_key",
            "dashscope",
            "model_studio",
            "временно недоступна",
        )
    ):
        return ""
    detail = _hide_service_names(reason)
    if detail == "временная ошибка" and len((reason or "").strip()) < 3:
        return ""
    return f"\nПричина: {detail}"


async def _prepare_photo_after_one(photo: bytes, data: dict, view: str) -> bytes:
    """«После» — fal Seedream/Flux edit; при ошибке — исходный кадр."""
    prompt = after_body_edit_prompt(data, view=view)
    out = await edit_after_body_image_flux(
        photo,
        prompt,
        intensity_tier=after_intensity_tier(data),
    )
    if out:
        if out == photo:
            logger.warning("after-body %s fal-flux: same bytes as input", view)
        return out
    logger.warning("after-body %s fal-flux: None — using original", view)
    return photo


def _photo_by_view(photos_ordered: list[bytes], view: str) -> bytes:
    idx = VIEWS_ORDER.index(view)  # type: ignore[arg-type]
    return photos_ordered[idx]


async def _prepare_photos_after(photos_ordered: list[bytes], data: dict) -> list[bytes]:
    """«После»: Hunyuan edit для ракурсов из PIPELINE_AFTER_VIEWS (по умолчанию front + back)."""
    views = pipeline_after_views()
    out = [bytes(p) for p in photos_ordered]
    logger.info("after-body: editing views=%s", ",".join(views))

    async def _one(view: str) -> tuple[str, bytes]:
        raw = _photo_by_view(photos_ordered, view)
        logger.info("after-body: preparing view=%s bytes=%s", view, len(raw))
        edited = await _prepare_photo_after_one(raw, data, view)
        return view, edited

    if views:
        results = await asyncio.gather(*[_one(v) for v in views])
        for view, edited in results:
            out[VIEWS_ORDER.index(view)] = edited  # type: ignore[arg-type]
    return out


def _hailuo_turn_frames(
    photos: list[bytes],
) -> tuple[bytes, bytes | None]:
    """Старт = анфас; финиш = спина, если back в PIPELINE_AFTER_VIEWS."""
    start = _photo_by_view(photos, "front")
    views = pipeline_after_views()
    end = _photo_by_view(photos, "back") if "back" in views else None
    return start, end


def _log_before_after_sets(before: list[bytes], after: list[bytes]) -> None:
    for view, b, a in zip(VIEWS_ORDER, before, after):
        hb = hashlib.sha256(b).hexdigest()[:12]
        ha = hashlib.sha256(a).hexdigest()[:12]
        logger.info(
            "before/after view=%s before_sha=%s bytes=%s after_sha=%s bytes=%s identical=%s",
            view,
            hb,
            len(b),
            ha,
            len(a),
            hb == ha,
        )


async def safe_generate_hailuo_video(
    prompt: str,
    start_frame: bytes,
    end_frame: bytes | None = None,
):
    async with veo_lock:
        return await generate_hailuo_fal_video(prompt, start_frame, end_frame)


async def retry_veo(fn, *args, retries: int = 3, **kwargs):
    for i in range(retries):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                await asyncio.sleep(2**i)
                continue
            raise
    return None, "unknown"


def _parse_int(raw: str) -> int | None:
    m = re.search(r"-?\d+", (raw or "").strip().replace(",", "."))
    if not m:
        return None
    return int(m.group(0))


MEASUREMENT_FIELDS: list[tuple[str, str, str]] = [
    ("waist", "Талия", ASK_MEAS_WAIST),
    ("hips", "Бёдра", ASK_MEAS_HIPS),
    ("chest", "Грудь", ASK_MEAS_CHEST),
    ("shoulders", "Плечи", ASK_MEAS_SHOULDERS),
    ("thigh", "Бедро", ASK_MEAS_THIGH),
    ("calf", "Икра", ASK_MEAS_CALF),
    ("biceps", "Бицепс", ASK_MEAS_BICEPS),
]


def _measurements_text(values: dict[str, int]) -> str:
    parts = [f"• {label}: {int(values[key])} см" for key, label, _ in MEASUREMENT_FIELDS]
    return "<b>📏 Замеры тела</b>\n" + "\n".join(parts)


def _measurements_prompt(values: dict[str, int]) -> str:
    return "\n".join([f"{label}: {int(values[key])} см" for key, label, _ in MEASUREMENT_FIELDS])


async def _refresh_muscle_board(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = data.get("muscles") or {}
    text = ask_muscles()
    kb = muscle_kb(selected)

    edit_ok = False
    for i in range(3):
        try:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            edit_ok = True
            break
        except TelegramBadRequest as e:
            low = str(e).lower()
            if "message is not modified" in low or "message_not_modified" in low:
                return
            break
        except TelegramNetworkError as e:
            logger.warning("muscle_board edit network try %s/3: %s", i + 1, e)
            if i < 2:
                await asyncio.sleep(0.25 * (2**i))
    if edit_ok:
        return

    for i in range(3):
        try:
            await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
            return
        except TelegramNetworkError as e:
            logger.warning("muscle_board answer network try %s/3: %s", i + 1, e)
            if i == 2:
                raise
            await asyncio.sleep(0.25 * (2**i))


# ─── /start ───────────────────────────────────


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await init_ui(state)
    await message.answer(WELCOME, parse_mode="HTML", reply_markup=welcome_kb())


@router.callback_query(F.data == CB.START_FLOW)
async def start_flow(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Onboarding.photos)
    await state.update_data(
        photos=[],
        muscles={},
        water_ml_today=0,
        photo_aspect_warn_idx=None,
        photo_replace_at=None,
    )
    await safe_answer(cb)
    try:
        await cb.message.edit_text(ASK_PHOTOS, parse_mode="HTML")
    except Exception:
        await cb.message.answer(ASK_PHOTOS, parse_mode="HTML")


# ─── Фото ─────────────────────────────────────


async def _send_photo_step_ack(message: Message, state: FSMContext, n: int) -> None:
    if n == 1:
        await message.answer(PHOTO_1_OK, parse_mode="HTML")
    elif n == 2:
        await message.answer(PHOTO_2_OK, parse_mode="HTML")
    elif n >= 3:
        await message.answer(PHOTO_3_OK, parse_mode="HTML")
        await state.set_state(Onboarding.gender)
        await message.answer(ASK_GENDER, parse_mode="HTML", reply_markup=gender_kb())


async def _download_tg_photo(message: Message) -> bytes | None:
    try:
        buf = await message.bot.download(message.photo[-1])
        try:
            return buf.read()
        finally:
            if hasattr(buf, "close"):
                buf.close()
    except Exception as e:
        logger.warning("photo download: %s", e)
        return None


async def _apply_photo_chunk(
    message: Message,
    state: FSMContext,
    chunk: bytes,
    *,
    replace_at: int | None,
) -> None:
    data = await state.get_data()
    photos: list[bytes] = list(data.get("photos") or [])

    if replace_at is not None:
        if replace_at == len(photos):
            photos.append(chunk)
        elif 0 <= replace_at < len(photos):
            photos[replace_at] = chunk
        else:
            photos.append(chunk)
        await state.update_data(photos=photos, photo_replace_at=None)
    else:
        if data.get("photo_aspect_warn_idx") is not None:
            await state.update_data(photo_aspect_warn_idx=None)
        photos.append(chunk)
        await state.update_data(photos=photos)

    n = len(photos)
    hint = photo_aspect_hint(chunk)
    if hint:
        await state.update_data(photo_aspect_warn_idx=n - 1)
        if n < 3:
            hint += (
                "\n\n<b>Заменить</b> это фото или <b>начать с 3 фото заново</b> — кнопки ниже. "
                "Можно и просто прислать <b>следующее</b> фото."
            )
        else:
            hint += (
                "\n\n<b>Заменить</b> третье фото, <b>загрузить все 3 заново</b> "
                "или нажать <b>«Оставить и продолжить»</b>."
            )
        await message.answer(
            hint,
            parse_mode="HTML",
            reply_markup=photo_aspect_kb(show_keep=(n >= 3)),
        )
        if n < 3:
            await _send_photo_step_ack(message, state, n)
        return

    await state.update_data(photo_aspect_warn_idx=None)
    await _send_photo_step_ack(message, state, n)


@router.message(StateFilter(Onboarding.photos), F.photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[bytes] = list(data.get("photos") or [])
    replace_at = data.get("photo_replace_at")
    if replace_at is None and len(photos) >= 3:
        if data.get("photo_aspect_warn_idx") is not None:
            await message.answer(
                "Сначала замените третье фото, нажмите «Оставить и продолжить» "
                "или загрузите все 3 заново — кнопки под предупреждением выше.",
            )
        else:
            await message.answer("Уже есть 3 фото. Используйте «Изменить параметры» или /start.")
        return

    chunk = await _download_tg_photo(message)
    if chunk is None:
        await message.answer(ERROR_NOT_PHOTO)
        return

    await _apply_photo_chunk(
        message,
        state,
        chunk,
        replace_at=replace_at if replace_at is not None else None,
    )


@router.callback_query(StateFilter(Onboarding.photos), F.data == CB.PHOTO_REPLACE)
async def on_photo_aspect_replace(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[bytes] = list(data.get("photos") or [])
    idx = data.get("photo_aspect_warn_idx")
    if idx is None or not isinstance(idx, int) or idx < 0 or idx >= len(photos):
        await safe_answer(cb, "Нечего заменять — пришлите следующее фото.", alert=True)
        return
    photos.pop(idx)
    await state.update_data(
        photos=photos,
        photo_replace_at=idx,
        photo_aspect_warn_idx=None,
    )
    await safe_answer(cb)
    await cb.message.answer(photo_resend_prompt(idx), parse_mode="HTML")


@router.callback_query(StateFilter(Onboarding.photos), F.data == CB.PHOTO_RESTART_ALL)
async def on_photo_aspect_restart(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        photos=[],
        photo_aspect_warn_idx=None,
        photo_replace_at=None,
    )
    await safe_answer(cb)
    await cb.message.answer(ASK_PHOTOS, parse_mode="HTML")


@router.callback_query(StateFilter(Onboarding.photos), F.data == CB.PHOTO_KEEP)
async def on_photo_aspect_keep(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[bytes] = list(data.get("photos") or [])
    if data.get("photo_aspect_warn_idx") is None:
        await safe_answer(cb, "Предупреждение уже неактуально.", alert=True)
        return
    if len(photos) < 3:
        await safe_answer(cb, "Сначала загрузите 3 фото.", alert=True)
        return
    await state.update_data(photo_aspect_warn_idx=None, photo_replace_at=None)
    await safe_answer(cb)
    await _send_photo_step_ack(cb.message, state, 3)


@router.message(StateFilter(Onboarding.photos))
async def on_photo_bad(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("photo_replace_at") is not None:
        slot = int(data["photo_replace_at"])
        await message.answer(
            f"{photo_resend_prompt(slot)}\n\n(Нужно именно <b>фото</b>, не файл.)",
            parse_mode="HTML",
        )
        return
    await message.answer(ERROR_NOT_PHOTO)


# ─── Пол ──────────────────────────────────────


@router.callback_query(StateFilter(Onboarding.gender), F.data.in_({CB.GENDER_MALE, CB.GENDER_FEMALE}))
async def on_gender(cb: CallbackQuery, state: FSMContext) -> None:
    gender = "male" if cb.data == CB.GENDER_MALE else "female"
    await state.update_data(gender=gender)
    await state.set_state(Onboarding.age)
    await safe_answer(cb)
    await cb.message.answer(ASK_AGE, parse_mode="HTML")


# ─── Числа: возраст / рост / вес ──────────────


@router.message(StateFilter(Onboarding.age), F.text)
async def on_age(message: Message, state: FSMContext) -> None:
    v = _parse_int(message.text)
    if v is None:
        await message.answer(ERROR_NOT_NUMBER)
        return
    if not (12 <= v <= 90):
        await message.answer(ERROR_RANGE)
        return
    await state.update_data(age=v)
    await state.set_state(Onboarding.height)
    await message.answer(ASK_HEIGHT, parse_mode="HTML")


@router.message(StateFilter(Onboarding.height), F.text)
async def on_height(message: Message, state: FSMContext) -> None:
    v = _parse_int(message.text)
    if v is None:
        await message.answer(ERROR_NOT_NUMBER)
        return
    if not (120 <= v <= 230):
        await message.answer(ERROR_RANGE)
        return
    await state.update_data(height=v)
    await state.set_state(Onboarding.weight)
    await message.answer(ASK_WEIGHT, parse_mode="HTML")


@router.message(StateFilter(Onboarding.weight), F.text)
async def on_weight(message: Message, state: FSMContext) -> None:
    v = _parse_int(message.text)
    if v is None:
        await message.answer(ERROR_NOT_NUMBER)
        return
    if not (35 <= v <= 250):
        await message.answer(ERROR_RANGE)
        return
    await state.update_data(weight=v)
    await state.set_state(Onboarding.activity)
    await message.answer(ASK_ACTIVITY, parse_mode="HTML", reply_markup=activity_kb())


# ─── Активность ──────────────────────────────


@router.callback_query(StateFilter(Onboarding.activity), F.data.in_({CB.ACT_LOW, CB.ACT_MID, CB.ACT_HIGH}))
async def on_activity(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(activity=cb.data)
    await safe_answer(cb)
    data = await state.get_data()
    if data.get("gender") == "female":
        await state.set_state(Onboarding.cycle)
        await cb.message.answer(ASK_CYCLE, parse_mode="HTML", reply_markup=cycle_kb())
        return
    await state.set_state(Onboarding.muscles)
    await cb.message.answer(
        ask_muscles(),
        parse_mode="HTML",
        reply_markup=muscle_kb(data.get("muscles") or {}),
    )


@router.callback_query(
    StateFilter(Onboarding.cycle),
    F.data.in_(
        {
            CB.CYCLE_MENSTRUATION,
            CB.CYCLE_FOLLICULAR,
            CB.CYCLE_OVULATION,
            CB.CYCLE_LUTEAL,
            CB.CYCLE_UNKNOWN,
        }
    ),
)
async def on_cycle(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(cycle_phase=cb.data)
    await state.set_state(Onboarding.muscles)
    await safe_answer(cb)
    data = await state.get_data()
    await cb.message.answer(
        ask_muscles(),
        parse_mode="HTML",
        reply_markup=muscle_kb(data.get("muscles") or {}),
    )


# ─── Мышцы ────────────────────────────────────


@router.callback_query(StateFilter(Onboarding.muscles), F.data.startswith("mg_info_"))
async def on_muscle_info(cb: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(cb, MUSCLE_HINT, alert=True)


@router.callback_query(
    StateFilter(Onboarding.muscles),
    F.data.startswith("mg_"),
    ~F.data.startswith("mg_info_"),
)
async def on_muscle_toggle(cb: CallbackQuery, state: FSMContext) -> None:
    m = re.match(r"^mg_([a-z]+)_(\d+)$", cb.data or "")
    if not m:
        await safe_answer(cb)
        return
    key, val = m.group(1), int(m.group(2))
    data = await state.get_data()
    muscles = dict(data.get("muscles") or {})
    if val == 0:
        muscles.pop(key, None)
    else:
        muscles[key] = val
    await state.update_data(muscles=muscles)
    await safe_answer(cb)
    await _refresh_muscle_board(cb, state)


# ─── Генерация видео ──────────────────────────


async def _send_generated_videos(
    message: Message,
    video_current: bytes,
    video_after: bytes,
) -> None:
    """Отправка двух MP4 в Telegram; увеличенный timeout и fallback по одному файлу."""
    cap_now = "◀ Сейчас · поворот анфас → спина"
    cap_after = "После ▶ · поворот анфас → спина, зоны из анкеты"
    timeout = TELEGRAM_REQUEST_TIMEOUT_SEC
    media = [
        InputMediaVideo(
            media=BufferedInputFile(video_current, "seychas.mp4"),
            caption=cap_now,
        ),
        InputMediaVideo(
            media=BufferedInputFile(video_after, "posle.mp4"),
            caption=cap_after,
        ),
    ]
    logger.info(
        "telegram upload: 2 videos bytes=%s+%s timeout=%ss",
        len(video_current),
        len(video_after),
        timeout,
    )
    for attempt in range(3):
        try:
            await message.answer_media_group(media, request_timeout=timeout)
            return
        except TelegramNetworkError as e:
            logger.warning("answer_media_group attempt %s/3: %s", attempt + 1, e)
            if attempt < 2:
                await asyncio.sleep(2.0 * (attempt + 1))
    logger.warning("media_group failed — sending videos separately")
    await message.answer_video(
        BufferedInputFile(video_current, "seychas.mp4"),
        caption=cap_now,
        request_timeout=timeout,
    )
    await message.answer_video(
        BufferedInputFile(video_after, "posle.mp4"),
        caption=cap_after,
        request_timeout=timeout,
    )


async def _run_video_generation(cb: CallbackQuery, state: FSMContext) -> None:
    user_id = cb.from_user.id
    if is_busy(user_id):
        await safe_answer(cb, "Уже идёт задача. Подождите.", alert=True)
        return

    data = await state.get_data()
    photos = data.get("photos") or []
    if len(photos) < 3:
        await safe_answer(cb, "Нужны 3 фото. Начните с /start.", alert=True)
        return

    await safe_answer(cb)
    _active_tasks[user_id] = "video"

    if not (FAL_KEY or "").strip():
        await cb.message.answer(
            "⚠️ Генерация видео сейчас недоступна. Попробуйте позже.\n\n"
            "Программу тренировок и питание можно запросить ниже:",
            reply_markup=video_fallback_kb(),
        )
        _active_tasks.pop(user_id, None)
        await state.set_state(PostGen.menu)
        return

    summary = profile_summary(data)
    status = await cb.message.answer(summary + "\n\n" + progress_msg(0), parse_mode="HTML")
    start = time.monotonic()

    async def progress():
        while True:
            await asyncio.sleep(10)
            try:
                elapsed = int(time.monotonic() - start)
                await status.edit_text(summary + "\n\n" + progress_msg(elapsed), parse_mode="HTML")
            except Exception:
                pass

    prog = asyncio.create_task(progress())
    video_current = video_after = None
    reason_current = reason_after = "unknown"
    photos_after: list[bytes] | None = None
    generation_ok = False
    try:
        photos_ordered = await order_photos_front_side_back(list(photos))
        photos_before = [fit_image_for_hailuo(bytes(p)) for p in photos_ordered]
        await state.update_data(photos_ordered=photos_before)

        views = pipeline_after_views()
        before_start, before_end = _hailuo_turn_frames(photos_before)
        logger.info(
            "video pipeline: after-edit views=%s; Kling start=front end=%s",
            ",".join(views),
            "back" if before_end else "none",
        )
        video_current, reason_current = await retry_veo(
            safe_generate_hailuo_video,
            hailuo_before_turn_prompt(dual_frame=before_end is not None),
            before_start,
            before_end,
        )
        photos_after = await _prepare_photos_after(photos_before, data)
        _log_before_after_sets(photos_before, photos_after)
        after_start, after_end = _hailuo_turn_frames(photos_after)
        video_after, reason_after = await retry_veo(
            safe_generate_hailuo_video,
            hailuo_after_turn_prompt(data, dual_frame=after_end is not None),
            after_start,
            after_end,
        )
        generation_ok = bool(video_current and video_after)
    except Exception as e:
        logger.error("Video generation: %s", e, exc_info=True)
        video_current = video_after = None
        reason_current = reason_after = "unknown"
        generation_ok = False
    finally:
        prog.cancel()
        _active_tasks.pop(user_id, None)
        try:
            await status.delete()
        except Exception:
            pass

    if not generation_ok:
        if reason_current == "safety" or reason_after == "safety":
            fail_text = (
                "⚠️ Генерация видео отклонена фильтрами безопасности контента.\n"
                "Попробуйте более нейтральное фото (без откровенного контента) "
                "или начните заново через /start.\n"
                "Программу тренировок и питание можно запросить ниже:"
            )
        elif reason_current == "aspect_ratio" or reason_after == "aspect_ratio":
            fail_text = (
                "⚠️ Не удалось собрать видео: кадр слишком узкий или обрезанный.\n"
                "Пришлите 3 фото <b>в полный рост</b> в портретном режиме (9:16), "
                "без сильного кропа по бокам, и начните заново через /start.\n"
                "Программу тренировок и питание можно запросить ниже:"
            )
        else:
            fail_text = (
                "⚠️ Не удалось получить видео. Попробуйте позже или /start.\n"
                "Программу тренировок и питание всё равно можно запросить ниже:"
            )
        await cb.message.answer(
            fail_text,
            reply_markup=video_fallback_kb(),
        )
        await state.set_state(PostGen.menu)
        return

    try:
        await _send_generated_videos(cb.message, video_current, video_after)
        await cb.message.answer(
            VIDEOS_READY,
            parse_mode="HTML",
            reply_markup=post_gen_kb(),
            request_timeout=TELEGRAM_REQUEST_TIMEOUT_SEC,
        )
    except TelegramNetworkError as e:
        logger.error("telegram video upload failed: %s", e, exc_info=True)
        await cb.message.answer(
            "⚠️ Видео сгенерированы, но не удалось отправить их в Telegram (таймаут сети). "
            "Попробуйте «Снова сгенерировать видео» или /start позже.",
            reply_markup=video_fallback_kb(),
        )
        await state.set_state(PostGen.menu)
        return
    await state.set_state(PostGen.menu)


@router.callback_query(StateFilter(Onboarding.muscles), F.data == CB.CONFIRM)
async def confirm_from_muscles(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Onboarding.generating)
    await _run_video_generation(cb, state)


@router.callback_query(StateFilter(PostGen.menu), F.data == CB.CONFIRM)
async def retry_video(cb: CallbackQuery, state: FSMContext) -> None:
    await _run_video_generation(cb, state)


# ─── Тренировка на сегодня ───────────────────────────────────────────

_WEEKDAY_RU = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


async def _send_workout_chunks(message: Message, text: str, *, header_html: str = "") -> None:
    if header_html:
        await message.answer(header_html, parse_mode="HTML")
    body = remove_all_html(text)
    for i in range(0, len(body), 4000):
        await message.answer(body[i : i + 4000])


async def _deliver_workout_today(
    message: Message,
    state: FSMContext,
    user_id: int,
    *,
    force_refresh: bool = False,
) -> None:
    today = date.today()
    day_key = today.isoformat()
    weekday_ru = _WEEKDAY_RU[today.weekday()]
    day_label = today.strftime("%d.%m.%Y")

    if not force_refresh:
        cached = await get_workout_day_body(user_id, day_key)
        if cached:
            await _send_workout_chunks(
                message,
                cached,
                header_html=workout_today_header_html(
                    weekday_ru, day_label, from_cache=True
                ),
            )
            await message.answer(
                POST_GEN_MENU,
                parse_mode="HTML",
                reply_markup=workout_today_kb(show_refresh=True),
            )
            return

    data = dict(await state.get_data())
    meas = await get_latest_body_measurement(user_id)
    if meas:
        data["body_measurements"] = meas

    loading = await message.answer(
        workout_generating_html(weekday_ru),
        parse_mode="HTML",
    )
    prompt = workout_prompt_today(data, today.weekday())
    result: str | None = None
    try:
        await task_manager.run(user_id, "workout")
        result = await generate_workout(prompt, max_tokens=1600)
    finally:
        task_manager.release(user_id)
    try:
        await loading.delete()
    except Exception:
        pass

    if not result:
        await message.answer(WORKOUT_FAIL, reply_markup=workout_today_kb())
        return

    text = remove_all_html(result)
    await save_workout_day_body(user_id, day_key, text)
    await _send_workout_chunks(
        message,
        text,
        header_html=workout_today_header_html(weekday_ru, day_label, from_cache=False),
    )
    await message.answer(
        POST_GEN_MENU,
        parse_mode="HTML",
        reply_markup=workout_today_kb(show_refresh=True),
    )


@router.callback_query(F.data == CB.WORKOUT)
async def cb_workout_today(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    if not cb.from_user:
        await safe_answer(cb)
        return
    await safe_answer(cb)
    await _deliver_workout_today(cb.message, state, cb.from_user.id, force_refresh=False)


@router.callback_query(F.data == CB.WORKOUT_REFRESH)
async def cb_workout_refresh(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    if not cb.from_user:
        await safe_answer(cb)
        return
    await safe_answer(cb)
    await delete_workout_day(cb.from_user.id, date.today().isoformat())
    await _deliver_workout_today(cb.message, state, cb.from_user.id, force_refresh=True)


# ─── Питание + вода ───────────────────────────


@router.callback_query(F.data == CB.NUTRITION)
async def get_nutrition(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    user_id = cb.from_user.id
    await safe_answer(cb)
    _active_tasks[user_id] = "nutrition"
    data = await state.get_data()
    loading = await cb.message.answer("🥗 Готовлю основы питания…")
    try:
        result = await ask_dashscope_text(nutrition_prompt(data), max_tokens=600)
    finally:
        _active_tasks.pop(user_id, None)
    try:
        await loading.delete()
    except Exception:
        pass
    if not result:
        await cb.message.answer("❌ Не удалось получить ответ.")
        return
    clean = remove_all_html(result)
    for i in range(0, len(clean), 4000):
        await cb.message.answer(clean[i : i + 4000])
    await state.update_data(water_ml_today=int(data.get("water_ml_today") or 0))
    await cb.message.answer(
        water_hint_text(await state.get_data()),
        parse_mode="HTML",
        reply_markup=water_footer_kb(),
    )


@router.callback_query(F.data == CB.WATER_ADD)
async def water_add(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    data = await state.get_data()
    n = int(data.get("water_ml_today") or 0) + 250
    await state.update_data(water_ml_today=n)
    await safe_answer(cb, "+250 мл")
    try:
        await cb.message.edit_text(
            water_hint_text(await state.get_data()),
            parse_mode="HTML",
            reply_markup=water_footer_kb(),
        )
    except Exception:
        pass


@router.callback_query(F.data == CB.WATER_RESET)
async def water_reset(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await state.update_data(water_ml_today=0)
    await safe_answer(cb, "Сброшено")
    try:
        await cb.message.edit_text(
            water_hint_text(await state.get_data()),
            parse_mode="HTML",
            reply_markup=water_footer_kb(),
        )
    except Exception:
        pass


# ─── Замеры тела ──────────────────────────────


async def _save_measurement_step(
    message: Message,
    state: FSMContext,
    *,
    field: str,
    next_state,
    next_prompt: str,
) -> None:
    v = _parse_int(message.text)
    if v is None:
        await message.answer(ERROR_NOT_NUMBER)
        return
    if not (20 <= v <= 250):
        await message.answer(ERROR_RANGE)
        return
    await state.update_data(measurements={**((await state.get_data()).get("measurements") or {}), field: v})
    await state.set_state(next_state)
    await message.answer(next_prompt, parse_mode="HTML")


@router.callback_query(F.data == CB.MEASUREMENTS)
async def start_measurements(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await safe_answer(cb)
    await state.update_data(measurements={})
    await state.set_state(Measurements.waist)
    guide_path = Path(__file__).resolve().parent.parent / "assets" / "img" / "Измерение тела.jpg"
    try:
        await cb.message.answer_photo(
            FSInputFile(str(guide_path)),
            caption=(
                "📸 <b>Как правильно измерять</b>\n\n"
                "Используйте сантиметровую ленту, держите ее параллельно полу и не перетягивайте."
            ),
            parse_mode="HTML",
        )
    except Exception:
        logger.warning("measurements guide image not sent: %s", guide_path)
    await cb.message.answer(MEASUREMENTS_START + "\n\n" + ASK_MEAS_WAIST, parse_mode="HTML")


@router.callback_query(F.data == CB.MEASUREMENTS_VIEW)
async def view_measurements(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await safe_answer(cb)
    rec = await get_latest_body_measurement(cb.from_user.id)
    if not rec:
        await cb.message.answer(
            "📊 Замеров пока нет.\n\nНажмите «📏 Ввести замеры тела», чтобы добавить первый набор.",
            parse_mode="HTML",
            reply_markup=post_gen_kb(),
        )
        return
    created = datetime.fromtimestamp(rec["created_at"]).strftime("%d.%m.%Y %H:%M")
    text = _measurements_text(
        {
            "waist": rec["waist"],
            "hips": rec["hips"],
            "chest": rec["chest"],
            "shoulders": rec["shoulders"],
            "thigh": rec["thigh"],
            "calf": rec["calf"],
            "biceps": rec["biceps"],
        }
    )
    text += f"\n\n🕒 Обновлено: {created}"
    if rec["runninghub_status"] == "ok":
        text += "\n✅ Фото с подписями замеров было сгенерировано (см. сообщения выше при сохранении)."
    else:
        text += "\n⚠️ Подписи на фото пока не готовы — можно отправить фото замеров ещё раз."
    await cb.message.answer(text, parse_mode="HTML", reply_markup=post_gen_kb())


@router.message(StateFilter(Measurements.waist), F.text)
async def meas_waist(message: Message, state: FSMContext) -> None:
    await _save_measurement_step(
        message,
        state,
        field="waist",
        next_state=Measurements.hips,
        next_prompt=ASK_MEAS_HIPS,
    )


@router.message(StateFilter(Measurements.hips), F.text)
async def meas_hips(message: Message, state: FSMContext) -> None:
    await _save_measurement_step(
        message,
        state,
        field="hips",
        next_state=Measurements.chest,
        next_prompt=ASK_MEAS_CHEST,
    )


@router.message(StateFilter(Measurements.chest), F.text)
async def meas_chest(message: Message, state: FSMContext) -> None:
    await _save_measurement_step(
        message,
        state,
        field="chest",
        next_state=Measurements.shoulders,
        next_prompt=ASK_MEAS_SHOULDERS,
    )


@router.message(StateFilter(Measurements.shoulders), F.text)
async def meas_shoulders(message: Message, state: FSMContext) -> None:
    await _save_measurement_step(
        message,
        state,
        field="shoulders",
        next_state=Measurements.thigh,
        next_prompt=ASK_MEAS_THIGH,
    )


@router.message(StateFilter(Measurements.thigh), F.text)
async def meas_thigh(message: Message, state: FSMContext) -> None:
    await _save_measurement_step(
        message,
        state,
        field="thigh",
        next_state=Measurements.calf,
        next_prompt=ASK_MEAS_CALF,
    )


@router.message(StateFilter(Measurements.calf), F.text)
async def meas_calf(message: Message, state: FSMContext) -> None:
    await _save_measurement_step(
        message,
        state,
        field="calf",
        next_state=Measurements.biceps,
        next_prompt=ASK_MEAS_BICEPS,
    )


@router.message(StateFilter(Measurements.biceps), F.text)
async def meas_biceps(message: Message, state: FSMContext) -> None:
    v = _parse_int(message.text)
    if v is None:
        await message.answer(ERROR_NOT_NUMBER)
        return
    if not (20 <= v <= 250):
        await message.answer(ERROR_RANGE)
        return
    data = await state.get_data()
    measurements = dict(data.get("measurements") or {})
    measurements["biceps"] = v
    await state.update_data(measurements=measurements)
    await state.set_state(Measurements.photo)
    await message.answer(ASK_MEAS_FRONT_PHOTO, parse_mode="HTML")


@router.message(StateFilter(Measurements.photo), F.photo)
async def meas_photo(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if is_busy(user_id):
        await message.answer("Сейчас идёт другая генерация. Подождите.")
        return
    data = await state.get_data()
    measurements = dict(data.get("measurements") or {})
    if any(key not in measurements for key, _label, _ in MEASUREMENT_FIELDS):
        await state.set_state(Measurements.waist)
        await message.answer("Давайте заполним замеры заново.\n\n" + ASK_MEAS_WAIST, parse_mode="HTML")
        return

    try:
        buf = await message.bot.download(message.photo[-1])
        try:
            photo_bytes = buf.read()
        finally:
            if hasattr(buf, "close"):
                buf.close()
    except Exception as e:
        logger.warning("measurements photo download: %s", e)
        await message.answer(ERROR_MEAS_PHOTO)
        return

    _active_tasks[user_id] = "measurements"
    loading = await message.answer("⏳ Рисую подписи с замерами на фото…")
    task_id = ""
    output_url = ""
    reason = ""
    status = "error"
    try:
        if not (DASHSCOPE_API_KEY or "").strip():
            reason = "Генерация изображения временно недоступна."
        else:
            prompt = body_measurements_overlay_prompt(measurements)
            overlay = await edit_measurements_overlay_qwen(photo_bytes, prompt)
            if overlay:
                await message.answer_photo(
                    BufferedInputFile(overlay, filename="zamery.png"),
                    caption="📏 Фото с подписями замеров (см).",
                )
                status = "ok"
                task_id = "dashscope-qwen-overlay"
            else:
                reason = (
                    "Не удалось получить изображение. Попробуйте другое фото (полный рост, ровный свет) или позже."
                )
    except Exception as e:
        logger.exception("measurements overlay: %s", e)
        reason = str(e) or "ошибка генерации"
    finally:
        _active_tasks.pop(user_id, None)
        try:
            await loading.delete()
        except Exception:
            pass

    await save_body_measurement(
        user_id,
        measurements,
        front_photo_file_id=message.photo[-1].file_id or "",
        runninghub_task_id=task_id,
        runninghub_result_url=output_url,
        runninghub_status=status,
        runninghub_reason=reason,
    )

    text = _measurements_text(measurements) + "\n\n✅ Замеры сохранены."
    if status == "ok":
        text += "\nФото с подписями отправлено выше."
    else:
        text += "\n⚠️ Подписи на фото сгенерировать не удалось; замеры в базе сохранены."
        if reason:
            if "sensitive" in reason.lower() or "e005" in reason.lower():
                text += "\nПричина: запрос отклонён по правилам контента. Попробуйте другое фото (более нейтральное) или повторите позже."
            else:
                text += _user_error_appendix(reason)
    await state.set_state(PostGen.menu)
    await message.answer(text, parse_mode="HTML", reply_markup=post_gen_kb())


@router.message(StateFilter(Measurements.photo))
async def meas_photo_bad(message: Message, state: FSMContext) -> None:
    await message.answer(ERROR_MEAS_PHOTO)


# ─── Редактирование / рестарт ─────────────────


@router.callback_query(F.data == CB.EDIT)
async def edit_menu(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await safe_answer(cb)
    await state.set_state(PostGen.edit_params)
    await cb.message.answer(
        "✏️ <b>Что изменить?</b>\n\nАнкета — пол, возраст, рост, вес, активность.\n"
        "Зоны — только проценты по группам мышц.",
        parse_mode="HTML",
        reply_markup=edit_menu_kb(),
    )


@router.callback_query(F.data == CB.EDIT_BACK)
async def edit_back(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await safe_answer(cb)
    await state.set_state(PostGen.menu)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(POST_GEN_MENU, parse_mode="HTML", reply_markup=post_gen_kb())


@router.callback_query(F.data == CB.EDIT_PROFILE)
async def edit_profile(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await safe_answer(cb)
    await state.set_state(Onboarding.gender)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer("Обновим анкету.\n\n" + ASK_GENDER, parse_mode="HTML", reply_markup=gender_kb())


@router.callback_query(F.data == CB.EDIT_MUSCLES)
async def edit_muscles(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await safe_answer(cb)
    await state.set_state(Onboarding.muscles)
    data = await state.get_data()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(
        ask_muscles(),
        parse_mode="HTML",
        reply_markup=muscle_kb(data.get("muscles") or {}),
    )


@router.callback_query(F.data == CB.RESTART)
async def restart(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    await safe_answer(cb)
    await state.clear()
    await init_ui(state)
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer(WELCOME, parse_mode="HTML", reply_markup=welcome_kb())


def setup_handlers(dp: Dispatcher) -> None:
    dp.include_router(router)
