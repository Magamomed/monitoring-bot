from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import Message

class PauseMiddleware(BaseMiddleware):
    """
    Если функция paused() возвращает True, любые входящие сообщения игнорируются (кроме команд с декоратором).
    """
    def __init__(self, paused: Callable[[], bool]):
        super().__init__()
        self._paused = paused

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        message: Message,
        data: dict[str, Any]
    ) -> Any:
        # Команды админов всё равно обрабатываются — это на уровне декораторов в хендлерах
        if message.text and message.text.startswith("/"):
            return await handler(message, data)
        if self._paused():
            # молча игнорируем
            return
        return await handler(message, data)
