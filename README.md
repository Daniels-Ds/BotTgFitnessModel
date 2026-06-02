# BotTgFitnessModel

Telegram-бот для фитнес-сценариев: анкета, два видео (fal Kling O3 image-to-video), кадры «после» (fal Hunyuan Image v3 instruct edit), тренировки/питание (DashScope), замеры с оверлеем (Qwen).

## Quick start (local/server)

1. Установите Python 3.11+.
2. Скопируйте `.env.example` в `.env`.
3. Заполните обязательные переменные в `.env`:
   - `BOT_TOKEN` — токен Telegram-бота
   - `FAL_KEY` — [fal.ai](https://fal.ai): кадры «после» ([Hunyuan v3 instruct edit](https://fal.ai/models/fal-ai/hunyuan-image/v3/instruct/edit)) и оба видео ([Kling O3 image-to-video](https://fal.ai/models/fal-ai/kling-video/o3/standard/image-to-video))
   - `GOOGLE_AI_API_KEY` — сортировка ракурсов фото (Gemini 2.5 Flash)
   - `DASHSCOPE_API_KEY` — тренировка на сегодня, питание, оверлей замеров (Qwen Image Edit)
4. Опционально: `FAL_HAILUO_DURATION=5` (или `10`), `FAL_HAILUO_MODEL` (полный id Kling-модели, при необходимости), `FAL_FLUX_SEED=3558685`, `FAL_FLUX_SAFETY_TOLERANCE=5` (только Flux), `HTTPS_PROXY`.
5. Установите зависимости: `pip install -r requirements.txt`
6. Запуск: `python bot.py`

## Пайплайн генерации

1. Три фото → Gemini определяет порядок анфас / профиль / спина.
2. fal Kling O3 — видео «сейчас» (кадр анфас).
3. fal Hunyuan Image v3 — кадр(ы) «после» (по зонам анкеты; в тесте — только анфас).
4. fal Kling O3 — видео «после» (отредактированный анфас).

## Deploy (simple VPS)

Пример минимального запуска через `systemd`:

1. Склонируйте репозиторий на сервер.
2. Создайте virtualenv и установите зависимости.
3. Положите `.env` в корень проекта.
4. Создайте unit `/etc/systemd/system/fitness-bot.service`:

```ini
[Unit]
Description=Fitness Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/BotTgFitnessModel
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/BotTgFitnessModel/.venv/bin/python /opt/BotTgFitnessModel/bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

5. `sudo systemctl daemon-reload && sudo systemctl enable --now fitness-bot`

## Security

- Не коммитьте `.env`.
- Если ключи попали в историю или чат — перевыпустите их у провайдеров.
- Для публичного репозитория храните секреты только на сервере.
