from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.core import AsyncSessionLocal

class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                # Auto-commit if no exception occurred
                # Warning: If handler returns explicitly but logic failed logic-wise, we still commit.
                # Business logic must raise exceptions to trigger rollback.
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
