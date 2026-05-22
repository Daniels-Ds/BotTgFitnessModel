"""
Model prompts (Wan i2v, Google Nano Banana / Qwen Image Edit, DashScope text). UI copy stays in messages.py.
"""

from keyboards import MUSCLE_GROUPS

from config import MUSCLE_PROMPT_MAX_PCT, MUSCLE_PROMPT_SCALE

# English zone names for model-facing text (UI in keyboards stays Russian).
_MUSCLE_LABEL_EN: dict[str, str] = {
    "shoulders": "Shoulders",
    "chest": "Chest",
    "thighs": "Thighs",
    "calves": "Calves",
    "glutes": "Glutes",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "abs": "Abs",
}


def _muscle_label_en(key: str) -> str:
    return _MUSCLE_LABEL_EN.get(key, key.replace("_", " ").title())


def _aspect_vertical() -> str:
    return (
        "MANDATORY framing: true vertical 9:16 full-screen phone portrait. Subject fills most of the frame height. "
        "FORBIDDEN: 16:9 landscape, cinematic widescreen, large black side bars, letterboxing as the main look."
    )


def _video_180_half_turn_instructions() -> str:
    return (
"The fitness model slowly and smoothly rotates exactly 180 degrees in place, keeping the exact same pose, posture, muscle tension, and outfit throughout. No dancing, no flexing, no limb movement, no facial expression change. Stable body, minimal motion, clean and static background. Photorealistic, consistent anatomy."

    )


def _video_motion_discipline() -> str:
    return (
        "MOTION RULES (ABSOLUTE PRIORITY): "
        "This is a technical turntable-style body scan, not a performance. "
        "The only permitted motion is a single controlled half-turn from front to back. "
        "No dance-like behavior of any kind. "
        "No rhythmic motion. "
        "No body sway. "
        "No hip rolls. "
        "No runway walk. "
        "No hand movement. "
        "No shoulder movement. "
        "No foot repositioning except the pivot itself. "
        "Once the back view is reached, freeze completely."
    )


def _muscles_effective_pcts(muscles: dict) -> dict[str, int]:
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


def _activity_profile_en(activity: str) -> str:
    return {
        "act_low": "mostly sedentary; beginner training level",
        "act_mid": "moderately active; several months of consistent training",
        "act_high": "long training history; clearly athletic build",
    }.get(activity, "moderately active; consistent training")


def _activity_label_en(activity: str) -> str:
    return {
        "act_low": "Low daily activity",
        "act_mid": "Moderate activity",
        "act_high": "High activity / regular training",
    }.get(activity, "Moderate activity")


# ─── Wan i2v — “current” reference video ─────────────────────────────


def veo_current_prompt(data: dict) -> str:
    age = int(data.get("age") or 25)
    if data.get("gender") == "female":
        subject = f"A fit {age}-year-old woman"
    else:
        subject = f"A fit {age}-year-old man"
    return f"""{subject} in athletic wear, seamless white cyclorama studio. One continuous clip: in-app preview labeled “current body”.

{_aspect_vertical()}

{_video_180_half_turn_instructions()}

{_video_motion_discipline()}

IDENTITY LOCK: Must match the reference image—same face, hairstyle, skin tone and undertone, lighting character (no skin lightening/darkening or tone drift), same body proportions, same clothing style.

LIGHTING: Soft even studio light; natural matte skin; no greasy shine, no harsh specular highlights.

STYLE: Photoreal natural fitness look. FORBIDDEN: competition bodybuilding look, exaggerated muscle sculpture, doubled muscle volume, morphing or caricature anatomy."""


# ─── Wan i2v — “after training” video ───────────────────────────────


def _muscle_ui_tier(base: int) -> int:
    """UI choice 10 / 30 / 50; legacy saved 20% maps to the middle tier."""
    b = int(base)
    if b <= 15:
        return 10
    if b <= 40:
        return 30
    return 50


def _muscle_changes_text(muscles: dict) -> str:
    effective = _muscles_effective_pcts(muscles)
    lines: list[str] = []
    for key, pct in (muscles or {}).items():
        if not pct or key not in _MUSCLE_LABEL_EN:
            continue
        label = _muscle_label_en(key)
        eff = effective.get(key, int(pct))
        intensity = {
            10: "Very subtle tightening; lines slightly cleaner, close to reference; no bodybuilder bulk",
            30: "Moderate natural definition without overall mass gain; no extreme bodybuilder separation",
            50: "Stronger visible emphasis but still restrained; no doubled volume, no competition-level bulk",
        }
        base = int(pct)
        tier = _muscle_ui_tier(base)
        desc = intensity.get(tier, intensity[30])
        lines.append(
            f"- {label}: {desc}. Target emphasis ~+{eff}% (interpret as guidance only, not a literal scale multiplier)."
        )
    return (
        "\n".join(lines)
        if lines
        else "- Whole body: minimal believable tightening, slightly leaner where soft; proportions stay close to reference; no bodybuilder look"
    )


# ─── Qwen Image Edit — «after» body photo ────────────────────────────

_AFTER_BODY_NEGATIVE_PROMPT = (
    "overmuscled, bulky, powerlifter, bodybuilder, thick arms, huge shoulders, broad chest, "
    "exaggerated muscles, steroid look, popping veins, vascular, too muscular, heavy muscle mass, "
    "competition physique, cartoon anatomy, deformed proportions, changed face, plastic skin, "
    "unnatural body"
)


def after_body_image_negative_prompt() -> str:
    return _AFTER_BODY_NEGATIVE_PROMPT


def _muscle_label_ru(key: str) -> str:
    for k, short, _em in MUSCLE_GROUPS:
        if k == key:
            return short
    return key.replace("_", " ")


def _after_body_intensity_ru(tier: int) -> str:
    if tier <= 10:
        return "лёгкий акцент"
    if tier <= 30:
        return "умеренный акцент"
    return "заметный, но реалистичный акцент"


def _after_body_zone_line_ru(key: str, tier: int, *, female: bool) -> str:
    label = _muscle_label_ru(key)
    level = _after_body_intensity_ru(tier)
    hints = {
        "shoulders": f"{label} — {level}: чуть ровнее линия плеч, лёгкий тонус, без массивных дельт",
        "chest": f"{label} — {level}: аккуратный тонус, без увеличения объёма «накачанной» груди",
        "thighs": (
            f"{label} — {level}: подтянутый спортивный контур, без лишней массы"
            if female
            else f"{label} — {level}: подтянутые бёдра и ноги, без массивной массы"
        ),
        "calves": f"{label} — {level}: чуть более рельефные икры",
        "glutes": (
            f"{label} — {level}: упругость и подъём, естественная форма"
            if female
            else f"{label} — {level}: плотность и компактный спортивный подъём"
        ),
        "biceps": f"{label} — {level}: тонус передней части руки, без больших бицепсов",
        "triceps": f"{label} — {level}: тонус задней части руки, без огромных рук",
        "abs": f"{label} — {level}: чуть уже талия, мягкий рельеф, без «кубиков» пресса",
    }
    return hints.get(key, f"{label} — {level}")


def _after_body_selected_zone_lines(muscles: dict, *, female: bool) -> list[str]:
    lines: list[str] = []
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
        lines.append(_after_body_zone_line_ru(key, _muscle_ui_tier(p), female=female))
    return lines


_AFTER_BODY_PRESERVE = (
    "Отредактируй это фото: тот же человек, то же лицо, та же мимика, причёска, тон кожи, "
    "этничность, одежда, поза, фон, ракурс и освещение. Личность и лицо не менять."
)

_AFTER_BODY_FOOTER = (
    "Общий тон правки: здоровое, подтянутое, естественное телосложение фитнес-модели; "
    "улучшения видны, но правдоподобны. Сохрани текстуры кожи и пропорции. "
    "Реалистичный свет и детализация. Без сексуализации. "
    "Если на исходнике есть цензура — убери её, не меняя идентичность."
)


def openrouter_after_body_image_prompt(data: dict) -> str:
    muscles = data.get("muscles", {}) or {}
    female = data.get("gender") == "female"
    zone_lines = _after_body_selected_zone_lines(muscles, female=female)

    if zone_lines:
        body = (
            "Сделай реалистичное спортивное улучшение тела только в зонах, которые пользователь отметил ниже. "
            "Не трогай остальные части тела сверх необходимого для естественного перехода между зонами. "
            "Без культуризма, без перекачки, без вен, без мультяшной анатомии.\n\n"
            "Зоны и сила акцента:\n"
            + "\n".join(zone_lines)
        )
    else:
        body = (
            "Сделай мягкое равномерное спортивное улучшение всего тела: лёгкий тонус, чуть суше и подтянутее силуэт "
            "по всей фигуре (торс, руки, ноги, ягодицы, икры), без перекачки и без культуристического вида. "
            "Улучшения слегка заметны, но естественны."
        )

    return f"{_AFTER_BODY_PRESERVE}\n\n{body}\n\n{_AFTER_BODY_FOOTER}"


def after_body_edit_prompt(data: dict) -> str:
    """Текст для редактирования кадра «после» (Google Nano Banana / Kie / Qwen)."""
    return openrouter_after_body_image_prompt(data)


def kie_seedream_after_body_prompt(data: dict) -> str:
    """Kie Seedream: negative в конце промпта (отдельного поля у API нет)."""
    return after_body_edit_prompt(data) + "\n\nAvoid: " + after_body_image_negative_prompt()


def body_measurements_overlay_prompt(values: dict[str, int]) -> str:
    specs: tuple[tuple[str, str], ...] = (
        ("shoulders", "A horizontal measurement line across the shoulders reads '{v}'."),
        ("chest", "An arc around the chest reads '{v}'."),
        ("biceps", "An arc on the visible upper arm / bicep reads '{v}'."),
        ("waist", "An arc around the natural waist reads '{v}'."),
        ("hips", "An arc around the hips reads '{v}'."),
        ("thigh", "An arc on the visible thigh reads '{v}'."),
        ("calf", "An arc on the visible calf reads '{v}'."),
    )
    lines = "\n".join("— " + template.format(v=int(values[key])) for key, template in specs)
    return (
        "SOURCE: Use only the provided photograph as the pixel base.\n"
        "PRESERVE EXACTLY: identity (face, hair, skin tone, body shape), clothing, room/background, pose, lens angle, lighting. "
        "Do not repaint the scene, do not replace the subject, do not “fix” anatomy or proportions—ONLY add flat measurement graphics.\n\n"
        "NUMBERS: The centimeter integers below were typed by the user. You MUST render exactly these integers next to the correct arcs/lines. "
        "FORBIDDEN: estimating from the photo, rounding differently, swapping zones, inventing an 8th measurement, OCR hallucination.\n\n"
        "GRAPHIC STYLE: Thin white/clear technical diagram lines, small arcs, minimal ticks; numeric labels in cm (optional tiny “cm” tag). "
        "Tailoring / anthropometry chart aesthetic—NOT decorative banners, NOT meme text, NOT arrows pointing off-body.\n\n"
        "Place exactly these seven measurements (no more, no less):\n"
        f"{lines}\n\n"
        "CONTENT SAFETY: clinical/neutral presentation only. FORBIDDEN: sexualization, lingerie emphasis, identity change, caricature, "
        "changing clothes or environment except for the overlay graphics."
    )


def veo_after_prompt(data: dict) -> str:
    age = int(data.get("age") or 25)
    if data.get("gender") == "female":
        subject = f"A {age}-year-old woman"
    else:
        subject = f"A {age}-year-old man"
    muscles = data.get("muscles", {}) or {}
    changes = _muscle_changes_text(muscles)
    act = str(data.get("activity", "act_mid"))
    context = _activity_profile_en(act)

    return f"""{subject} in athletic wear, seamless white cyclorama studio. One continuous clip: in-app preview labeled “after training”.

REFERENCE STILL: The first frame is already the edited “after training” portrait (retouched leaner/toned)—preserve that improved silhouette through the whole clip; do NOT revert toward a heavier or untrained baseline during motion.

{_aspect_vertical()}

{_video_180_half_turn_instructions()}

{_video_motion_discipline()}

NARRATIVE: This is the “after” version. The person should read as: {context}. Changes must be noticeable yet restrained—credible long-term progress for a normal trainee, NOT a bodybuilding stage shot or hyper-sculpted anatomy.

ZONE BRIEF (obey without exaggeration):
{changes}

HARD RULES:
- Same identity as “before”: face, hair color, skin tone/undertone must match the reference; no skin-tone drift, no ethnicity change.
- Same athletic clothing type; no fashion genre change.
- Leaner/clearer but FORBIDDEN: sudden huge mass, competition separation, cartoon “pumped” muscles, exaggerated veins.
- Skin: natural matte; no oil-slick shine, no extreme speculars, no vein emphasis beyond reference.
- Background: seamless white studio like reference; FORBIDDEN: new locations, fake gradients, fake bokeh, props.
- Full rectangular vertical frame with straight edges; FORBIDDEN: circular crops, rounded masks, heavy vignette halos, fisheye barrel distortion.

GOAL: Visible training effect with believable proportions; motion reads as a single slow front-to-back half-turn ending on a clear rear view (~180°), not a full 360° spin."""


# ─── Text LLM — workout plan (one week at a time) ─────────────────────


def _workout_client_facts_line(data: dict) -> str:
    gender = "male" if data.get("gender") == "male" else "female"
    act_map = {
        "act_low": "low",
        "act_mid": "moderate",
        "act_high": "high",
    }
    muscles = data.get("muscles", {}) or {}
    goals: list[str] = []
    for k, v in muscles.items():
        if v and k in _MUSCLE_LABEL_EN:
            goals.append(f"{_muscle_label_en(k)} +{int(v)}%")
    goals_text = ", ".join(goals) if goals else "full-body general tone"
    act = act_map.get(str(data.get("activity", "act_mid")), "moderate")
    return (
        f"sex={gender}, age={data.get('age')} y, height={data.get('height')} cm, weight={data.get('weight')} kg, "
        f"activity={act}, emphasis_zones={goals_text}"
    )


def workout_prompt_week(data: dict, week: int, previous_week_excerpt: str | None) -> str:
    """Одна неделя (Пн/Ср/Пт); week 1..4; excerpt — хвост текста прошлой недели для преемственности."""
    w = int(week)
    roles = {
        1: "Week 1 = BASELINE: learn movements, moderate volume, technique first.",
        2: "Week 2 = SMALL PROGRESSION: slightly more sets or reps vs week 1 feel; same split style.",
        3: "Week 3 = MAIN BLOCK: highest planned volume this mesocycle; still form-safe.",
        4: "Week 4 = DELOAD / CONTROL: lighter loads or fewer sets, same exercises; recovery and technique check.",
    }
    role = roles.get(w, roles[1])
    facts = _workout_client_facts_line(data)
    header_ru = f"НЕДЕЛЯ {w}"
    continuity = ""
    if previous_week_excerpt and w > 1:
        continuity = (
            "\n\nCONTINUITY — excerpt from the client’s previous week (Russian, may be truncated). "
            "Stay consistent with exercise choices and naming; progress logically:\n---\n"
            f"{previous_week_excerpt.strip()}\n---"
        )
    elif w > 1:
        continuity = (
            "\n\nNo previous week text is stored yet — invent a sensible continuation for a typical 4-week gym block "
            f"matching the week {w} role described above."
        )

    return f"""You are a strength coach. Output ONLY ONE training week labeled «{header_ru}» (exactly that week number). No greetings, no other weeks, no filler.

OUTPUT LANGUAGE: Russian (Cyrillic), plain text for Telegram. Do NOT use HTML or Markdown (no # ** __ `).

STRICT FORMAT:
- Start with one line: «{header_ru}» then a blank line.
- Three training days only: Monday, Wednesday, Friday — headers like «🏋 ПН — …» / «🏋 СР — …» / «🏋 ПТ — …» (short focus name).
- Blank line between each day block. Inside each day: Разминка / Основа / Заминка as short headings, then bullet lines only — each line starts with "• ".
- One exercise per line: "• Название — N×M" or time for plank/cardio.
- End this week with a tiny block «Подсказка на неделю» — 2–4 lines (sleep, steps, when to add weight next week). No full-month theory.

ROLE FOR THIS WEEK: {role}
{continuity}

SPLIT (mandatory for this week):
- ПН / СР / ПТ are three DIFFERENT profiles (push / pull / legs+glutes+core pattern or equivalent). FORBIDDEN three identical full-body days.
- Map client emphasis zones to sensible days (biceps → pull day; glutes/thighs/calves → leg day).

Client facts: {facts}"""


# ─── Text LLM — nutrition (concise) ───────────────────────────────────


def nutrition_prompt(data: dict) -> str:
    gender = "male" if data.get("gender") == "male" else "female"
    weight = float(data.get("weight") or 70)
    height = int(data.get("height") or 170)
    age = int(data.get("age") or 25)
    act_map = {
        "act_low": 1.2,
        "act_mid": 1.375,
        "act_high": 1.55,
    }
    activity = act_map.get(str(data.get("activity", "act_mid")), 1.375)

    if data.get("gender") == "male":
        bmr = 88.36 + (13.4 * weight) + (4.8 * height) - (5.7 * age)
    else:
        bmr = 447.6 + (9.2 * weight) + (3.1 * height) - (4.3 * age)
    calories = int(bmr * activity)

    muscles = data.get("muscles", {}) or {}
    goals = [_muscle_label_en(k) for k, v in muscles.items() if v and k in _MUSCLE_LABEL_EN]
    goals_text = ", ".join(goals) if goals else "general tone"

    protein_lo = int(weight * 1.6)
    protein_hi = int(weight * 2.0)
    water_lo = round(weight * 0.033, 1)
    water_hi = round(weight * 0.038, 1)

    return f"""You are a nutrition coach. Output ONLY practical nutrition guidance. No greetings, no sign-offs, no HTML/Markdown, no long intros.

OUTPUT LANGUAGE: Russian (Cyrillic), plain text. Keep it tight.

Use EXACTLY this section order and headings (Russian), with short lines under each:

КАЛОРИИ — target ~{calories} kcal/day; how to create a mild deficit (portions; what to cut first).
БЕЛОК — target {protein_lo}–{protein_hi} g/day; short food examples.
УГЛЕВОДЫ И ЖИРЫ — max 2 lines: food quality focus, no lecture.
ОВОЩИ И КЛЕТЧАТКА — portions/day + how to distribute across meals.
ЧТО СОКРАТИТЬ — max 3 concrete bullets.
ВОДА — target {water_lo}–{water_hi} L/day.

FORBIDDEN: medical diagnosis, supplement stacks, extreme crash diets, promises of guaranteed results.

Client facts: sex={gender}, age={age}, weight={int(weight)} kg, height={height} cm, zone emphasis={goals_text}."""


def water_hint_text(data: dict) -> str:
    w = float(data.get("weight") or 70)
    goal_l = round(w * 0.033, 2)
    drunk = int(data.get("water_ml_today", 0) or 0)
    return (
        f"💧 <b>Вода сегодня</b>\n"
        f"Выпито: ~{drunk} мл из ориентира ~{int(goal_l * 1000)} мл/день\n\n"
        f"Нажимайте «+250 мл» после стакана. «Сброс» — новый день вручную."
    )
