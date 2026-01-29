from aiogram import Router, F
from aiogram.types import Message, ContentType, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.states import ReceiptState, SupportState
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.billing_service import parse_receipt, validate_receipt_logic, create_payment_from_receipt
from bot.services.tenant_service import get_or_create_tenant
from bot.services.stay_service import create_stay # Only for admin, but maybe we need read access
from bot.database.models import TenantStay, StayStatus, ReceiptDecision, PaymentType
from sqlalchemy import select

router = Router()

async def get_active_stay(session, tenant_id):
    stmt = select(TenantStay).where(
        TenantStay.tenant_id == tenant_id,
        TenantStay.status == StayStatus.active.value
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@router.message(Command("status"))
async def status_command(message: Message, tenant, session: AsyncSession):
    """Show tenant's payment status - quick overview"""
    from bot.utils.ui import UIEmojis, UIMessages, format_amount, format_date
    from bot.database.models import RentCharge, CommCharge, ChargeStatus
    from sqlalchemy import select, func
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from sqlalchemy.orm import selectinload
    
    # Need to load rental_object for address
    from bot.database.models import TenantStay as TS
    stmt = select(TS).where(
        TS.tenant_id == tenant.id,
        TS.status == StayStatus.active.value
    ).options(selectinload(TS.rental_object))
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if not stay:
        await message.answer(UIMessages.error("У вас нет активного договора аренды"))
        return
    
    # Get pending rent charges
    rent_stmt = select(func.sum(RentCharge.amount)).where(
        RentCharge.stay_id == stay.id,
        RentCharge.status == ChargeStatus.pending.value
    )
    rent_result = await session.execute(rent_stmt)
    rent_debt = rent_result.scalar() or 0
    
    # Get pending comm charges
    comm_stmt = select(func.sum(CommCharge.amount)).where(
        CommCharge.stay_id == stay.id,
        CommCharge.status == ChargeStatus.pending.value
    )
    comm_result = await session.execute(comm_stmt)
    comm_debt = comm_result.scalar() or 0
    
    # Get stay info for context
    address = stay.rental_object.address if stay.rental_object else "—"
    rent_day = stay.rent_day
    comm_day = stay.comm_day
    
    total_debt = float(rent_debt) + float(comm_debt)
    
    text = UIMessages.header("Статус оплаты", UIEmojis.PAYMENT)
    text += f"📍 {address}\n\n"
    
    if total_debt > 0:
        text += f"🔴 <b>К оплате: {format_amount(total_debt)}</b>\n\n"
        if rent_debt > 0:
            text += UIMessages.field("Аренда", format_amount(rent_debt), UIEmojis.HOME)
        if comm_debt > 0:
            text += UIMessages.field("Коммуналка", format_amount(comm_debt), UIEmojis.ELECTRIC)
    else:
        text += "🟢 <b>Все оплачено!</b>\n"
    
    text += f"\n📅 Аренда: {rent_day}-е число | Коммуналка: {comm_day}-е число"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.PHOTO} Загрузить чек", callback_data="upload_receipt_start")],
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} В меню", callback_data="back_to_tenant_menu")]
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text.contains("Личный кабинет"))
@router.message(Command("menu"))
async def tenant_menu(message: Message, tenant, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.services.balance_service import get_stay_balance
    
    text = UIMessages.header("Личный кабинет", UIEmojis.TENANT)
    
    if not tenant:
        await message.answer(UIMessages.error("Вы не зарегистрированы как жилец"), parse_mode="HTML")
        return

    text += f"Здравствуйте, <b>{tenant.full_name}</b>!\n\n"
    
    # Try to get balance info
    stay = await get_active_stay(session, tenant.id)
    if stay:
        try:
            balance = await get_stay_balance(session, stay.id)
            if balance.balance > 0:
                text += f"🔴 <b>К оплате: {format_amount(balance.balance)}</b>\n\n"
            elif balance.balance < 0:
                text += f"🟢 <b>Аванс: {format_amount(abs(balance.balance))}</b>\n\n"
            else:
                text += f"✅ <b>Всё оплачено!</b>\n\n"
        except Exception as e:
            # If balance calculation fails, just show menu
            text += "\n"
    
    text += UIMessages.section("Доступные функции")
    text += f"{UIEmojis.PHOTO} Загрузить чек об оплате\n"
    text += f"{UIEmojis.INFO} /status — Мои начисления\n"
    text += f"{UIEmojis.MESSAGE} /message — Написать администратору\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.PHOTO} Загрузить чек", callback_data="upload_receipt_start")],
        [InlineKeyboardButton(text=f"{UIEmojis.INFO} Мои начисления", callback_data="my_charges")],
        [InlineKeyboardButton(text=f"{UIEmojis.MESSAGE} Написать сообщение", callback_data="send_message")],
    ])
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "upload_receipt_start")
async def start_upload_receipt(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📸 <b>Отправьте фото чека или файл (PDF).</b>", parse_mode="HTML")
    await state.set_state(ReceiptState.waiting_for_photo)
    await call.answer()

@router.message(F.photo | F.document)
async def on_photo_received(message: Message, tenant, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import InlineKeyboardMarkup, InlineKeyboardButton
    
    # Get file ID
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    
    # Check for PDF
    is_pdf = False
    if message.document and message.document.mime_type == 'application/pdf':
        is_pdf = True
        
    # 1. If explicit state -> process immediately
    current_state = await state.get_state()
    if current_state == ReceiptState.waiting_for_photo.state:
        await _process_receipt_impl(message, tenant, file_id, state, session, is_pdf=is_pdf)
        return

    # 2. Ambiguous -> Ask user
    await state.update_data(temp_file_id=file_id, temp_caption=message.caption, temp_mime_type=message.document.mime_type if message.document else None)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 Это оплата (чек)", callback_data="confirm_type_receipt")],
        [InlineKeyboardButton(text="💬 В поддержку", callback_data="confirm_type_support")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    
    await message.answer(
        "🛠 <b>Я получил файл. Что это?</b>\n"
        "Выберите действие ниже:", 
        reply_markup=kb
    )
    await state.set_state(ReceiptState.confirm_type)

@router.callback_query(ReceiptState.confirm_type, F.data == "confirm_type_receipt")
async def on_receipt_confirmed(call: CallbackQuery, tenant, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    file_id = data.get("temp_file_id")
    mime_type = data.get("temp_mime_type")
    is_pdf = mime_type == 'application/pdf'
    
    if not file_id:
        await call.message.edit_text("❌ Ошибка: файл потерян.")
        await state.clear()
        return
        
    await call.message.edit_text("🔄 Обрабатываю чек...")
    # Call impl with message object mocked or just passed for answer purposes? 
    # _process_receipt_impl uses message.answer. We can pass call.message.
    await _process_receipt_impl(call.message, tenant, file_id, state, session, is_pdf=is_pdf)

@router.callback_query(ReceiptState.confirm_type, F.data == "confirm_type_support")
async def on_support_confirmed(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✍️ <b>Напишите комментарий к этому фото:</b>\n(Опишите проблему или вопрос)")
    await state.set_state(SupportState.waiting_for_message)
    await call.answer()

@router.callback_query(F.data == "cancel_action")
async def on_cancel_action(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("❌ Действие отменено.")
    await state.clear()
    await call.answer()

async def _process_receipt_impl(message: Message, tenant, file_id: str, state: FSMContext, session: AsyncSession, is_pdf: bool = False):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount
    from bot.services.billing_service import ParsedReceipt
    
    # 1. Get Active Stay (with relations just in case validation logic grows)
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
        text = UIMessages.error("У вас нет активного договора аренды")
        text += "\n\n" + UIMessages.info_box("Обратитесь к администратору для оформления договора")
        await message.answer(text)
        await state.clear()
        return

    # message.answer might be editing if called from callback, but message.answer adds new message.
    # It is safer to send new message.
    await message.answer(f"{UIEmojis.PROCESSING} <b>Анализирую чек...</b>")
    
    # 2-3. Download and Parse
    try:
        parsed = None
        
        if is_pdf:
            # Skip download/OCR for PDF
            parsed = ParsedReceipt(text="", amount=None, parsed_date=None, confidence=0.0)
        else:
            if isinstance(message, CallbackQuery):
                bot_instance = message.bot
            else:
                bot_instance = message.bot
                
            file_info = await bot_instance.get_file(file_id)
            downloaded = await bot_instance.download_file(file_info.file_path)
            file_bytes = downloaded.read()
            
            parsed = await parse_receipt(file_bytes)
        
        
        # 4. Validate
        decision, reason, pay_type, amount = await validate_receipt_logic(session, stay, parsed)
        
        # 5. Save
        payment, receipt = await create_payment_from_receipt(
            session=session,
            stay_id=stay.id,
            file_id=file_id,
            parsed=parsed,
            decision=decision,
            pay_type=pay_type,
            reject_reason=reason
        )
        
        # 6. Response
        if decision == ReceiptDecision.accepted:
            if amount > 0:
                text = UIMessages.header("Чек принят", UIEmojis.SUCCESS)
                pay_type_text = "Аренда" if pay_type == PaymentType.rent else "Коммунальные услуги"
                text += UIMessages.field("Тип платежа", pay_type_text)
                text += UIMessages.field("Сумма", format_amount(amount), UIEmojis.MONEY)
                text += UIMessages.field("Статус", "Ожидает подтверждения", UIEmojis.PENDING)
            else:
                text = UIMessages.header("Чек получен", UIEmojis.SUCCESS)
                text += UIMessages.info_box("Сумма не распознана автоматически. Чек отправлен администратору на ручную проверку.")
            
            await message.answer(text)
        else:
            text = UIMessages.header("Чек отклонён", UIEmojis.ERROR)
            text += UIMessages.field("Причина", reason, UIEmojis.WARNING)
            text += "\n" + UIMessages.info_box("Пожалуйста, убедитесь в качестве фото или документа.")
            await message.answer(text)
            
    except Exception as e:
        import logging
        logging.error(f"Error processing receipt: {e}", exc_info=True)
        await message.answer(f"❌ Произошла ошибка при обработке чека: {e}")
        
    finally:
        await state.clear()


# --- Missing Callback Handlers ---
@router.callback_query(F.data == "my_charges")
async def my_charges_callback(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount
    from bot.database.models import RentCharge, ChargeStatus
    from sqlalchemy import select
    
    stay = await get_active_stay(session, tenant.id)
    if not stay:
        await call.message.edit_text(UIMessages.error("У вас нет активного договора аренды"))
        await call.answer()
        return
    
    # Get pending charges
    stmt = select(RentCharge).where(
        RentCharge.stay_id == stay.id,
        RentCharge.status == ChargeStatus.pending.value
    )
    result = await session.execute(stmt)
    charges = result.scalars().all()
    
    if not charges:
        text = UIMessages.header("Мои начисления", UIEmojis.INVOICE)
        text += UIMessages.success("Нет неоплаченных начислений")
    else:
        text = UIMessages.header("Мои начисления", UIEmojis.INVOICE)
        text += f"Неоплаченных: <b>{len(charges)}</b>\n\n"
        for c in charges:
            text += f"• {c.month.strftime('%B %Y')}: {format_amount(c.amount)}\n"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} Назад", callback_data="back_to_tenant_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "send_message")
async def send_message_callback(call: CallbackQuery, state):
    from aiogram.fsm.context import FSMContext
    from bot.states import SupportState
    
    await call.message.edit_text("💬 Напишите ваше сообщение для администратора:")
    await state.set_state(SupportState.waiting_for_message)
    await call.answer()


@router.callback_query(F.data == "back_to_tenant_menu")
async def back_to_tenant_menu(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from bot.services.balance_service import get_stay_balance
    
    text = UIMessages.header("Личный кабинет", UIEmojis.TENANT)
    text += f"Здравствуйте, <b>{tenant.full_name}</b>!\n\n"
    
    # Try to get balance info
    stay = await get_active_stay(session, tenant.id)
    if stay:
        try:
            balance = await get_stay_balance(session, stay.id)
            if balance.balance > 0:
                text += f"🔴 <b>К оплате: {format_amount(balance.balance)}</b>\n\n"
            elif balance.balance < 0:
                text += f"🟢 <b>Аванс: {format_amount(abs(balance.balance))}</b>\n\n"
            else:
                text += f"✅ <b>Всё оплачено!</b>\n\n"
        except Exception as e:
            # If balance calculation fails, just show menu
            text += "\n"
    
    text += UIMessages.section("Доступные функции")
    text += f"{UIEmojis.PHOTO} Загрузить чек об оплате\n"
    text += f"{UIEmojis.INFO} /status — Мои начисления\n"
    text += f"{UIEmojis.MESSAGE} /message — Написать администратору\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.INFO} Мои начисления", callback_data="my_charges")],
        [InlineKeyboardButton(text=f"{UIEmojis.MESSAGE} Написать сообщение", callback_data="send_message")],
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

# --- Reply Keyboard Handlers ---

@router.message(F.text.contains("Мои платежи"))
async def my_charges_msg(message: Message, tenant, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount
    from bot.database.models import RentCharge, ChargeStatus
    from sqlalchemy import select
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    stay = await get_active_stay(session, tenant.id)
    if not stay:
        await message.answer(UIMessages.error("У вас нет активного договора аренды"))
        return
    
    # Get pending charges
    stmt = select(RentCharge).where(
        RentCharge.stay_id == stay.id,
        RentCharge.status == ChargeStatus.pending.value
    )
    result = await session.execute(stmt)
    charges = result.scalars().all()
    
    if not charges:
        text = UIMessages.header("Мои начисления", UIEmojis.INVOICE)
        text += UIMessages.success("Нет неоплаченных начислений")
    else:
        text = UIMessages.header("Мои начисления", UIEmojis.INVOICE)
        text += f"Неоплаченных: <b>{len(charges)}</b>\n\n"
        for c in charges:
            text += f"• {c.month.strftime('%B %Y')}: {format_amount(c.amount)}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} Назад", callback_data="back_to_tenant_menu")]
    ])
    await message.answer(text, reply_markup=kb)

@router.message(F.text.contains("Написать") | F.text.contains("Поддержка"))
async def send_message_msg(message: Message, state):
    from bot.states import SupportState
    
    await message.answer("💬 Напишите ваше сообщение для администратора:")
    await state.set_state(SupportState.waiting_for_message)

@router.message(F.text == "📸 Загрузить чек")
async def start_receipt_upload(message: Message, state: FSMContext):
    await message.answer("📸 Пожалуйста, отправьте фото или файл чека.")
    await state.set_state(ReceiptState.waiting_for_photo)


# --- Services Menu ---
@router.message(F.text.contains("Услуги"))
async def services_menu(message: Message, tenant, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, get_service_icon
    from bot.database.models import ServiceSubscription, CommProvider
    from bot.services.settings_service import get_service_subscriptions
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    stay = await get_active_stay(session, tenant.id)
    if not stay:
        await message.answer(UIMessages.error("У вас нет активного договора"))
        return
    
    # Get subscriptions with provider info
    stmt = (
        select(ServiceSubscription)
        .where(ServiceSubscription.stay_id == stay.id)
        .options(selectinload(ServiceSubscription.provider))
    )
    result = await session.execute(stmt)
    subs = result.scalars().all()
    
    text = UIMessages.header("Мои услуги", UIEmojis.SETTINGS)
    kb_rows = []
    
    if not subs:
        text += UIMessages.info_box("Нет подключённых услуг")
    else:
        for sub in subs:
            icon = get_service_icon(sub.provider.service_type)
            status = "🟢" if sub.enabled else "🔴"
            text += f"{icon} {sub.provider.name} {status}\n"
            
            toggle_text = "Выключить" if sub.enabled else "Включить"
            kb_rows.append([
                InlineKeyboardButton(
                    text=f"{icon} {toggle_text} {sub.provider.name}",
                    callback_data=f"toggle_service_{sub.provider_id}"
                )
            ])
    
    kb_rows.append([InlineKeyboardButton(text=f"{UIEmojis.BACK} Назад", callback_data="back_to_tenant_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("toggle_service_"))
async def toggle_service_callback(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.utils.ui import UIMessages
    from bot.services.settings_service import toggle_service, get_service_subscriptions
    
    provider_id = int(call.data.split("_")[2])
    
    stay = await get_active_stay(session, tenant.id)
    if not stay:
        await call.answer("Ошибка: нет активного договора", show_alert=True)
        return
    
    # Get current state
    from bot.database.models import ServiceSubscription
    from sqlalchemy import select
    stmt = select(ServiceSubscription).where(
        ServiceSubscription.stay_id == stay.id,
        ServiceSubscription.provider_id == provider_id
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()
    
    new_state = not sub.enabled if sub else True
    await toggle_service(session, stay.id, provider_id, new_state)
    
    status_text = "включена" if new_state else "выключена"
    await call.answer(f"Услуга {status_text}")
    
    # Refresh the menu
    await services_menu(call, tenant, session)


# --- Settings Menu ---
@router.message(F.text.contains("Настройки"))
async def settings_menu(message: Message, tenant, session: AsyncSession, state: FSMContext):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.config import config
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    user_id = message.from_user.id
    is_owner = user_id in config.OWNER_IDS
    is_admin = user_id in config.ADMIN_IDS or is_owner
    
    # Check testing mode
    data = await state.get_data()
    role_mode = data.get("role_mode")
    
    # Force tenant mode if requested
    if role_mode == "tenant":
        is_admin = False
    
    # Admin/Owner settings
    if is_admin:
        text = UIMessages.header("⚙️ Настройки", "")
        
        kb_rows = [
            [InlineKeyboardButton(text="👔 Управление админами", callback_data="manage_admins")],
            [InlineKeyboardButton(text="📞 Контакты администрации", callback_data="admin_contacts")],
            [InlineKeyboardButton(text="➕ Добавить адрес", callback_data="add_object")],
            [InlineKeyboardButton(text="➕ Заселить жильца", callback_data="add_stay_start")],
        ]
        
        if is_owner:
            text += "Вы — владелец системы.\n\n"
        else:
            text += "Вы — администратор.\n\n"
        
        text += "Выберите раздел:"
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await message.answer(text, reply_markup=kb)
        return
    
    # Tenant settings
    if not tenant:
        await message.answer(UIMessages.error("Нет доступа к настройкам"))
        return
    
    from bot.services.settings_service import get_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    # Read all values inside session context
    notifications_enabled = settings.notifications_enabled
    rent_notifications = settings.rent_notifications
    comm_notifications = settings.comm_notifications
    reminder_days = settings.reminder_days
    reminder_count = getattr(settings, 'reminder_count', 1) or 1
    
    text = UIMessages.header("Настройки уведомлений", UIEmojis.SETTINGS)
    
    notif_status = "🟢 Вкл" if notifications_enabled else "🔴 Выкл"
    rent_status = "✅" if rent_notifications else "❌"
    comm_status = "✅" if comm_notifications else "❌"
    
    text += UIMessages.field("Уведомления", notif_status)
    text += UIMessages.field("Напоминания об аренде", rent_status)
    text += UIMessages.field("Напоминания о коммуналке", comm_status)
    text += UIMessages.field("За сколько дней до оплаты", f"{reminder_days} дн.")
    text += UIMessages.field("Раз в день", f"{reminder_count}")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'🔴 Выключить' if notifications_enabled else '🟢 Включить'} уведомления",
            callback_data="toggle_notifications"
        )],
        [InlineKeyboardButton(
            text=f"{rent_status} Аренда",
            callback_data="toggle_rent_notif"
        ), InlineKeyboardButton(
            text=f"{comm_status} Коммуналка", 
            callback_data="toggle_comm_notif"
        )],
        [
            InlineKeyboardButton(text="⏪ -1 дн", callback_data="reminder_days_dec"),
            InlineKeyboardButton(text=f"📅 {reminder_days} дн.", callback_data="noop"),
            InlineKeyboardButton(text="⏩ +1 дн", callback_data="reminder_days_inc")
        ],
        [
            InlineKeyboardButton(text="⏪ -1 раз", callback_data="reminder_count_dec"),
            InlineKeyboardButton(text=f"🔔 {reminder_count} раз/день", callback_data="noop"),
            InlineKeyboardButton(text="⏩ +1 раз", callback_data="reminder_count_inc")
        ],
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} Назад", callback_data="back_to_tenant_menu")]
    ])
    
    # Support both Message (new) and CallbackQuery (edit)
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.services.settings_service import get_tenant_settings, update_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    new_state = not settings.notifications_enabled
    await update_tenant_settings(session, tenant.id, notifications_enabled=new_state)
    
    await call.answer(f"Уведомления {'включены' if new_state else 'выключены'}")
    await settings_menu(call, tenant, session)


@router.callback_query(F.data == "toggle_rent_notif")
async def toggle_rent_notif(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.services.settings_service import get_tenant_settings, update_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    new_state = not settings.rent_notifications
    await update_tenant_settings(session, tenant.id, rent_notifications=new_state)
    
    await call.answer(f"Напоминания об аренде {'вкл' if new_state else 'выкл'}")
    await settings_menu(call, tenant, session)


@router.callback_query(F.data == "toggle_comm_notif")
async def toggle_comm_notif(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.services.settings_service import get_tenant_settings, update_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    new_state = not settings.comm_notifications
    await update_tenant_settings(session, tenant.id, comm_notifications=new_state)
    
    await call.answer(f"Напоминания о коммуналке {'вкл' if new_state else 'выкл'}")
    await settings_menu(call, tenant, session)


# --- My Object ---
@router.message(F.text.contains("Моя квартира"))
async def my_object_menu(message: Message, tenant, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount, format_date
    from bot.database.models import RentalObject
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    stay = await get_active_stay(session, tenant.id)
    if not stay:
        await message.answer(UIMessages.error("У вас нет активного договора"))
        return
    
    # Get object info
    stmt = select(RentalObject).where(RentalObject.id == stay.object_id)
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()
    
    text = UIMessages.header("Мой объект", UIEmojis.HOME)
    text += UIMessages.field("Адрес", obj.address if obj else "—", UIEmojis.BUILDING)
    text += UIMessages.field("Аренда", format_amount(stay.rent_amount), UIEmojis.MONEY)
    text += UIMessages.field("День оплаты аренды", f"{stay.rent_day}-е число")
    text += UIMessages.field("День оплаты коммуналки", f"{stay.comm_day}-е число")
    text += UIMessages.field("Дата заселения", format_date(stay.date_from), UIEmojis.CALENDAR)
    
    await message.answer(text)


# --- Charges shortcut ---
@router.message(F.text.contains("Начисления"))
async def charges_menu(message: Message, tenant):
    # Redirect to my_charges_msg
    await my_charges_msg(message, tenant)


# --- Reminder Settings Callbacks ---
@router.callback_query(F.data == "reminder_days_inc")
async def reminder_days_inc(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.services.settings_service import get_tenant_settings, update_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    new_days = min(settings.reminder_days + 1, 14)  # Max 14 days
    await update_tenant_settings(session, tenant.id, reminder_days=new_days)
    
    await call.answer(f"Напоминание за {new_days} дней до оплаты")
    await settings_menu(call, tenant, session)


@router.callback_query(F.data == "reminder_days_dec")
async def reminder_days_dec(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.services.settings_service import get_tenant_settings, update_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    new_days = max(settings.reminder_days - 1, 1)  # Min 1 day
    await update_tenant_settings(session, tenant.id, reminder_days=new_days)
    
    await call.answer(f"Напоминание за {new_days} дней до оплаты")
    await settings_menu(call, tenant, session)


@router.callback_query(F.data == "reminder_count_inc")
async def reminder_count_inc(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.services.settings_service import get_tenant_settings, update_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    current = getattr(settings, 'reminder_count', 1) or 1
    new_count = min(current + 1, 5)  # Max 5 times per day
    await update_tenant_settings(session, tenant.id, reminder_count=new_count)
    
    await call.answer(f"Напоминание {new_count} раз в день")
    await settings_menu(call, tenant, session)


@router.callback_query(F.data == "reminder_count_dec")
async def reminder_count_dec(call: CallbackQuery, tenant, session: AsyncSession):
    from bot.services.settings_service import get_tenant_settings, update_tenant_settings
    
    settings = await get_tenant_settings(session, tenant.id)
    current = getattr(settings, 'reminder_count', 1) or 1
    new_count = max(current - 1, 1)  # Min 1 time per day
    await update_tenant_settings(session, tenant.id, reminder_count=new_count)
    
    await call.answer(f"Напоминание {new_count} раз в день")
    await settings_menu(call, tenant, session)


@router.callback_query(F.data == "noop")
async def noop_callback(call: CallbackQuery):
    await call.answer()
