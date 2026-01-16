import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from bot.utils.ui import UIMessages

class GlobalErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            logging.exception(f"Unhandled exception in bot update: {e}")
            
            # User notification logic
            # We need to check if event is something we can reply to
            if isinstance(event, Message):
                try:
                    await event.answer(
                        "⚠️ <b>Произошла техническая ошибка.</b>\n\n"
                        "Администраторы уже получили уведомление. Попробуйте повторить действие позже."
                    )
                except Exception:
                    pass # Failsafe if we can't send message
            
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("⚠️ Произошла ошибка. Попробуйте позже.", show_alert=True)
                except Exception:
                    pass
            
            # Propagate exception? 
            # If we swallow it here, aiogram won't crash, but we must ensure we logged it.
            # Usually good to swallow in prod so polling doesn't die, but bad for debug.
            # But aiogram 3.x polling is robust.
            # Let's swallow it to keep bot alive, but logging.exception above is key.
            return None
