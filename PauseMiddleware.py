from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Awaitable, Dict

class PauseMiddleware(BaseMiddleware):
    def __init__(self, paused_ref: Callable[[], bool]):
        self.paused_ref = paused_ref

    async def __call__(self, handler: Callable[[Message, Dict], Awaitable], message: Message, data: Dict):
        if self.paused_ref() and not message.text.startswith("/resume"):
            return  # просто молчит
        return await handler(message, data)
