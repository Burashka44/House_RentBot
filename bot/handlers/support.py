from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Role, StayStatus
from bot.services.support_service import create_support_message
from bot.services.notification_service import notification_service
from bot.handlers.admin import AdminFilter

router = Router()

from bot.states import SupportState

# --- Tenant Side ---
@router.message(Command("message"))
async def tenant_message_start(message: Message, state: FSMContext, tenant):
    await message.answer("Напишите ваше сообщение для администратора (или отправьте фото):")
    await state.set_state(SupportState.waiting_for_message)

@router.message(SupportState.waiting_for_message)
async def tenant_message_process(message: Message, state: FSMContext, tenant, session: AsyncSession):
    from bot.config import config
    
    # Check if we have a pre-uploaded photo from "smart handler" in state
    data = await state.get_data()
    temp_file_id = data.get("temp_file_id")
    # If user sent a NEW photo now, use it
    if message.photo:
         temp_file_id = message.photo[-1].file_id

    # Text content
    msg_text = message.text or message.caption or "[Без текста]"
    
    # Load stay with rental_object for address access
    from bot.database.models import TenantStay
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    stmt = select(TenantStay).where(
        TenantStay.tenant_id == tenant.id,
        TenantStay.status == StayStatus.active.value
    ).options(selectinload(TenantStay.rental_object))
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if not stay:
        await message.answer("Ошибка: нет active проживания.")
        await state.clear()
        return
    
    # Address info
    address = stay.rental_object.address if stay.rental_object else "Неизвестно"

    # Prepare text for admin
    admin_text = f"📩 <b>Сообщение от жильца</b>\n"
    admin_text += f"👤 <b>{tenant.full_name}</b>\n"
    admin_text += f"🏠 {address}\n\n"
    admin_text += f"💬 {msg_text}"
    
    # Save to DB (History)
    await create_support_message(session, stay.id, Role.tenant, msg_text)
    
    # Notify Admins
    targets = set(config.OWNER_IDS + config.ADMIN_IDS)
    for admin_id in targets:
        try:
            if temp_file_id:
                    await message.bot.send_photo(admin_id, photo=temp_file_id, caption=admin_text)
            else:
                    await message.bot.send_message(admin_id, admin_text)
        except Exception:
            pass 
    
    await message.answer("✅ Сообщение отправлено администратору!")
    await state.clear()


# --- Admin Side (Reply) ---
# Simple Reply Logic: Admin selects user from list (TODO) or replies to forwarded msg?
# For MVP: Admin command /reply <stay_id> <text>
@router.message(Command("reply"), AdminFilter())
async def admin_reply_command(message: Message, session: AsyncSession):
    from bot.database.models import TenantStay
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /reply <stay_id> <text>")
        return
        
    try:
        stay_id = int(args[1])
    except ValueError:
        await message.answer("❌ stay_id должен быть числом")
        return
    
    text = args[2]
    admin_name = message.from_user.full_name
    
    # Save to DB
    await create_support_message(session, stay_id, Role.admin, text)
    
    # Get tenant info to send notification
    stmt = (
        select(TenantStay)
        .where(TenantStay.id == stay_id)
        .options(selectinload(TenantStay.tenant))
    )
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if stay and stay.tenant and stay.tenant.tg_id:
        tg_id = stay.tenant.tg_id
        
        # Send notification to tenant
        try:
            tenant_text = f"📩 <b>Ответ от администратора</b>\n"
            tenant_text += f"👤 {admin_name}\n\n"
            tenant_text += f"💬 {text}"
            
            await message.bot.send_message(tg_id, tenant_text)
            await message.answer(f"✅ Ответ доставлен жильцу (stay #{stay_id})")
        except Exception as e:
            await message.answer(f"⚠️ Сохранено в историю, но не удалось доставить: {e}")
    else:
        await message.answer(f"⚠️ Телеграм жильца не найден. Ответ сохранен в историю (stay #{stay_id})")
