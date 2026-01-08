import asyncio
import logging
from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from bot.database.core import AsyncSessionLocal
from bot.database.models import TenantStay, StayStatus, CommCharge, ChargeStatus, ObjectSettings, CommProvider, TenantSettings, Tenant
from bot.utils.ui import format_date
from bot.services.billing_service import ensure_rent_charge
from bot.services.notification_service import notification_service

async def check_utility_aggregation(session, stay: TenantStay) -> tuple[bool, int, int]:
    """
    Check if utility charges are ready for notification.
    Returns: (is_ready, collected_count, total_providers)
    """
    # Get object settings
    settings_stmt = select(ObjectSettings).where(ObjectSettings.object_id == stay.object_id)
    settings_result = await session.execute(settings_stmt)
    settings = settings_result.scalar_one_or_none()
    
    min_ratio = settings.min_ready_ratio if settings else 0.7
    
    # Count expected providers for this object
    providers_stmt = select(func.count(CommProvider.id)).where(
        CommProvider.object_id == stay.object_id,
        CommProvider.active == True
    )
    providers_result = await session.execute(providers_stmt)
    total_providers = providers_result.scalar() or 0
    
    if total_providers == 0:
        return False, 0, 0
    
    # Count pending comm charges for current month
    current_month = date.today().replace(day=1)
    charges_stmt = select(func.count(CommCharge.id)).where(
        CommCharge.stay_id == stay.id,
        CommCharge.month == current_month,
        CommCharge.status == ChargeStatus.pending.value
    )
    charges_result = await session.execute(charges_stmt)
    collected_count = charges_result.scalar() or 0
    
    ratio = collected_count / total_providers if total_providers > 0 else 0
    is_ready = ratio >= min_ratio
    
    return is_ready, collected_count, total_providers

async def daily_billing_job():
    logging.info("Running daily billing job...")
    
    async with AsyncSessionLocal() as session:
        # Fetch active stays with tenant and settings
        stmt = (
            select(TenantStay)
            .where(TenantStay.status == StayStatus.active.value)
            .options(
                selectinload(TenantStay.tenant)
                .selectinload(Tenant.settings)
            )
        )
        result = await session.execute(stmt)
        stays = result.scalars().all()
        
        today = date.today()
        
        for stay in stays:
            try:
                # 1. Rent Logic - Create charge for current month
                # Always ensure charge exists for the current calendar month
                current_month = today.replace(day=1)
                await ensure_rent_charge(session, stay, current_month)
                
                # Get Settings
                settings = stay.tenant.settings if stay.tenant else None
                remind_days = settings.reminder_days if settings else 3
                rent_notif = settings.rent_notifications if settings else True
                comm_notif = settings.comm_notifications if settings else True
                
                # 2. Rent Reminders
                if rent_notif:
                    # Find next rent date
                    try:
                        # Target day in THIS month
                        target_date = today.replace(day=stay.rent_day)
                    except ValueError:
                        target_date = today # Fallback
                    
                    # If target date passed, look at next month
                    if target_date < today:
                        target_date = (target_date.replace(day=1) + timedelta(days=32)).replace(day=stay.rent_day)
                    
                    # Check notification date
                    notif_date = target_date - timedelta(days=remind_days)
                    
                    if today == notif_date:
                        try:
                            await notification_service.notify_tenant(
                                stay.tenant.tg_id,
                                f"⏰ <b>Напоминание об оплате аренды</b>\n"
                                f"📅 Дата: {format_date(target_date)}\n"
                                f"💰 Сумма: {stay.rent_amount} руб."
                            )
                        except Exception as e:
                            logging.warning(f"Failed to notify tenant {stay.tenant.tg_id}: {e}")
                
                # 3. Comm Aggregation Logic
                if comm_notif:
                    # Same date logic for utilities
                    try:
                        target_comm = today.replace(day=stay.comm_day)
                    except ValueError:
                        target_comm = today
                    
                    if target_comm < today:
                        target_comm = (target_comm.replace(day=1) + timedelta(days=32)).replace(day=stay.comm_day)
                    
                    check_date = target_comm - timedelta(days=remind_days)
                    
                    if today == check_date:
                        is_ready, collected, total = await check_utility_aggregation(session, stay)
                        if is_ready and collected > 0:
                            try:
                                await notification_service.notify_tenant(
                                    stay.tenant.tg_id,
                                    f"📊 <b>Коммунальные платежи готовы</b>\n"
                                    f"✅ Сдано: {collected} из {total} услуг\n"
                                    f"📅 Оплатить до: {format_date(target_comm)}"
                                )
                            except Exception as e:
                                logging.warning(f"Failed to notify tenant {stay.tenant.tg_id}: {e}")
                
                # 4. Meter Reading Reminder (Fixed on 20th of month for now)
                # TODO: Make configurable via TenantSettings
                if today.day == 20 and comm_notif:
                     # Check if object has metered services (Water, Electric, Heating)
                     # We use a simple query or helper. For now, assume if any providers exist, we remind.
                     # Or better: check service types.
                     
                     metered_types = ["water", "electric", "heating"]
                     # We can query CommProvider joined with ObjectRSOLink (or UKRSOLink via House)
                     # But stay.rental_object.comm_providers might be lazily loaded or not available if not joined.
                     # 'stays' query in line 56 uses selectinload(TenantStay.tenant).
                     # We need to load providers or query them.
                     
                     # Sub-query to check for metered providers for this object
                     metered_stmt = select(CommProvider).join(ObjectRSOLink).where(
                         ObjectRSOLink.object_id == stay.object_id,
                         CommProvider.service_type.in_(metered_types),
                         CommProvider.active == True
                     )
                     metered_result = await session.execute(metered_stmt)
                     has_metered = metered_result.first() is not None
                     
                     if has_metered:
                         try:
                             await notification_service.notify_tenant(
                                 stay.tenant.tg_id,
                                 f"📝 <b>Пора сдать показания счетчиков!</b>\n"
                                 f"Сегодня 20-е число. Не забудьте передать показания за воду и электричество управляющей компании или через приложения РСО."
                             )
                         except Exception as e:
                             logging.warning(f"Failed to notify tenant {stay.tenant.tg_id} about readings: {e}")

                # Commit updates for this stay (if any)
                await session.commit()
                
            except Exception as e:
                logging.error(f"Error processing billing for stay {stay.id}: {e}")
                await session.rollback()
            
    logging.info("Daily billing job finished.")

async def scheduler_loop():
    """Run job once a day at 09:00 AM."""
    from datetime import datetime
    
    logging.info("Scheduler started.")
    
    # Initial delay to settle startup
    await asyncio.sleep(10)
    
    while True:
        try:
            now = datetime.now()
            target_hour = 9
            target_minute = 0
            
            today_target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            
            if now < today_target:
                next_run = today_target
            else:
                next_run = today_target + timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            
            logging.info(f"Next scheduler job at {next_run} (in {wait_seconds/3600:.1f}h)")
            
            await asyncio.sleep(wait_seconds)
            
            # Run Job
            await daily_billing_job()
            
            # Buffer to skip current minute
            await asyncio.sleep(60)
            
        except Exception as e:
            logging.error(f"Error in scheduler loop: {e}")
            await asyncio.sleep(60) # Prevent tight loop on error 
