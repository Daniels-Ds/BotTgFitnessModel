from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core.callbacks import CB


def kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn(text: str, cb: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb)


def welcome_kb() -> InlineKeyboardMarkup:
    return kb([[btn("✨ Давайте начнём", CB.START_FLOW)]])


def gender_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("Мужчина", CB.GENDER_MALE), btn("Женщина", CB.GENDER_FEMALE)],
        ]
    )


def activity_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("Малоподвижный", CB.ACT_LOW)],
            [btn("Средняя активность", CB.ACT_MID)],
            [btn("Регулярные тренировки", CB.ACT_HIGH)],
        ]
    )


# (key, short label for row, emoji)
MUSCLE_GROUPS: list[tuple[str, str, str]] = [
    ("shoulders", "Плечи", "💪"),
    ("chest", "Грудь", "🏋"),
    ("thighs", "Бёдра", "🦵"),
    ("calves", "Икры", "🦶"),
    ("glutes", "Ягодицы", "🍑"),
    ("biceps", "Бицепсы", "💪"),
    ("abs", "Пресс", "🔥"),
]

PERCENTS = (10, 20, 30)


def muscle_kb(selected: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, short, em in MUSCLE_GROUPS:
        cur = int(selected.get(key, 0) or 0)
        label = f"{em} {short}"
        row = [
            btn(label, f"mg_info_{key}"),
        ]
        for p in PERCENTS:
            mark = "✓ " if cur == p else ""
            row.append(btn(f"{mark}{p}%", f"mg_{key}_{p}"))
        if cur:
            row.append(btn("✕", f"mg_{key}_0"))
        rows.append(row)
    rows.append([btn("✨ Получить лучшегоЯ", CB.CONFIRM)])
    return kb(rows)


def _workout_week_btn_label(week_no: int, ready: set[int]) -> str:
    can_open = week_no == 1 or (week_no - 1) in ready
    if week_no in ready:
        return f"✅ Неделя {week_no}"
    if not can_open:
        return f"🔒 Неделя {week_no}"
    return f"📌 Неделя {week_no}"


def workout_plan_kb(ready: set[int]) -> InlineKeyboardMarkup:
    """Календарь: 4 недели по порядку, «Сегодня», сброс, назад в пост-меню."""
    r = ready
    return kb(
        [
            [
                btn(_workout_week_btn_label(1, r), CB.PLAN_W1),
                btn(_workout_week_btn_label(2, r), CB.PLAN_W2),
            ],
            [
                btn(_workout_week_btn_label(3, r), CB.PLAN_W3),
                btn(_workout_week_btn_label(4, r), CB.PLAN_W4),
            ],
            [btn("📆 Что по плану сегодня", CB.PLAN_TODAY)],
            [btn("🗑 Сбросить сохранённые недели", CB.PLAN_RESET)],
            [btn("◀️ В меню после видео", CB.PLAN_HUB_BACK)],
        ]
    )


def post_gen_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🎬 Снова сгенерировать видео", CB.CONFIRM)],
            [btn("📏 Ввести замеры тела", CB.MEASUREMENTS)],
            [btn("📊 Посмотреть замеры", CB.MEASUREMENTS_VIEW)],
            [btn("✏️ Изменить параметры", CB.EDIT)],
            [btn("🏋️ План тренировок", CB.WORKOUT)],
            [btn("🥗 Основы питания", CB.NUTRITION)],
            [btn("🔄 С начала", CB.RESTART)],
        ]
    )


def edit_menu_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("📝 Анкета (пол, возраст, рост…)", CB.EDIT_PROFILE)],
            [btn("🎯 Зоны и проценты", CB.EDIT_MUSCLES)],
            [btn("◀️ Назад в меню", CB.EDIT_BACK)],
        ]
    )


def cancel_kb() -> InlineKeyboardMarkup:
    return kb([[btn("🔄 С начала", CB.RESTART)]])


def retry_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🔁 Повторить видео", CB.CONFIRM)],
            [btn("🔄 С начала", CB.RESTART)],
        ]
    )


def video_fallback_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🔁 Повторить видео", CB.CONFIRM)],
            [btn("🏋️ План тренировок", CB.WORKOUT)],
            [btn("🥗 Основы питания", CB.NUTRITION)],
            [btn("🔄 С начала", CB.RESTART)],
        ]
    )


def water_footer_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [
                btn("+250 мл", CB.WATER_ADD),
                btn("🔄 Сброс дня", CB.WATER_RESET),
            ],
        ]
    )
