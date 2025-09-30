import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from middlewares.pause import PauseMiddleware
from config import BOT_TOKEN, PAUSED, LOG_CHAT_ID
from handlers.admin import register_admin_handlers
from handlers.user import register_user_handlers
from handlers.filters import STOPWORDS_RE, normalize, register_filter_handlers
from database import init_db
from filters.ai_filter import is_bad_content

# async def _smoke_tests():
#     samples = [
#         "Заработай легко 7500₽ в день! Пиши @karina_mladcha",
#         "Работа 18+ без вложений",
#         "Привет! Мемчик видел? 😂",
#     ]
#     for s in samples:
#         norm = normalize(s)
#         sw = bool(STOPWORDS_RE.search(norm))
#         ai = await is_bad_content(s)
#         print(f"[TEST] raw={s!r} stop={sw} ai={ai}")


def setup_logging():
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    logging.basicConfig(
        level=logging.INFO,  # на время диагностики можно INFO, потом WARNING
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # шумные логгеры aiogram можно притушить при необходимости:
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    # наши:
    logging.getLogger("moderation.handler").setLevel(logging.INFO)
    logging.getLogger("moderation.ai").setLevel(logging.DEBUG)  # хотим видеть тело ответа/запроса



async def main():
    # await _smoke_tests()  # убрать, когда всё ок
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # middleware, который молчит при паузе
    dp.message.middleware(PauseMiddleware(lambda: PAUSED[0]))

    # Регистрация хендлеров
    register_admin_handlers(dp)
    register_user_handlers(dp)
    register_filter_handlers(dp)

    # Инициализация БД
    await init_db()

    logging.info("🚀 Бот запущен, БД инициализирована")
    
  
    updates = await bot.get_updates(offset=None)
    if updates:
        last_update_id = updates[-1].update_id
        await bot.get_updates(offset=last_update_id + 1) 
        

    try:
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logging.error(f"❌ Бот аварийно остановлен: {e}")
        if LOG_CHAT_ID is not None:
            try:
                await bot.send_message(LOG_CHAT_ID, "⚠️ Ухожу по техническим причинам. Не балуйтесь! Скоро вернусь!")
            except Exception:
                pass
        raise e


if __name__ == "__main__":
    asyncio.run(main())
