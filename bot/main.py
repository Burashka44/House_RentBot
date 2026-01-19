import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.config import config
from bot.handlers import common, admin, tenant, support #, admin_rso
from bot.middlewares.consent import ConsentMiddleware

from bot.services.notification_service import setup_notifications
from bot.cron import scheduler_loop



async def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout,
    )

    bot = Bot(
        token=config.BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Setup Services
    setup_notifications(bot)

    # Middleware registration
    # Order: Outer -> Inner
    # 1. Error Handler (wraps everything)
    # 2. Rate Limiting (prevents spam)
    # 3. DB Session (provides session)
    # 4. Consent (uses session)
    from bot.middlewares.db import DbSessionMiddleware
    from bot.middlewares.consent import ConsentMiddleware
    from bot.middlewares.error import GlobalErrorMiddleware
    from bot.middlewares.rate_limit import RateLimitMiddleware, FileUploadRateLimiter
    
    # Order matters: Error -> RateLimit -> DB -> Consent
    dp.update.outer_middleware(GlobalErrorMiddleware())
    dp.update.middleware(RateLimitMiddleware(rate=10, per=60))  # 10 req/min
    dp.message.middleware(FileUploadRateLimiter(rate=3, per=60))  # 3 files/min
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(ConsentMiddleware())

    # Router registration - ORDER MATTERS!
    # Admin first - AdminFilter passes admins to admin handlers
    # Non-admins skip admin router and go to common/tenant
    # dp.include_router(admin_rso.router) # Disabled to use admin.py RSO handlers
    dp.include_router(admin.router)
    dp.include_router(common.router)
    dp.include_router(tenant.router)
    dp.include_router(support.router)

    # Load admins from DB
    from bot.database.core import AsyncSessionLocal
    from bot.services.user_service import reload_admin_cache
    
    try:
        async with AsyncSessionLocal() as session:
            count = await reload_admin_cache(session)
            logging.info(f"Loaded {count} admins from DB.")
    except Exception as e:
        logging.error(f"Failed to load admins from DB: {e}")

    # Start Scheduler
    asyncio.create_task(scheduler_loop())

    logging.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
