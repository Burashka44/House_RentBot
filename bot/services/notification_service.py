import logging
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Tenant, TenantStay, StayStatus

class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify_tenant(self, tg_id: int, text: str):
        """Send notification to tenant by their Telegram ID"""
        try:
            await self.bot.send_message(tg_id, text, parse_mode="HTML")
            logging.info(f"Notification sent to {tg_id}")
        except Exception as e:
            logging.warning(f"Failed to notify tenant {tg_id}: {e}")
            raise

    async def notify_admins(self, admin_ids: list, text: str):
        """Send notification to all admins"""
        for admin_id in admin_ids:
            try:
                await self.bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception as e:
                logging.warning(f"Failed to notify admin {admin_id}: {e}")

    async def send_message(self, chat_id: int, text: str):
        """Generic send message"""
        try:
            await self.bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            logging.warning(f"Failed to send to {chat_id}: {e}")

notification_service = None

def setup_notifications(bot: Bot):
    global notification_service
    notification_service = NotificationService(bot)
