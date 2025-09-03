from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

from utils.rules import load_rules
from database import get_warnings

router = Router()

@router.message(Command("правила"))
async def cmd_rules(message: Message):
    await message.answer(f"📋 <b>Правила чата:</b>\n\n{load_rules()}", parse_mode="HTML")

@router.message(Command("warns"))
async def cmd_warns(message: Message):
    warns = await get_warnings(message.from_user.id)
    await message.answer(f"📝 У вас {warns}/3 выговоров.")

# Фан-ответы
@router.message(lambda m: m.text and m.text.lower() == "что будет если ты не будешь работать?")
async def funny_response(message: Message):
    member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return
    await message.reply("меня поругает мой хозяин, только не говорите ему когда я сломаюсь пж")

@router.message(lambda m: m.text and m.text.lower() == "кто твой хозяин?")
async def funny_response_owner(message: Message):
    await message.reply("Мой хозян @Maga22804")

def register_user_handlers(dp):
    dp.include_router(router)
