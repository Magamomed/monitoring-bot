import re
import logging
from typing import Iterable, Set
from datetime import timezone
from aiogram import Router, F
from aiogram.types import Message

from config import BOT_START_TIME, ADMIN_USERNAMES, IMMUNE_USERS
from database import add_warning, is_immune_user
from filters.ai_filter import is_bad_content
from filters.stopwords import STOP_WORDS as IMPORTED_STOP_WORDS  # из твоего модуля

log = logging.getLogger("moderation.handler")
router = Router()

# --- нормализация и стоп-слова ---
def normalize(text: str) -> str:
    t = (text or "").casefold()
    t = (t.replace("₽", " руб")
         .replace("р.", " руб")
         .replace("руб.", " руб")
         .replace("₸", " тг")
         .replace("тенге", " тг"))
    # оставляем @ и #, удаляем прочие не-словесные символы
    t = re.sub(r"[^\w@#]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# локальные добавки — не затираем импорт
STATIC_STOP_WORDS = {"заработай легко", "доход без вложений", "работа 18", "пиши @"}

def _to_set(xs: Iterable[int] | int | None) -> Set[int]:
    if xs is None:
        return set()
    if isinstance(xs, int):
        return {xs}
    if isinstance(xs, (list, set, tuple)):
        if len(xs) == 1 and isinstance(xs[0], (list, set, tuple)):
            return set(xs[0])
        return set(xs)
    return set()

# соберём итоговый список стоп-слов (экранируем, чтобы спецсимволы не сломали regex)
_ALL_WORDS = []
for w in list(IMPORTED_STOP_WORDS) + list(STATIC_STOP_WORDS):
    if isinstance(w, str):
        s = w.strip()
        if s:
            _ALL_WORDS.append(re.escape(s))

STOPWORDS_RE = re.compile(r"(?:\b|_)" + r"|".join(_ALL_WORDS) + r"(?:\b|_)", re.IGNORECASE) if _ALL_WORDS else None

# НЕ сохраняем snapshot иммунитета — проверяем актуальный IMMUNE_USERS в рантайме
def is_static_immune(user_id: int) -> bool:
    return user_id in _to_set(IMMUNE_USERS)

# Если понадобится ограничить параллельные запросы к AI — можно тут использовать Semaphore:
# import asyncio
# _AI_SEMAPHORE = asyncio.Semaphore(4)
# and in handler: async with _AI_SEMAPHORE: ai_bad = await is_bad_content(raw_text)

# Правильный фильтр: только текстовые сообщения и НЕ команды (начинающиеся с "/")
@router.message(F.text & ~F.text.startswith("/"))
async def filter_and_warn(message: Message):
    log.info(
        "IN message_id=%s chat_id=%s user=%s(%s) date=%s",
        message.message_id, message.chat.id, message.from_user.full_name, message.from_user.id, message.date
    )

    # приводим message.date к timezone-aware UTC чтобы корректно сравнить с BOT_START_TIME
    msg_date = message.date
    if msg_date is not None and msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=timezone.utc)

    if msg_date is not None and msg_date < BOT_START_TIME:
        log.info("SKIP: old message (msg_date=%s < BOT_START_TIME=%s)", msg_date, BOT_START_TIME)
        return

    # иммунитет: статический (runtime) + БД
    static_immune = is_static_immune(message.from_user.id)
    try:
        db_immune = await is_immune_user(message.from_user.id)
    except Exception as e:
        db_immune = False
        log.exception("is_immune_user failed: %s", e)

    log.info("immune: db=%s static=%s", db_immune, static_immune)
    if static_immune or db_immune:
        log.info("SKIP: immune user id=%s", message.from_user.id)
        return

    raw_text = message.text or ""
    norm_text = normalize(raw_text)
    log.debug("text_raw=%r norm=%r", raw_text, norm_text)

    # стоп-слова (быстрая локальная проверка)
    if STOPWORDS_RE:
        m = STOPWORDS_RE.search(norm_text)
        hit = bool(m)
        log.info("stopwords: enabled=%s hit=%s match=%r", True, hit, (m.group(0) if m else None))
        if hit:
            try:
                total = await add_warning(message.from_user.id)
                log.info("warning added user_id=%s total_warns=%s", message.from_user.id, total)
            except Exception as e:
                log.exception("add_warning failed: %s", e)

            admins_text = ", ".join(ADMIN_USERNAMES)
            try:
                await message.bot.send_message(
                    message.chat.id,
                    (
                        f"⚠️ Нарушение от {message.from_user.full_name} "
                        f"(@{message.from_user.username or 'нет ника'})\n"
                        f"{admins_text}, посмотрите пожалуйста."
                    ),
                    reply_to_message_id=message.message_id
                )
                log.info("ADMIN ALERT sent chat_id=%s msg_id=%s", message.chat.id, message.message_id)
            except Exception as e:
                log.exception("send_message(admin alert) failed: %s", e)
            return
    else:
        log.warning("stopwords: pattern is empty/disabled")

    # ИИ-модерация (весь текст) — аккуратно, асинхронный вызов
    try:
        # Если хочешь ограничить параллелизм, оберни этот вызов в Semaphore (см. комментарий выше).
        ai_bad = await is_bad_content(raw_text)
        log.info("ai_bad=%s", ai_bad)
    except Exception as e:
        ai_bad = False
        log.exception("is_bad_content failed: %s", e)

    if ai_bad:
        mention = ", ".join(ADMIN_USERNAMES)
        try:
            await message.reply(
                f"⚠️ Обнаружено нежелательное содержание от {message.from_user.full_name}.\n"
                f"{mention}, пожалуйста, проверьте."
            )
            log.info("AI ALERT reply sent message_id=%s", message.message_id)
        except Exception as e:
            log.exception("reply(ai alert) failed: %s", e)
        return

    log.info("OK: no violation")

def register_filter_handlers(dp):
    dp.include_router(router)
