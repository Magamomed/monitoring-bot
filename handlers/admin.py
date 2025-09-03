import re
from aiogram import Router, F
from aiogram import types
from aiogram.filters import Command, CommandObject
from aiogram.enums import ChatType
from aiogram.types import ChatPermissions, Message

from config import (
    ADMIN_USERNAMES,
    SUPER_ADMINS,
    AI_ENABLED,
    PAUSED,
    IMMUNE_USERS,
)
from database import add_immune_user, is_immune_user, list_immune_users, remove_immune_user
from utils.decorators import only_admin_or_owner
from utils.rules import load_rules, save_rules
from filters.stopwords import STOP_WORDS, save_stopwords

router = Router()

@router.message(Command("pause"))
@only_admin_or_owner
async def cmd_pause(message: Message):
    PAUSED[0] = True
    await message.answer("🤖 Бот ушёл перекусить. Не шалите тут без меня!")

@router.message(Command("resume"))
@only_admin_or_owner
async def cmd_resume(message: Message):
    PAUSED[0] = False
    await message.answer("✅ Я снова в деле! Порядок в чате под контролем.")

@router.message(Command("getid"))
@only_admin_or_owner
async def cmd_getid(message: Message):
    await message.answer(f"🆔 Chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")

@router.message(Command("addword"))
@only_admin_or_owner
async def add_word(message: Message, command: CommandObject):
    word = (command.args or "").strip().lower()
    if not word:
        return await message.answer("❗ Укажите слово. Пример: /addword spam")
    STOP_WORDS.append(word)
    save_stopwords(STOP_WORDS)
    await message.answer(f"✅ Добавлено слово: {word}")

@router.message(Command("removeword"))
@only_admin_or_owner
async def remove_word(message: Message, command: CommandObject):
    word = (command.args or "").strip().lower()
    if not word:
        return await message.answer("❗ Укажите слово. Пример: /removeword spam")
    if word in STOP_WORDS:
        STOP_WORDS.remove(word)
        save_stopwords(STOP_WORDS)
        await message.answer(f"❌ Удалено слово: {word}")
    else:
        await message.answer(f"⚠️ Слово не найдено: {word}")

@router.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message, command: CommandObject):
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        is_chat_admin = member.status in ("administrator", "creator")
    except Exception:
        is_chat_admin = False

    if username not in SUPER_ADMINS and not is_chat_admin:
        return await message.answer("❗ Только супер-админы или админы чата могут снимать доступ.")

    target_username = None
    if message.reply_to_message and message.reply_to_message.from_user.username:
        target_username = f"@{message.reply_to_message.from_user.username}"
    elif command.args:
        raw = command.args.strip()
        target_username = raw if raw.startswith("@") else f"@{raw}"
    else:
        return await message.answer("❗ Укажите пользователя через @username или пересланное сообщение.")

    if target_username not in ADMIN_USERNAMES:
        return await message.answer(f"ℹ️ {target_username} не в списке админов.")

    ADMIN_USERNAMES.remove(target_username)
    await message.answer(f"✅ {target_username} удалён из списка админов.")

@router.message(Command("offai"))
@only_admin_or_owner
async def cmd_disable_ai(message: Message):
    AI_ENABLED[0] = False
    await message.answer("❌ Проверка через AI отключена.")

@router.message(Command("onai"))
@only_admin_or_owner
async def cmd_enable_ai(message: Message):
    AI_ENABLED[0] = True
    await message.answer("✅ Проверка через AI включена.")

@router.message(Command("addadmin"))
@only_admin_or_owner
async def cmd_addadmin(message: Message, command: CommandObject):
    username = None
    if message.reply_to_message and message.reply_to_message.from_user.username:
        username = f"@{message.reply_to_message.from_user.username}"
    elif command.args:
        raw = command.args.strip()
        username = raw if raw.startswith("@") else f"@{raw}"
    else:
        return await message.answer("❗ Укажите пользователя через @username или пересланное сообщение.")

    if username in ADMIN_USERNAMES:
        return await message.answer(f"ℹ️ {username} уже в списке админов.")

    ADMIN_USERNAMES.append(username)
    await message.answer(f"✅ {username} добавлен в список владельцев/админов.")

@router.message(Command("helpadmin"))
@only_admin_or_owner
async def cmd_helpadmin(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("❗️ Команда /helpadmin только в группе.")

    await message.answer(
        "👮‍♂️ <b>Админ-команды:</b>\n\n"
        "/helpadmin — показать это сообщение\n"
        "/clearwarns — очистить выговоры (ответом на сообщение)\n"
        "/warns — узнать свои выговоры\n"
        "/mute — замутить пользователя (ответом на сообщение)\n"
        "/unmute — размутить пользователя (ответом на сообщение)\n"
        "/stoplist — показать стоп-слова\n"
        "/ping — проверить, что бот жив\n"
        "/kick — исключить без блокировки (можно снова пригласить)\n"
        "/ban — навсегда забанить (пермач)\n"
        "/addword — добавить слово в стоп-лист\n"
        "/removeword — удалить слово с стоп-листа\n"
        "/правила — показать правила установленные в беседе(для всех)\n"
        "/установить_правила — установить новые правила для беседы\n"
        "/god - иммунитет от фильтраций\n"
        "/godoff - забрать иммунитет от фильтраций\n"
        "/onai - Проверка через AI включена\n"
        "/offai - Проверка через AI отключена\n",
        parse_mode="HTML"
    )

@router.message(Command("mute"))
@only_admin_or_owner
async def cmd_mute(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("❗️ Используйте /mute в группе.")

    target = message.reply_to_message.from_user if message.reply_to_message else None

    if not target:
        return await message.answer("❗ Укажите пользователя ответом или через @username.")

    await message.bot.restrict_chat_member(
        message.chat.id, target.id,
        permissions=ChatPermissions(can_send_messages=False)
    )
    await message.answer(f"🔇 {target.full_name} замучен.")

@router.message(Command("kick"))
@only_admin_or_owner
async def cmd_kick(message: Message, command: CommandObject):
    target = message.reply_to_message.from_user if message.reply_to_message else None

    if not target:
        return await message.answer("❗ Укажите пользователя через @username или ответом.")

    try:
        await message.bot.ban_chat_member(message.chat.id, target.id)
        await message.bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"👢 {target.full_name} был исключён.")
    except Exception as e:
        await message.answer(f"⚠️ Не удалось кикнуть: {e}")

@router.message(Command("ban"))
@only_admin_or_owner
async def cmd_ban(message: Message, command: CommandObject):
    target = message.reply_to_message.from_user if message.reply_to_message else None

    if not target:
        return await message.answer("❗ Укажите пользователя через @username или ответом.")

    try:
        await message.bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🔨 {target.full_name} получил пермач бан.")
    except Exception as e:
        await message.answer(f"⚠️ Не удалось забанить: {e}")

async def _resolve_target_user(message: Message, command: CommandObject):
    """
    Порядок:
    1) если reply → берём автора ответа
    2) если есть аргумент → пытаемся найти участника по username (без @) ИЛИ по id (цифры)
    3) иначе → сам вызывающий
    """
    if message.reply_to_message:
        return message.reply_to_message.from_user

    arg = (command.args or "").strip()
    if arg:
        raw = arg.lstrip("@")
        # попытка как user_id
        if raw.isdigit():
            try:
                member = await message.bot.get_chat_member(message.chat.id, int(raw))
                return member.user
            except Exception:
                pass
        # как username
        try:
            member = await message.bot.get_chat_member(message.chat.id, raw)
            return member.user
        except Exception:
            # Telegram API get_chat_member обычно принимает id, не username-строку.
            # Поэтому fallback: пройдёмся по последним участникам чата, НО это тяжело.
            # Проще попросить, чтобы указали реплаем или числовой id.
            await message.answer("❗ Не удалось найти пользователя. Укажите ответом на сообщение или передайте числовой user_id.")
            return None

    return message.from_user

@router.message(Command("god"))
@only_admin_or_owner
async def cmd_god(message: Message, command: CommandObject):
    target = await _resolve_target_user(message, command)
    if not target:
        return
    await add_immune_user(target.id, target.username)
    await message.answer(f"✨ Пользователь {target.full_name} (@{target.username or '—'}) получил иммунитет от фильтрации.")

@router.message(Command("godoff"))
@only_admin_or_owner
async def cmd_godoff(message: Message, command: CommandObject):
    target = await _resolve_target_user(message, command)
    if not target:
        return
    if await is_immune_user(target.id):
        await remove_immune_user(target.id)
        await message.answer(f"🧯 Иммунитет с {target.full_name} снят.")
    else:
        await message.answer(f"ℹ️ У пользователя {target.full_name} не было иммунитета.")

@router.message(Command("godlist"))
@only_admin_or_owner
async def cmd_godlist(message: Message):
    rows = await list_immune_users()
    if not rows:
        return await message.answer("Список иммунитета пуст.")
    text = "🛡️ <b>Иммунитет:</b>\n" + "\n".join(
        f"- <code>{uid}</code> @{uname or '—'} (с {added_at})" for uid, uname, added_at in rows
    )
    await message.answer(text, parse_mode="HTML")

@router.message(Command("ping"))
@only_admin_or_owner
async def cmd_ping(message: Message):
    await message.answer("Pong! 🤖")

@router.message(Command("установить_правила"))
@only_admin_or_owner
async def cmd_set_rules(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("❗ Укажите новые правила. Пример:\n/установить_правила 1. Не спамить\n2. Не материться")
    save_rules(command.args)
    await message.answer("✅ Правила обновлены.")

@router.message(Command("stoplist"))
@only_admin_or_owner
async def cmd_stoplist(message: Message):
    stops = "\n".join(f"- {w}" for w in STOP_WORDS)
    try:
        await message.bot.send_message(
            message.from_user.id,
            f"📋 <b>Список стоп-слов:</b>\n{stops}",
            parse_mode="HTML"
        )
        if message.chat.type != ChatType.PRIVATE:
            await message.answer("✅ Отправил список стоп-слов вам в личку.")
    except Exception:
        await message.answer("❗ Не удалось отправить ЛС. Напишите мне в личку /start и попробуйте снова.")


def register_admin_handlers(dp):
    dp.include_router(router)
