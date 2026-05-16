import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY") or None
# RunningHub (опционально): только для runninghub_text_client, если зададите RH_TEXT_WEBAPP_ID + WAN_API_KEY.
WAN_API_KEY = os.getenv("WAN_API_KEY")
WAN_BASE_URL = os.getenv("WAN_BASE_URL", "https://www.runninghub.cn")
RH_TEXT_WEBAPP_ID = os.getenv("RH_TEXT_WEBAPP_ID", "").strip()
RH_TEXT_PROMPT_NODE_ID = os.getenv("RH_TEXT_PROMPT_NODE_ID", "176")
RH_TEXT_PROMPT_FIELD_NAME = os.getenv("RH_TEXT_PROMPT_FIELD_NAME", "text")
RH_TEXT_MAX_WAIT_SEC = int(os.getenv("RH_TEXT_MAX_WAIT_SEC", "180"))

# OpenRouter (опционально, legacy; чат и резерв картинки — через DashScope ниже)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_CHAT_COMPLETIONS_URL = os.getenv(
    "OPENROUTER_CHAT_COMPLETIONS_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.6-flash")
# Модель с output modality image (legacy OpenRouter; основной поток — Qwen Image Edit в DashScope).
# Резерв при отказе/пустом ответе — OPENROUTER_IMAGE_FALLBACK_MODEL (slug с openrouter.ai/models?output_modalities=image).
OPENROUTER_IMAGE_MODEL = os.getenv("OPENROUTER_IMAGE_MODEL", "sourceful/riverflow-v2-max-preview")
OPENROUTER_IMAGE_FALLBACK_MODEL = os.getenv("OPENROUTER_IMAGE_FALLBACK_MODEL", "").strip()

# Alibaba Model Studio / DashScope (тот же ключ, что в консоли Model Studio → API Key)
DASHSCOPE_API_KEY = (
    os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_MODEL_STUDIO_API_KEY") or ""
).strip()
# Хост API (без слэша в конце). Singapore intl по умолчанию; для ключа региона Beijing: https://dashscope.aliyuncs.com
DASHSCOPE_HTTP_ORIGIN = os.getenv("DASHSCOPE_HTTP_ORIGIN", "https://dashscope-intl.aliyuncs.com").rstrip("/")
DASHSCOPE_CHAT_COMPLETIONS_URL = os.getenv(
    "DASHSCOPE_CHAT_COMPLETIONS_URL",
    f"{DASHSCOPE_HTTP_ORIGIN}/compatible-mode/v1/chat/completions",
).strip()
DASHSCOPE_TEXT_MODEL = os.getenv("DASHSCOPE_TEXT_MODEL", "qwen-plus").strip()
# Qwen Image Edit: только оверлей замеров на фото (см. body_measurements_overlay_prompt).
DASHSCOPE_QWEN_IMAGE_EDIT_MODEL = os.getenv(
    "DASHSCOPE_QWEN_IMAGE_EDIT_MODEL",
    "qwen-image-2.0",
).strip()
# Кадр «после»: slug из списка моделей Model Studio (intl), не «человеческое» имя — иначе 400 Model not exist.
# См. https://www.alibabacloud.com/help/en/model-studio/models — серия qwen-image-edit-plus.
DASHSCOPE_QWEN_IMAGE_EDIT_AFTER_MODEL = os.getenv(
    "DASHSCOPE_QWEN_IMAGE_EDIT_AFTER_MODEL",
    "qwen-image-edit-plus",
).strip()
# Для кадра «после»: prompt_extend часто переписывает промпт и модель остаётся «слишком близко» к исходнику — по умолчанию выкл.
DASHSCOPE_QWEN_AFTER_PROMPT_EXTEND = os.getenv(
    "DASHSCOPE_QWEN_AFTER_PROMPT_EXTEND", "false"
).strip().lower() in ("1", "true", "yes")
DASHSCOPE_QWEN_IMAGE_EDIT_SIZE = os.getenv("DASHSCOPE_QWEN_IMAGE_EDIT_SIZE", "1080*1920").strip()
# Видео Wan 2.2 image-to-video (полуоборот ~180°, async task)
DASHSCOPE_WAN_I2V_MODEL = os.getenv("DASHSCOPE_WAN_I2V_MODEL", "wan2.2-i2v-plus").strip()
DASHSCOPE_WAN_I2V_RESOLUTION = os.getenv("DASHSCOPE_WAN_I2V_RESOLUTION", "480P").strip()


def _parse_wan_i2v_seed(raw: str, env_name: str) -> int | None:
    v = (raw or "").strip()
    if not v:
        return None
    try:
        n = int(v)
    except ValueError:
        import logging

        logging.getLogger(__name__).warning(
            "%s=%r is not an integer — seed ignored", env_name, raw
        )
        return None
    if not 0 <= n <= 2147483647:
        import logging

        logging.getLogger(__name__).warning(
            "%s=%s out of range [0, 2147483647] — seed ignored", env_name, n
        )
        return None
    return n


# Фиксированный seed из веб-консоли (опционально). Пусто = случайный seed у API.
DASHSCOPE_WAN_I2V_SEED = _parse_wan_i2v_seed(
    os.getenv("DASHSCOPE_WAN_I2V_SEED", ""), "DASHSCOPE_WAN_I2V_SEED"
)
# Второе видео («после»); если пусто — используется DASHSCOPE_WAN_I2V_SEED (если задан).
DASHSCOPE_WAN_I2V_SEED_AFTER = _parse_wan_i2v_seed(
    os.getenv("DASHSCOPE_WAN_I2V_SEED_AFTER", ""), "DASHSCOPE_WAN_I2V_SEED_AFTER"
)

DASHSCOPE_WAN_I2V_PROMPT_EXTEND = os.getenv("DASHSCOPE_WAN_I2V_PROMPT_EXTEND", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
# Wan i2v: prompt_extend часто добавляет «киношную» динамику (вплоть до танца); negative_prompt — подавляет танец/клип.
DASHSCOPE_WAN_I2V_NEGATIVE_PROMPT = os.getenv(
    "DASHSCOPE_WAN_I2V_NEGATIVE_PROMPT",
    "dancing, dance moves, rhythmic sway, bouncing, jumping, twirling, leg kicks, arm choreography, runway walk, "
    "music video, party, nightclub, hip rolls, exaggerated posing, aerobic steps, side-to-side footwork, head bopping, "
    "zoom in, dolly in, camera orbit, handheld shake, fast cuts, jump cuts, lens flare, text overlay, watermark, "
    "nudity, lingerie, sexualized posing",
).strip()
DASHSCOPE_VIDEO_POLL_INTERVAL_SEC = float(os.getenv("DASHSCOPE_VIDEO_POLL_INTERVAL_SEC", "4"))
DASHSCOPE_VIDEO_MAX_WAIT_SEC = int(os.getenv("DASHSCOPE_VIDEO_MAX_WAIT_SEC", "600"))

# В промпты (WAN / OpenRouter image) уходят «смягчённые» проценты зон: иначе модели завышают эффект.
# UI по-прежнему 10/20/30; здесь множитель и потолок для текста промптов.
MUSCLE_PROMPT_SCALE = float(os.getenv("MUSCLE_PROMPT_SCALE", "0.55"))
MUSCLE_PROMPT_MAX_PCT = int(os.getenv("MUSCLE_PROMPT_MAX_PCT", "18"))

# USE_WAN_FOR_VIDEO=0 — только превью: два фото (реф + Qwen «после»), без видео Wan i2v.
USE_WAN_FOR_VIDEO = os.getenv("USE_WAN_FOR_VIDEO", "1").strip().lower() in ("1", "true", "yes")

# ⚡ ВАЖНО: быстрая модель Gemini
GEMINI_MODEL = "gemini-2.5-flash"

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"
