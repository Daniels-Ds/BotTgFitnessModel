"""
Хендлеры бота: онбординг, два видео Wan 2.2 i2v (DashScope); кадр «после» — Qwen Image Edit.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
import logging
import re
import time
from pathlib import Path
from aiogram import Dispatcher, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile, InputMediaPhoto, InputMediaVideo, Message

from core.callbacks import CB
from core.tasks import task_manager
from db import (
    clear_workout_plan,
    get_latest_body_measurement,
    get_workout_ready_weeks,
    get_workout_week_body,
    save_body_measurement,
    save_workout_week_body,
)
from keyboards import (
    activity_kb,
    edit_menu_kb,
    gender_kb,
    muscle_kb,
    post_gen_kb,
    video_fallback_kb,
    water_footer_kb,
    welcome_kb,
    workout_plan_kb,
)
from messages import (
    ASK_ACTIVITY,
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
    PHOTO_PREVIEW_READY,
    POST_GEN_MENU,
    VIDEOS_READY,
    WELCOME,
    MEASUREMENTS_START,
    WORKOUT_PLAN_CLEARED,
    WORKOUT_PLAN_EMPTY,
    WORKOUT_TODAY_REST,
    WORKOUT_WEEK_FAIL,
    WORKOUT_WEEK_LOCKED,
    ask_muscles,
    profile_summary,
    progress_msg,
    progress_msg_photo_preview,
    workout_generating_week_html,
    workout_plan_hub_html,
    workout_today_train_html,
)
from prompts import (
    body_measurements_overlay_prompt,
    nutrition_prompt,
    openrouter_after_body_image_prompt,
    veo_after_prompt,
    veo_current_prompt,
    water_hint_text,
    workout_prompt_week,
)
from services.dashscope_qwen_image_edit_client import (
    edit_after_body_image_qwen,
    edit_measurements_overlay_qwen,
)
from services.dashscope_wan_i2v_client import generate_wan_i2v_video
from services.dashscope_text_client import ask_dashscope_text
from services.gemini_service import generate_workout
from config import DASHSCOPE_API_KEY, USE_WAN_FOR_VIDEO
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
    cleaned = text or ""
    for token in (
        "RunningHub",
        "runninghub",
        "OpenRouter",
        "openrouter",
        "DashScope",
        "dashscope",
        "Model Studio",
        "Alibaba",
        "Gemini",
        "VEO",
        "WAN",
    ):
        cleaned = cleaned.replace(token, "сервис")
    return cleaned


async def safe_generate_video(prompt: str, photo: bytes):
    async with veo_lock:
        return await generate_wan_i2v_video(prompt, photo)


async def safe_generate_video_after(prompt: str, photo: bytes):
    async with veo_lock:
        return await generate_wan_i2v_video(prompt, photo)


async def _prepare_photo_after(photo: bytes, data: dict) -> bytes:
    """Qwen Image Edit (референс + текст); при ошибке — исходный референс."""
    logger.info("after-body: Qwen edit start input_bytes=%s", len(photo))
    prompt = openrouter_after_body_image_prompt(data)
    q_img = await edit_after_body_image_qwen(photo, prompt)
    if q_img:
        if q_img == photo:
            logger.warning(
                "after-body: Qwen returned same bytes as input — API accepted request but likely skipped real edit"
            )
        return q_img
    logger.warning(
        "after-body: Qwen returned None (see Qwen image edit logs above) — using original photo for second slot"
    )
    return photo


async def retry_veo(fn, *args, retries: int = 3):
    for i in range(retries):
        try:
            return await fn(*args)
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
    await state.update_data(photos=[], muscles={}, water_ml_today=0)
    await safe_answer(cb)
    try:
        await cb.message.edit_text(ASK_PHOTOS, parse_mode="HTML")
    except Exception:
        await cb.message.answer(ASK_PHOTOS, parse_mode="HTML")


# ─── Фото ─────────────────────────────────────


@router.message(StateFilter(Onboarding.photos), F.photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list[bytes] = list(data.get("photos") or [])
    if len(photos) >= 3:
        await message.answer("Уже есть 3 фото. Используйте «Изменить параметры» или /start.")
        return

    try:
        buf = await message.bot.download(message.photo[-1])
        try:
            chunk = buf.read()
        finally:
            if hasattr(buf, "close"):
                buf.close()
    except Exception as e:
        logger.warning("photo download: %s", e)
        await message.answer(ERROR_NOT_PHOTO)
        return

    photos.append(chunk)
    await state.update_data(photos=photos)
    n = len(photos)
    if n == 1:
        await message.answer(PHOTO_1_OK, parse_mode="HTML")
    elif n == 2:
        await message.answer(PHOTO_2_OK, parse_mode="HTML")
    else:
        await state.set_state(Onboarding.gender)
        await message.answer(PHOTO_3_OK, parse_mode="HTML")
        await message.answer(ASK_GENDER, parse_mode="HTML", reply_markup=gender_kb())


@router.message(StateFilter(Onboarding.photos))
async def on_photo_bad(message: Message, state: FSMContext) -> None:
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

    photo = photos[0]
    summary = profile_summary(data)
    progress_fn = progress_msg if USE_WAN_FOR_VIDEO else progress_msg_photo_preview
    status = await cb.message.answer(summary + "\n\n" + progress_fn(0), parse_mode="HTML")
    start = time.monotonic()

    async def progress():
        while True:
            await asyncio.sleep(10)
            try:
                elapsed = int(time.monotonic() - start)
                await status.edit_text(summary + "\n\n" + progress_fn(elapsed), parse_mode="HTML")
            except Exception:
                pass

    prog = asyncio.create_task(progress())
    video_current = video_after = None
    reason_current = reason_after = "unknown"
    photo_after: bytes | None = None
    generation_ok = False
    try:
        if USE_WAN_FOR_VIDEO:
            video_current, reason_current = await retry_veo(safe_generate_video, veo_current_prompt(data), photo)
            photo_after = await _prepare_photo_after(photo, data)
            video_after, reason_after = await retry_veo(
                safe_generate_video_after, veo_after_prompt(data), photo_after
            )
            generation_ok = bool(video_current and video_after)
        else:
            photo_after = await _prepare_photo_after(photo, data)
            generation_ok = True
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
        if USE_WAN_FOR_VIDEO:
            if reason_current == "safety" or reason_after == "safety":
                fail_text = (
                    "⚠️ Генерация видео отклонена фильтрами безопасности контента.\n"
                    "Попробуйте более нейтральное фото (без откровенного контента) "
                    "или начните заново через /start.\n"
                    "Программу тренировок и питание можно запросить ниже:"
                )
            else:
                fail_text = (
                    "⚠️ Не удалось получить видео. Попробуйте позже или /start.\n"
                    "Программу тренировок и питание всё равно можно запросить ниже:"
                )
        else:
            fail_text = (
                "⚠️ Не удалось подготовить превью.\n"
                "Попробуйте позже или /start.\n"
                "Программу тренировок и питание можно запросить ниже:"
            )
        await cb.message.answer(
            fail_text,
            reply_markup=video_fallback_kb(),
        )
        await state.set_state(PostGen.menu)
        return

    if USE_WAN_FOR_VIDEO:
        media = [
            InputMediaVideo(
                media=BufferedInputFile(video_current, "seychas.mp4"),
                caption="◀ Сейчас (по вашим фото)",
            ),
            InputMediaVideo(
                media=BufferedInputFile(video_after, "posle.mp4"),
                caption="После ▶ (с учётом выбранных зон)",
            ),
        ]
        ready_text = VIDEOS_READY
    else:
        assert photo_after is not None
        media = [
            InputMediaPhoto(
                media=BufferedInputFile(photo, "ref.jpg"),
                caption="◀ Сейчас (референс, фото 1/3)",
            ),
            InputMediaPhoto(
                media=BufferedInputFile(photo_after, "posle.jpg"),
                caption="После ▶ (превью по зонам)",
            ),
        ]
        ready_text = PHOTO_PREVIEW_READY

    await cb.message.answer_media_group(media)
    await cb.message.answer(ready_text, parse_mode="HTML", reply_markup=post_gen_kb())
    await state.set_state(PostGen.menu)


@router.callback_query(StateFilter(Onboarding.muscles), F.data == CB.CONFIRM)
async def confirm_from_muscles(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Onboarding.generating)
    await _run_video_generation(cb, state)


@router.callback_query(StateFilter(PostGen.menu), F.data == CB.CONFIRM)
async def retry_video(cb: CallbackQuery, state: FSMContext) -> None:
    await _run_video_generation(cb, state)


# ─── Тренировки (календарь по неделям) ───────────────────────────────


async def _send_workout_chunks(message: Message, text: str, *, header: str = "") -> None:
    body = remove_all_html(text)
    if header:
        body = header.rstrip() + "\n\n" + body
    for i in range(0, len(body), 4000):
        await message.answer(body[i : i + 4000])


@router.callback_query(F.data == CB.WORKOUT)
async def cb_workout_open_hub(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    uid = cb.from_user.id if cb.from_user else 0
    ready = await get_workout_ready_weeks(uid)
    await cb.message.answer(
        workout_plan_hub_html(ready),
        parse_mode="HTML",
        reply_markup=workout_plan_kb(ready),
    )


@router.callback_query(F.data.in_({CB.PLAN_W1, CB.PLAN_W2, CB.PLAN_W3, CB.PLAN_W4}))
async def cb_workout_week(cb: CallbackQuery, state: FSMContext) -> None:
    if await reject_if_busy(cb):
        return
    if not cb.data or not cb.from_user:
        await safe_answer(cb)
        return
    week_map = {CB.PLAN_W1: 1, CB.PLAN_W2: 2, CB.PLAN_W3: 3, CB.PLAN_W4: 4}
    week = week_map[cb.data]
    uid = cb.from_user.id
    ready = await get_workout_ready_weeks(uid)
    if week > 1 and (week - 1) not in ready:
        await cb.answer(WORKOUT_WEEK_LOCKED, show_alert=True)
        return
    await cb.answer()
    cached = await get_workout_week_body(uid, week)
    if cached:
        await _send_workout_chunks(
            cb.message,
            cached,
            header=f"Неделя {week} · из памяти бота",
        )
        return
    data = await state.get_data()
    loading = await cb.message.answer(
        workout_generating_week_html(week),
        parse_mode="HTML",
    )
    prev = await get_workout_week_body(uid, week - 1) if week > 1 else None
    excerpt = (prev[-3200:] if prev else None)
    prompt = workout_prompt_week(data, week, excerpt)
    result: str | None = None
    try:
        await task_manager.run(uid, "workout")
        result = await generate_workout(prompt, max_tokens=2200)
    finally:
        task_manager.release(uid)
    try:
        await loading.delete()
    except Exception:
        pass
    if not result:
        await cb.message.answer(WORKOUT_WEEK_FAIL)
        return
    text = remove_all_html(result)
    await save_workout_week_body(uid, week, text)
    await _send_workout_chunks(cb.message, text, header=f"Неделя {week}")
    ready2 = await get_workout_ready_weeks(uid)
    try:
        await cb.message.edit_reply_markup(reply_markup=workout_plan_kb(ready2))
    except Exception:
        pass


@router.callback_query(F.data == CB.PLAN_TODAY)
async def cb_workout_today(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    uid = cb.from_user.id if cb.from_user else 0
    wd = date.today().weekday()
    names = (
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    )
    ready = await get_workout_ready_weeks(uid)
    kb = workout_plan_kb(ready)
    if wd not in (0, 2, 4):
        await cb.message.answer(WORKOUT_TODAY_REST, parse_mode="HTML", reply_markup=kb)
    else:
        await cb.message.answer(
            workout_today_train_html(names[wd]),
            parse_mode="HTML",
            reply_markup=kb,
        )


@router.callback_query(F.data == CB.PLAN_RESET)
async def cb_workout_plan_reset(cb: CallbackQuery, state: FSMContext) -> None:
    if not cb.from_user:
        await safe_answer(cb)
        return
    uid = cb.from_user.id
    ready = await get_workout_ready_weeks(uid)
    if not ready:
        await cb.answer(WORKOUT_PLAN_EMPTY, show_alert=True)
        return
    await clear_workout_plan(uid)
    await cb.answer(WORKOUT_PLAN_CLEARED, show_alert=True)
    ready2 = await get_workout_ready_weeks(uid)
    try:
        await cb.message.edit_text(
            workout_plan_hub_html(ready2),
            parse_mode="HTML",
            reply_markup=workout_plan_kb(ready2),
        )
    except Exception:
        pass


@router.callback_query(F.data == CB.PLAN_HUB_BACK)
async def cb_workout_hub_back(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    try:
        await cb.message.edit_text(
            POST_GEN_MENU,
            parse_mode="HTML",
            reply_markup=post_gen_kb(),
        )
    except Exception:
        await cb.message.answer(POST_GEN_MENU, parse_mode="HTML", reply_markup=post_gen_kb())


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
        text += "\n✅ Обработано"
        if rec["runninghub_result_url"]:
            text += f"\nРезультат: {rec['runninghub_result_url']}"
        else:
            text += "\nФото с подписями замеров отправлялось в чат при сохранении."
    else:
        text += "\n⚠️ Результат пока недоступен"
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
            reason = "Не задан ключ API для генерации изображения (DASHSCOPE_API_KEY / ALIBABA_MODEL_STUDIO_API_KEY)."
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
                text += "\nПричина: запрос отклонён по контент-политике. Попробуйте другое фото (более нейтральное) или повторите позже."
            else:
                text += f"\nПричина: {_hide_service_names(reason)}"
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
