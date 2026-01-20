from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.tenant_service import get_tenant_by_tg_id
from bot.database.models import Tenant

class ConsentMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:
        
        # Get the user from the event (Message or CallbackQuery)
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        
        # Skip consent check for owners and admins
        from bot.config import config
        if user.id in config.OWNER_IDS or user.id in config.ADMIN_IDS:
            return await handler(event, data)
        
        # Ensure session exists (injected by DbSessionMiddleware)
        session: AsyncSession = data.get("session")
        if not session:
            # Fallback (should not happen if configured correctly)
            return await handler(event, data)
            
        # Inspect tenant status
        try:
            tenant = await get_tenant_by_tg_id(session, user.id)
            data["tenant"] = tenant # Inject tenant into handler
            
            # If tenant exists, check consent
            if tenant:
                if not tenant.personal_data_consent:
                    # If this is the callback for accepting consent, let it pass
                    if event.callback_query and event.callback_query.data == "accept_consent":
                        return await handler(event, data)
                    
                    # Otherwise, block and show consent message
                    if event.message:
                        await self.send_consent_request(event.message)
                        return # Stop processing
                    if event.callback_query:
                        await event.callback_query.answer("Требуется согласие на обработку данных.", show_alert=True)
                        return
                        
        except Exception:
            # Let ErrorMiddleware handle DB errors
            raise

        return await handler(event, data)

    async def send_consent_request(self, message: Message):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        text = (
            "Для использования сервиса требуется ваше согласие\n"
            "на обработку персональных данных.\n\n"
            "Мы храним только следующие данные:\n\n"
            "• ваше ФИО\n"
            "• паспортные данные\n"
            "• ваши фотографии (в том числе чеки и вложения)\n"
            "• номер телефона\n"
            "• электронную почту\n"
            "• Telegram ID\n"
            "• данные об оплатах и начислениях\n\n"
            "Эти данные вы уже предоставили при заключении договора.\n"
            "Используются строго только для работы сервиса."
        )
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="☑ Я согласен на обработку перечисленных данных", callback_data="accept_consent")]
        ])
        
        await message.answer(text, reply_markup=kb)
