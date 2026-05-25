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


def cycle_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🩸 Менструация", CB.CYCLE_MENSTRUATION)],
            [btn("🌱 После месячных (фолликулярная)", CB.CYCLE_FOLLICULAR)],
            [btn("✨ Овуляция / середина цикла", CB.CYCLE_OVULATION)],
            [btn("🌙 Перед месячными (лютеиновая)", CB.CYCLE_LUTEAL)],
            [btn("Не отслеживаю", CB.CYCLE_UNKNOWN)],
        ]
    )


# (key, short label for row, emoji)
MUSCLE_GROUPS: list[tuple[str, str, str]] = [
    ("shoulders", "Плечи", "💪"),
    ("chest", "Грудь", "🏋"),
    ("thighs", "Бёдра", "🦵"),
    ("calves", "Икры", "🦶"),
    ("glutes", "Ягодицы", "🍑"),
    ("biceps", "Бицепсы", "🦾"),
    ("triceps", "Трицепсы", "🔻"),
    ("abs", "Пресс", "🔥"),
]

PERCENTS = (10, 30, 50)


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


def workout_today_kb(*, show_refresh: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [btn("🏋️ Тренировка на сегодня", CB.WORKOUT)],
    ]
    if show_refresh:
        rows.append([btn("🔄 Другая на сегодня", CB.WORKOUT_REFRESH)])
    rows.append([btn("◀️ В меню", CB.EDIT_BACK)])
    return kb(rows)


def post_gen_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🎬 Снова сгенерировать видео", CB.CONFIRM)],
            [btn("📏 Ввести замеры тела", CB.MEASUREMENTS)],
            [btn("📊 Посмотреть замеры", CB.MEASUREMENTS_VIEW)],
            [btn("✏️ Изменить параметры", CB.EDIT)],
            [btn("🏋️ Тренировка на сегодня", CB.WORKOUT)],
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
            [btn("🏋️ Тренировка на сегодня", CB.WORKOUT)],
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
