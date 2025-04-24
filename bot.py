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
from aiogram.types import ChatPermissions, Message

# ─── ЗАГРУЗКА ТОКЕНА ─────────────────────────────────────────────────────
load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в окружении")

bot = Bot(token=API_TOKEN)
dp  = Dispatcher()

# ─── ПАРАМЕТРЫ ───────────────────────────────────────────────────────────
STOP_WORDS = [
    'заработок', 'подробности в лс', 'гандон', 'работа мечты',
    'быстрый доход', 'порно', 'гей', 'в лс', 'пишите +в л.с', 'пизда', 
    'пизду', 'иди нахуй', 'нахуй', 'сука', 'пидарас', 'еблан', 'Нюхать пизду', 'ебалан',
]
DB_PATH = 'warnings.db'
STOPWORDS_PATH = 'stopwords.txt'

# ─── СТОРЕДЖИ ДЛЯ КАПЧ ───────────────────────────────────────────────────
# pending_captcha[(chat_id,user_id)] = (answer:int, kind:str)
# kind: "join" или "test"
pending_captcha: dict[tuple[int,int], tuple[int,str]] = {}
# Когда истёк mute, следующая попытка требует капчи снова
require_captcha_after_mute: set[tuple[int,int]] = set()

# ─── ПАРСЕЛЬ ДЛЯ ОГРАНИЧЕНИЙ ─────────────────────────────────────────────
async def schedule_restrict_for_failed_captcha(chat_id: int, user_id: int):
    # Дать 60 сек на ответ, иначе мьют на 5 мин
    await asyncio.sleep(60)
    key = (chat_id, user_id)
    if key in pending_captcha and pending_captcha[key][1] == "join":
        pending_captcha.pop(key, None)
        # проверим, не админ ли
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status not in ("creator", "administrator"):
            # мутим на 5 минут
            await bot.restrict_chat_member(
                chat_id, user_id,
                permissions=ChatPermissions(can_send_messages=False)
            )
            # после 5 мин размьют и поставят флаг на капчу
            asyncio.create_task(schedule_auto_unmute_and_flag(chat_id, user_id))

async def schedule_auto_unmute_and_flag(chat_id: int, user_id: int):
    await asyncio.sleep(300)  # 5 минут
    # размьючиваем
    await bot.restrict_chat_member(
        chat_id, user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
    )
    # на следующую попытку писать требуем капчу
    require_captcha_after_mute.add((chat_id, user_id))
    await bot.send_message(
        chat_id,
        f"<a href=\"tg://user?id={user_id}\">{user_id}</a>, прежде чем писать, решите капчу!",
        parse_mode="HTML"
    )
    
    
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
@dp.message(Command("addword"))
async def add_word(message: Message, command: CommandObject):
    if message.chat.type != ChatType.PRIVATE:
        return
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return
    word = command.args.strip().lower()
    STOP_WORDS.append(word)
    save_stopwords(STOP_WORDS)
    await message.answer(f"✅ Добавлено слово: {word}")

@dp.message(Command("removeword"))
async def remove_word(message: Message, command: CommandObject):
    if message.chat.type != ChatType.PRIVATE:
        return
    word = command.args.strip().lower()
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
        "/testcaptcha — запустить тест-капчу для любого\n"
        "/stoplist — показать стоп-слова\n"
        "/ping — проверить, что бот жив\n",
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
    args = message.text.split(maxsplit=1)

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(args) > 1:
        username = args[1].lstrip("@")
        try:
            chat_member = await bot.get_chat_member(message.chat.id, username)
            target = chat_member.user
        except Exception:
            return await message.answer("❗ Не удалось найти пользователя по нику.")

    if not target:
        return await message.answer("❗ Укажите пользователя через @username или ответом.")

    await bot.restrict_chat_member(
        message.chat.id, target.id,
        permissions=ChatPermissions(can_send_messages=False)
    )
    await message.answer(f"🔇 {target.full_name} замучен.")
    
@dp.message(Command("kick"))
async def cmd_kick(message: Message, command: CommandObject):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in ("administrator", "creator"):
        return await message.answer("Только админ.")
    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif command.args:
        username = command.args.strip().lstrip("@")
        async for u in bot.get_chat_members(message.chat.id):
            if u.user.username == username:
                target = u.user
                break
    if target:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"🚫 {target.full_name} был исключён.")
    
@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("Pong! 🤖")

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
    args = message.text.split(maxsplit=1)

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(args) > 1:
        username = args[1].lstrip("@")
        try:
            chat_member = await bot.get_chat_member(message.chat.id, username)
            target = chat_member.user
        except Exception:
            return await message.answer("❗ Не удалось найти пользователя по нику.")

    if not target:
        return await message.answer("❗ Укажите пользователя через @username или ответом.")

    await bot.restrict_chat_member(
        message.chat.id, target.id,
        permissions=ChatPermissions(can_send_messages=True)
    )
    await message.answer(f"✅ {target.full_name} размучен.")
    
@dp.message(Command("testcaptcha"))
async def cmd_testcaptcha(message: Message):
    chat_id, user_id = message.chat.id, message.from_user.id
    a, b = random.randint(1,9), random.randint(1,9)
    pending_captcha[(chat_id, user_id)] = (a + b, "test")
    await message.answer(f"🧮 Тест-капча: сколько будет {a} + {b}? (60 сек.)")
    asyncio.create_task(schedule_restrict_for_failed_captcha(chat_id, user_id))

# ─── НОВЫЕ УЧАСТНИКИ → СРАЗУ КАПЧА ───────────────────────────────────────
@dp.message(F.new_chat_members)
async def new_member_handler(message: types.Message):
    chat_id = message.chat.id
    for user in message.new_chat_members:
        chat_id, user_id = message.chat.id, user.id
        a, b = random.randint(1,9), random.randint(1,9)
        pending_captcha[(chat_id, user_id)] = (a + b, "join")
        await message.answer(f"🛡️ {user.full_name}, решите {a} + {b} = ? (60 сек.)")
        asyncio.create_task(schedule_restrict_for_failed_captcha(chat_id, user_id))

# ─── ПЕРВАЯ ПОПЫТКА ПОСЛЕ МУТА → КАПЧА ─────────────────────────────────
@dp.message(lambda m: (m.chat.id, m.from_user.id) in require_captcha_after_mute)
async def on_first_after_unmute(message: Message):
    key = (message.chat.id, message.from_user.id)
    require_captcha_after_mute.discard(key)
    await message.delete()
    a, b = random.randint(1,9), random.randint(1,9)
    pending_captcha[key] = (a + b, "join")
    await message.answer(f"🛡️ {message.from_user.full_name}, решите {a} + {b} = ? (60 сек.)")
    asyncio.create_task(schedule_restrict_for_failed_captcha(message.chat.id, message.from_user.id))

# ─── ОТЛОВ ОТВЕТОВ НА КАПЧУ ─────────────────────────────────────────────
@dp.message(lambda m: (m.chat.id, m.from_user.id) in pending_captcha)
async def catch_captcha_answer(message: Message):
    key = (message.chat.id, message.from_user.id)
    answer, kind = pending_captcha.pop(key)
    nums = re.findall(r"\d+", message.text or "")
    given = int(nums[0]) if nums else None

    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status in ("creator", "administrator"):
        return await message.answer("✅ Админ, проверка не нужна.")

    if given == answer:
        # если это initial join или first-after-mute, просто снимаем мут
        await bot.restrict_chat_member(
            message.chat.id, message.from_user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await message.answer("✅ Капча пройдена, можете писать.")
    else:
        # ответ неверный → мут на 5 мин и флаг на капчу
        await message.answer("❌ Неверный ответ, мут на 5 мин.")
        await bot.restrict_chat_member(
            message.chat.id, message.from_user.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        asyncio.create_task(schedule_auto_unmute_and_flag(message.chat.id, message.from_user.id))

# ─── ОБЩИЙ ФИЛЬТР СТОП-СЛОВ ─────────────────────────────────────────────
@dp.message(F.text, lambda m: not m.text.startswith("/"))
async def filter_and_warn(message: Message):
    text = message.text.lower()
    if any(w in text for w in STOP_WORDS):
        await message.delete()
        user_id = message.from_user.id
        warns = await add_warning(user_id)

        if warns < 3:
            return await message.answer(f"⚠️ {message.from_user.full_name}, стоп-слова — {warns}/3 выговоров.")
        member = await bot.get_chat_member(message.chat.id, user_id)
        if member.status in ("creator", "administrator"):
            return await message.answer("🚫 Три выговора, но админа/владельца исключить нельзя.")
        await message.answer(f"🚫 {message.from_user.full_name}, 3/3 — исключаю.")
        await bot.ban_chat_member(message.chat.id, user_id)
        await reset_warnings(user_id)

# ─── СТАРТ БОТА ─────────────────────────────────────────────────────────
async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    logging.info("🚀 Бот запущен, БД инициализирована")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
