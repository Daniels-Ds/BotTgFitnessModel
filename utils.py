"""
Утилиты для обработки текста
"""
import re
from aiogram.types import Message

def strip_html_tags(text: str) -> str:
    """
    Полностью удаляет все HTML-теги из текста.
    Оставляет только чистый текст.
    """
    # Удаляем все HTML теги
    text = re.sub(r'<[^>]+>', '', text)
    
    # Очищаем множественные переносы строк
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    
    # Убираем лишние пробелы
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text.strip()


def clean_for_telegram(text: str) -> str:
    """
    Очищает текст для отправки в Telegram.
    Удаляет HTML-теги, форматирует списки.
    """
    # Заменяем <li> на маркеры
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    
    # Удаляем закрывающие теги li, ul, ol, p, div и др.
    text = re.sub(r'</?(ul|ol|li|p|div|span|strong|em|h[1-6])[^>]*>', '', text, flags=re.IGNORECASE)
    
    # Удаляем оставшиеся теги
    text = re.sub(r'<[^>]+>', '', text)
    
    # Чистим лишние переносы
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Добавляем отступы для вложенных списков
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        # Убираем лишние пробелы в начале
        line = line.strip()
        if line:
            cleaned.append(line)
    
    return '\n'.join(cleaned)


def format_workout_plan(text: str) -> str:
    """
    Специальная обработка для плана тренировок.
    Превращает HTML-списки в читаемый формат.
    """
    # Заменяем <b> на ** (Telegram Markdown)
    text = re.sub(r'<b>(.*?)</b>', r'*\1*', text, flags=re.IGNORECASE)
    
    # Обрабатываем списки
    lines = text.split('\n')
    result = []
    in_list = False
    
    for line in lines:
        # Проверяем на открывающий тег списка
        if re.match(r'<ul|<ol', line, re.IGNORECASE):
            in_list = True
            continue
        
        # Проверяем на закрывающий тег списка
        if re.match(r'</ul|</ol', line, re.IGNORECASE):
            in_list = False
            continue
        
        # Обрабатываем элемент списка
        li_match = re.match(r'<li[^>]*>(.*?)</li>', line, re.IGNORECASE)
        if li_match:
            content = li_match.group(1)
            # Убираем оставшиеся теги
            content = re.sub(r'<[^>]+>', '', content)
            result.append(f"  • {content}")
            continue
        
        # Обычная строка
        if not in_list:
            # Убираем теги p, div и т.д.
            clean_line = re.sub(r'<[^>]+>', '', line)
            if clean_line.strip():
                result.append(clean_line)
    
    return '\n'.join(result)

# utils.py добавить функцию:

def remove_all_html(text: str) -> str:
    """Удаляет все HTML-теги и заменяет их на обычный текст."""
    import re
    # Заменяем <li> на маркер •
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    # Убираем все остальные теги
    text = re.sub(r'<[^>]+>', '', text)
    # Чистим множественные переносы
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    # Убираем лишние пробелы в начале строк
    text = '\n'.join(line.strip() for line in text.splitlines())
    return text.strip()

async def init_ui(state):
    await state.update_data(ui_messages=[])


async def track_ui(state, message):
    data = await state.get_data()
    msgs = data.get("ui_messages", [])
    msgs.append(message.message_id)
    await state.update_data(ui_messages=msgs)


async def clear_ui(bot, chat_id, state):
    data = await state.get_data()
    msgs = data.get("ui_messages", [])

    for mid in msgs:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except:
            pass

    await state.update_data(ui_messages=[])




async def safe_delete_message(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

from aiogram.types import CallbackQuery

async def cleanup_chat(call: CallbackQuery):
    # удаляет текущее сообщение
    try:
        await call.message.delete()
    except:
        pass