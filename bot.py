import asyncio
import logging
import random
import os
import re

from dotenv import load_dotenv
import aiosqlite

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command , CommandObject
from aiogram.enums import ChatType
from aiogram.types import ChatPermissions, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from PauseMiddleware import PauseMiddleware
from datetime import datetime, timezone

# ─── ЗАГРУЗКА ТОКЕНА ─────────────────────────────────────────────────────
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в окружении")

bot = Bot(token=API_TOKEN)
dp  = Dispatcher()

BOT_START_TIME = datetime.now(timezone.utc)



# ─── ПАРАМЕТРЫ ───────────────────────────────────────────────────────────
DB_PATH = 'warnings.db'
STOPWORDS_PATH = 'stopwords.txt'
PAUSED = False

RULES_PATH = 'rules.txt'

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
async def cmd_pause(message: Message):
    global PAUSED
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("❗ Только админ может приостановить бота.")
    
    PAUSED = True
    await message.answer("🤖 Бот ушёл перекусить. Не шалите тут без меня!")

@dp.message(Command("resume"))
async def cmd_resume(message: Message):
    global PAUSED
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("❗ Только админ может вернуть бота.")

    PAUSED = False
    await message.answer("✅ Я снова в деле! Порядок в чате под контролем.")


@dp.message(Command("getid"))
async def cmd_getid(message: Message):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("❗ Только админ может использовать эту команду.")
    
    await message.answer(f"🆔 Chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")


@dp.message(Command("addword"))
async def add_word(message: Message, command: CommandObject):
    if message.chat.type != ChatType.PRIVATE:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.answer("❗ Только админ может добавлять слова.")
    word = command.args.strip().lower()
    if not word:
        return await message.answer("❗ Укажите слово. Пример: /addword spam")
    STOP_WORDS.append(word)
    save_stopwords(STOP_WORDS)
    await message.answer(f"✅ Добавлено слово: {word}")


@dp.message(Command("removeword"))
async def remove_word(message: Message, command: CommandObject):
    if message.chat.type != ChatType.PRIVATE:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.answer("❗ Только админ может удалять слова.")
    word = command.args.strip().lower()
    if not word:
        return await message.answer("❗ Укажите слово. Пример: /removeword spam")
    if word in STOP_WORDS:
        STOP_WORDS.remove(word)
        save_stopwords(STOP_WORDS)
        await message.answer(f"❌ Удалено слово: {word}")
    else:
        await message.answer(f"⚠️ Слово не найдено: {word}")
      
        
@dp.message(Command("helpadmin"))
async def cmd_helpadmin(message: Message):
    
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("❗️ Команда /helpadmin только в группе.")
    
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("⚠️ Только админы могут видеть список админ-команд.")
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
async def cmd_mute(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("❗️ Используйте /mute в группе.")

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("⚠️ Только админы могут мутить пользователей.")

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
async def cmd_kick(message: Message, command: CommandObject):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("❗ Только админ может кикать.")

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
async def cmd_ban(message: Message, command: CommandObject):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("❗ Только админ может банить.")

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
async def cmd_ping(message: Message):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("❗ Только админ может использовать эту команду.")
    
    await message.answer("Pong! 🤖")
    
    
@dp.message(Command("правила"))
async def cmd_rules(message: Message):
    await message.answer(f"📋 <b>Правила чата:</b>\n\n{load_rules()}", parse_mode="HTML")

@dp.message(Command("установить_правила"))
async def cmd_set_rules(message: Message, command: CommandObject):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("❗ Только админ может менять правила.")

    if not command.args:
        return await message.answer("❗ Укажите новые правила. Пример:\n/установить_правила 1. Не спамить\n2. Не материться")

    save_rules(command.args)
    await message.answer("✅ Правила обновлены.")


@dp.message(Command("stoplist"))
async def cmd_stoplist(message: Message):
    
    if message.chat.type != ChatType.PRIVATE:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            return await message.answer("⚠️ Только админы могут просматривать список стоп-слов.")

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
async def cmd_clearwarns(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("Используйте в группе.")
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("Только админы.")
    if not message.reply_to_message:
        return await message.answer("Ответьте на сообщение и введите /clearwarns")
    target = message.reply_to_message.from_user
    await reset_warnings(target.id)
    await message.answer(f"✅ Выговоры {target.full_name} очищены.")



@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.answer("❗️ Используйте /unmute в группе.")

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("⚠️ Только админы.")

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

@dp.message(F.new_chat_members)
async def new_member_handler(message: Message):
    chat_id = message.chat.id
    for user in message.new_chat_members:
        user_id = user.id

       
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ("administrator", "creator"):
            continue

        
        await bot.restrict_chat_member(
            chat_id, user_id,
            permissions=ChatPermissions(can_send_messages=False)
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👤", callback_data=f"verify_{user_id}"),
                InlineKeyboardButton(text="🤖", callback_data=f"robot_{user_id}")
            ]
        ])

        msg = await message.answer(
            f"Приветствую 👋 {user.full_name}, подтвердите, что вы человек, нажав кнопку ниже в течение 45 секунд.",
            reply_markup=keyboard
        )

        pending_verification[(chat_id, user_id)] = msg.message_id
        asyncio.create_task(kick_if_not_verified(chat_id, user_id))

        
async def kick_if_not_verified(chat_id: int, user_id: int):
    await asyncio.sleep(45)
    key = (chat_id, user_id)
    if key in pending_verification:
        msg_id = pending_verification.pop(key)
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            await bot.delete_message(chat_id, msg_id)
        except:
            pass


@dp.callback_query(F.data.startswith("verify_"))
async def verify_user(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    chat_id = callback.message.chat.id

    if callback.from_user.id != user_id:
        return await callback.answer("⛔ Сиди не рыпайся йоу, проверяю не тебя")

    # Снимаем ограничение
    await bot.restrict_chat_member(
        chat_id, user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
    )

    key = (chat_id, user_id)
    if key in pending_verification:
        msg_id = pending_verification.pop(key)
        await bot.delete_message(chat_id, msg_id)

    await callback.answer("✅ Вы подтвердили, что вы человек!")


@dp.callback_query(F.data.startswith("robot_"))
async def bot_click(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    chat_id = callback.message.chat.id

    if callback.from_user.id != user_id:
        return await callback.answer("⛔ Ты не можешь это трогать, не ты на проверке.")

    await callback.answer("🤖 Вы признались, что бот. Пока!")

    await asyncio.sleep(5)  # Даём увидеть сообщение

    # Удалим сообщение
    key = (chat_id, user_id)
    if key in pending_verification:
        msg_id = pending_verification.pop(key)
        try:
            await bot.delete_message(chat_id, msg_id)
        except:
            pass

    # Кик без бана
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
    except:
        pass


# ─── ОБЩИЙ ФИЛЬТР СТОП-СЛОВ ─────────────────────────────────────────────
@dp.message(F.text, lambda m: not m.text.startswith("/"))
async def filter_and_warn(message: Message):
    
    if message.date < BOT_START_TIME:
        return 
    
    text = message.text.lower()
    if any(w in text for w in STOP_WORDS):
        await message.delete()
        user_id = message.from_user.id
        warns = await add_warning(user_id)

        if warns == 1:
            await message.answer(f"⚠️ {message.from_user.full_name}, стоп-слово! 1/3 предупреждений. Мут на 5 минут.")
            await bot.restrict_chat_member(
                message.chat.id, user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=types.datetime.datetime.now() + types.timedelta(minutes=5)
            )
        elif warns == 2:
            await message.answer(f"⚠️ {message.from_user.full_name}, снова стоп-слово! 2/3 предупреждений. Мут на 15 минут.")
            await bot.restrict_chat_member(
                message.chat.id, user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=types.datetime.datetime.now() + types.timedelta(minutes=15)
            )
        elif warns >= 3:
            member = await bot.get_chat_member(message.chat.id, user_id)
            if member.status in ("creator", "administrator"):
                return await message.answer("🚫 3/3, но админа/создателя кикнуть нельзя.")
            await message.answer(f"🚫 {message.from_user.full_name}, 3/3 — исключаю из чата.")
            await bot.ban_chat_member(message.chat.id, user_id)
            await reset_warnings(user_id)

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
