from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Filter, Command
from aiogram.fsm.context import FSMContext
from bot.config import config
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.stay_service import create_object, get_all_objects, create_stay
from bot.services.tenant_service import get_tenant_by_tg_id
from bot.states import AddObjectState, AddStayState, EditObjectState, EditStayState, EditTenantState, AddTenantState, AddContactState, InviteAdminState, InviteTenantState, AdminMessageState, ManualPaymentState, AddRSOState, LinkRSOState, AddUKState, CancelPaymentState, ApproveReceiptState, RejectReceiptState
from datetime import date, datetime, timezone
import logging
from pydantic import ValidationError
from bot.schemas.validation import AmountModel, DayOfMonthModel


class AdminFilter(Filter):
    async def __call__(self, event) -> bool:
        # Works for both Message and CallbackQuery
        if hasattr(event, 'from_user'):
            user_id = event.from_user.id
            return user_id in config.ADMIN_IDS or user_id in config.OWNER_IDS
        return False

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())  # Also filter callbacks for admin

# --- Utility Handlers ---
@router.callback_query(F.data == "ignore")
async def ignore_callback(call: CallbackQuery):
    """Ignore callback (for informational buttons)"""
    await call.answer()

# --- Menu ---
@router.message(F.text.contains("Панель владельца"))
async def owner_dashboard(message: Message):
    from bot.utils.ui import UIEmojis, UIMessages
    
    text = UIMessages.header("Панель владельца", "👑")
    text += "У вас полный доступ к системе.\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏠 Адреса", callback_data="list_objects")],
        [InlineKeyboardButton(text=f"{UIEmojis.GROUP} Арендаторы", callback_data="list_tenants")],
        [InlineKeyboardButton(text=f"{UIEmojis.PAYMENT} Платежи", callback_data="list_payments")],
        [InlineKeyboardButton(text="📊 Отчёты", callback_data="reports_menu")],
        [InlineKeyboardButton(text="👔 Управление админами", callback_data="manage_admins")],
    ])
    await message.answer(text, reply_markup=kb)


@router.message(F.text.contains("Админ Панель"))
@router.message(Command("admin"))
async def admin_dashboard(message: Message):
    from bot.utils.ui import UIEmojis, UIMessages
    
    text = UIMessages.header("Панель администратора", UIEmojis.ADMIN)
    text += "Выберите нужный раздел:\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏠 Мои адреса", callback_data="list_objects")],
        [InlineKeyboardButton(text=f"{UIEmojis.PAYMENT} Проверка платежей", callback_data="list_payments")],
        [
            InlineKeyboardButton(text=f"{UIEmojis.ADD} Добавить адрес", callback_data="add_object"),
            InlineKeyboardButton(text=f"{UIEmojis.KEY} Заселить жильца", callback_data="add_stay_start")
        ],
        [InlineKeyboardButton(text=f"{UIEmojis.GROUP} Список жильцов", callback_data="list_tenants")],
        [InlineKeyboardButton(text=f"{UIEmojis.BUILDING} Управление УК/РСО", callback_data="manage_uk_rso")],
    ])
    await message.answer(text, reply_markup=kb)

# --- Add Object Flow (with UK/RSO detection) ---
@router.callback_query(F.data == "add_object")
async def start_add_object(call: CallbackQuery, state: FSMContext):
    from bot.utils.ui import UIMessages, UIEmojis
    
    text = UIMessages.header("Добавление объекта", UIEmojis.ADD)
    text += UIMessages.info_box("Введите полный адрес объекта\nПример: г. Москва, ул. Ленина, д. 12А")
    
    await call.message.answer(text)
    await state.set_state(AddObjectState.waiting_for_address)
    await call.answer()

@router.message(AddObjectState.waiting_for_address)
async def process_add_object(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.services.address_service import normalize_address, find_house, get_uk_by_house
    from bot.services.rso_service import get_rso_by_uk
    
    # Guard: cancel on commands
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Добавление адреса отменено.")
        await state.clear()
        return
    
    # Guard: ignore menu buttons
    if message.text and any(e in message.text for e in ["🏠", "👥", "💳", "📊", "⚙️", "❔"]):
        await message.answer("⚠️ Введите адрес или /cancel для отмены")
        return
    
    address = message.text
    owner_id = message.from_user.id
    
    # 1. Normalize address
    norm_addr = normalize_address(address)
    
    # 2. Try to find house in DB
    house = await find_house(session, norm_addr)
    
    # 3. Create object
    obj = await create_object(session, owner_id, address)
    logging.info(f"Admin {owner_id} created object {obj.id} ({address})")

    
    # Store object_id in state for potential RSO assignment
    await state.update_data(object_id=obj.id)
    
    # 4. If house found with UK -> offer to assign RSO
    if house and house.uk_id:
        uk = await get_uk_by_house(session, house)
        if uk:
            # Store UK info in state
            await state.update_data(uk_id=uk.id, uk_name=uk.name)
            
            text = UIMessages.success(f"Объект создан! ID: {obj.id}")
            text += "\n\n" + UIMessages.section("Найдена управляющая компания")
            text += UIMessages.field("Название", uk.name, UIEmojis.BUILDING)
            if uk.inn:
                text += UIMessages.field("ИНН", uk.inn)
            
            # Check if UK has RSO links
            rso_list = await get_rso_by_uk(session, uk.id)
            if rso_list:
                text += f"\n{UIEmojis.INFO} Найдено {len(rso_list)} поставщиков услуг от этой УК"
                
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f"{UIEmojis.CHECK} Привязать РСО от УК", callback_data="assign_uk_rso")],
                    [InlineKeyboardButton(text=f"{UIEmojis.CANCEL} Пропустить", callback_data="skip_uk_rso")]
                ])
                await message.answer(text, reply_markup=kb)
                return
    
    # No UK/RSO found -> just confirm creation
    text = UIMessages.success(f"Объект создан! ID: {obj.id}")
    text += "\n" + UIMessages.info_box("УК не найдена. Вы можете добавить РСО вручную через /rso_add")
    await message.answer(text)
    await state.clear()

# --- RSO Assignment Callbacks ---
@router.callback_query(F.data == "assign_uk_rso")
async def assign_uk_rso_callback(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIMessages, UIEmojis
    from bot.services.rso_service import get_rso_by_uk, assign_rso_to_object
    
    data = await state.get_data()
    object_id = data.get('object_id')
    uk_id = data.get('uk_id')
    
    if not object_id or not uk_id:
        await call.message.answer(UIMessages.error("Ошибка: данные не найдены"))
        await call.answer()
        return
    
    # Get RSO providers from UK
    rso_list = await get_rso_by_uk(session, uk_id)
    
    if not rso_list:
        await call.message.edit_text(UIMessages.warning("У данной УК нет привязанных РСО"))
        await call.answer()
        return
    
    # Assign all RSO to object
    provider_ids = [rso.id for rso in rso_list]
    created_links = await assign_rso_to_object(session, object_id, provider_ids)
    
    text = UIMessages.success(f"Привязано {len(created_links)} поставщиков услуг")
    text += "\n\n" + UIMessages.section("Добавленные РСО")
    for rso in rso_list:
        text += f"{UIEmojis.CHECK} {rso.name} ({rso.service_type})\n"
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Настроить лицевые счета", callback_data=f"obj_rso_manage_{object_id}")],
        [InlineKeyboardButton(text="👌 Готово", callback_data="list_objects")] # Or back to menu
    ]))
    
    await state.clear()
    await call.answer()

@router.callback_query(F.data == "skip_uk_rso")
async def skip_uk_rso_callback(call: CallbackQuery, state: FSMContext):
    from bot.utils.ui import UIMessages
    
    await call.message.edit_text(UIMessages.info_box("РСО не привязаны. Вы можете добавить их позже через /rso_add"))
    await state.clear()
    await call.answer()


# list_objects callback moved to line ~1653 (uses list_objects_msg)

# --- Add Stay Flow ---
@router.callback_query(F.data.startswith("create_tenant_for_obj_"))
async def create_tenant_for_object(call: CallbackQuery, state: FSMContext):
    """Start tenant creation flow with pre-selected object"""
    obj_id = int(call.data.split("_")[-1])
    
    # Save object_id to state
    await state.update_data(preselected_object_id=obj_id)
    
    from bot.utils.ui import UIMessages
    text = "👤 Введите Telegram ID жильца:\n\n"
    text += "💡 Жилец должен сначала запустить бота и получить свой ID.\n"
    text += "Для отмены введите /cancel"
    
    await call.message.answer(text)
    await state.set_state(AddStayState.waiting_for_tenant_id)
    await call.answer()

@router.callback_query(F.data == "add_stay_start")
async def start_add_stay(call: CallbackQuery, state: FSMContext):
    from bot.utils.ui import UIMessages
    text = "👤 Введите Telegram ID жильца:\n\n"
    text += "💡 Жилец должен сначала запустить бота и получить свой ID.\n"
    text += "Для отмены введите /cancel"
    await call.message.answer(text)
    await state.set_state(AddStayState.waiting_for_tenant_id)
    await call.answer()

@router.message(AddStayState.waiting_for_tenant_id)
async def process_stay_tenant(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIMessages
    
    user_input = message.text.strip()
    
    # Check for cancel
    if user_input.lower() == "/cancel" or user_input.startswith("/"):
        await message.answer("❌ Заселение отменено.")
        await state.clear()
        return
    
    # Check for menu buttons (ignore them)
    if any(emoji in user_input for emoji in ["🏠", "👥", "💳", "📊", "⚙️", "❔"]):
        await message.answer("⚠️ Введите числовой ID жильца или /cancel для отмены")
        return
    
    tenant = None
    
    # Try to find by ID
    if user_input.isdigit():
        tenant = await get_tenant_by_tg_id(session, int(user_input))
    
    if not tenant:
        await message.answer(
            "❌ Жилец с таким ID не найден.\n\n"
            "Убедитесь что жилец:\n"
            "1. Запустил бота (/start)\n"
            "2. Сообщил вам свой ID\n\n"
            "Для отмены введите /cancel"
        )
        return

    await state.update_data(tenant_id=tenant.id, tenant_name=tenant.full_name)
    
    # Check if object was preselected (from object menu button)
    data = await state.get_data()
    preselected_obj_id = data.get('preselected_object_id')
    
    if preselected_obj_id:
        # Skip object selection, go directly to rent amount
        await state.update_data(object_id=preselected_obj_id)
        await message.answer("Введите сумму аренды (число, например 30000):")
        await state.set_state(AddStayState.waiting_for_rent_amount)
        return
    
    # List objects to select
    objects = await get_all_objects(session)
    
    if not objects:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить адрес", callback_data="add_object_start")],
            [InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_add_stay")]
        ])
        await message.answer(
            "⚠️ Нет адресов для заселения.\n"
            "Сначала добавьте адрес:",
            reply_markup=kb
        )
        await state.clear()
        return
    
    if not providers:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Привязать провайдера", callback_data=f"link_rso_to_obj_{obj_id}")],
            [InlineKeyboardButton(text="◀️ К объекту", callback_data=f"manage_obj_{obj_id}")]
        ])
        await call.message.edit_text(
            "💡 <b>Провайдеры объекта</b>\n\n"
            "Провайдеры не привязаны.\n"
            "Сначала создайте их в общем меню.",
            reply_markup=kb
        )
        await call.answer()
        return
    
    kb_rows = []
    for obj in objects:
        kb_rows.append([InlineKeyboardButton(text=f"🏠 {obj.address}", callback_data=f"sel_obj_{obj.id}")])
    kb_rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_stay")])
    
    await message.answer(
        f"✅ Жилец: <b>{tenant.full_name}</b>\n\nВыберите адрес для заселения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )
    await state.set_state(AddStayState.waiting_for_object_id)


@router.callback_query(F.data == "cancel_add_stay")
async def cancel_add_stay(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("❌ Заселение отменено.")
    await state.clear()
    await call.answer()

@router.callback_query(AddStayState.waiting_for_object_id, F.data.startswith("sel_obj_"))
async def process_stay_object(call: CallbackQuery, state: FSMContext):
    object_id = int(call.data.split("_")[-1])
    await state.update_data(object_id=object_id)
    
    await call.message.answer("Введите сумму аренды (число, например 30000):")
    await state.set_state(AddStayState.waiting_for_rent_amount)
    await call.answer()

@router.message(AddStayState.waiting_for_rent_amount)
async def process_stay_rent_amount(message: Message, state: FSMContext):
    # Guard: cancel on commands
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Заселение отменено.")
        await state.clear()
        return
    
    # Guard: ignore menu buttons
    if message.text and any(e in message.text for e in ["🏠", "👥", "💳", "📊", "⚙️", "❔"]):
        await message.answer("⚠️ Введите число или /cancel для отмены")
        return
    
    try:
        model = AmountModel(amount=message.text)
        amount = model.amount
        await state.update_data(stay_amount=amount)
    except ValidationError:
        await message.answer("❌ Введите корректное положительное число для суммы аренды.")
        return

    await message.answer("Введите процент налога/наценки (например, 6). Если нет — введите 0:")
    await state.set_state(AddStayState.waiting_for_tax_rate)


@router.message(AddStayState.waiting_for_tax_rate)
async def process_stay_tax_rate(message: Message, state: FSMContext):
    # Guard: commands
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Заселение отменено.")
        await state.clear()
        return

    try:
        tax = float(message.text.replace(',', '.'))
        if tax < 0 or tax > 100: raise ValueError
        await state.update_data(stay_tax_rate=tax)
    except ValueError:
        await message.answer("Введите число от 0 до 100.")
        return

    await message.answer("Введите день оплаты аренды (1-31):")
    await state.set_state(AddStayState.waiting_for_rent_day)

@router.message(AddStayState.waiting_for_rent_day)
async def process_stay_final(message: Message, state: FSMContext, session: AsyncSession):
    # Guard: cancel on commands
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Заселение отменено.")
        await state.clear()
        return
    
    # Guard: ignore menu buttons  
    if message.text and any(e in message.text for e in ["🏠", "👥", "💳", "📊", "⚙️", "❔"]):
        await message.answer("⚠️ Введите день (1-31) или /cancel")
        return
    
    try:
        model = DayOfMonthModel(day=message.text)
        day = model.day
    except ValidationError:
        await message.answer("❌ Введите число от 1 до 31.")
        return

    data = await state.get_data()
    
    # Create stay starting today
    try:
        stay = await create_stay(
            session=session,
            tenant_id=data['tenant_id'],
            object_id=data['object_id'],
            date_from=date.today(),
            rent_amount=data['stay_amount'],
            rent_day=day,
            comm_day=25, # Default for now
            tax_rate=data.get('stay_tax_rate', 0.0)
        )
        
        logging.info(f"Admin {message.from_user.id} created stay {stay.id} for tenant {data['tenant_id']} at object {data['object_id']}")
        await message.answer(f"✅ Заселение создано! ID: {stay.id}")
    except ValueError as e:
        # Validation error (e.g., object already occupied)
        await message.answer(f"❌ {str(e)}")
    
    await state.clear()

# --- Pending Payments Logic ---
from bot.database.models import Payment, PaymentStatus, PaymentType
from sqlalchemy import select, update

# list_payments callback moved to NAVIGATION CALLBACKS section (uses list_payments_msg)

@router.callback_query(F.data.startswith("pay_ok_"))
async def approve_payment(call: CallbackQuery, session: AsyncSession):
    from bot.services.payment_service import allocate_payment
    
    payment_id = int(call.data.split("_")[-1])
    
    # Update payment status
    await session.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(status=PaymentStatus.confirmed, confirmed_at=datetime.now(timezone.utc))
    )
    # Middleware will commit
    
    # Allocate payment across charges (FIFO)
    try:
        allocations = await allocate_payment(session, payment_id)
        alloc_count = len(allocations)
        await call.message.edit_text(
            f"✅ Платеж #{payment_id} подтвержден.\n"
            f"💰 Распределено на {alloc_count} начисление(ний)."
        )
    except Exception as e:
        logging.error(f"Failed to allocate payment {payment_id}: {e}")
        await call.message.edit_text(
            f"✅ Платеж #{payment_id} подтвержден.\n"
            f"⚠️ Ошибка распределения: {e}"
        )
    
    await call.answer()

@router.callback_query(F.data.startswith("pay_bad_"))
async def reject_payment(call: CallbackQuery, session: AsyncSession):
    from bot.services.payment_service import deallocate_payment
    
    payment_id = int(call.data.split("_")[-1])
    
    # Deallocate if already allocated
    try:
        await deallocate_payment(session, payment_id)
    except Exception as e:
        logging.warning(f"Failed to deallocate payment {payment_id}: {e}")
    
    # Update status
    await session.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(status=PaymentStatus.rejected)
    )
    # Middleware will commit
    
    await call.message.edit_text(f"❌ Платеж #{payment_id} отклонен.")
    await call.answer()

# --- Back to Menu ---
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    from bot.utils.ui import UIEmojis, UIMessages
    
    text = UIMessages.header("Панель администратора", UIEmojis.ADMIN)
    text += "Выберите нужный раздел:\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏠 Мои адреса", callback_data="list_objects")],
        [InlineKeyboardButton(text=f"{UIEmojis.PAYMENT} Проверка платежей", callback_data="list_payments")],
        [
            InlineKeyboardButton(text=f"{UIEmojis.ADD} Добавить адрес", callback_data="add_object"),
            InlineKeyboardButton(text=f"{UIEmojis.KEY} Заселить жильца", callback_data="add_stay_start")
        ],
        [InlineKeyboardButton(text=f"{UIEmojis.GROUP} Список жильцов", callback_data="list_tenants")],
        [InlineKeyboardButton(text=f"{UIEmojis.BUILDING} Управление УК/РСО", callback_data="manage_uk_rso")],
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# list_tenants callback moved to NAVIGATION CALLBACKS section (uses list_tenants_msg)




# --- Reply Keyboard Handlers ---

@router.message(F.text.contains("Адреса"))
async def list_objects_msg(message: Message, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import RentalObject, TenantStay, StayStatus, RentCharge, ChargeStatus
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    from datetime import date
    
    # Get objects with active stays AND tenant data
    stmt = (
        select(RentalObject)
        .options(
            selectinload(RentalObject.stays)
            .selectinload(TenantStay.tenant)
        )
    )
    result = await session.execute(stmt)
    objects = result.scalars().all()
    
    # Check payment status for each object - collect all data INSIDE session
    object_data = []
    for obj in objects:
        active_stay = next((s for s in obj.stays if s.status == StayStatus.active.value), None)
        
        if not active_stay:
            status_icon = "➖"  # No tenant
            tenant_name = ""
        else:
            # Check for unpaid charges
            debt_stmt = select(func.count(RentCharge.id)).where(
                RentCharge.stay_id == active_stay.id,
                RentCharge.status == ChargeStatus.pending.value
            )
            debt_result = await session.execute(debt_stmt)
            has_debt = debt_result.scalar() > 0
            
            status_icon = "🔴" if has_debt else "🟢"
            tenant_name = f" ({active_stay.tenant.full_name})" if active_stay.tenant else ""
        
        # Store simple values, not ORM objects
        object_data.append({
            "address": obj.address,
            "id": obj.id,
            "status_icon": status_icon,
            "tenant_name": tenant_name
        })
    
    text = UIMessages.header("Ваши адреса", "🏠")
    text += "🟢 оплачено | 🔴 долг | ➖ свободно\n\n"
    kb_rows = []
    
    if not object_data:
        text += UIMessages.info_box("Список пуст. Добавьте первый объект.")
    else:
        for obj_info in object_data:
            kb_rows.append([InlineKeyboardButton(
                text=f"{obj_info['status_icon']} {obj_info['address']}{obj_info['tenant_name']}", 
                callback_data=f"obj_manage_{obj_info['id']}"
            )])
            
    kb_rows.append([InlineKeyboardButton(text=f"{UIEmojis.ADD} Добавить адрес", callback_data="add_object")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    await message.answer(text, reply_markup=kb)

# --- Add Tenant (Invite Flow) ---
@router.callback_query(F.data == "add_tenant")
async def start_add_tenant(call: CallbackQuery, state: FSMContext):
    await call.message.answer("📝 Введите ФИО нового жильца:")
    await state.set_state(AddTenantState.waiting_for_name)
    await call.answer()

@router.message(AddTenantState.waiting_for_name)
async def process_tenant_name(message: Message, state: FSMContext):
    # Guard: cancel on commands
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Добавление жильца отменено.")
        await state.clear()
        return
    
    # Guard: ignore menu buttons
    if message.text and any(e in message.text for e in ["🏠", "👥", "💳", "📊", "⚙️", "❔"]):
        await message.answer("⚠️ Введите ФИО или /cancel для отмены")
        return
    
    await state.update_data(name=message.text)
    await message.answer("📞 Введите телефон (или отправьте '-' чтобы пропустить):")
    await state.set_state(AddTenantState.waiting_for_phone)

@router.message(AddTenantState.waiting_for_phone)
async def process_tenant_phone(message: Message, state: FSMContext, session: AsyncSession):
    from bot.database.models import Tenant, TenantStatus
    from bot.services.invite_service import generate_invite
    import random
    
    # Check for commands - cancel the flow
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Добавление жильца отменено.")
        await state.clear()
        return
    
    # Check for menu buttons
    if message.text and any(emoji in message.text for emoji in ["🏠", "👥", "💳", "📊", "⚙️", "❔"]):
        await message.answer("⚠️ Введите телефон или '-' чтобы пропустить")
        return
    
    from bot.schemas.validation import PhoneModel
    
    phone = None
    if message.text != "-":
        try:
            model = PhoneModel(phone=message.text)
            phone = model.phone
        except ValidationError:
             await message.answer("❌ Введите корректный номер телефона (например, +79001234567) или '-' для пропуска.")
             return

    data = await state.get_data()
    name = data['name']
    admin_id = message.from_user.id
    
    # Create tenant with temporary tg_id (will be replaced when they use invite)
    temp_tg_id = -random.randint(1000000, 9999999)  # Negative to avoid conflicts
    
    tenant = Tenant(
        full_name=name,
        phone=phone,
        tg_id=temp_tg_id,  # Temp ID, will be replaced when tenant redeems invite code
        status=TenantStatus.active.value 
    )
    session.add(tenant)
    await session.flush() # flush to get ID
    await session.refresh(tenant)
    tenant_id = tenant.id
    
    logging.info(f"Admin {admin_id} created tenant {tenant.id} ({name})")

    
    # Generate invite code (uses its own session)
    code = await generate_invite(session, admin_id, tenant_id)
    
    # Generate link
    bot_info = await message.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start={code}"
        
    text = f"✅ Жилец <b>{name}</b> создан!\n\n"
    text += f"🔗 <b>Ссылка-приглашение:</b>\n<code>{invite_link}</code>\n\n"
    text += "Перешлите эту ссылку жильцу. Он автоматически получит доступ."
    
    # Add Share Button (actually just text copy helper, real share needs inline query or just forward hint)
    # But we can add a button to "Manage" immediately
    # Or just Back
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 К списку жильцов", callback_data="list_tenants")]
    ])
    
    await message.answer(text, reply_markup=kb)
    await state.clear()

@router.message(F.text.contains("Жильцы") | F.text.contains("Арендаторы"))
async def list_tenants_msg(message: Message, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import TenantStay, StayStatus, RentCharge, ChargeStatus
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    
    stmt = (
        select(TenantStay)
        .where(TenantStay.status == StayStatus.active.value)
        .options(selectinload(TenantStay.tenant), selectinload(TenantStay.rental_object))
    )
    result = await session.execute(stmt)
    stays = result.scalars().all()
    
    # Collect all data as simple values INSIDE session
    tenant_data = []
    for stay in stays:
        debt_stmt = select(func.count(RentCharge.id)).where(
            RentCharge.stay_id == stay.id,
            RentCharge.status == ChargeStatus.pending.value
        )
        debt_result = await session.execute(debt_stmt)
        has_debt = debt_result.scalar() > 0
        
        # Store simple values
        tenant_data.append({
            "stay_id": stay.id,
            "tenant_name": stay.tenant.full_name if stay.tenant else "?",
            "address": stay.rental_object.address if stay.rental_object else "?",
            "has_debt": has_debt
        })
    
    text = UIMessages.header("Арендаторы", UIEmojis.GROUP)
    text += "🟢 оплачено | 🔴 долг\n\n"
    kb_rows = []
    
    if not tenant_data:
        text += UIMessages.info_box("Нет активных арендаторов")
    else:
        text += f"Всего: <b>{len(tenant_data)}</b>\n"
        for t in tenant_data:
            status_icon = "🔴" if t["has_debt"] else "🟢"
            # Short address (last part)
            addr = t["address"].split(",")[-1].strip()
            kb_rows.append([InlineKeyboardButton(
                text=f"{status_icon} {t['tenant_name']} • {addr}", 
                callback_data=f"stay_manage_{t['stay_id']}"
            )])
    
    # Add archive and create buttons
    kb_rows.append([
        InlineKeyboardButton(text="📦 Архив", callback_data="list_archived_tenants"),
        InlineKeyboardButton(text="➕ Добавить жильца", callback_data="add_tenant")
    ])
    kb_rows.append([InlineKeyboardButton(text="📞 Контакты администрации", callback_data="admin_contacts")])
         
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await message.answer(text, reply_markup=kb)

@router.message(F.text.contains("Проверка"))
async def list_payments_msg(message: Message, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount, format_date
    from bot.database.models import Payment, PaymentStatus, PaymentType
    from sqlalchemy import select
    
    stmt = select(Payment).where(Payment.status == PaymentStatus.pending_manual.value).limit(10)
    result = await session.execute(stmt)
    payments = result.scalars().all()
    
    if not payments:
        text = UIMessages.header("Проверка платежей", UIEmojis.PAYMENT)
        text += UIMessages.success("Нет платежей, ожидающих подтверждения")
        await message.answer(text)
        return

    text = UIMessages.header("Платежи на проверке", UIEmojis.PENDING)
    text += f"Всего: <b>{len(payments)}</b> платежей\n\n"
    await message.answer(text)
    
    for p in payments:
        payment_type_emoji = UIEmojis.HOME if p.type == PaymentType.rent.value else UIEmojis.ELECTRIC
        payment_type_text = "Аренда" if p.type == PaymentType.rent.value else "Коммуналка"
        
        msg_text = f"{payment_type_emoji} <b>Платеж #{p.id}</b>\n"
        msg_text += UIMessages.DIVIDER_HALF + "\n"
        msg_text += UIMessages.field("Тип", payment_type_text)
        msg_text += UIMessages.field("Сумма", format_amount(p.amount), UIEmojis.MONEY)
        msg_text += UIMessages.field("Создан", format_date(p.created_at), "📅")
        msg_text += UIMessages.field("Источник", p.source, UIEmojis.PHOTO)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{UIEmojis.SUCCESS} Подтвердить", callback_data=f"pay_ok_{p.id}"),
                InlineKeyboardButton(text=f"{UIEmojis.CANCEL} Отклонить", callback_data=f"pay_bad_{p.id}")
            ]
        ])
        await message.answer(msg_text, reply_markup=kb)

@router.callback_query(F.data.startswith("obj_manage_"))
async def manage_object(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_date, format_amount
    from bot.database.models import RentalObject
    
    obj_id = int(call.data.split("_")[-1])
    
    obj = await session.get(RentalObject, obj_id)
        
    if not obj:
        await call.answer("Объект не найден", show_alert=True)
        return

    status_map = {
        "free": "🟢 Свободен",
        "occupied": "🔴 Занят",
        "repair": "⚠️ Ремонт"
    }
    status_text = status_map.get(obj.status, obj.status)
    
    # Get short address for title
    short_addr = obj.address.split(",")[-1].strip() if "," in obj.address else obj.address

    text = UIMessages.header(f"🏠 {short_addr}", "")
    text += f"📍 {obj.address}\n"
    text += f"Статус: {status_text}\n"
    
    # Show tenant info if occupied
    if obj.status == "occupied":
        from bot.database.models import TenantStay, StayStatus
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        stmt = (
            select(TenantStay)
            .where(TenantStay.object_id == obj.id, TenantStay.status == StayStatus.active.value)
            .options(selectinload(TenantStay.tenant))
        )
        result = await session.execute(stmt)
        stay = result.scalar_one_or_none()
        
        if stay and stay.tenant:
            text += f"\n👤 Жилец: <b>{stay.tenant.full_name}</b>\n"
            if stay.tenant.phone:
                text += f"📱 <code>{stay.tenant.phone}</code>\n"
            text += f"💰 Аренда: {format_amount(stay.rent_amount)}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_obj_{obj.id}")],
        [InlineKeyboardButton(text="👤 Заселить жильца", callback_data=f"create_tenant_for_obj_{obj.id}")],
        [InlineKeyboardButton(text="💡 Провайдеры (РСО)", callback_data=f"obj_rso_manage_{obj.id}")],
        [InlineKeyboardButton(text="📊 Финансы (Год)", callback_data=f"obj_stats_{obj.id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_obj_{obj.id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="list_objects")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("edit_obj_"))
async def edit_object(call: CallbackQuery, state: FSMContext):
    from bot.utils.ui import UIKeyboards
    
    obj_id = int(call.data.split("_")[-1])
    await state.update_data(obj_id=obj_id)
    await state.set_state(EditObjectState.waiting_for_address)
    
    await call.message.edit_text(
        "✏️ Введите новый адрес объекта:", 
        reply_markup=UIKeyboards.back_button(f"obj_manage_{obj_id}")
    )
    await call.answer()

@router.message(EditObjectState.waiting_for_address)
async def obj_address_submitted(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import RentalObject
    from sqlalchemy import update
    
    data = await state.get_data()
    obj_id = data.get("obj_id")
    new_address = message.text
    
    await session.execute(
        update(RentalObject)
        .where(RentalObject.id == obj_id)
        .values(address=new_address)
    )
    # Middleware commits
    
    await state.clear()
    
    text = UIMessages.success(f"Адрес объекта обновлен на: <b>{new_address}</b>")
    # Show object details again? Or just success.
    # Let's show success message with button to go back to object
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} К объекту", callback_data=f"obj_manage_{obj_id}")]
    ])
    await message.answer(text, reply_markup=kb)

# manage_stay handler moved to line ~1489 with enhanced functionality
    
@router.callback_query(F.data.startswith("edit_stay_"))
async def edit_stay(call: CallbackQuery):
    from bot.utils.ui import UIEmojis
    stay_id = int(call.data.split("_")[-1])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.MONEY} Изменить стоимость", callback_data=f"edit_stay_amt_{stay_id}")],
        [InlineKeyboardButton(text=f"🔢 Изменить налог", callback_data=f"edit_stay_tax_{stay_id}")],
        [InlineKeyboardButton(text=f"📅 Изменить дату", callback_data=f"edit_stay_date_{stay_id}")],
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} Назад", callback_data=f"stay_manage_{stay_id}")]
    ])
    await call.message.edit_text("Выберите параметр для изменения:", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("edit_stay_amt_"))
async def edit_stay_amount_start(call: CallbackQuery, state: FSMContext):
    from bot.utils.ui import UIKeyboards
    
    stay_id = int(call.data.split("_")[-1])
    await state.update_data(stay_id=stay_id)
    await state.set_state(EditStayState.waiting_for_rent_amount)
    
    await call.message.edit_text(
        "Введите новую сумму аренды (число):", 
        reply_markup=UIKeyboards.back_button(f"edit_stay_{stay_id}")
    )
    await call.answer()

@router.message(EditStayState.waiting_for_rent_amount)
async def stay_amount_submitted(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import TenantStay
    from sqlalchemy import update
    
    data = await state.get_data()
    stay_id = data.get("stay_id")
    
    try:
        model = AmountModel(amount=message.text)
        new_amount = model.amount
    except ValidationError:
        await message.answer("❌ Пожалуйста, введите корректное положительное число.")
        return
        
    await session.execute(
        update(TenantStay)
        .where(TenantStay.id == stay_id)
        .values(rent_amount=new_amount)
    )
    # Middleware commits
    
    logging.info(f"Admin {message.from_user.id} updated rent amount for stay {stay_id} to {new_amount}")
    
    await state.clear()
    
    text = UIMessages.success(f"Стоимость аренды обновлена: <b>{new_amount:,.0f} ₽</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} К аренде", callback_data=f"stay_manage_{stay_id}")]
    ])
    await message.answer(text, reply_markup=kb)

# --- Extended Admin Functions ---

@router.callback_query(F.data.startswith("evict_stay_"))
async def evict_stay_ask(call: CallbackQuery):
    stay_id = int(call.data.split("_")[-1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚪 Да, выселить", callback_data=f"evict_confirm_{stay_id}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"stay_manage_{stay_id}")
        ]
    ])
    await call.message.edit_text("⚠️ <b>Вы уверены, что хотите выселить жильца?</b>\n\nДоговор будет перенесен в архив, а объект станет свободным.", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("evict_confirm_"))
async def evict_stay_confirm(call: CallbackQuery, session: AsyncSession):
    from bot.services.stay_service import end_stay
    from bot.utils.ui import UIMessages, UIEmojis
    
    stay_id = int(call.data.split("_")[-1])
    
    await end_stay(session, stay_id)
        
    await call.message.edit_text(UIMessages.success("Жилец выселен. Объект свободен."))
    await call.answer()

@router.callback_query(F.data.startswith("delete_obj_"))
async def delete_obj_ask(call: CallbackQuery, session: AsyncSession):
    from bot.database.models import RentalObject, ObjectStatus
    
    obj_id = int(call.data.split("_")[-1])
    
    obj = await session.get(RentalObject, obj_id)
        
    if obj.status == ObjectStatus.occupied.value:
         await call.answer("❌ Нельзя удалить занятый объект. Сначала выселите жильца.", show_alert=True)
         return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"del_obj_yes_{obj_id}"),
            InlineKeyboardButton(text="Отмена", callback_data=f"obj_manage_{obj_id}")
        ]
    ])
    await call.message.edit_text(f"⚠️ <b>Удалить объект {obj.address}?</b>\n\nЭто действие нельзя отменить.", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("del_obj_yes_"))
async def delete_obj_confirm(call: CallbackQuery, session: AsyncSession):
    from bot.database.models import RentalObject
    
    obj_id = int(call.data.split("_")[-1])
    
    obj = await session.get(RentalObject, obj_id)
    if obj:
        await session.delete(obj)
        # Middleware commits
            
    await call.message.edit_text("✅ Объект удален.")
    await call.answer()

@router.callback_query(F.data.startswith("edit_stay_date_"))
async def edit_stay_date_start(call: CallbackQuery, state: FSMContext):
    from bot.utils.ui import UIKeyboards
    stay_id = int(call.data.split("_")[-1])
    await state.update_data(stay_id=stay_id)
    await state.set_state(EditStayState.waiting_for_rent_day)
    
    await call.message.edit_text(
        "Введите новый день оплаты (число от 1 до 31):",
        reply_markup=UIKeyboards.back_button(f"edit_stay_{stay_id}")
    )
    await call.answer()

@router.message(EditStayState.waiting_for_rent_day)
async def stay_day_submitted(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import TenantStay
    from sqlalchemy import update
    
    data = await state.get_data()
    stay_id = data.get("stay_id")
    
    try:
        val = int(message.text.strip())
        if not (1 <= val <= 31):
            raise ValueError
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число от 1 до 31.")
        return
        
    await session.execute(
        update(TenantStay)
        .where(TenantStay.id == stay_id)
        .values(rent_day=val)
    )
    # Middleware commits
    
    await state.clear()
    
    text = UIMessages.success(f"День оплаты изменен на: <b>{val}-е число</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} К аренде", callback_data=f"stay_manage_{stay_id}")]
    ])
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("edit_tenant_"))
async def edit_tenant_start(call: CallbackQuery, state: FSMContext):
    tenant_id = int(call.data.split("_")[-1])
    await state.update_data(tenant_id=tenant_id)
    await state.set_state(EditTenantState.waiting_for_fullname)
    
    await call.message.edit_text("✏️ Введите новое ФИО жильца:")
    await call.answer()

@router.message(EditTenantState.waiting_for_fullname)
async def tenant_name_submitted(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import Tenant
    from sqlalchemy import update
    
    data = await state.get_data()
    tenant_id = data.get("tenant_id")
    new_name = message.text
    
    await session.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(full_name=new_name)
    )
    # Middleware commits
    
    await state.clear()
    await message.answer(UIMessages.success(f"ФИО жильца обновлено на: <b>{new_name}</b>"))


# --- Reply Keyboard Handlers for new menu ---
@router.message(F.text.contains("Платежи"))
async def payments_menu(message: Message, session: AsyncSession):
    # Redirect to payment check
    await list_payments_msg(message, session)


@router.message(F.text.contains("Отчёты"))
async def reports_menu_msg(message: Message):
    from bot.utils.ui import UIEmojis, UIMessages
    
    text = UIMessages.header("Отчёты", "📊")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Должники", callback_data="report_debtors")],
        [InlineKeyboardButton(text="💰 Платежи за месяц", callback_data="report_monthly")],
        [InlineKeyboardButton(text="🏠 Статус адресов", callback_data="report_objects")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "reports_menu")
async def reports_menu_callback(call: CallbackQuery):
    from bot.utils.ui import UIMessages
    
    text = UIMessages.header("Отчёты", "📊")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Должники", callback_data="report_debtors")],
        [InlineKeyboardButton(text="💰 Платежи за месяц", callback_data="report_monthly")],
        [InlineKeyboardButton(text="🏠 Статус адресов", callback_data="report_objects")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "report_debtors")
async def report_debtors(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages, format_amount
    from bot.database.models import RentCharge, ChargeStatus, TenantStay, Tenant, RentalObject
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    stmt = (
        select(RentCharge)
        .where(RentCharge.status == ChargeStatus.pending.value)
        .options(
            selectinload(RentCharge.stay)
            .selectinload(TenantStay.tenant),
            selectinload(RentCharge.stay)
            .selectinload(TenantStay.rental_object)
        )
    )
    result = await session.execute(stmt)
    charges = result.scalars().all()
    
    # Collect data INSIDE session
    debtors_data = []
    total = 0
    for c in charges[:10]:
        tenant_name = c.stay.tenant.full_name if c.stay and c.stay.tenant else "?"
        address = c.stay.rental_object.address if c.stay and c.stay.rental_object else "?"
        amount = float(c.amount)
        total += amount
        # Short address (last part after comma)
        short_addr = address.split(",")[-1].strip() if "," in address else address
        debtors_data.append({
            "id": c.id,
            "name": tenant_name,
            "address": short_addr,
            "amount": amount
        })
    
    text = UIMessages.header("Должники", "📋")
    
    if not debtors_data:
        text += UIMessages.success("Нет неоплаченных начислений")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="reports_menu")]
        ])
    else:
        text += f"Всего долгов: <b>{format_amount(total)}</b>\n\n"
        
        kb_rows = []
        for d in debtors_data:
            text += f"• <b>{d['name']}</b>\n   📍 {d['address']}\n   💰 {format_amount(d['amount'])}\n\n"
            # Add button to mark as paid
            kb_rows.append([
                InlineKeyboardButton(
                    text=f"✅ Отметить оплаченным - {d['name'][:15]}",
                    callback_data=f"mark_paid_rent_{d['id']}"
                )
            ])
        
        kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="reports_menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# --- Manual Payment Marking ---
@router.callback_query(F.data.startswith("mark_paid_"))
async def confirm_mark_paid(call: CallbackQuery, session: AsyncSession):
    """Confirm manual payment marking"""
    from bot.utils.ui import UIMessages
    from bot.database.models import RentCharge, CommCharge
    
    parts = call.data.split("_")
    charge_type = parts[2]  # "rent" or "comm"
    charge_id = int(parts[3])
    
    # Get charge details
    if charge_type == "rent":
        charge = await session.get(RentCharge, charge_id)
    else:
        charge = await session.get(CommCharge, charge_id)
    
    if not charge:
        await call.answer("❌ Начисление не найдено", show_alert=True)
        return
    
    tenant_name = charge.stay.tenant.full_name if charge.stay and charge.stay.tenant else "?"
    
    text = UIMessages.header("⚠️ Подтверждение ручной отметки", "")
    text += f"\n<b>Жилец:</b> {tenant_name}\n"
    text += f"<b>Сумма:</b> {float(charge.amount):.2f} ₽\n\n"
    text += "Вы уверены, что хотите отметить это начисление как оплаченное?\n\n"
    text += UIMessages.info_box("Это создаст виртуальный платёж без чека.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отметить", callback_data=f"confirm_mark_{charge_type}_{charge_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="report_debtors")
        ]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("confirm_mark_"))
async def execute_mark_paid(call: CallbackQuery, session: AsyncSession):
    """Execute manual payment marking"""
    from bot.services.payment_service import mark_charge_as_paid
    from bot.utils.ui import UIMessages
    
    parts = call.data.split("_")
    charge_type = parts[2]
    charge_id = int(parts[3])
    admin_id = call.from_user.id
    admin_name = call.from_user.full_name or "Admin"
    
    try:
        payment = await mark_charge_as_paid(
            session, charge_id, charge_type, admin_id,
            admin_name=admin_name,
            note=f"Отмечено вручную админом {admin_name}"
        )
        
        text = UIMessages.success("Начисление отмечено как оплаченное")
        text += f"\n\n<b>Начисление:</b> #{charge_id}\n"
        text += f"<b>Виртуальный платёж:</b> #{payment.id}\n"
        text += f"<b>Отметил:</b> {admin_name}"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К списку должников", callback_data="report_debtors")]
        ])
        
        await call.message.edit_text(text, reply_markup=kb)
        await call.answer("✅ Готово!", show_alert=False)
        
    except ValueError as e:
        await call.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    except Exception as e:
        await call.answer(f"❌ Неизвестная ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data == "manage_admins")
async def manage_admins_callback(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages
    from bot.services.user_service import get_all_admins
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    
    admins = await get_all_admins(session)
    admins_data = [{"name": a.full_name, "username": a.tg_username, "role": a.role} for a in admins]
    
    text = UIMessages.header("👔 Управление админами", "")
    
    if not admins_data:
        text += "Нет добавленных администраторов.\n"
    else:
        for admin in admins_data:
            role_emoji = "👑" if admin["role"] == "owner" else "👔"
            text += f"{role_emoji} {admin['name']} (@{admin['username'] or '?'})\n"
    
    text += "\n➕ Выберите способ добавления админа:"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Создать ссылку-приглашение", callback_data="create_admin_invite_link")],
        [InlineKeyboardButton(text="📨 Переслать сообщение", callback_data="invite_admin_forward")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "create_admin_invite_link")
async def create_admin_invite_link(call: CallbackQuery, session: AsyncSession):
    """Create invite link for admin"""
    from bot.database.models import InviteCode
    import secrets
    
    # Only owners can add admins
    if call.from_user.id not in config.OWNER_IDS:
        await call.answer("Только владельцы могут добавлять админов", show_alert=True)
        return
    
    # Generate unique code
    code = f"admin_{secrets.token_hex(4)}"
    
    # Save to DB
    invite = InviteCode(
        code=code,
        created_by=call.from_user.id,
        role="admin",
        is_used=False
    )
    session.add(invite)
    # Middleware commits
    
    # Get bot username for link
    bot_info = await call.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start={code}"
    
    text = "🔗 <b>Ссылка-приглашение создана!</b>\n\n"
    text += f"<code>{invite_link}</code>\n\n"
    text += "Отправьте эту ссылку будущему администратору.\n"
    text += "После перехода он автоматически получит права админа."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="manage_admins")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "invite_admin_forward")
async def invite_admin_forward(call: CallbackQuery, state: FSMContext):
    from bot.states import InviteAdminState
    
    # Only owners can add admins
    if call.from_user.id not in config.OWNER_IDS:
        await call.answer("Только владельцы могут добавлять админов", show_alert=True)
        return
    
    text = "👔 <b>Добавление администратора</b>\n\n"
    text += "Перешлите мне сообщение от будущего админа.\n"
    text += "Я отправлю ему приглашение автоматически.\n\n"
    text += "Для отмены: /cancel"
    
    await call.message.answer(text)
    await state.set_state(InviteAdminState.waiting_for_contact)
    await call.answer()


@router.message(InviteAdminState.waiting_for_contact, F.forward_from)
async def process_admin_invite_contact(message: Message, state: FSMContext, session: AsyncSession):
    """Process forwarded message for admin invite"""
    from bot.utils.ui import UIMessages
    from bot.database.models import User, UserRole
    from sqlalchemy import select
    
    target_user = message.forward_from
    if not target_user:
        await message.answer("❌ Не удалось получить информацию о пользователе.\nПопробуйте переслать другое сообщение.")
        return
    
    target_id = target_user.id
    target_name = target_user.full_name
    target_username = target_user.username
    
    # Check if already admin
    stmt = select(User).where(User.tg_id == target_id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        await message.answer(f"⚠️ {target_name} уже является {existing.role}")
        await state.clear()
        return
    
    # Create admin record
    new_admin = User(
        tg_id=target_id,
        tg_username=target_username,
        full_name=target_name,
        role=UserRole.admin.value,
        created_by=message.from_user.id,
        is_active=True
    )
    session.add(new_admin)
    await session.flush()  # Flush to ensure the record exists before reload
    
    # Reload admin cache to update runtime config
    from bot.services.user_service import reload_admin_cache
    await reload_admin_cache(session)
    
    # Send invite to the new admin
    try:
        invite_text = f"🎉 <b>Вас добавили как администратора!</b>\n\n"
        invite_text += f"Вас пригласил: {message.from_user.full_name}\n\n"
        invite_text += "Теперь у вас есть доступ к панели администратора.\n"
        invite_text += "Нажмите /start для начала работы."
        
        await message.bot.send_message(target_id, invite_text)
        
        await message.answer(
            f"✅ <b>Администратор добавлен!</b>\n\n"
            f"👤 {target_name}\n"
            f"📲 @{target_username or '—'}\n"
            f"🆔 <code>{target_id}</code>\n\n"
            f"✉️ Приглашение отправлено!"
        )
    except Exception as e:
        await message.answer(
            f"✅ Администратор добавлен!\n\n"
            f"⚠️ Но не удалось отправить приглашение.\n"
            f"Пользователь должен сначала запустить бота (/start)"
        )
    
    await state.clear()




# === ADMIN MANAGEMENT (Owner Only) ===

@router.callback_query(F.data == "manage_admins")
async def manage_admins_menu(call: CallbackQuery, session: AsyncSession):
    """Show admin management interface (Owner only)"""
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.services.user_service import get_all_admins
    
    user_id = call.from_user.id
    
    if user_id not in config.OWNER_IDS:
        await call.answer("Только владелец может управлять админами", show_alert=True)
        return
    
    admins = await get_all_admins(session)
    
    text = UIMessages.header("Управление администраторами", "👔")
    text += f"Всего: <b>{len(admins)}</b>\n\n"
    
    kb_rows = []
    for admin in admins:
        role_emoji = "👑" if admin.role == "owner" else "👨‍💼"
        username_display = f"@{admin.tg_username}" if admin.tg_username else "—"
        kb_rows.append([InlineKeyboardButton(
            text=f"{role_emoji} {admin.full_name} ({username_display})",
            callback_data=f"admin_view_{admin.tg_id}"
        )])
    
    kb_rows.append([InlineKeyboardButton(text=f"{UIEmojis.ADD} Добавить админа", callback_data="admin_add_menu")])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()


@router.callback_query(F.data == "admin_add_menu")
async def admin_add_menu(call: CallbackQuery):
    """Choose how to add new admin"""
    from bot.utils.ui import UIMessages
    
    user_id = call.from_user.id
    if user_id not in config.OWNER_IDS:
        await call.answer("Только владелец может добавлять админов", show_alert=True)
        return
    
    text = UIMessages.header("Добавление администратора", "➕")
    text += "Выберите способ:\n\n"
    text += "🔹 <b>По Telegram ID</b> — если знаете ID пользователя\n"
    text += "🔹 <b>Переслать сообщение</b> — перешлите любое сообщение от будущего админа\n"
    text += "🔹 <b>Через invite-код</b> — создать ссылку-приглашение\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆔 По Telegram ID", callback_data="admin_add_by_id")],
        [InlineKeyboardButton(text="📨 Переслать сообщение", callback_data="admin_add_by_forward")],
        [InlineKeyboardButton(text="🔗 Через invite-код", callback_data="admin_add_by_invite")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="manage_admins")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "admin_add_by_id")
async def admin_add_by_id_start(call: CallbackQuery, state: FSMContext):
    """Start adding admin by ID"""
    user_id = call.from_user.id
    if user_id not in config.OWNER_IDS:
        await call.answer("Только владелец может добавлять админов", show_alert=True)
        return
    
    await call.message.edit_text(
        "🆔 <b>Добавление по Telegram ID</b>\n\n"
        "Введите Telegram ID пользователя (например, 123456789):\n\n"
        "Для отмены: /cancel"
    )
    await state.set_state(InviteAdminState.waiting_for_contact)
    await call.answer()


@router.callback_query(F.data == "admin_add_by_forward")
async def admin_add_by_forward_start(call: CallbackQuery, state: FSMContext):
    """Start adding admin by forwarding message (existing handler will process)"""
    user_id = call.from_user.id
    if user_id not in config.OWNER_IDS:
        await call.answer("Только владелец может добавлять админов", show_alert=True)
        return
    
    await call.message.edit_text(
        "📨 <b>Добавление через пересылку</b>\n\n"
        "Перешлите мне любое сообщение от будущего администратора.\n\n"
        "Для отмены: /cancel"
    )
    await state.set_state(InviteAdminState.waiting_for_contact)
    await call.answer()


@router.callback_query(F.data == "admin_add_by_invite")
async def admin_add_by_invite_start(call: CallbackQuery, session: AsyncSession):
    """Create admin invite code"""
    from bot.services.invite_service import generate_invite
    from bot.utils.ui import UIMessages
    
    user_id = call.from_user.id
    if user_id not in config.OWNER_IDS:
        await call.answer("Только владелец может добавлять админов", show_alert=True)
        return
    
    # Generate admin invite
    code = await generate_invite(session, user_id, role="admin")
    
    # Generate link
    bot_info = await call.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start={code}"
    
    text = UIMessages.success("Invite-код создан!")
    text += f"\n\n🔗 <b>Ссылка-приглашение:</b>\n<code>{invite_link}</code>\n\n"
    text += "Отправьте эту ссылку будущему администратору.\n"
    text += f"Срок действия: 7 дней"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Поделиться", url=f"https://t.me/share/url?url={invite_link}&text=Приглашение в панель администратора")],
        [InlineKeyboardButton(text="◀️ К списку админов", callback_data="manage_admins")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("admin_view_"))
async def admin_view_detail(call: CallbackQuery, session: AsyncSession):
    """View admin details and management options"""
    from bot.services.user_service import get_user_by_tg_id
    from bot.utils.ui import UIEmojis, UIMessages, format_date
    
    user_id = call.from_user.id
    if user_id not in config.OWNER_IDS:
        await call.answer("Только владелец может просматривать админов", show_alert=True)
        return
    
    admin_tg_id = int(call.data.split("_")[-1])
    admin = await get_user_by_tg_id(session, admin_tg_id)
    
    if not admin:
        await call.answer("Админ не найден", show_alert=True)
        return
    
    role_emoji = "👑" if admin.role == "owner" else "👨‍💼"
    role_name = "Владелец" if admin.role == "owner" else "Администратор"
    
    text = UIMessages.header(f"{role_emoji} {admin.full_name}", "")
    text += UIMessages.field("Роль", role_name)
    text += UIMessages.field("Telegram", f"@{admin.tg_username}" if admin.tg_username else "—")
    text += UIMessages.field("ID", f"<code>{admin.tg_id}</code>")
    text += UIMessages.field("Добавлен", format_date(admin.created_at))
    
    kb_rows = []
    
    # Can't deactivate yourself or other owners
    if admin.role != "owner" and admin.tg_id != user_id:
        kb_rows.append([InlineKeyboardButton(text="🗑 Деактивировать", callback_data=f"admin_deactivate_{admin.tg_id}")])
    
    kb_rows.append([InlineKeyboardButton(text="◀️ К списку", callback_data="manage_admins")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()


@router.callback_query(F.data.startswith("admin_deactivate_"))
async def admin_deactivate_confirm(call: CallbackQuery, session: AsyncSession):
    """Deactivate admin (with confirmation)"""
    from bot.services.user_service import deactivate_admin, reload_admin_cache
    from bot.utils.ui import UIMessages
    
    user_id = call.from_user.id
    if user_id not in config.OWNER_IDS:
        await call.answer("Только владелец может деактивировать админов", show_alert=True)
        return
    
    admin_tg_id = int(call.data.split("_")[-1])
    
    # Deactivate
    success = await deactivate_admin(session, admin_tg_id)
    
    if success:
        # Reload admin cache to update runtime config
        await reload_admin_cache(session)
        
        # Notify the deactivated admin
        try:
            await call.bot.send_message(
                admin_tg_id,
                "⚠️ <b>Ваш доступ к панели администратора отозван.</b>\n\n"
                "Если это ошибка, обратитесь к владельцу системы."
            )
        except Exception:
            pass  # User might have blocked bot
        
        await call.answer("✅ Администратор деактивирован", show_alert=True)
    else:
        await call.answer("❌ Не удалось деактивировать", show_alert=True)
    
    # Return to list
    await manage_admins_menu(call, session)


# === INVITE ADMIN (Existing forward-based handler) ===

@router.message(InviteAdminState.waiting_for_contact)
async def admin_invite_fallback(message: Message, state: FSMContext):
    """Fallback for non-forwarded messages"""
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Добавление админа отменено.")
        await state.clear()
        return
    
    await message.answer("⚠️ Перешлите мне сообщение от будущего админа или /cancel для отмены")



# === RSO MANAGEMENT (GLOBAL) ===

@router.callback_query(F.data == "manage_uk_rso")
async def manage_uk_rso_menu(call: CallbackQuery):
    from bot.utils.ui import UIEmojis, UIMessages
    
    text = UIMessages.header("Управление УК и РСО", UIEmojis.BUILDING)
    text += "Выберите раздел:\n\n"
    text += f"{UIEmojis.BUILDING} <b>Управляющие Компании</b>\nСписок компаний, к которым привязаны дома.\n\n"
    text += f"{UIEmojis.SETTINGS} <b>Провайдеры (РСО)</b>\nГлобальный список поставщиков услуг.\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.BUILDING} Список УК", callback_data="uk_list")],
        [InlineKeyboardButton(text=f"{UIEmojis.SETTINGS} Список РСО", callback_data="list_all_rsos")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "list_all_rsos")
async def list_all_rsos_handler(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.services.rso_service import get_all_rsos
    
    providers = await get_all_rsos(session)
    
    text = UIMessages.header("Список РСО (Провайдеры)", UIEmojis.SETTINGS)
    
    if not providers:
        text += UIMessages.info_box("Список провайдеров пуст")
    else:
        text += f"Всего провайдеров: <b>{len(providers)}</b>\n\n"
        for p in providers:
            icon = "⚡" if "электро" in p.service_type.lower() else "💧"
            if "газ" in p.service_type.lower(): icon = "🔥"
            
            text += f"{icon} <b>{p.name}</b>\n   ├ {p.service_type}\n   └ ИНН: {p.inn or '—'}\n\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.ADD} Добавить РСО", callback_data="add_rso_start")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="manage_uk_rso")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "add_rso_start")
async def add_rso_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddRSOState.waiting_for_name)
    await call.message.edit_text("🏭 <b>Название провайдера</b>\n\nВведите название (например, ПАО Мосэнерго):")
    await call.answer()
    
# ... (RSO Add process continues as before) ...
    
# === UK MANAGEMENT (RESTORED) ===
@router.callback_query(F.data == "uk_list")
async def uk_list_handler(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import UKCompany
    from sqlalchemy import select
    
    stmt = select(UKCompany).order_by(UKCompany.name)
    result = await session.execute(stmt)
    uks = result.scalars().all()
    
    text = UIMessages.header("Список Управляющих Компаний", UIEmojis.BUILDING)
    
    kb_rows = []
    if uks:
        for uk in uks:
            kb_rows.append([InlineKeyboardButton(text=f"{uk.name}", callback_data=f"uk_manage_{uk.id}")])
    else:
        text += "Список пуст."
    
    kb_rows.append([InlineKeyboardButton(text="➕ Добавить новую УК", callback_data="uk_add")])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="manage_uk_rso")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@router.callback_query(F.data == "uk_add")
async def uk_add_start(call: CallbackQuery, state: FSMContext):
    from bot.states import AddUKState
    await call.message.edit_text("🏢 <b>Новая УК</b>\n\nВведите название Управляющей Компании:")
    await state.set_state(AddUKState.waiting_for_name)
    await call.answer()

@router.message(AddUKState.waiting_for_name)
async def process_uk_name(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Отменено")
        await state.clear()
        return
        
    await state.update_data(name=message.text)
    await message.answer("📝 Введите ИНН (или '-' чтобы пропустить):")
    await state.set_state(AddUKState.waiting_for_inn)

@router.message(AddUKState.waiting_for_inn)
async def process_uk_inn(message: Message, state: FSMContext, session: AsyncSession):
    from bot.database.models import UKCompany
    from bot.utils.ui import UIMessages
    
    data = await state.get_data()
    name = data['name']
    inn = message.text.strip()
    if inn == "-": inn = None
    
    uk = UKCompany(name=name, inn=inn)
    session.add(uk)
    await session.commit()
    
    await message.answer(UIMessages.success(f"УК <b>{name}</b> добавлена!"),
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="◀️ К списку УК", callback_data="uk_list")]
                         ]))
    await state.clear()

@router.callback_query(F.data.startswith("uk_manage_"))
async def uk_manage_handler(call: CallbackQuery, session: AsyncSession):
    from bot.database.models import UKCompany
    from bot.utils.ui import UIEmojis, UIMessages
    
    uk_id = int(call.data.split("_")[-1])
    uk = await session.get(UKCompany, uk_id)
    
    if not uk:
        await call.answer("УК не найдена", show_alert=True)
        return

    text = UIMessages.header(uk.name, UIEmojis.BUILDING)
    if uk.inn: text += UIMessages.field("ИНН", uk.inn)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.SETTINGS} Настроить РСО для этой УК", callback_data=f"uk_rsos_{uk_id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="uk_list")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("uk_rsos_"))
async def uk_rsos_list(call: CallbackQuery, session: AsyncSession):
    from bot.services.rso_service import get_rso_by_uk, get_all_rsos, create_uk_rso_link
    from bot.utils.ui import UIEmojis, UIMessages
    
    uk_id = int(call.data.split("_")[-1])
    rsos = await get_rso_by_uk(session, uk_id)
    
    text = UIMessages.header("РСО управляющей компании", UIEmojis.SETTINGS)
    text += "Поставщики услуг, которые будут автоматически предлагаться при добавлении квартир от этой УК.\n"
    
    kb_rows = []
    for rso in rsos:
        kb_rows.append([InlineKeyboardButton(text=f"✅ {rso.name} ({rso.service_type})", callback_data="ignore")])
        
    kb_rows.append([InlineKeyboardButton(text="➕ Привязать РСО", callback_data=f"uk_link_rso_sel_{uk_id}")])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"uk_manage_{uk_id}")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@router.callback_query(F.data.startswith("uk_link_rso_sel_"))
async def uk_link_rso_select(call: CallbackQuery, session: AsyncSession):
    from bot.services.rso_service import get_all_rsos
    
    uk_id = int(call.data.split("_")[-1])
    
    # Get all providers to pick from
    providers = await get_all_rsos(session)
    
    kb_rows = []
    for p in providers:
        kb_rows.append([InlineKeyboardButton(text=f"➕ {p.name}", callback_data=f"uk_do_link_{uk_id}_{p.id}")])
        
    kb_rows.append([InlineKeyboardButton(text="🔙 Отмена", callback_data=f"uk_rsos_{uk_id}")])
    
    await call.message.edit_text("Выберите РСО для привязки к УК:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@router.callback_query(F.data.startswith("uk_do_link_"))
async def uk_link_rso_perform(call: CallbackQuery, session: AsyncSession):
    from bot.services.rso_service import create_uk_rso_link
    
    parts = call.data.split("_")
    uk_id = int(parts[3])
    provider_id = int(parts[4])
    
    await create_uk_rso_link(session, uk_id, provider_id)
    
    await call.answer("РСО привязана к УК!", show_alert=True)
    # Return to list
    await uk_rsos_list(call, session)



@router.message(AddRSOState.waiting_for_name)
async def process_rso_name(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Отменено")
        await state.clear()
        return

    await state.update_data(name=message.text)
    
    # Show service types
    types = [
        ("⚡ Электричество", "Электроснабжение"),
        ("💧 Вода", "Водоснабжение"), 
        ("🔥 Отопление", "Отопление"),
        ("🗑 Мусор", "Вывоз ТКО"),
        ("🔧 Содержание", "Содержание жилья"),
        ("🌐 Интернет", "Интернет"),
        ("📺 ТВ", "ТВ"),
        ("❓ Другое", "Прочее")
    ]
    
    kb_rows = []
    for label, val in types:
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"sel_rst_{val}")])
    
    await message.answer("Выберите тип услуги:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await state.set_state(AddRSOState.waiting_for_service_type)


@router.callback_query(AddRSOState.waiting_for_service_type, F.data.startswith("sel_rst_"))
async def process_rso_type(call: CallbackQuery, state: FSMContext):
    stype = call.data.split("_", 2)[2]
    await state.update_data(service_type=stype)
    
    await call.message.edit_text(f"Выбрано: {stype}\n\n📝 Введите ИНН организации (или '-' чтобы пропустить):")
    await state.set_state(AddRSOState.waiting_for_inn)
    await call.answer()


@router.message(AddRSOState.waiting_for_inn)
async def process_rso_inn(message: Message, state: FSMContext, session: AsyncSession):
    from bot.services.rso_service import create_provider
    from bot.utils.ui import UIMessages
    
    data = await state.get_data()
    name = data['name']
    stype = data['service_type']
    inn = message.text.strip()
    
    if inn == "-":
        inn = None
    
    await create_provider(session, name, stype, inn)
    
    await message.answer(UIMessages.success(f"Провайдер <b>{name}</b> создан!"), 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="◀️ К списку РСО", callback_data="manage_uk_rso")]
                         ]))
    await state.clear()



# === OBJECT RSO MANAGEMENT ===

@router.callback_query(F.data.startswith("obj_rso_manage_"))
async def manage_object_rso(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.services.rso_service import get_object_rso_links
    
    obj_id = int(call.data.split("_")[-1])
    links = await get_object_rso_links(session, obj_id)
    
    text = UIMessages.header("Провайдеры объекта", UIEmojis.BUILDING)
    
    if not links:
        text += UIMessages.info_box("Провайдеры не привязаны")
    else:
        text += f"Привязано провайдеров: <b>{len(links)}</b>\n\n"
        for link in links:
            provider = link.provider
            acc = link.personal_account or link.account_number or "Не указан"
            text += f"🔹 <b>{provider.name}</b>\n   Л/С: <code>{acc}</code>\n\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.ADD} Привязать провайдера", callback_data=f"link_rso_start_{obj_id}")],
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} К объекту", callback_data=f"obj_manage_{obj_id}")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("link_rso_start_"))
async def link_rso_start(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    from bot.services.rso_service import get_all_rsos
    
    obj_id = int(call.data.split("_")[-1])
    await state.update_data(obj_id=obj_id)
    
    providers = await get_all_rsos(session)
    if not providers:
        await call.answer("Нет доступных провайдеров. Сначала создайте их в общем меню.", show_alert=True)
        return

    kb_rows = []
    for p in providers:
        kb_rows.append([InlineKeyboardButton(text=f"{p.name} ({p.service_type})", callback_data=f"link_sel_{p.id}")])
        
    kb_rows.append([InlineKeyboardButton(text="Отмена", callback_data=f"obj_rso_manage_{obj_id}")])
    
    await call.message.edit_text("Выберите провайдера для привязки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await state.set_state(LinkRSOState.waiting_for_provider_selection)
    await call.answer()


@router.callback_query(LinkRSOState.waiting_for_provider_selection, F.data.startswith("link_sel_"))
async def link_rso_select(call: CallbackQuery, state: FSMContext):
    provider_id = int(call.data.split("_")[-1])
    await state.update_data(provider_id=provider_id)
    
    await call.message.edit_text("📝 Введите лицевой счет (номер абонента) для этого провайдера:")
    await state.set_state(LinkRSOState.waiting_for_account_number)
    await call.answer()


@router.message(LinkRSOState.waiting_for_account_number)
async def process_link_account(message: Message, state: FSMContext, session: AsyncSession):
    from bot.services.rso_service import assign_rso_to_object, update_rso_account_details
    from bot.utils.ui import UIMessages
    
    data = await state.get_data()
    obj_id = data['obj_id']
    provider_id = data['provider_id']
    account = message.text.strip()
    
    # Create link
    await assign_rso_to_object(session, obj_id, [provider_id])
    
    # Update account details
    await update_rso_account_details(session, obj_id, provider_id, account)
    
    await message.answer(UIMessages.success(f"Провайдер привязан! Л/С: {account}"), 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="◀️ К списку провайдеров", callback_data=f"obj_rso_manage_{obj_id}")]
                         ]))
    await state.clear()


# === ARCHIVE FUNCTIONALITY ===

@router.callback_query(F.data == "list_archived_tenants")
async def list_archived_tenants(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_date
    from bot.database.models import TenantStay, StayStatus
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    stmt = (
        select(TenantStay)
        .where(TenantStay.status == StayStatus.archived.value)
        .options(selectinload(TenantStay.tenant), selectinload(TenantStay.rental_object))
        .order_by(TenantStay.date_to.desc())
    )
    result = await session.execute(stmt)
    stays = result.scalars().all()
    
    text = UIMessages.header("Архив арендаторов", "📦")
    kb_rows = []
    
    if not stays:
        text += UIMessages.info_box("Архив пуст")
    else:
        text += f"Всего в архиве: <b>{len(stays)}</b>\n\n"
        for stay in stays[:10]:  # Show last 10
            date_str = format_date(stay.date_to) if stay.date_to else "?"
            kb_rows.append([InlineKeyboardButton(
                text=f"📦 {stay.tenant.full_name} (до {date_str})", 
                callback_data=f"archived_stay_{stay.id}"
            )])
    
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад к активным", callback_data="list_tenants")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("archived_stay_"))
async def view_archived_stay(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount, format_date
    from bot.database.models import TenantStay, RentCharge, ChargeStatus
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    
    stay_id = int(call.data.split("_")[2])
    
    stmt = (
        select(TenantStay)
        .where(TenantStay.id == stay_id)
        .options(selectinload(TenantStay.tenant), selectinload(TenantStay.rental_object))
    )
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if not stay:
        await call.answer("Запись не найдена", show_alert=True)
        return
    
    # Check for unpaid charges (debt)
    debt_stmt = select(func.sum(RentCharge.amount)).where(
        RentCharge.stay_id == stay_id,
        RentCharge.status == ChargeStatus.pending.value
    )
    debt_result = await session.execute(debt_stmt)
    debt = debt_result.scalar() or 0
    
    text = UIMessages.header(f"Архив: {stay.tenant.full_name}", "📦")
    text += UIMessages.field("Объект", stay.rental_object.address, UIEmojis.BUILDING)
    text += UIMessages.field("Период", f"{format_date(stay.date_from)} — {format_date(stay.date_to)}")
    text += UIMessages.field("Аренда", format_amount(stay.rent_amount), UIEmojis.MONEY)
    
    if debt > 0:
        text += f"\n⚠️ <b>ДОЛГ: {format_amount(debt)}</b>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Восстановить", callback_data=f"restore_stay_{stay_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="list_archived_tenants")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("restore_stay_"))
async def restore_stay(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages
    from bot.database.models import TenantStay, StayStatus, RentCharge, ChargeStatus
    from sqlalchemy import select, update, func
    
    stay_id = int(call.data.split("_")[2])
    
    # Check for debt
    debt_stmt = select(func.sum(RentCharge.amount)).where(
        RentCharge.stay_id == stay_id,
        RentCharge.status == ChargeStatus.pending.value
    )
    debt_result = await session.execute(debt_stmt)
    debt = debt_result.scalar() or 0
    
    # Restore the stay
    await session.execute(
        update(TenantStay)
        .where(TenantStay.id == stay_id)
        .values(status=StayStatus.active.value, date_to=None)
    )
    # Middleware commits
    
    if debt > 0:
        text = f"🔄 Арендатор восстановлен!\n\n⚠️ Внимание: у него есть долг!"
    else:
        text = "🔄 Арендатор успешно восстановлен!"
    
    await call.answer(text, show_alert=True)
    await list_archived_tenants(call)


@router.callback_query(F.data.startswith("archive_stay_"))
async def archive_stay(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages
    from bot.database.models import TenantStay, StayStatus
    from sqlalchemy import update
    from datetime import date
    
    stay_id = int(call.data.split("_")[2])
    
    await session.execute(
        update(TenantStay)
        .where(TenantStay.id == stay_id)
        .values(status=StayStatus.archived.value, date_to=date.today())
    )
    # Middleware commits
    
    await call.answer("📦 Арендатор архивирован", show_alert=True)


# === STAY MANAGEMENT (Enhanced) ===

@router.callback_query(F.data.startswith("stay_manage_"))
async def manage_stay(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages, format_amount, format_date
    from bot.database.models import TenantStay, RentCharge, ChargeStatus
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    
    logging.info(f"manage_stay called with data: {call.data}")
    
    stay_id = int(call.data.split("_")[2])
    
    stmt = (
        select(TenantStay)
        .where(TenantStay.id == stay_id)
        .options(selectinload(TenantStay.tenant), selectinload(TenantStay.rental_object))
    )
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if not stay:
        await call.answer("Запись не найдена", show_alert=True)
        return
    
    # Get debt info
    debt_stmt = select(func.sum(RentCharge.amount)).where(
        RentCharge.stay_id == stay_id,
        RentCharge.status == ChargeStatus.pending.value
    )
    debt_result = await session.execute(debt_stmt)
    debt = debt_result.scalar() or 0
    
    text = UIMessages.header(stay.tenant.full_name, UIEmojis.TENANT)
    
    # Show copyable contact info
    if stay.tenant.phone:
        text += f"📱 Телефон: <code>{stay.tenant.phone}</code> (нажмите для копирования)\n"
    if stay.tenant.tg_username:
        text += f"📲 Telegram: @{stay.tenant.tg_username}\n"
    if stay.tenant.tg_id:
        text += f"🆔 ID: <code>{stay.tenant.tg_id}</code>\n"
    
    text += "\n"
    text += UIMessages.field("Объект", stay.rental_object.address, UIEmojis.BUILDING)
    text += UIMessages.field("Аренда", format_amount(stay.rent_amount), UIEmojis.MONEY)
    text += UIMessages.field("День оплаты", f"{stay.rent_day}-е число")
    text += UIMessages.field("С даты", format_date(stay.date_from))
    
    if debt > 0:
        text += f"\n🔴 <b>Долг: {format_amount(debt)}</b>"
    else:
        text += f"\n🟢 <b>Долгов нет</b>"
    
    kb_buttons = [
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data=f"view_balance_{stay_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_stay_{stay_id}"),
            InlineKeyboardButton(text="📦 Архивировать", callback_data=f"archive_stay_{stay_id}")
        ],
    ]
    
    # Add mark-as-paid button if there are debts
    if debt > 0:
        kb_buttons.append([InlineKeyboardButton(text="✅ Отметить оплачено (наличные)", callback_data=f"mark_paid_{stay_id}")])
    
    # Only show "Write" button if tenant has valid Telegram ID
    if stay.tenant.tg_id and stay.tenant.tg_id > 0:
        kb_buttons.append([InlineKeyboardButton(text="💬 Написать", callback_data=f"message_tenant_{stay.tenant.tg_id}")])
    kb_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="list_tenants")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()



# === MARK AS PAID (Cash payment) ===
@router.callback_query(F.data.startswith("mark_paid_"))
async def mark_paid_callback(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages, format_amount
    from bot.database.models import RentCharge, ChargeStatus
    from sqlalchemy import select, update
    
    stay_id = int(call.data.split("_")[2])
    
    # Get pending charges
    stmt = select(RentCharge).where(
        RentCharge.stay_id == stay_id,
        RentCharge.status == ChargeStatus.pending.value
    )
    result = await session.execute(stmt)
    charges = result.scalars().all()
    
    if not charges:
        await call.answer("Нет неоплаченных начислений", show_alert=True)
        return
    
    total = sum(float(c.amount) for c in charges)
    
    # Mark all as paid
    await session.execute(
        update(RentCharge)
        .where(RentCharge.stay_id == stay_id, RentCharge.status == ChargeStatus.pending.value)
        .values(status=ChargeStatus.paid.value)
    )
    # Middleware commits
    
    await call.answer(f"✅ Отмечено оплачено: {format_amount(total)} (наличные)", show_alert=True)


# === VIEW BALANCE (New Financial UI) ===
@router.callback_query(F.data.startswith("view_balance_"))
async def view_balance_callback(call: CallbackQuery, session: AsyncSession):
    """Display detailed balance for a stay using BalanceService"""
    from bot.services.balance_service import get_stay_balance
    from bot.utils.ui import UIMessages, UIEmojis, format_amount, format_date
    
    stay_id = int(call.data.split("_")[2])
    
    try:
        balance = await get_stay_balance(session, stay_id)
    except Exception as e:
        await call.answer(f"❌ Ошибка: {e}", show_alert=True)
        return
    
    # Build balance report
    text = UIMessages.header("💰 Баланс", "")
    text += "\n"
    
    # Overall balance
    if balance.balance > 0:
        text += f"🔴 <b>Долг: {format_amount(balance.balance)}</b>\n\n"
    elif balance.balance < 0:
        text += f"🟢 <b>Аванс: {format_amount(abs(balance.balance))}</b>\n\n"
    else:
        text += f"✅ <b>Баланс: 0₽</b> (всё оплачено)\n\n"
    
    # Breakdown
    text += "📊 <b>Детализация:</b>\n"
    text += f"├ Начислено: {format_amount(balance.total_charged)}\n"
    text += f"│  ├ Аренда: {format_amount(balance.rent_charged)}\n"
    text += f"│  └ Комм.: {format_amount(balance.comm_charged)}\n"
    text += f"├ Оплачено: {format_amount(balance.total_paid)}\n"
    text += f"│  ├ Аренда: {format_amount(balance.rent_paid)}\n"
    text += f"│  └ Комм.: {format_amount(balance.comm_paid)}\n"
    
    if balance.advances > 0:
        text += f"└ Аванс (в счёт аренды): {format_amount(balance.advances)}\n"
    
    # List unpaid charges
    if balance.unpaid_charges:
        text += "\n\n🔴 <b>Неоплаченные начисления:</b>\n"
        for charge in balance.unpaid_charges[:5]:  # Show max 5
            month_str = format_date(charge.month)
            charge_type = "🏠 Аренда" if charge.type == "rent" else "⚡ Комм."
            
            if charge.status == "partial":
                text += f"├ {charge_type} за {month_str}\n"
                text += f"│  Начислено: {format_amount(charge.amount)}\n"
                text += f"│  Оплачено: {format_amount(charge.paid_amount)}\n"
                text += f"│  Остаток: {format_amount(charge.amount - charge.paid_amount)}\n"
            else:
                text += f"├ {charge_type} за {month_str}: {format_amount(charge.amount)}\n"
        
        if len(balance.unpaid_charges) > 5:
            text += f"\n... и ещё {len(balance.unpaid_charges) - 5}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Создать платёж вручную", callback_data=f"manual_payment_{stay_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"stay_manage_{stay_id}")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# === MANUAL PAYMENT (Admin creates payment manually) ===
@router.callback_query(F.data.startswith("manual_payment_"))
async def manual_payment_start(call: CallbackQuery, state: FSMContext):
    """Start manual payment creation flow"""
    
    stay_id = int(call.data.split("_")[2])
    await state.update_data(stay_id=stay_id)
    await state.set_state(ManualPaymentState.waiting_for_amount)
    
    await call.message.answer(
        "💵 <b>Создание платежа вручную</b>\n\n"
        "Введите сумму платежа (например: 30000):\n\n"
        "Для отмены: /cancel"
    )
    await call.answer()


@router.message(ManualPaymentState.waiting_for_amount)
async def manual_payment_amount(message: Message, state: FSMContext, session: AsyncSession):
    """Process manual payment amount and create payment"""
    from bot.services.payment_service import allocate_payment
    from bot.database.models import Payment, PaymentStatus, PaymentType
    from bot.utils.ui import UIMessages, format_amount
    
    # Cancel check
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Создание платежа отменено.")
        await state.clear()
        return
    
    # Validate amount
    try:
        model = AmountModel(amount=message.text)
        amount = model.amount
    except ValidationError:
        await message.answer("❌ Введите корректное число для суммы платежа.")
        return
    
    data = await state.get_data()
    stay_id = data.get("stay_id")
    
    # Create payment
    payment = Payment(
        stay_id=stay_id,
        amount=amount,
        total_amount=amount,
        type=PaymentType.rent.value,  # Default to rent
        status=PaymentStatus.confirmed.value,
        confirmed_at=datetime.now(timezone.utc),
        source="manual_admin"
    )
    session.add(payment)
    await session.flush()
    await session.refresh(payment)
    
    # Allocate payment
    try:
        allocations = await allocate_payment(session, payment.id)
        alloc_count = len(allocations)
        
        text = UIMessages.success(f"Платёж создан: {format_amount(amount)}")
        text += f"\n💰 Распределено на {alloc_count} начисление(ний)."
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Посмотреть баланс", callback_data=f"view_balance_{stay_id}")],
            [InlineKeyboardButton(text="◀️ К жильцу", callback_data=f"stay_manage_{stay_id}")]
        ])
        
        await message.answer(text, reply_markup=kb)
    except Exception as e:
        logging.error(f"Failed to allocate manual payment: {e}")
        await message.answer(f"✅ Платёж создан, но ошибка распределения: {e}")
    
    await state.clear()



# === MESSAGE TENANT (Admin sending message to tenant) ===
@router.callback_query(F.data.startswith("message_tenant_"))
async def message_tenant_start(call: CallbackQuery, state: FSMContext):
    """Start composing message to tenant"""
    from bot.states import AdminMessageState
    
    try:
        tg_id = int(call.data.split("_")[2])
    except (ValueError, IndexError):
        await call.answer("❌ Ошибка: неверный ID жильца", show_alert=True)
        return
    
    await state.update_data(target_tenant_tg_id=tg_id)
    
    await call.message.answer(
        "💬 <b>Напишите сообщение жильцу:</b>\n"
        "Введите текст или /cancel для отмены"
    )
    await state.set_state(AdminMessageState.waiting_for_text)
    await call.answer()


@router.message(AdminMessageState.waiting_for_text)
async def send_message_to_tenant(message: Message, state: FSMContext):
    """Send message from admin to tenant"""
    from bot.utils.ui import UIMessages
    
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Отправка сообщения отменена.")
        await state.clear()
        return
    
    data = await state.get_data()
    tg_id = data.get("target_tenant_tg_id")
    
    if not tg_id:
        await message.answer("❌ Ошибка: получатель не найден.")
        await state.clear()
        return
    
    msg_text = message.text or "[Без текста]"
    admin_name = message.from_user.full_name
    
    # Send message to tenant
    try:
        tenant_text = f"📩 <b>Сообщение от администратора</b>\n"
        tenant_text += f"👤 {admin_name}\n\n"
        tenant_text += f"💬 {msg_text}"
        
        await message.bot.send_message(tg_id, tenant_text)
        await message.answer(UIMessages.success("Сообщение отправлено жильцу!"))
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")
    
    await state.clear()


# === ADMIN CONTACTS PAGE ===
@router.callback_query(F.data == "admin_contacts")
async def admin_contacts_callback(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages
    from bot.database.models import AdminContact
    from sqlalchemy import select
    
    stmt = select(AdminContact).where(AdminContact.is_active == True).order_by(AdminContact.display_order)
    result = await session.execute(stmt)
    contacts = result.scalars().all()
    
    text = UIMessages.header("Контакты администрации", "📞")
    
    if not contacts:
        # Show default placeholder
        text += "Контакты не добавлены.\n\n"
        text += UIMessages.info_box("Для добавления контактов используйте /add_contact")
    else:
        for c in contacts:
            text += f"\n<b>{c.name}</b>"
            if c.role:
                text += f" — {c.role}"
            text += "\n"
            if c.phone:
                text += f"📱 <code>{c.phone}</code>\n"
            if c.telegram:
                text += f"📲 {c.telegram}\n"
            if c.email:
                text += f"📧 {c.email}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить контакт", callback_data="add_admin_contact")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="list_tenants")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# === ADD ADMIN CONTACT ===
@router.callback_query(F.data == "add_admin_contact")
async def add_admin_contact_start(call: CallbackQuery, state: FSMContext):
    from bot.states import AddContactState
    
    await call.message.answer("Введите имя контакта:\n(Например: Иван Петров — управляющий)")
    await state.set_state(AddContactState.waiting_for_name)
    await call.answer()


@router.message(AddContactState.waiting_for_name)
async def add_contact_name(message: Message, state: FSMContext):
    from bot.states import AddContactState
    
    await state.update_data(contact_name=message.text)
    await message.answer("Введите телефон контакта:\n(Например: +7 999 123-45-67)")
    await state.set_state(AddContactState.waiting_for_phone)


@router.message(AddContactState.waiting_for_phone)
async def add_contact_phone(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIMessages
    from bot.database.models import AdminContact
    
    from bot.schemas.validation import PhoneModel
    
    data = await state.get_data()
    name = data.get("contact_name", "")
    
    try:
        model = PhoneModel(phone=message.text)
        phone = model.phone
    except ValidationError:
         await message.answer("❌ Введите корректный номер телефона (например, +79001234567).")
         return
    
    contact = AdminContact(
        name=name,
        phone=phone,
        is_active=True
    )
    session.add(contact)
    # Middleware commits
    
    logging.info(f"Admin {message.from_user.id} added contact {name} ({phone})")
    
    await message.answer(UIMessages.success(f"Контакт добавлен:\n<b>{name}</b>\n📱 {phone}"))
    await state.clear()


# === NAVIGATION CALLBACKS ===

@router.callback_query(F.data == "list_tenants")
async def list_tenants_callback(call: CallbackQuery, session: AsyncSession):
    """Forward to tenants list"""
    await list_tenants_msg(call.message, session)
    await call.answer()


@router.callback_query(F.data == "list_objects")
async def list_objects_callback(call: CallbackQuery):
    """Forward to objects list"""
    await list_objects_msg(call.message)
    await call.answer()


@router.callback_query(F.data == "list_payments")
async def list_payments_callback(call: CallbackQuery):
    """Forward to payments list"""
    await list_payments_msg(call.message)
    await call.answer()


@router.callback_query(F.data == "report_monthly")
async def report_monthly(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages, format_amount
    from bot.database.models import Payment, PaymentStatus
    from sqlalchemy import select, func
    from datetime import date
    
    current_month = date.today().replace(day=1)
    
    stmt = select(func.sum(Payment.amount)).where(
        Payment.status == PaymentStatus.confirmed.value
    )
    result = await session.execute(stmt)
    total = result.scalar() or 0
    
    text = UIMessages.header("Платежи за месяц", "💰")
    text += f"Подтверждённые платежи: <b>{format_amount(total)}</b>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="reports_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "report_objects")
async def report_objects(call: CallbackQuery, session: AsyncSession):
    from bot.utils.ui import UIMessages, format_amount
    from bot.database.models import RentalObject, ObjectStatus, TenantStay, StayStatus, RentCharge, ChargeStatus
    from sqlalchemy import select, func
    from sqlalchemy.orm import selectinload
    
    # Get ALL objects with their active stays (if any)
    obj_result = await session.execute(
        select(RentalObject)
        .options(
            selectinload(RentalObject.stays)
            .selectinload(TenantStay.tenant)
        )
    )
    all_objects = obj_result.scalars().all()
    
    # Collect detailed info for each object
    objects_data = []
    total_income = 0
    occupied_count = 0
    free_count = 0
    
    for obj in all_objects:
        # Find active stay
        active_stay = next((s for s in obj.stays if s.status == StayStatus.active.value), None)
        
        if active_stay:
            occupied_count += 1
            tenant_name = active_stay.tenant.full_name if active_stay.tenant else "?"
            tenant_phone = active_stay.tenant.phone if active_stay.tenant else None
            rent = float(active_stay.rent_amount or 0)
            total_income += rent
            
            # Check payment status
            debt_stmt = select(func.count(RentCharge.id)).where(
                RentCharge.stay_id == active_stay.id,
                RentCharge.status == ChargeStatus.pending.value
            )
            debt_result = await session.execute(debt_stmt)
            has_debt = debt_result.scalar() > 0
            payment_status = "🔴 долг" if has_debt else "🟢 оплачено"
        else:
            free_count += 1
            tenant_name = None
            tenant_phone = None
            rent = 0
            payment_status = "➖"
        
        objects_data.append({
            "address": obj.address,
            "is_occupied": active_stay is not None,
            "tenant_name": tenant_name,
            "tenant_phone": tenant_phone,
            "rent": rent,
            "payment_status": payment_status
        })
    
    # Build report text
    text = UIMessages.header("Статус адресов", "🏠")
    text += f"Всего: <b>{len(objects_data)}</b>\n"
    text += f"🟢 Свободно: <b>{free_count}</b>\n"
    text += f"🔴 Занято: <b>{occupied_count}</b>\n\n"
    text += f"💰 <b>Ежемесячный доход: {format_amount(total_income)}</b>\n"
    text += "━" * 20 + "\n\n"
    
    for obj in objects_data:
        # Short address for display
        addr = obj["address"].split(",")[-1].strip() if "," in obj["address"] else obj["address"]
        
        if obj["is_occupied"]:
            text += f"🏠 <b>{addr}</b>\n"
            text += f"   👤 {obj['tenant_name']}\n"
            if obj["tenant_phone"]:
                text += f"   📱 <code>{obj['tenant_phone']}</code>\n"
            text += f"   💰 {format_amount(obj['rent'])} {obj['payment_status']}\n\n"
        else:
            text += f"🏠 <b>{addr}</b>\n"
            text += f"   ➖ Свободно\n\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="reports_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# --- Tax and Finance Handlers ---

@router.callback_query(F.data.startswith("edit_stay_tax_"))
async def edit_stay_tax_start(call: CallbackQuery, state: FSMContext):
    from bot.utils.ui import UIKeyboards, UIEmojis
    
    stay_id = int(call.data.split("_")[-1])
    await state.update_data(stay_id=stay_id)
    await state.set_state(EditStayState.waiting_for_tax_rate)
    
    await call.message.edit_text(
        "🔢 Введите новый процент налога (0-100, число):", 
        reply_markup=UIKeyboards.back_button(f"edit_stay_{stay_id}")
    )
    await call.answer()


@router.message(EditStayState.waiting_for_tax_rate)
async def stay_tax_submitted(message: Message, state: FSMContext, session: AsyncSession):
    from bot.utils.ui import UIEmojis, UIMessages
    from bot.database.models import TenantStay
    from sqlalchemy import update
    
    data = await state.get_data()
    stay_id = data.get("stay_id")
    
    try:
        new_tax = float(message.text.replace(",", ".").strip())
        if new_tax < 0 or new_tax > 100: raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректное число от 0 до 100.")
        return
        
    await session.execute(
        update(TenantStay)
        .where(TenantStay.id == stay_id)
        .values(tax_rate=new_tax)
    )
    # Middleware commits
    
    await state.clear()
    
    text = UIMessages.success(f"Налог обновлен: <b>{new_tax}%</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.BACK} К меню", callback_data=f"edit_stay_{stay_id}")]
    ])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("obj_stats_"))
async def show_obj_stats(call: CallbackQuery, session: AsyncSession):
    from bot.services.analytics_service import get_object_stats
    from datetime import date
    from bot.utils.ui import UIEmojis, UIMessages, format_amount
    
    obj_id = int(call.data.split("_")[-1])
    year = date.today().year
    
    stats = await get_object_stats(session, obj_id, year)
        
    text = f"📊 <b>Финансовый отчет ({year})</b>\n\n"
    
    text += f"🔹 <b>Начислено (Billed):</b>\n"
    text += f"   Всего: <b>{format_amount(stats.billed_total)}</b>\n"
    text += f"   ├ Аренда: {format_amount(stats.billed_base)}\n"
    text += f"   └ Налог: {format_amount(stats.billed_tax)}\n\n"
    
    text += f"💰 <b>Собрано (Collected):</b>\n"
    text += f"   Всего: <b>{format_amount(stats.collected_total)}</b>\n"
    text += f"   ├ Аренда: {format_amount(stats.collected_base)}\n"
    text += f"   └ Налог: <b>{format_amount(stats.collected_tax)}</b>\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"obj_manage_{obj_id}")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# --- Payment Cancellation ---

@router.callback_query(F.data.startswith("cancel_payment:"))
async def cancel_payment_start(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
):
    """Start payment cancellation process"""
    from bot.utils.ui import UIMessages
    from bot.states import CancelPaymentState
    
    payment_id = int(call.data.split(":")[1])
    
    # Save payment_id to state
    await state.update_data(cancel_payment_id=payment_id)
    
    # Ask for reason
    text = "❓ Укажите причину отмены платежа:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    
    await call.message.answer(text, reply_markup=kb)
    await state.set_state(CancelPaymentState.waiting_for_reason)
    await call.answer()


@router.message(CancelPaymentState.waiting_for_reason)
async def cancel_payment_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """Process cancellation reason and show confirmation"""
    from bot.utils.ui import UIMessages, UIEmojis
    
    reason = message.text
    data = await state.get_data()
    payment_id = data['cancel_payment_id']
    
    # Show confirmation
    text = UIMessages.header("Подтверждение отмены", UIEmojis.WARNING)
    text += f"\n💳 Платёж: #{payment_id}\n"
    text += f"📝 Причина: {reason}\n\n"
    text += "⚠️ Это действие:\n"
    text += "• Откатит распределение платежа\n"
    text += "• Вернёт начисления в статус 'неоплачено'\n"
    text += "• Пометит платёж как 'отменён'\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить отмену",
                callback_data=f"confirm_cancel:{payment_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_action"
            )
        ]
    ])
    
    await state.update_data(cancel_reason=reason)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("confirm_cancel:"))
async def confirm_cancel_payment(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
):
    """Execute payment cancellation"""
    from bot.utils.ui import UIMessages, UIEmojis
    from bot.services.payment_service import cancel_payment
    
    payment_id = int(call.data.split(":")[1])
    data = await state.get_data()
    reason = data.get('cancel_reason', 'Не указана')
    admin_id = call.from_user.id
    
    try:
        # Cancel payment
        success = await cancel_payment(
            session,
            payment_id,
            admin_id,
            reason
        )
        
        if success:
            text = UIMessages.success(f"Платёж #{payment_id} успешно отменён")
            text += f"\n\n📝 Причина: {reason}"
            await call.message.edit_text(text)
            
            logging.info(f"Payment {payment_id} cancelled by admin {admin_id}")
        
    except PermissionError as e:
        text = UIMessages.error(f"Нет прав: {e}")
        await call.message.edit_text(text)
    except ValueError as e:
        text = UIMessages.error(f"Ошибка: {e}")
        await call.message.edit_text(text)
    except Exception as e:
        text = UIMessages.error(f"Неизвестная ошибка: {e}")
        await call.message.edit_text(text)
        logging.error(f"Error cancelling payment {payment_id}: {e}")
    
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "cancel_action")
async def cancel_action_handler(call: CallbackQuery, state: FSMContext):
    """Cancel current action"""
    from bot.utils.ui import UIMessages
    
    await state.clear()
    await call.message.edit_text(UIMessages.info_box("Действие отменено"))
    await call.answer()


# --- Receipt Approval/Rejection ---

@router.callback_query(F.data.startswith("approve_receipt:"))
async def approve_receipt_handler(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
):
    """Approve receipt and ask for amount"""
    from bot.states import ApproveReceiptState
    
    payment_id = int(call.data.split(":")[1])
    
    # Save to state
    await state.update_data(approve_payment_id=payment_id)
    
    # Ask for amount
    text = "💰 Укажите сумму платежа (в рублях):"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    
    await call.message.answer(text, reply_markup=kb)
    await state.set_state(ApproveReceiptState.waiting_for_amount)
    await call.answer()


@router.message(ApproveReceiptState.waiting_for_amount)
async def process_receipt_amount(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """Process amount and confirm payment"""
    from bot.services.payment_service import allocate_payment
    from bot.utils.ui import UIMessages
    from bot.database.models import Payment
    from datetime import datetime
    
    try:
        amount = float(message.text.replace(',', '.').replace(' ', ''))
        
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше нуля")
            return
        
        data = await state.get_data()
        payment_id = data['approve_payment_id']
        
        # Get payment with stay
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        stmt = select(Payment).where(Payment.id == payment_id).options(
            selectinload(Payment.stay).selectinload(TenantStay.tenant)
        )
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        
        if not payment:
            await message.answer("❌ Платёж не найден")
            await state.clear()
            return
        
        # Update payment
        payment.amount = amount
        payment.total_amount = amount
        payment.status = 'confirmed'
        payment.confirmed_at = datetime.now()
        payment.confirmed_by = message.from_user.id
        
        await session.commit()
        
        # Allocate payment
        await allocate_payment(session, payment_id)
        
        # Notify tenant
        stay = payment.stay
        if stay and stay.tenant and stay.tenant.tg_id:
            tenant_text = UIMessages.success("Ваш платёж одобрен!")
            tenant_text += f"\n\n💰 Сумма: {amount:,.2f} ₽"
            tenant_text += f"\n📅 Дата: {datetime.now().strftime('%d.%m.%Y')}"
            
            try:
                await message.bot.send_message(
                    stay.tenant.tg_id,
                    tenant_text
                )
            except Exception as e:
                logging.error(f"Failed to notify tenant: {e}")
        
        # Confirm to admin
        text = UIMessages.success(f"Платёж #{payment_id} одобрен")
        text += f"\n\n💰 Сумма: {amount:,.2f} ₽"
        await message.answer(text)
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Неверный формат суммы. Введите число (например: 25000 или 25000.50)")


@router.callback_query(F.data.startswith("reject_receipt:"))
async def reject_receipt_handler(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession
):
    """Reject receipt and ask for reason"""
    from bot.states import RejectReceiptState
    
    payment_id = int(call.data.split(":")[1])
    
    await state.update_data(reject_payment_id=payment_id)
    
    text = "📝 Укажите причину отклонения чека:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    
    await call.message.answer(text, reply_markup=kb)
    await state.set_state(RejectReceiptState.waiting_for_reason)
    await call.answer()


@router.message(RejectReceiptState.waiting_for_reason)
async def process_reject_reason(
    message: Message,
    state: FSMContext,
    session: AsyncSession
):
    """Process rejection reason and notify tenant"""
    from bot.utils.ui import UIMessages
    from bot.database.models import Payment
    from datetime import datetime
    
    reason = message.text
    data = await state.get_data()
    payment_id = data['reject_payment_id']
    
    # Get payment with stay
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    stmt = select(Payment).where(Payment.id == payment_id).options(
        selectinload(Payment.stay).selectinload(TenantStay.tenant)
    )
    result = await session.execute(stmt)
    payment = result.scalar_one_or_none()
    
    if not payment:
        await message.answer("❌ Платёж не найден")
        await state.clear()
        return
    
    # Update payment
    payment.status = 'rejected'
    if not payment.meta_json:
        payment.meta_json = {}
    payment.meta_json['reject_reason'] = reason
    payment.meta_json['rejected_by'] = message.from_user.id
    payment.meta_json['rejected_at'] = datetime.now().isoformat()
    
    await session.commit()
    
    # Notify tenant
    stay = payment.stay
    if stay and stay.tenant and stay.tenant.tg_id:
        tenant_text = UIMessages.error("Ваш чек отклонён")
        tenant_text += f"\n\n📝 Причина: {reason}"
        tenant_text += "\n\n💡 Пожалуйста, загрузите новый чек с исправлениями"
        
        try:
            await message.bot.send_message(
                stay.tenant.tg_id,
                tenant_text
            )
        except Exception as e:
            logging.error(f"Failed to notify tenant: {e}")
    
    # Confirm to admin
    await message.answer(UIMessages.success(f"Чек #{payment_id} отклонён"))
    await state.clear()
