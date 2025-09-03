import asyncio
import logging

from aiogram import Bot, Dispatcher
from middlewares.pause import PauseMiddleware
from config import BOT_TOKEN, PAUSED, LOG_CHAT_ID
from handlers.admin import register_admin_handlers
from handlers.user import register_user_handlers
from handlers.filters import register_filter_handlers
from database import init_db


async def main():
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
    try:
        await dp.start_polling(bot)
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
