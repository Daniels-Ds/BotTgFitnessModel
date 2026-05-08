"""
Промпты для VEO и Gemini.
"""

from keyboards import MUSCLE_GROUPS

from config import MUSCLE_PROMPT_MAX_PCT, MUSCLE_PROMPT_SCALE


def _muscle_label_map() -> dict[str, str]:
    return {key: short for key, short, _em in MUSCLE_GROUPS}


def _aspect_vertical_cn() -> str:
    return (
        "画幅必须严格竖屏 9:16（手机竖屏全屏），纵向构图，人物占画面主体高度；"
        "禁止输出横向 16:9 或电影宽屏；画面两侧不要留大黑边。"
    )


def _muscles_effective_pcts(muscles: dict) -> dict[str, int]:
    """Сжимает UI-проценты для текста промптов (модели сильно завышают «+30%»)."""
    out: dict[str, int] = {}
    for key, raw in (muscles or {}).items():
        if not raw:
            continue
        try:
            p = int(raw)
        except (TypeError, ValueError):
            continue
        eff = int(round(p * MUSCLE_PROMPT_SCALE))
        eff = max(10, min(MUSCLE_PROMPT_MAX_PCT, eff))
        out[key] = eff
    return out


# ─────────────────────────────────────────────
#  VEO — видео «сейчас» (референс)
# ─────────────────────────────────────────────


def veo_current_prompt(data: dict) -> str:
    gender = "女性" if data.get("gender") == "female" else "男性"
    age = data.get("age", 25)
    return f"""一位{age}岁的健身{gender}，在纯白摄影棚背景中做缓慢、平滑的原地360度旋转。

{_aspect_vertical_cn()}

人物必须与参考图一致：同一张脸、同一发型、同一肤色及冷暖基调与明暗（禁止美白、美黑、换肤色）、同一体型比例、同一服装风格。

动作要求：双脚基本固定，身体自然放松，8秒内完成一整圈旋转，动作稳定顺滑。

光线要求：柔和均匀的棚拍光，皮肤自然哑光，无油光、无夸张高光。

风格要求：健身App里的“当前状态”展示视频，真实自然；禁止健美比赛或大块头“肌肉雕塑”风格，不要过度阳刚的块头感；不做体型强化，不做夸张肌肉效果。"""


# ─────────────────────────────────────────────
#  VEO — видео «после»
# ─────────────────────────────────────────────


def _muscle_changes_text(muscles: dict) -> str:
    label_map = _muscle_label_map()
    effective = _muscles_effective_pcts(muscles)
    lines: list[str] = []
    for key, pct in muscles.items():
        if not pct or key not in label_map:
            continue
        label = label_map[key]
        eff = effective.get(key, int(pct))
        intensity = {
            10: "极轻微收紧，线条略清晰，几乎接近原图；非健美块头",
            20: "适度增强，轮廓自然清晰，不增大块头；拒绝分离度很高的健美造型",
            30: "略更明显但仍克制，禁止体积翻倍或健美比赛级夸张；不要大块鼓起的肌肉雕塑感",
        }
        base = int(pct)
        tier = 10 if base <= 12 else 20 if base <= 22 else 30
        desc = intensity.get(tier, intensity[20])
        lines.append(f"- {label}：{desc}（参考强度约 +{eff}%，禁止当成字面放大倍数）")
    return "\n".join(lines) if lines else "- 全身极轻微塑形，略紧致，整体接近原图比例；非健美体型"


def openrouter_after_body_image_prompt(data: dict) -> str:
    """Промпт для OpenRouter (image+text): кадр «после» — только параметры из анкеты (сырые % из UI)."""
    act_ru = {
        "act_low": "Низкая активность",
        "act_mid": "Средняя активность",
        "act_high": "Высокая активность",
    }.get(data.get("activity", "act_mid"), "Средняя активность")

    muscles = data.get("muscles", {}) or {}
    label_map = _muscle_label_map()
    zone_bits: list[str] = []
    for key, _short, _em in MUSCLE_GROUPS:
        raw = muscles.get(key)
        if raw is None or raw == "":
            continue
        try:
            p = int(raw)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        label = label_map.get(key, key)
        zone_bits.append(f"{label}: + {p}%")

    head = (
        "create image: Кадр «после тренировок» по параметрам "
        f"Активность: {act_ru}, тон кожи не меняй, лицо не меняй"
    )
    if not zone_bits:
        return head
    return head + ", " + ", ".join(zone_bits)


def veo_after_prompt(data: dict) -> str:
    gender = "女性" if data.get("gender") == "female" else "男性"
    age = data.get("age", 25)
    muscles = data.get("muscles", {}) or {}
    changes = _muscle_changes_text(muscles)

    act = data.get("activity", "act_mid")
    context = {
        "act_low": "刚开始训练一段时间的人",
        "act_mid": "持续规律训练数月的人",
        "act_high": "长期规律训练、体态明显运动化的人",
    }.get(act, "规律健身的人")

    return f"""一位{age}岁的{gender}，在纯白摄影棚背景中做缓慢、平滑的原地360度旋转。

{_aspect_vertical_cn()}

这是“训练后”版本，人物应呈现为：{context}。体型变化要自然可辨但必须克制，禁止把肌肉体积做成“放大一倍”的夸张效果；整体像普通人长期训练可达成的样子，绝不是健美舞台或大块头雕塑风格。重点如下：
{changes}

必须严格遵守：
- 与“训练前”是同一个人：脸部、五官、发色、肤色与肤色的冷暖基调必须与参考图一致；禁止美白、美黑、换肤色或改变人种特征
- 服装保持同类型运动装，不更换为其他风格
- 更紧致、更有线条，但块头不要暴涨；禁止健美比赛级分离度、禁止大块鼓起的“雕塑肌肉”与过度阳刚的块头感；不要血管暴凸的特效
- 皮肤质感自然哑光，无油光、无过度高光、无夸张血管；保留参考图中的皮肤色调与细腻度
- 背景必须与参考图一致：纯白无缝棚拍，不要换景、不要加渐变或虚化光斑；亮度与色调尽量与参考一致
- 画面为完整矩形竖屏，四边笔直填满画幅；禁止圆形裁切、圆角相框、椭圆蒙版、边缘暗角晕环（vignette）、镜头鱼眼鼓形畸变等“一圈一圈”的装饰效果

动作要求：8秒内完成一整圈旋转，姿态自信稳定，动作连贯。
目标效果：能看出训练痕迹，但比例仍真实、可信、可达成。"""


# ─────────────────────────────────────────────
#  Gemini — программа тренировок
# ─────────────────────────────────────────────


def workout_prompt(data: dict) -> str:
    gender_ru = "М" if data.get("gender") == "male" else "Ж"
    act_map = {
        "act_low": "низкий",
        "act_mid": "средний",
        "act_high": "высокий",
    }
    muscles = data.get("muscles", {}) or {}
    label_map = _muscle_label_map()
    goals: list[str] = []
    for k, v in muscles.items():
        if v and k in label_map:
            goals.append(f"{label_map[k]} +{int(v)}%")
    goals_text = ", ".join(goals) if goals else "всё тело"
    act = act_map.get(data.get("activity", "act_mid"), "средний")
    line = (
        f"{gender_ru}, {data.get('age')} лет, {data.get('height')} см, {data.get('weight')} кг, "
        f"активность {act}, акценты: {goals_text}"
    )

    return f"""Составь только календарь силовых тренировок на 1 месяц (строго 4 недели). Без приветствий, без вводных и заключительных абзацев, без «воды» — сразу по делу, текстом покороче.

Оформление под Telegram (чтобы в чате было приятно читать с телефона):
— Русский язык, обычный текст, без HTML и без Markdown (# ** __).
— Между крупными блоками вставляй пустую строку: месяц → пустая строка → день → пустая строка → разминка / основа / заминка отдельно.
— Заголовки недели и дня — одна короткая строка; можно один эмодзи в заголовке (например 📅 НЕДЕЛЯ 1, затем 🏋 ПН — …, 🏋 СР — …, 🏋 ПТ — …) — не перегружай эмодзи, только акценты.
— Разминка, основной блок и заминка — списками: каждая строка с маркером «• » в начале; не сваливай всё в один абзац.
— Упражнение = одна строка: «• Название — N×M» (N подходов, M повторений) или «• Название — N подходов × M повторений»; для кардио/планки — время вместо повторов.
— Строки держи короткими; не дублируй одно и то же разными формулировками.

Расписание:
— Строго 4 недели: НЕДЕЛЯ 1, НЕДЕЛЯ 2, НЕДЕЛЯ 3, НЕДЕЛЯ 4.
— В каждой неделе только три тренировочных дня: понедельник, среда, пятница. Остальные дни не описывать.
— Неделя 1 — базовый объём. Неделя 2 — небольшая прогрессия. Неделя 3 — основная нагрузка. Неделя 4 — облегчённая/контрольная неделя с сохранением техники.
— В самом конце — блок «Прогрессия» (3–6 коротких строк: как добавлять или снижать нагрузку по неделям), без теории.

Разделение мышц по дням (обязательно):
— ПН, СР и ПТ — это три **разные** тренировки: у **каждого** дня свой «профиль» групп мышц, а не полный перечень всего тела на каждый из трёх дней.
— Логичный шаблон на выбор (или эквивалентный): ПН — толкание/передняя цепь (грудь, плечи, трицепс, пресс по необходимости); СР — тяга/задняя цепь (спина, бицепс, задняя дельта, шея трапеции по месту); ПТ — ноги и ягодицы + икры + пресс/кор. Можно чуть сместить акценты, но смысл тот же: **три дня — три разных фокуса**, без трёх одинаковых «фулбоди на всё».
— Приоритетные зоны из данных клиента **распредели** по тем дням, где это естественно (например бицепсы → в день тяги, бёдра/ягодицы/икры → в день ног), а не сваливай все выбранные группы в один день.

Учитывай акценты по группам мышц из данных клиента.

Данные клиента: {line}"""


# ─────────────────────────────────────────────
#  Gemini — питание (кратко)
# ─────────────────────────────────────────────


def nutrition_prompt(data: dict) -> str:
    gender_ru = "М" if data.get("gender") == "male" else "Ж"
    weight = float(data.get("weight") or 70)
    height = int(data.get("height") or 170)
    age = int(data.get("age") or 25)
    act_map = {
        "act_low": 1.2,
        "act_mid": 1.375,
        "act_high": 1.55,
    }
    activity = act_map.get(data.get("activity", "act_mid"), 1.375)

    if data.get("gender") == "male":
        bmr = 88.36 + (13.4 * weight) + (4.8 * height) - (5.7 * age)
    else:
        bmr = 447.6 + (9.2 * weight) + (3.1 * height) - (4.3 * age)
    calories = int(bmr * activity)

    muscles = data.get("muscles", {}) or {}
    label_map = _muscle_label_map()
    goals = [label_map[k] for k, v in muscles.items() if v and k in label_map]
    goals_text = ", ".join(goals) if goals else "тонус"

    protein_lo = int(weight * 1.6)
    protein_hi = int(weight * 2.0)
    water_lo = round(weight * 0.033, 1)
    water_hi = round(weight * 0.038, 1)

    return f"""Дай только практические рекомендации по питанию. Без приветствий и прощаний, без HTML/Markdown, без длинных вступлений — без «воды», только сжатые пункты по делу.

Структура ответа (заголовки + короткие строки под каждым):

КАЛОРИИ — ориентир {calories} ккал/день; как сделать лёгкий минус (порции, что убрать в первую очередь).
БЕЛОК — ориентир {protein_lo}–{protein_hi} г/сутки; примеры продуктов.
УГЛЕВОДЫ И ЖИРЫ — по сути в паре строк (качество рациона, не разжёвывать теорию).
ОВОЩИ И КЛЕТЧАТКА — сколько порций в день, как встроить в приёмы пищи.
ЧТО СОКРАТИТЬ — до 3 конкретных пунктов.
ВОДА — ориентир {water_lo}–{water_hi} л в день.

Данные человека: {gender_ru}, {age} лет, {int(weight)} кг, {height} см, акцент по зонам: {goals_text}."""


def water_hint_text(data: dict) -> str:
    w = float(data.get("weight") or 70)
    goal_l = round(w * 0.033, 2)
    drunk = int(data.get("water_ml_today", 0) or 0)
    return (
        f"💧 <b>Вода сегодня</b>\n"
        f"Выпито: ~{drunk} мл из ориентира ~{int(goal_l * 1000)} мл/день\n\n"
        f"Нажимайте «+250 мл» после стакана. «Сброс» — новый день вручную."
    )
