from functools import wraps
from aiogram.types import Message
from config import ADMIN_USERNAMES

async def is_admin_user(message: Message) -> bool:
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ("administrator", "creator"):
            return True
    except Exception:
        pass
    return username in ADMIN_USERNAMES

def only_admin_or_owner(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if not await is_admin_user(message):
            return await message.answer("❗ Только админ или владелец может использовать эту команду.")
        return await handler(message, *args, **kwargs)
    return wrapper
