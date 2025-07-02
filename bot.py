import asyncio
import logging
import random
import os
import re

from dotenv import load_dotenv
import aiosqlite
load_dotenv()
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command , CommandObject
from aiogram.enums import ChatType
from aiogram.types import ChatPermissions, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from PauseMiddleware import PauseMiddleware
from datetime import datetime, timezone

from functools import wraps
from aiogram.types import Message
import requests
import os
# ─── ЗАГРУЗКА ТОКЕНА ─────────────────────────────────────────────────────

API_TOKEN          = os.getenv("BOT_TOKEN")
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
AZURE_API_KEY = os.getenv("OPENAI_API_KEY")
API_VERSION = os.getenv("OPENAI_API_VERSION")


headers = {
    "Content-Type": "application/json",
    "api-key": AZURE_API_KEY,
}


if not API_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в окружении")

bot = Bot(token=API_TOKEN)
dp  = Dispatcher()

BOT_START_TIME = datetime.now(timezone.utc)



# ─── ПАРАМЕТРЫ ───────────────────────────────────────────────────────────
DB_PATH = 'warnings.db'
STOPWORDS_PATH = 'stopwords.txt'
PAUSED = False
AI_ENABLED = True


RULES_PATH = 'rules.txt'
ADMIN_USERNAMES = ["@scrmmzdk", "@Maga22804"]
SUPER_ADMINS = ["@Maga22804", "@scrmmzdk"]


# AI bad content cheking

async def is_bad_content(text: str) -> bool:
    if not AI_ENABLED:
        return False

    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_DEPLOYMENT_NAME}/chat/completions?api-version={API_VERSION}"

    data = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict content moderation AI for a group chat. "
                    "Reply YES only if the message includes any of the following:\n"
                    "1) Hate speech, threats, or discriminatory remarks.\n"
                    "2) Explicit personal insults, especially involving family members.\n"
                    "3) SPAM or SCAMS, including messages about:\n"
                    "   - Quick money (e.g. '7500₽ в день', 'easy income', 'без вложений')\n"
                    "   - Work-from-home schemes\n"
                    "   - Cryptocurrency or investments promising high returns\n"
                    "   - Fake jobs or get-rich-quick offers\n"
                    "   - Contact requests like '@username' with job/money offers\n"
                    "   - Promises of income tied to age or minimal effort (e.g. '18+', 'без опыта')\n"
                    "   - Messages with emotional triggers to lure users (e.g. 'не упусти шанс')\n\n"
                    "Ignore jokes, memes, surprise expressions, and informal slang like 'бля', 'ахуеть' unless they contain clear threats or insults.\n"
                    "Reply strictly with YES or NO."
                )
            },
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
        "max_tokens": 1
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip().lower()
        return answer.startswith("yes")
    except Exception as e:
        print("❗ is_bad_content failed:", e)
        return False



# Проверка: админ по статусу ИЛИ владелец по нику
async def is_admin_user(message: Message) -> bool:
    username = f"@{message.from_user.username}" if message.from_user.username else ""

    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ("administrator", "creator"):
            return True
    except:
        pass

    return username in ADMIN_USERNAMES

# Декоратор
def only_admin_or_owner(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if not await is_admin_user(message):
            return await message.answer("❗ Только админ или владелец может использовать эту команду.")
        return await handler(message, *args, **kwargs)
    return wrapper


# ХРАНЕНИЕ ПРАВИЛ БЕСЕДЫ
def load_rules() -> str:
    if not os.path.exists(RULES_PATH):
        return "Правила чата ещё не установлены."
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        return f.read()

def save_rules(text: str):
    with open(RULES_PATH, 'w', encoding='utf-8') as f:
        f.write(text.strip())



# ─── ХРАНЕНИЕ СТОП-СЛОВ ──────────────────────────────────────────────────
def load_stopwords() -> list[str]:
    if not os.path.exists(STOPWORDS_PATH):
        return []
    with open(STOPWORDS_PATH, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def save_stopwords(words: list[str]):
    with open(STOPWORDS_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(set(words))))

STOP_WORDS = load_stopwords()

@dp.message(F.text.lower() == "что будет если ты не будешь работать?")
async def funny_response(message: Message):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return  # молча игнорим остальных

    await message.reply("меня поругает мой хозяин, только не говорите ему когда я сломаюсь пж")

@dp.message(F.text.lower() == "кто твой хозяин?")
async def funny_response1(message: Message):
    await message.reply("Мой хозян @Maga22804")



pending_verification = {}  # (chat_id, user_id): message_id



# ─── SQLITE: СИСТЕМА ВЫГОВОРОВ ───────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                user_id INTEGER PRIMARY KEY,
                count   INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def get_warnings(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT count FROM warnings WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0

async def add_warning(user_id: int) -> int:
    current = await get_warnings(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if current == 0:
            await db.execute("INSERT INTO warnings (user_id, count) VALUES (?, 1)", (user_id,))
        else:
            await db.execute("UPDATE warnings SET count = count + 1 WHERE user_id = ?", (user_id,))
        await db.commit()
    return current + 1

async def reset_warnings(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
        await db.commit()

# ─── КОМАНДЫ ─────────────────────────────────────────────────────────────
@dp.message(Command("pause"))
@only_admin_or_owner
async def cmd_pause(message: Message):
    global PAUSED
    PAUSED = True
    await message.answer("🤖 Бот ушёл перекусить. Не шалите тут без меня!")


@dp.message(Command("resume"))
@only_admin_or_owner
async def cmd_resume(message: Message):
    global PAUSED
    PAUSED = False
    await message.answer("✅ Я снова в деле! Порядок в чате под контролем.")


@dp.message(Command("getid"))
@only_admin_or_owner
async def cmd_getid(message: Message):
    await message.answer(f"🆔 Chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")


@dp.message(Command("addword"))
@only_admin_or_owner
async def add_word(message: Message, command: CommandObject):
    word = command.args.strip().lower()
    if not word:
        return await message.answer("❗ Укажите слово. Пример: /addword spam")
    STOP_WORDS.append(word)
    save_stopwords(STOP_WORDS)
    await message.answer(f"✅ Добавлено слово: {word}")


@dp.message(Command("removeword"))
@only_admin_or_owner
async def remove_word(message: Message, command: CommandObject):
    word = command.args.strip().lower()
    if not word:
        return await message.answer("❗ Укажите слово. Пример: /removeword spam")
    if word in STOP_WORDS:
        STOP_WORDS.remove(word)
        save_stopwords(STOP_WORDS)
        await message.answer(f"❌ Удалено слово: {word}")
    else:
        await message.answer(f"⚠️ Слово не найдено: {word}")
        
@dp.message(Command("removeadmin"))
async def cmd_removeadmin(message: Message, command: CommandObject):
    # Проверка: является ли супер-админом или админом чата
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        is_chat_admin = member.status in ("administrator", "creator")
    except:
        is_chat_admin = False

    if username not in SUPER_ADMINS and not is_chat_admin:
        return await message.answer("❗ Только супер-админы или админы чата могут снимать доступ.")

    # Получаем ник, кого удалить
    target_username = None

    if message.reply_to_message:
        user = message.reply_to_message.from_user
        if user.username:
            target_username = f"@{user.username}"
        else:
            return await message.answer("❗ У пользователя нет @username.")
    elif command.args:
        arg = command.args.strip()
        target_username = arg if arg.startswith("@") else f"@{arg}"
    else:
        return await message.answer("❗ Укажите пользователя через @username или пересланное сообщение.")

    if target_username not in ADMIN_USERNAMES:
        return await message.answer(f"ℹ️ {target_username} не в списке админов.")

    ADMIN_USERNAMES.remove(target_username)
    await message.answer(f"✅ {target_username} удалён из списка админов.")
    
@dp.message(Command("offai"))
@only_admin_or_owner
async def cmd_disable_ai(message: Message):
    global AI_ENABLED
    AI_ENABLED = False
    await message.answer("❌ Проверка через AI отключена.")

@dp.message(Command("onai"))
@only_admin_or_owner
async def cmd_enable_ai(message: Message):
    global AI_ENABLED
    AI_ENABLED = True
    await message.answer("✅ Проверка через AI включена.")


        
@dp.message(Command("addadmin"))
@only_admin_or_owner
async def cmd_addadmin(message: Message, command: CommandObject):
    username = None

    # 📌 Если команда вызвана как ответ на сообщение
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        if target.username:
            username = f"@{target.username}"
        else:
            return await message.answer("❗ У пользователя нет @username, не могу добавить.")
    
    # 📌 Если передан @ник в команде
    elif command.args:
        raw_username = command.args.strip()
        if raw_username.startswith("@"):
            username = raw_username
        else:
            username = f"@{raw_username}"
    
    # 🛑 Если ни то, ни другое — ошибка
    else:
        return await message.answer("❗ Укажите пользователя через @username или пересланное сообщение.")

    # 📥 Добавляем в список (если ещё нет)
    if username in ADMIN_USERNAMES:
        return await message.answer(f"ℹ️ {username} уже в списке админов.")
    
    ADMIN_USERNAMES.append(username)
    await message.answer(f"✅ {username} добавлен в список владельцев/админов.")

@dp.message(Command("helpadmin"))
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
        "/установить_правила — установить новые правила для беседы\n",
        parse_mode="HTML"
    )


@dp.message(Command("mute"))
@only_admin_or_owner
async def cmd_mute(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("❗️ Используйте /mute в группе.")

    

    target = None

    # reply
    if message.reply_to_message:
        target = message.reply_to_message.from_user

    # @username
    elif message.text:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            username = args[1].lstrip("@")
            try:
                chat_member = await bot.get_chat_member(message.chat.id, username)
                target = chat_member.user
            except Exception:
                return await message.answer("❗ Не удалось найти пользователя. Возможно, он не писал в чат.")

    if not target:
        return await message.answer("❗ Укажите пользователя ответом или через @username.")

    await bot.restrict_chat_member(
        message.chat.id, target.id,
        permissions=ChatPermissions(can_send_messages=False)
    )
    await message.answer(f"🔇 {target.full_name} замучен.")

    
@dp.message(Command("kick"))
@only_admin_or_owner
async def cmd_kick(message: Message, command: CommandObject):

    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif command.args:
        username = command.args.strip().lstrip("@")
        async for chat_member in bot.get_chat_administrators(message.chat.id):
            if chat_member.user.username and chat_member.user.username.lower() == username.lower():
                target = chat_member.user
                break

    if not target:
        return await message.answer("❗ Укажите пользователя через @username или ответом.")

    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await bot.unban_chat_member(message.chat.id, target.id)  
        await message.answer(f"👢 {target.full_name} был исключён.")
    except Exception as e:
        await message.answer(f"⚠️ Не удалось кикнуть: {e}")


@dp.message(Command("ban"))
@only_admin_or_owner
async def cmd_ban(message: Message, command: CommandObject):

    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif command.args:
        username = command.args.strip().lstrip("@")
        async for chat_member in bot.get_chat_administrators(message.chat.id):
            if chat_member.user.username and chat_member.user.username.lower() == username.lower():
                target = chat_member.user
                break

    if not target:
        return await message.answer("❗ Укажите пользователя через @username или ответом.")

    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🔨 {target.full_name} получил пермач бан.")
    except Exception as e:
        await message.answer(f"⚠️ Не удалось забанить: {e}")


@dp.message(Command("ping"))
@only_admin_or_owner
async def cmd_ping(message: Message):
    await message.answer("Pong! 🤖")
    
    
@dp.message(Command("правила"))
async def cmd_rules(message: Message):
    await message.answer(f"📋 <b>Правила чата:</b>\n\n{load_rules()}", parse_mode="HTML")

@dp.message(Command("установить_правила"))
@only_admin_or_owner
async def cmd_set_rules(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer("❗ Укажите новые правила. Пример:\n/установить_правила 1. Не спамить\n2. Не материться")

    save_rules(command.args)
    await message.answer("✅ Правила обновлены.")


@dp.message(Command("stoplist"))
@only_admin_or_owner
async def cmd_stoplist(message: Message):

    stops = "\n".join(f"- {w}" for w in STOP_WORDS)
    
    try:
        await bot.send_message(
            message.from_user.id,
            f"📋 <b>Список стоп-слов:</b>\n{stops}",
            parse_mode="HTML"
        )
        
        if message.chat.type != ChatType.PRIVATE:
            await message.answer("✅ Отправил список стоп-слов вам в личку.")
    except Exception:
        
        await message.answer(
            "❗ Не удалось отправить ЛС. Пожалуйста, напишите мне в личку /start и попробуйте снова."
        )

@dp.message(Command("warns"))
async def cmd_warns(message: Message):
    warns = await get_warnings(message.from_user.id)
    await message.answer(f"📝 У вас {warns}/3 выговоров.")

@dp.message(Command("clearwarns"))
@only_admin_or_owner
async def cmd_clearwarns(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("Используйте в группе.")
    
    if not message.reply_to_message:
        return await message.answer("Ответьте на сообщение и введите /clearwarns")
    target = message.reply_to_message.from_user
    await reset_warnings(target.id)
    await message.answer(f"✅ Выговоры {target.full_name} очищены.")



@dp.message(Command("unmute"))
@only_admin_or_owner
async def cmd_unmute(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("❗️ Используйте /unmute в группе.")


    target = None


    if message.reply_to_message:
        target = message.reply_to_message.from_user

    
    elif message.text:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            username = args[1].lstrip("@")
            try:
                chat_member = await bot.get_chat_member(message.chat.id, username)
                target = chat_member.user
            except Exception:
                return await message.answer("❗ Не удалось найти пользователя. Возможно, он не писал в чат.")

    if not target:
        return await message.answer("❗ Укажите пользователя ответом или через @username.")

    await bot.restrict_chat_member(
        message.chat.id, target.id,
        permissions=ChatPermissions(can_send_messages=True)
    )
    await message.answer(f"✅ {target.full_name} размучен.")

    

# ─── НОВЫЕ УЧАСТНИКИ ───────────────────────────────────────

# @dp.message(F.new_chat_members)
# async def new_member_handler(message: Message):
#     chat_id = message.chat.id
#     for user in message.new_chat_members:
#         user_id = user.id

       
#         member = await bot.get_chat_member(chat_id, user_id)
#         if member.status in ("administrator", "creator"):
#             continue

        
#         await bot.restrict_chat_member(
#             chat_id, user_id,
#             permissions=ChatPermissions(can_send_messages=False)
#         )

#         keyboard = InlineKeyboardMarkup(inline_keyboard=[
#             [
#                 InlineKeyboardButton(text="👤", callback_data=f"verify_{user_id}"),
#                 InlineKeyboardButton(text="🤖", callback_data=f"robot_{user_id}")
#             ]
#         ])

#         msg = await message.answer(
#             f"Приветствую 👋 {user.full_name}, подтвердите, что вы человек, нажав кнопку ниже в течение 45 секунд.",
#             reply_markup=keyboard
#         )

#         pending_verification[(chat_id, user_id)] = msg.message_id
#         asyncio.create_task(kick_if_not_verified(chat_id, user_id))

        
# async def kick_if_not_verified(chat_id: int, user_id: int):
#     await asyncio.sleep(45)
#     key = (chat_id, user_id)
#     if key in pending_verification:
#         msg_id = pending_verification.pop(key)
#         try:
#             await bot.ban_chat_member(chat_id, user_id)
#             await bot.unban_chat_member(chat_id, user_id)
#             await bot.delete_message(chat_id, msg_id)
#         except:
#             pass


# @dp.callback_query(F.data.startswith("verify_"))
# async def verify_user(callback: CallbackQuery):
#     user_id = int(callback.data.split("_")[1])
#     chat_id = callback.message.chat.id

#     if callback.from_user.id != user_id:
#         return await callback.answer("⛔ Сиди не рыпайся йоу, проверяю не тебя")

    
#     await bot.restrict_chat_member(
#         chat_id, user_id,
#         permissions=ChatPermissions(
#             can_send_messages=True,
#             can_send_media_messages=True,
#             can_send_other_messages=True,
#             can_add_web_page_previews=True
#         )
#     )

#     key = (chat_id, user_id)
#     if key in pending_verification:
#         msg_id = pending_verification.pop(key)
#         await bot.delete_message(chat_id, msg_id)

#     await callback.answer("✅ Вы подтвердили, что вы человек!")


# @dp.callback_query(F.data.startswith("robot_"))
# async def bot_click(callback: CallbackQuery):
#     user_id = int(callback.data.split("_")[1])
#     chat_id = callback.message.chat.id

#     if callback.from_user.id != user_id:
#         return await callback.answer("⛔ Ты не можешь это трогать, не ты на проверке.")

#     await callback.answer("🤖 Вы признались, что бот. Пока!")

#     await asyncio.sleep(5)  

    
#     key = (chat_id, user_id)
#     if key in pending_verification:
#         msg_id = pending_verification.pop(key)
#         try:
#             await bot.delete_message(chat_id, msg_id)
#         except:
#             pass

    
#     try:
#         await bot.ban_chat_member(chat_id, user_id)
#         await bot.unban_chat_member(chat_id, user_id)
#     except:
#         pass


# ─── ОБЩИЙ ФИЛЬТР СТОП-СЛОВ ─────────────────────────────────────────────
@dp.message(F.text, lambda m: not m.text.startswith("/"))
async def filter_and_warn(message: Message):
    # игнорим старые сообщения
    if message.date < BOT_START_TIME:
        return
    text = message.text.strip()
    # 1) Проверка через GPT-4o
    if await is_bad_content(text):
        admins = ADMIN_USERNAMES  # замените на ваш список
        mention = ", ".join(admins)
        await message.reply(
            f"⚠️ Обнаружено нежелательное содержание от {message.from_user.full_name}.\n"
            f"{mention}, пожалуйста, проверьте."
        )
        return

    # 2) Ваша локальная проверка стоп-слов
    if any(w in text for w in STOP_WORDS):
        user_id = message.from_user.id
        warns = await add_warning(user_id)

        admins_text = ", ".join(ADMIN_USERNAMES)
        await bot.send_message(
            message.chat.id,
            f"⚠️ Нарушение от {message.from_user.full_name} (@{message.from_user.username or 'нет ника'})\n"
            f"{admins_text}, посмотрите пожалуйста.",
            reply_to_message_id=message.message_id
        )



    # Когда будет доступ админа можно раскомитить
    # if any(w in text for w in STOP_WORDS):
    #     await message.delete()
    #     user_id = message.from_user.id
    #     warns = await add_warning(user_id)

    #     if warns == 1:
    #         await message.answer(f"⚠️ {message.from_user.full_name}, стоп-слово! 1/3 предупреждений. Мут на 5 минут.")
    #         await bot.restrict_chat_member(
    #             message.chat.id, user_id,
    #             permissions=ChatPermissions(can_send_messages=False),
    #             until_date=types.datetime.datetime.now() + types.timedelta(minutes=5)
    #         )
    #     elif warns == 2:
    #         await message.answer(f"⚠️ {message.from_user.full_name}, снова стоп-слово! 2/3 предупреждений. Мут на 15 минут.")
    #         await bot.restrict_chat_member(
    #             message.chat.id, user_id,
    #             permissions=ChatPermissions(can_send_messages=False),
    #             until_date=types.datetime.datetime.now() + types.timedelta(minutes=15)
    #         )
    #     elif warns >= 3:
    #         member = await bot.get_chat_member(message.chat.id, user_id)
    #         if member.status in ("creator", "administrator"):
    #             return await message.answer("🚫 3/3, но админа/создателя кикнуть нельзя.")
    #         await message.answer(f"🚫 {message.from_user.full_name}, 3/3 — исключаю из чата.")
    #         await bot.ban_chat_member(message.chat.id, user_id)
    #         await reset_warnings(user_id)

# ─── СТАРТ БОТА ─────────────────────────────────────────────────────────
async def main():
    try:
        await init_db()
        logging.basicConfig(level=logging.INFO)

        # middleware, который молчит при паузе
        dp.message.middleware(PauseMiddleware(lambda: PAUSED))

        logging.info("🚀 Бот запущен, БД инициализирована")
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"❌ Бот аварийно остановлен: {e}")
        await bot.send_message(-1002667337596, "⚠️ Ухожу по техническим причинам. Не балуйтесь! Скоро вернусь!")
        raise e


if __name__ == "__main__":
    asyncio.run(main())
