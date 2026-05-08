import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY") or None
WAN_API_KEY = os.getenv("WAN_API_KEY")
WAN_BASE_URL = os.getenv("WAN_BASE_URL", "https://www.runninghub.cn")
WAN_WEBAPP_ID = os.getenv("WAN_WEBAPP_ID", "2044172566255902722")
# Кадр «после» (референс → картинка) через отдельный ai-app, затем эта картинка уходит в WAN_WEBAPP_ID на 360°.
# Шаблон Qwen Image Edit: LoadImage «7» → VAEEncode / TextEncodeQwenImageEditPlus; промпт зашит в узле 27 — по умолчанию не шлём.
WAN_AFTER_IMAGE_WEBAPP_ID = os.getenv("WAN_AFTER_IMAGE_WEBAPP_ID", "2051297563692810242").strip()
WAN_AFTER_IMAGE_NODE_IMAGE = os.getenv("WAN_AFTER_IMAGE_NODE_IMAGE", "7").strip()
WAN_AFTER_IMAGE_NODE_PROMPT = os.getenv("WAN_AFTER_IMAGE_NODE_PROMPT", "").strip()
WAN_AFTER_IMAGE_FIELD_IMAGE = os.getenv("WAN_AFTER_IMAGE_FIELD_IMAGE", "image").strip()
WAN_AFTER_IMAGE_FIELD_PROMPT = os.getenv("WAN_AFTER_IMAGE_FIELD_PROMPT", "prompt").strip()
WAN_AFTER_IMAGE_DURATION_NODE_ID = os.getenv("WAN_AFTER_IMAGE_DURATION_NODE_ID", "").strip()
WAN_WEBAPP_ID_AFTER = os.getenv("WAN_WEBAPP_ID_AFTER", WAN_WEBAPP_ID or "")
WAN_MEASUREMENTS_WEBAPP_ID = os.getenv("WAN_MEASUREMENTS_WEBAPP_ID", "").strip()
WAN_MEASUREMENTS_NODE_IMAGE = os.getenv("WAN_MEASUREMENTS_NODE_IMAGE", "7").strip()
WAN_MEASUREMENTS_FIELD_IMAGE = os.getenv("WAN_MEASUREMENTS_FIELD_IMAGE", "image").strip()
WAN_MEASUREMENTS_NODE_PROMPT = os.getenv("WAN_MEASUREMENTS_NODE_PROMPT", "").strip()
WAN_MEASUREMENTS_FIELD_PROMPT = os.getenv("WAN_MEASUREMENTS_FIELD_PROMPT", "prompt").strip()
WAN_UPLOAD_URL = os.getenv("WAN_UPLOAD_URL", "https://www.runninghub.cn/task/openapi/upload")
RH_TEXT_WEBAPP_ID = os.getenv("RH_TEXT_WEBAPP_ID", WAN_WEBAPP_ID or "")
RH_TEXT_PROMPT_NODE_ID = os.getenv("RH_TEXT_PROMPT_NODE_ID", "176")
RH_TEXT_PROMPT_FIELD_NAME = os.getenv("RH_TEXT_PROMPT_FIELD_NAME", "text")
RH_TEXT_MAX_WAIT_SEC = int(os.getenv("RH_TEXT_MAX_WAIT_SEC", "180"))

# KIE.ai (генерация фото по замерам)
KIE_API_KEY = os.getenv("KIE_API_KEY", "").strip()
KIE_BASE_URL = os.getenv("KIE_BASE_URL", "https://api.kie.ai").strip()
KIE_UPLOAD_BASE_URL = os.getenv("KIE_UPLOAD_BASE_URL", "https://kieai.redpandaai.co").strip()
KIE_UPLOAD_PATH = os.getenv("KIE_UPLOAD_PATH", "images/user-uploads").strip()
KIE_IMAGE_MODEL = os.getenv("KIE_IMAGE_MODEL", "flux-kontext-pro").strip()
KIE_IMAGE_ASPECT_RATIO = os.getenv("KIE_IMAGE_ASPECT_RATIO", "9:16").strip()
KIE_IMAGE_MAX_WAIT_SEC = int(os.getenv("KIE_IMAGE_MAX_WAIT_SEC", "180"))

# OpenRouter (для тренировок/питания вместо RunningHub)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_CHAT_COMPLETIONS_URL = os.getenv(
    "OPENROUTER_CHAT_COMPLETIONS_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "qwen/qwen3.6-flash")
# Модель с output modality image: резерв, если RunningHub (WAN_AFTER_IMAGE_WEBAPP_ID) не вернул картинку.
# Резерв при отказе/пустом ответе — OPENROUTER_IMAGE_FALLBACK_MODEL (slug с openrouter.ai/models?output_modalities=image).
OPENROUTER_IMAGE_MODEL = os.getenv("OPENROUTER_IMAGE_MODEL", "sourceful/riverflow-v2-max-preview")
OPENROUTER_IMAGE_FALLBACK_MODEL = os.getenv("OPENROUTER_IMAGE_FALLBACK_MODEL", "").strip()

# В промпты (WAN / OpenRouter image) уходят «смягчённые» проценты зон: иначе модели завышают эффект.
# UI по-прежнему 10/20/30; здесь множитель и потолок для текста промптов.
MUSCLE_PROMPT_SCALE = float(os.getenv("MUSCLE_PROMPT_SCALE", "0.55"))
MUSCLE_PROMPT_MAX_PCT = int(os.getenv("MUSCLE_PROMPT_MAX_PCT", "18"))

# Опционально: если в ai-app есть узел под соотношение сторон (из JSON workflow), задайте id/поле/значение.
WAN_ASPECT_NODE_ID = os.getenv("WAN_ASPECT_NODE_ID", "").strip()
WAN_ASPECT_FIELD_NAME = os.getenv("WAN_ASPECT_FIELD_NAME", "value").strip()
WAN_ASPECT_FIELD_VALUE = os.getenv("WAN_ASPECT_FIELD_VALUE", "9:16").strip()

# USE_WAN_FOR_VIDEO=0 — только превью: два фото (реф + OpenRouter), без RunningHub. По умолчанию включены два видео WAN.
USE_WAN_FOR_VIDEO = os.getenv("USE_WAN_FOR_VIDEO", "1").strip().lower() in ("1", "true", "yes")

# ⚡ ВАЖНО: быстрая модель Gemini
GEMINI_MODEL = "gemini-2.5-flash"

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"
