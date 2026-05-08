# BotTgFitnessModel

Telegram-бот для фитнес-сценариев: анкета, рекомендации по тренировкам/питанию и flow с замерами.

## Quick start (local/server)

1. Установите Python 3.11+.
2. Скопируйте `.env.example` в `.env`.
3. Заполните обязательные переменные в `.env`:
   - `BOT_TOKEN`
   - `GOOGLE_AI_API_KEY`
   - `OPENROUTER_API_KEY`
   - `KIE_API_KEY` (если используется соответствующий flow)
   - `WAN_API_KEY` (если используется соответствующий flow)
4. Установите зависимости:
   - `pip install -r requirements.txt`
5. Запуск:
   - `python bot.py`

## Deploy (simple VPS)

Пример минимального запуска через `systemd`:

1. Склонируйте репозиторий на сервер.
2. Создайте virtualenv и установите зависимости.
3. Положите `.env` в корень проекта.
4. Создайте unit:

`/etc/systemd/system/fitness-bot.service`

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

5. Активируйте:
   - `sudo systemctl daemon-reload`
   - `sudo systemctl enable fitness-bot`
   - `sudo systemctl start fitness-bot`
   - `sudo systemctl status fitness-bot`

## Security

- Не коммитьте `.env`.
- Если ключи уже попадали в историю/чат, перевыпустите их у провайдеров.
- Для публичного репозитория храните секреты только на сервере (env/systemd/secret manager).
