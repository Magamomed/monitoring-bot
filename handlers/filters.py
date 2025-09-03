import re
from aiogram import Router, F
from aiogram.types import Message

from config import BOT_START_TIME, ADMIN_USERNAMES, IMMUNE_USERS
from filters.stopwords import STOP_WORDS
from filters.ai_filter import is_bad_content
from database import add_warning, is_immune_user

router = Router()

@router.message(F.text, lambda m: not m.text.startswith("/"))
async def filter_and_warn(message: Message):
    if message.date < BOT_START_TIME:
        return

    
    if await is_immune_user(message.from_user.id):  
        return

@router.message(F.text, lambda m: not m.text.startswith("/"))
async def filter_and_warn(message: Message):
    # игнорим старые сообщения (до запуска бота)
    if message.date < BOT_START_TIME:
        return

    # иммунитет
    if message.from_user.id in IMMUNE_USERS[0]:
        return

    text = message.text.strip()

    # AI-модерация по фразам/предложениям
    for part in re.split(r"[.!?\n]", text):
        part = part.strip()
        if part:
            if await is_bad_content(part):
                mention = ", ".join(ADMIN_USERNAMES)
                await message.reply(
                    f"⚠️ Обнаружено нежелательное содержание от {message.from_user.full_name}.\n"
                    f"{mention}, пожалуйста, проверьте."
                )
                return

    # простая проверка по стоп-словам — только уведомляем и считаем выговоры
    if any(w for w in STOP_WORDS if w and w in text):
        user_id = message.from_user.id
        warns = await add_warning(user_id)

        admins_text = ", ".join(ADMIN_USERNAMES)
        await message.bot.send_message(
            message.chat.id,
            f"⚠️ Нарушение от {message.from_user.full_name} (@{message.from_user.username or 'нет ника'})\n"
            f"{admins_text}, посмотрите пожалуйста.",
            reply_to_message_id=message.message_id
        )

        # При необходимости можешь раскомментировать блок действий (удаление/мут/бан)
        # исходник оставлял это как опциональное поведение.

def register_filter_handlers(dp):
    dp.include_router(router)
