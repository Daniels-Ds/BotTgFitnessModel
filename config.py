import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Загрузка видео в Telegram (альбом ~2×MP4 после долгой генерации).
TELEGRAM_REQUEST_TIMEOUT_SEC = int(os.getenv("TELEGRAM_REQUEST_TIMEOUT_SEC", "600"))
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY") or None
# RunningHub (опционально): только для runninghub_text_client, если зададите RH_TEXT_WEBAPP_ID + WAN_API_KEY.
WAN_API_KEY = os.getenv("WAN_API_KEY")
WAN_BASE_URL = os.getenv("WAN_BASE_URL", "https://www.runninghub.cn")
RH_TEXT_WEBAPP_ID = os.getenv("RH_TEXT_WEBAPP_ID", "").strip()
RH_TEXT_PROMPT_NODE_ID = os.getenv("RH_TEXT_PROMPT_NODE_ID", "176")
RH_TEXT_PROMPT_FIELD_NAME = os.getenv("RH_TEXT_PROMPT_FIELD_NAME", "text")
RH_TEXT_MAX_WAIT_SEC = int(os.getenv("RH_TEXT_MAX_WAIT_SEC", "180"))

# Alibaba Model Studio / DashScope (текст, оверлей замеров на фото)
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
# Legacy-модуль qwen (оверлей замеров); кадр «после» — fal.ai Hunyuan instruct edit.
DASHSCOPE_QWEN_IMAGE_EDIT_AFTER_MODEL = os.getenv(
    "DASHSCOPE_QWEN_IMAGE_EDIT_AFTER_MODEL",
    "qwen-image-edit-plus",
).strip()
DASHSCOPE_QWEN_AFTER_PROMPT_EXTEND = os.getenv(
    "DASHSCOPE_QWEN_AFTER_PROMPT_EXTEND", "false"
).strip().lower() in ("1", "true", "yes")
DASHSCOPE_QWEN_IMAGE_EDIT_SIZE = os.getenv("DASHSCOPE_QWEN_IMAGE_EDIT_SIZE", "1080*1920").strip()

# В промпты уходят «смягчённые» проценты зон: иначе модели завышают эффект.
MUSCLE_PROMPT_SCALE = float(os.getenv("MUSCLE_PROMPT_SCALE", "0.55"))
MUSCLE_PROMPT_MAX_PCT = int(os.getenv("MUSCLE_PROMPT_MAX_PCT", "18"))

# Какие ракурсы править для «после» и отдавать в Hailuo (старт/финиш поворота).
# front,back | front | front,side,back
PIPELINE_AFTER_VIEWS_RAW = os.getenv("PIPELINE_AFTER_VIEWS", "front,back").strip().lower()


_VALID_AFTER_VIEWS = frozenset({"front", "side", "back"})


def pipeline_after_views() -> tuple[str, ...]:
    names = [v.strip() for v in PIPELINE_AFTER_VIEWS_RAW.split(",") if v.strip()]
    picked = tuple(v for v in names if v in _VALID_AFTER_VIEWS)
    return picked if picked else ("front", "back")


# Kling O3: один кадр или start/end с `end_image_url` в одной и той же модели.
# Названия переменных оставлены, чтобы не менять остальной код пайплайна.
FAL_HAILUO_DUAL_MODEL = os.getenv(
    "FAL_HAILUO_DUAL_MODEL",
    "fal-ai/kling-video/o3/standard/image-to-video",
).strip()

# fal.ai — кадры «после» (Hunyuan Image v3 instruct edit) и видео (Hailuo 2.3)
FAL_KEY = os.getenv("FAL_KEY", "").strip()
FAL_QUEUE_BASE = os.getenv("FAL_QUEUE_BASE", "https://queue.fal.run").rstrip("/")
# Интервал опроса очереди fal (subscribe по умолчанию ~0.1 с — слишком часто).
FAL_POLL_INTERVAL_SEC = float(os.getenv("FAL_POLL_INTERVAL_SEC", "10"))
FAL_MAX_WAIT_SEC = int(os.getenv("FAL_MAX_WAIT_SEC", "600"))
# Скачивание готовых файлов с CDN (часто падает на прокси — ConnectTimeout).
FAL_DOWNLOAD_RETRIES = max(1, int(os.getenv("FAL_DOWNLOAD_RETRIES", "4")))
FAL_DOWNLOAD_CONNECT_SEC = float(os.getenv("FAL_DOWNLOAD_CONNECT_SEC", "60"))
FAL_DOWNLOAD_READ_SEC = float(os.getenv("FAL_DOWNLOAD_READ_SEC", "600"))
FAL_DOWNLOAD_TRY_DIRECT = os.getenv("FAL_DOWNLOAD_TRY_DIRECT", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Кадр «после» — по умолчанию WAN 2.7 edit
# https://fal.ai/models/fal-ai/wan/v2.7/edit/api
FAL_FLUX_MODEL = os.getenv(
    "FAL_FLUX_MODEL",
    "fal-ai/wan/v2.7/edit",
).strip()
FAL_FLUX_ASPECT_RATIO = os.getenv("FAL_FLUX_ASPECT_RATIO", "9:16").strip()
FAL_FLUX_OUTPUT_FORMAT = os.getenv("FAL_FLUX_OUTPUT_FORMAT", "jpeg").strip().lower()
FAL_FLUX_GUIDANCE_SCALE = float(os.getenv("FAL_FLUX_GUIDANCE_SCALE", "3.5"))
FAL_FLUX_ENABLE_PROMPT_EXPANSION = os.getenv("FAL_FLUX_ENABLE_PROMPT_EXPANSION", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
FAL_FLUX_SAFETY_TOLERANCE = int(os.getenv("FAL_FLUX_SAFETY_TOLERANCE", "5"))
FAL_FLUX_ENABLE_SAFETY_CHECKER = os.getenv("FAL_FLUX_ENABLE_SAFETY_CHECKER", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)
# Seedream и др.: фиксированный seed для воспроизводимости; пусто — без seed (случайно).
_fal_flux_seed_raw = os.getenv("FAL_FLUX_SEED", "3558685").strip()
FAL_FLUX_SEED: int | None = int(_fal_flux_seed_raw) if _fal_flux_seed_raw else None

# WAN v2.7/edit: сиды по уровню интенсивности (10/30/50). Пусто => fallback на FAL_FLUX_SEED.
_wan_after_seed_10_raw = os.getenv("FAL_WAN_AFTER_SEED_10", "").strip()
FAL_WAN_AFTER_SEED_10: int | None = int(_wan_after_seed_10_raw) if _wan_after_seed_10_raw else None
_wan_after_seed_30_raw = os.getenv("FAL_WAN_AFTER_SEED_30", "").strip()
FAL_WAN_AFTER_SEED_30: int | None = int(_wan_after_seed_30_raw) if _wan_after_seed_30_raw else None
_wan_after_seed_50_raw = os.getenv("FAL_WAN_AFTER_SEED_50", "").strip()
FAL_WAN_AFTER_SEED_50: int | None = int(_wan_after_seed_50_raw) if _wan_after_seed_50_raw else None

# Hailuo 2.3 — standard 768p | pro 1080p
FAL_HAILUO_RESOLUTION = os.getenv("FAL_HAILUO_RESOLUTION", os.getenv("KIE_HAILUO_RESOLUTION", "768P")).strip().upper()
FAL_HAILUO_DURATION = int(os.getenv("FAL_HAILUO_DURATION", os.getenv("KIE_HAILUO_DURATION", "6")))
FAL_HAILUO_PROMPT_OPTIMIZER = os.getenv("FAL_HAILUO_PROMPT_OPTIMIZER", "false").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _fal_hailuo_duration() -> int:
    """
    Kling O3 image-to-video принимает duration в пределах 5/10 (в интерфейсе docs),
    поэтому маппим старый env FAL_HAILUO_DURATION (6/10) на допустимые значения.
    """
    return 10 if int(FAL_HAILUO_DURATION) > 6 else 5


def fal_hailuo_model_id() -> str:
    """Модель по желаемому разрешению (env FAL_HAILUO_MODEL переопределяет)."""
    explicit = os.getenv("FAL_HAILUO_MODEL", "").strip()
    if explicit:
        return explicit
    # Для Kling O3 нет отдельного "standard/pro" по resolution: используем стандарт.
    return "fal-ai/kling-video/o3/standard/image-to-video"


FAL_HAILUO_MODEL = fal_hailuo_model_id()

# ⚡ ВАЖНО: быстрая модель Gemini (сортировка ракурсов фото)
GEMINI_MODEL = "gemini-2.5-flash"

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"
