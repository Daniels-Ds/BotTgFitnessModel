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


def _normalize_muscles_for_prompt(muscles: dict) -> tuple[dict[str, int], int | None]:
    """
    Правило пользователя для промптов:
    - если выбрано >= 3 зон по 50% => использовать 50% везде по выбранным зонам
    - иначе если выбрано > 4 зон по 30% => использовать 30% везде по выбранным зонам
    - иначе => стандартно (как выбрал пользователь: 10/30/50 по каждой зоне)
    """
    cleaned: dict[str, int] = {}
    for key, raw in (muscles or {}).items():
        if raw in (None, ""):
            continue
        try:
            p = int(raw)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        cleaned[key] = p

    count50 = sum(1 for p in cleaned.values() if p == 50)
    count30 = sum(1 for p in cleaned.values() if p == 30)

    override: int | None = None
    if count50 >= 3:
        override = 50
    elif count30 > 4:
        override = 30

    if override is None:
        return cleaned, None
    return {k: override for k in cleaned.keys()}, override


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


HAILUO_I2V_PROMPT_MAX = 2000


_AFTER_INTENSITY_TEXT_EN: dict[int, str] = {
    10: (
        "Subtle natural tone. Body looks lightly active, not trained.\n"
        "Soft muscle definition, no visible separation.\n"
        "Slight firmness only. Relaxed everyday physique.\n"
        "No athletic emphasis on any zone."
    ),
    30: (
        "Athletic but natural build. Moderate muscle definition visible.\n"
        "Toned appearance without bulk. Fit everyday person look.\n"
        "Light muscle shape on shoulders, arms, core, legs.\n"
        "Realistic fitness result, not a gym obsessive."
    ),
    50: (
        "Clearly trained physique. Defined muscles with visible shape.\n"
        "Strong but not bulky. Lean with noticeable muscle tone.\n"
        "V-taper silhouette, firm arms, defined core, solid legs.\n"
        "Competitive fitness look, not bodybuilding."
    ),
}


def _muscle_average_tier(muscles: dict) -> int:
    """Средний tier по выбранным зонам (10/30/50), затем маппинг к ближайшему tier."""
    values: list[int] = []
    for key, _short, _em in MUSCLE_GROUPS:
        raw = (muscles or {}).get(key)
        if raw in (None, ""):
            continue
        try:
            p = int(raw)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        values.append(_muscle_ui_tier(p))
    if not values:
        return 10
    avg = sum(values) / len(values)
    return _muscle_ui_tier(int(round(avg)))


def _muscle_zone_brief_hailuo(muscles: dict) -> str:
    """Фиксированный текст уровня интенсивности для Hailuo (без % и без зонных списков)."""
    tier = _muscle_average_tier(muscles)
    return _AFTER_INTENSITY_TEXT_EN.get(tier, _AFTER_INTENSITY_TEXT_EN[30])


def _muscle_changes_text(muscles: dict) -> str:
    return _muscle_zone_brief_hailuo(muscles)


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
    """Для программы тренировок (не для промпта фото «после»)."""
    if tier <= 10:
        return "лёгкий акцент"
    if tier <= 30:
        return "умеренный акцент"
    return "заметный, но реалистичный акцент"


def _after_body_zone_phrase_en(key: str, pct: int) -> str:
    """Zone line for the accent block (UI tiers 10 / 30 / 50)."""
    label = _muscle_label_en(key)
    hint = _AFTER_ZONE_HINT_EN.get(key, "").strip()
    if pct >= 50:
        head = f"{label} — improve by {pct}%"
    else:
        head = f"{label} — improve by {pct}%"
    if hint:
        return f"{head}: {hint}"
    return f"{head}:"


# Зоны, которые имеет смысл править на данном ракурсе (остальные — не упоминать в промпте).
_AFTER_VIEW_VISIBLE: dict[str, frozenset[str]] = {
    "front": frozenset({"shoulders", "chest", "biceps", "triceps", "abs", "thighs", "calves", "glutes"}),
    "side": frozenset({"shoulders", "chest", "abs", "glutes", "thighs", "calves", "biceps"}),
    "back": frozenset({"shoulders", "triceps", "glutes", "thighs", "calves"}),
}

_VIEW_LABEL_EN = {
    "front": "front view (facing camera)",
    "side": "side profile",
    "back": "back view",
}

_AFTER_ZONE_HINT_EN: dict[str, str] = {
    "shoulders": "slightly cleaner shoulder line, light tone",
    "chest": "neat chest tone",
    "thighs": "firmer leg contour",
    "calves": "slightly more defined calves",
    "glutes": "natural lift and firmness",
    "biceps": "tone on the front of the arm",
    "triceps": "tone on the back of the arm",
    "abs": "slightly narrower waist, soft definition",
}

_AFTER_BODY_PRESERVE = (
    "Edit this photo: same person, same face, same expression, hairstyle, skin tone, "
    "ethnicity, clothing, pose, background, camera angle, and lighting. Do not change identity or face."
)

_AFTER_BODY_FOOTER = (
    "Overall edit tone: healthy, toned, natural fitness-model physique; improvements visible but believable. "
    "Preserve skin texture and proportions. Realistic light and detail. No sexualization. "
    "If the source has censorship bars, remove them without changing identity."
)


def _after_body_zones_text_for_view(muscles: dict, view: str) -> str:
    """Одна строка зон для промпта (через пробел), только видимые на ракурсе."""
    visible = _AFTER_VIEW_VISIBLE.get(view, frozenset())
    phrases: list[str] = []
    for key, _short, _em in MUSCLE_GROUPS:
        if key not in visible:
            continue
        raw = muscles.get(key)
        if raw is None or raw == "":
            continue
        try:
            p = int(raw)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        pct = _muscle_ui_tier(p)
        phrases.append(_after_body_zone_phrase_en(key, pct))
    return " ".join(phrases)


def after_body_image_prompt(data: dict, view: str | None = None) -> str:
    muscles = data.get("muscles", {}) or {}
    muscles, _override = _normalize_muscles_for_prompt(muscles)
    view_key = (view or "front").strip().lower()
    view_label = _VIEW_LABEL_EN.get(view_key, view_key)
    zones_text = _after_body_zones_text_for_view(muscles, view_key)

    parts: list[str] = [
        _AFTER_BODY_PRESERVE,
        (
            f"This photo: {view_label}. Improve only body zones that are actually visible in this angle; "
            "do not add definition or volume where the zone is not visible (e.g. abs on a back view)."
        ),
    ]

    if zones_text:
        parts.append(
            "Apply realistic athletic improvement only in the listed zones (visible in this frame). "
            "Leave everything else unchanged beyond a smooth blend. No bodybuilding look, no overpumping, no veins."
        )
        parts.append(f"Zones and emphasis: {zones_text}")
    else:
        parts.append(
            "Apply a mild even athletic improvement to visible body areas in this frame: "
            "light tone, slightly leaner silhouette."
        )

    parts.append(_AFTER_BODY_FOOTER)
    return "\n".join(parts)


def after_body_edit_prompt(data: dict, view: str | None = None) -> str:
    """Текст для редактирования кадра «после» (fal image instruct edit)."""
    return after_body_image_prompt(data, view=view)


HAILUO_TURN_VIDEO_PROMPT = (
    "Static camera. Person turns body 180 degrees in place.\n"
    "The person slowly rotates in place 180 degrees to show their back.\n"
    "Smooth, natural rotation. No dancing, no arm movements, no extra gestures.\n"
    "Feet stay in place. Camera is fixed, no zoom, no pan.\n"
    "Same lighting and background throughout."
)


def hailuo_before_turn_prompt(*, dual_frame: bool = True) -> str:
    """Hailuo i2v «до»: image_url = анфас; end_image_url = спина (если dual_frame)."""
    return HAILUO_TURN_VIDEO_PROMPT


def hailuo_after_turn_prompt(data: dict, *, dual_frame: bool = True) -> str:
    """Hailuo i2v «после»: поворот + after look + зоны (English, <=2000 chars)."""
    muscles = data.get("muscles", {}) or {}
    zones = _muscle_zone_brief_hailuo(muscles)

    if dual_frame:
        frame_hint = "Start: front after-training still. End: back view. Smooth in-place 180° turn."
    else:
        frame_hint = "From front after-training still, turn in place to show back."

    prompt = (
        f"{HAILUO_TURN_VIDEO_PROMPT}\n\n"
        f"{frame_hint}\n"
        "Keep the leaner toned 'after training' body from the reference stills; "
        "do not revert to untrained baseline. Realistic fitness look, not bodybuilding.\n"
        f"Intensity profile:\n{zones}"
    )
    if len(prompt) > HAILUO_I2V_PROMPT_MAX:
        prompt = prompt[:HAILUO_I2V_PROMPT_MAX]
    return prompt


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

_CYCLE_PHASE_EN: dict[str, str] = {
    "cyc_men": "menstruation (days 1–5): lower volume/intensity, technique and mobility OK; avoid max lifts if unwell",
    "cyc_foll": "follicular phase (after period): energy rising — good for progression and new loads",
    "cyc_ovu": "ovulation / mid-cycle: often peak strength — can push working weights carefully",
    "cyc_lut": "luteal phase (before period): may feel heavier — moderate volume, more rest, listen to fatigue",
    "cyc_skip": "cycle not tracked — use general female-friendly autoregulation (sleep, energy, no guilt deloads)",
}

_ACT_LABEL_RU = {
    "act_low": "малоподвижный / начинающий",
    "act_mid": "средняя активность",
    "act_high": "регулярные тренировки / продвинутый",
}


def _workout_muscle_goals_ru(muscles: dict) -> list[str]:
    lines: list[str] = []
    muscles, _override = _normalize_muscles_for_prompt(muscles)
    for key, _short, _em in MUSCLE_GROUPS:
        raw = muscles.get(key)
        if not raw:
            continue
        try:
            p = int(raw)
        except (TypeError, ValueError):
            continue
        if p <= 0:
            continue
        tier = _muscle_ui_tier(p)
        level = _after_body_intensity_ru(tier)
        lines.append(f"- {_muscle_label_ru(key)}: {level} (приоритет в сплите)")
    return lines


def _workout_body_measurements_block(data: dict) -> str:
    meas = data.get("body_measurements")
    if not isinstance(meas, dict):
        return ""
    labels = (
        ("waist", "талия"),
        ("hips", "бёдра"),
        ("chest", "грудь"),
        ("shoulders", "плечи"),
        ("thigh", "бедро"),
        ("calf", "икра"),
        ("biceps", "бицепс"),
    )
    parts = [f"{ru} {int(meas[k])} см" for k, ru in labels if meas.get(k) is not None]
    if not parts:
        return ""
    return "Замеры тела (последние в боте): " + ", ".join(parts) + "."


def _workout_bmi_line(height_cm: int, weight_kg: float) -> str:
    h_m = height_cm / 100.0
    if h_m <= 0:
        return ""
    bmi = weight_kg / (h_m * h_m)
    if bmi < 18.5:
        cat = "ниже нормы — не урезать калории агрессивно; акцент на технику и умеренный прогресс"
    elif bmi < 25:
        cat = "норма — стандартная прогрессия"
    elif bmi < 30:
        cat = "избыточный вес — беречь суставы, больше ног/ягодиц, контроль техники"
    else:
        cat = "ожирение — низкоударная нагрузка где нужно, постепенное увеличение объёма"
    return f"ИМТ ≈ {bmi:.1f} ({cat})."


def _workout_load_anchors(data: dict) -> str:
    """Ориентиры рабочих весов для недели 1 (модель должна подставлять в каждое упражнение)."""
    gender = data.get("gender", "male")
    weight_kg = float(data.get("weight") or 70)
    activity = str(data.get("activity", "act_mid"))
    age = int(data.get("age") or 25)

    mult = {"act_low": 0.55, "act_mid": 0.75, "act_high": 1.0}.get(activity, 0.75)
    if gender == "female":
        mult *= 0.82
    if age >= 50:
        mult *= 0.88
    elif age >= 40:
        mult *= 0.93

    def _rnd(x: float) -> float:
        return max(2.5, round(x / 2.5) * 2.5)

    squat = _rnd(weight_kg * 0.38 * mult)
    bench = _rnd(weight_kg * 0.28 * mult)
    rdl = _rnd(weight_kg * 0.42 * mult)
    row = _rnd(weight_kg * 0.32 * mult)
    press = _rnd(weight_kg * 0.20 * mult)
    leg_press = _rnd(weight_kg * 0.90 * mult)
    db_pair = _rnd(weight_kg * 0.14 * mult)

    return f"""
LOAD ANCHORS for THIS client (week 1 working weights — you MUST print similar kg on EVERY strength line; adjust by exercise type):
- Barbell back squat: ~{squat} kg
- Barbell bench press: ~{bench} kg (or dumbbells ~{db_pair} kg each hand if safer)
- Romanian deadlift / hip hinge: ~{rdl} kg
- Barbell / cable row: ~{row} kg
- Standing / seated press: ~{press} kg
- Leg press (machine, total load): ~{leg_press} kg
- Isolation (curls, extensions, raises): ~30–50% of related compound anchor; cables/machines by feel for 10–15 reps with 1–2 reps in reserve
- Week 2–3: +2.5–5 kg on compounds if form is solid; Week 4 deload: −25–30% from week 3 anchors
- If client is female in menstruation/luteal phase: use lower half of range or −10–15% vs anchors above
"""


def _workout_client_profile_block(data: dict) -> str:
    gender = str(data.get("gender", "male"))
    gender_ru = "мужчина" if gender == "male" else "женщина"
    age = int(data.get("age") or 25)
    height = int(data.get("height") or 170)
    weight = float(data.get("weight") or 70)
    activity = str(data.get("activity", "act_mid"))
    act_ru = _ACT_LABEL_RU.get(activity, activity)

    lines = [
        "CLIENT PROFILE (mandatory — program must match ALL of this):",
        f"- Пол: {gender_ru}",
        f"- Возраст: {age} лет",
        f"- Рост: {height} см, вес: {weight:.0f} кг",
        _workout_bmi_line(height, weight),
        f"- Активность / уровень: {act_ru}",
    ]

    goals = _workout_muscle_goals_ru(data.get("muscles", {}) or {})
    if goals:
        lines.append("- Желаемые акценты (зоны из анкеты):")
        lines.extend(goals)
    else:
        lines.append("- Желаемые акценты: равномерный тонус всего тела")

    meas = _workout_body_measurements_block(data)
    if meas:
        lines.append(f"- {meas}")

    if gender == "female":
        phase = str(data.get("cycle_phase", "cyc_skip"))
        lines.append(f"- Менструальный цикл (сейчас): {_CYCLE_PHASE_EN.get(phase, _CYCLE_PHASE_EN['cyc_skip'])}")
        lines.append(
            "- Female programming: prioritize glutes/hamstrings/mid delt; autoregulate volume by cycle phase; "
            "no max-effort tests during menstruation if client feels unwell."
        )

    lines.append(_workout_load_anchors(data))
    return "\n".join(line for line in lines if line)


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
    profile = _workout_client_profile_block(data)
    header_ru = f"НЕДЕЛЯ {w}"
    continuity = ""
    if previous_week_excerpt and w > 1:
        continuity = (
            "\n\nCONTINUITY — excerpt from the client's previous week (Russian, may be truncated). "
            "Stay consistent with exercise choices and naming; progress logically:\n---\n"
            f"{previous_week_excerpt.strip()}\n---"
        )
    elif w > 1:
        continuity = (
            "\n\nNo previous week text is stored yet — invent a sensible continuation for a typical 4-week gym block "
            f"matching the week {w} role described above."
        )
 
    # Определяем уровень подготовки из activity
    activity = str(data.get("activity", "act_mid"))
    if activity == "act_low":
        level_block = """
LEVEL = BEGINNER (act_low):
- Full-body 3 days/week. All three days cover all major muscle groups.
- Only compound multi-joint exercises. NO isolation-only days.
- 2–3 working sets per exercise, 12–15 reps.
- Do NOT include: skull crushers (французский жим), sumo deadlift, hack squat, behind-the-neck press.
- Squat depth: start at 90° knee angle, do not force deeper.
- Add a brief technique note for squat, bench press, and deadlift (if used).
"""
    elif activity == "act_high":
        level_block = """
LEVEL = ADVANCED (act_high):
- 3-day split. Each day targets different muscle groups.
- Pattern: Push (chest, shoulders, triceps) / Pull (back, biceps) / Legs + glutes + core.
- 4–5 working sets per exercise, 6–10 reps on compound lifts, 10–15 on isolation.
- Can include advanced techniques: supersets, forced reps (only in week 3).
- Skull crushers (французский жим) allowed ONLY in week 3; replace with close-grip bench in weeks 1,2,4.
- Deadlift and squat should NOT be in the same session.
"""
    else:
        level_block = """
LEVEL = INTERMEDIATE (act_mid):
- 3-day split. Each day targets different muscle groups.
- Pattern: Push (chest, shoulders, triceps) / Pull (back, biceps) / Legs + glutes + core.
- 3–4 working sets per exercise, 8–12 reps.
- Compound to isolation ratio ~60/40 per session.
- Deadlift and squat should NOT be in the same session.
"""
 
    gender = str(data.get("gender", "male"))
    if gender == "female":
        gender_block = """
FEMALE CLIENT SPECIFICS:
- Grip width for bench press: ~42 cm (narrower than male standard ~52 cm). Prefer dumbbells over barbell if unsure.
- Priority emphasis zones: glutes, hamstrings, middle deltoid.
- For abs: prefer crunches/скручивания (Group 1 — spine flexion), NOT roman chair sit-ups until core is strong.
- Scott bench curl with one dumbbell works well.
- Avoid behind-the-neck press entirely.
"""
    else:
        gender_block = """
MALE CLIENT SPECIFICS:
- Grip width for bench press: ~52 cm. Barbell or dumbbells both valid.
- Avoid behind-the-neck press entirely (95% injury probability with heavy loads over time).
"""
 
    return f"""You are a certified strength coach trained in the methodology of D.G. Kalashnikov «Exercises with Weights» (FPA Russia). Output ONLY ONE training week labeled «{header_ru}» (exactly that week number). No greetings, no other weeks, no filler.
 
OUTPUT LANGUAGE: Russian (Cyrillic), plain text for Telegram. Do NOT use HTML or Markdown (no # ** __ `).
 
━━━ KALASHNIKOV METHODOLOGY — MANDATORY RULES ━━━
 
EXERCISE ORDER (always follow this sequence inside each session):
1. Compound multi-joint first: squats, bench press, deadlift, pull-ups, overhead press
2. Auxiliary compound second: lunges, dumbbell press, barbell row
3. Isolation last: flyes, curls, extensions, deltoid raises
4. Stretching at the end only
 
TECHNIQUE REQUIREMENTS (embed brief cues in parentheses next to exercise name for beginners):
- Squats: knees track over foot, natural lumbar curve, controlled descent (no bounce at bottom)
- Bench press: scapulae retracted and pressed into bench throughout («карандаш между лопаток»), forearms vertical at bottom
- Back rows: retract scapulae at end of movement; elbow stays vertical in lat pulldown, does NOT go back
- Lateral raises: fixed elbow angle throughout, do NOT raise above ears, shoulder girdle stays «down»
- Deadlift: bar stays close to shins/thighs, neutral spine, simultaneous leg and trunk extension
 
SAFETY RULES (hard):
- NEVER put squats and deadlifts in the same session (both max-load spinal extensors)
- NEVER prescribe behind-the-neck press (жим из-за головы) — replace with standing barbell press
- Skull crushers (французский жим): only in advanced level week 3; otherwise use close-grip bench press
- All eccentric (lowering) phases: slow and controlled, no momentum/cheating for beginners
- Hack squat: knee angle maximum 90° — deeper risks knee injury
 
AB TRAINING RULES:
- «Upper» and «lower» abs cannot be truly isolated — the rectus abdominis contracts as a whole
- Group 1 (spine flexion — прямая работает динамически): crunches, reverse crunches — safer for lumbar
- Group 2 (hip flexors work dynamically — прямая как стабилизатор): roman chair, hanging leg raises — add only when core is strong
- Keep lumbar spine flexed throughout Group 2 exercises — never hyperextend lower back
 
EXERCISE SELECTION BY MUSCLE GROUP:
Legs/quads: squats, leg press (platform 45°), lunges, leg extension (isolation)
Legs/hamstrings+glutes: Romanian deadlift, leg curl, hyperextension, glute bridge
Calves: standing calf raise (gastrocnemius — straight leg), seated calf raise (soleus — bent knee)
Chest: bench press / incline bench press (30–45°) / dumbbell press / flyes (elbow angle ~120°) / cable crossover / pec deck
Back-vertical: lat pulldown to chest (torso leaned back, scapulae squeeze) / pull-ups
Back-horizontal: barbell row (45° torso) / dumbbell row / seated cable row / shrugs
Shoulders: standing/seated dumbbell press / lateral raises / bent-over rear delt raises / upright row
Biceps: barbell curl (underhand grip, elbow fixed) / incline dumbbell curl / Scott bench curl
Triceps: cable pushdown / close-grip bench press / overhead dumbbell extension (one arm) / dips (vertical torso)
Abs: crunches / reverse crunches / hanging leg raises / plank
 
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{level_block}
{gender_block}
 
ROLE FOR THIS WEEK: {role}
{continuity}
 
SPLIT (mandatory for this week):
- ПН / СР / ПТ are three DIFFERENT profiles. FORBIDDEN: three identical full-body days (except beginner level).
- Map client emphasis zones to sensible days (biceps → pull day; glutes/thighs/calves → leg day; shoulders → push day).

{profile}

STRICT FORMAT:
- Start with one line: «{header_ru}» then a blank line.
- Three training days: «🏋 ПН — [focus]» / «🏋 СР — [focus]» / «🏋 ПТ — [focus]»
- Blank line between each day block.
- Inside each day: Разминка / Основа / Заминка as short plain-text headings, then bullet lines only — each line starts with «• »
- One exercise per line MUST include working weight in kg: «• Название (подсказка) — N×M, ~XX кг (или гантели ~XX кг×2), отдых Xs»
- Every compound and machine strength exercise needs a concrete ~kg value derived from LOAD ANCHORS and week role (not «по ощущениям» alone).
- End this week with a block «Подсказка на неделю» — 2–4 lines (sleep, recovery, when to add weight). No full-month theory."""


_WEEKDAY_RU = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)

# Фокус сессии по дню недели (ротация, работает в любой день)
_DAY_FOCUS: dict[int, tuple[str, str]] = {
    0: ("Ноги и ягодицы", "квадрицепс, бёдра, ягодицы, икры, пресс"),
    1: ("Грудь, плечи, трицепс", "жимовые, отжимания, плечи, трицепс"),
    2: ("Спина и бицепс", "тяги, подтягивания, бицепс, задняя дельта"),
    3: ("Ноги и корпус", "присед, выпады, пресс, поясница — умеренный объём"),
    4: ("Верх тела", "грудь + спина + плечи в одной сессии, без максимумов"),
    5: ("Функциональная / лёгкая", "всё тело, умеренные веса, больше повторений"),
    6: ("Восстановление + тонус", "лёгкая круговая, мобильность, не до отказа"),
}


def _workout_level_block(data: dict) -> str:
    activity = str(data.get("activity", "act_mid"))
    if activity == "act_low":
        return """
LEVEL = BEGINNER (act_low):
- Одна сессия на сегодня: всё тело, базовые многосуставные упражнения.
- 2–3 рабочих подхода, 12–15 повторений. Без изоляции «только одной мышцы».
- Не включать: жим из-за головы, сумо-становую, гакк-присед глубже 90°.
"""
    if activity == "act_high":
        return """
LEVEL = ADVANCED (act_high):
- Одна полноценная сессия под фокус дня; 4–5 подходов на ключевые упражнения.
- Базовые 6–10 пов, изоляция 10–15. Без максимальных тестов.
- Становая и присед в один день не ставить.
"""
    return """
LEVEL = INTERMEDIATE (act_mid):
- Одна сессия под фокус дня; 3–4 подхода, 8–12 пов на базовые, 10–12 на изоляцию.
- Становая и присед в один день не ставить.
"""


def _workout_gender_block(data: dict) -> str:
    if str(data.get("gender", "male")) == "female":
        return """
FEMALE CLIENT: акцент ягодицы/бёдра/средняя дельта; жим гантелями допустим; пресс — скручивания; без жима из-за головы.
"""
    return """
MALE CLIENT: жим штанги/гантелей; без жима из-за головы.
"""


def workout_prompt_today(data: dict, weekday_index: int) -> str:
    """Одна тренировка на календарный день (любой день недели)."""
    wd = int(weekday_index) % 7
    weekday_ru = _WEEKDAY_RU[wd]
    title, muscles = _DAY_FOCUS.get(wd, _DAY_FOCUS[0])
    profile = _workout_client_profile_block(data)
    anchors = _workout_load_anchors(data).replace(
        "week 1 working weights",
        "today's working weights",
    ).replace("Week 2–3:", "Progression:").replace("Week 4 deload:", "If fatigued:")

    return f"""You are a certified strength coach (Kalashnikov methodology, FPA Russia). Output ONLY ONE gym session for TODAY ({weekday_ru}). No greetings, no weekly plan, no other days.

OUTPUT LANGUAGE: Russian (Cyrillic), plain text for Telegram. No HTML/Markdown.

TODAY SESSION FOCUS: «{title}» — emphasize: {muscles}.

RULES (mandatory):
- One session only: Разминка → Основа → Заминка.
- Compound exercises first, isolation last. Stretching at the end.
- Never squat + deadlift same session. No behind-the-neck press.
- Each strength line: «• Упражнение (краткая техника) — N×M, ~XX кг, отдых Xs» using LOAD ANCHORS.
- Total 6–10 exercises in Основа (fewer if beginner).
- End with «Подсказка на сегодня» — 2–3 короткие строки (вода, сон, когда добавить вес).

FORMAT:
- First line exactly: «🏋 Тренировка на сегодня — {weekday_ru}»
- Subtitle: «Фокус: {title}»
- Then Разминка / Основа / Заминка as plain headings, bullets «• » only.

{_workout_level_block(data)}
{_workout_gender_block(data)}

{anchors}

{profile}
"""


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
