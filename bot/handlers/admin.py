from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Filter, Command
from aiogram.fsm.context import FSMContext
from bot.config import config
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.stay_service import create_object, get_all_objects, create_stay
from bot.services.tenant_service import get_tenant_by_tg_id
from bot.states import AddObjectState, AddStayState, EditObjectState, EditStayState, EditTenantState, AddTenantState, AddContactState, InviteAdminState, InviteTenantState, AdminMessageState
from datetime import date, datetime
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
    
    # List objects to select
    objects = await get_all_objects(session)
    
    if not objects:
        await message.answer(
            "⚠️ Нет адресов для заселения.\n"
            "Сначала добавьте адрес через меню Настройки → Добавить адрес"
        )
        await state.clear()
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
    await state.clear()

# --- Pending Payments Logic ---
from bot.database.models import Payment, PaymentStatus, PaymentType
from sqlalchemy import select, update

# list_payments callback moved to NAVIGATION CALLBACKS section (uses list_payments_msg)

@router.callback_query(F.data.startswith("pay_ok_"))
async def approve_payment(call: CallbackQuery, session: AsyncSession):
    payment_id = int(call.data.split("_")[-1])
    
    await session.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(status=PaymentStatus.confirmed, confirmed_at=datetime.now())
    )
    # Middleware commits
    
    await call.message.edit_text(f"✅ Платеж #{payment_id} подтвержден.")
    await call.answer()

@router.callback_query(F.data.startswith("pay_bad_"))
async def reject_payment(call: CallbackQuery, session: AsyncSession):
    payment_id = int(call.data.split("_")[-1])
    
    await session.execute(
        update(Payment)
        .where(Payment.id == payment_id)
        .values(status=PaymentStatus.rejected)
    )
    # Middleware commits
    
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
async def payments_menu(message: Message):
    # Redirect to payment check
    await list_payments_msg(message)


@router.message(F.text.contains("Отчёты"))
async def reports_menu_msg(message: Message):
    from bot.utils.ui import UIEmojis, UIMessages
    
    text = UIMessages.header("Отчёты", "📊")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Должники", callback_data="report_debtors")],
        [InlineKeyboardButton(text="💰 Платежи за месяц", callback_data="report_monthly")],
        [InlineKeyboardButton(text="🏠 Статус адресов", callback_data="report_objects")],
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
            "name": tenant_name,
            "address": short_addr,
            "amount": amount
        })
    
    text = UIMessages.header("Должники", "📋")
    
    if not debtors_data:
        text += UIMessages.success("Нет неоплаченных начислений")
    else:
        text += f"Всего долгов: <b>{format_amount(total)}</b>\n\n"
        
        for d in debtors_data:
            text += f"• <b>{d['name']}</b>\n   📍 {d['address']}\n   💰 {format_amount(d['amount'])}\n\n"
    
    await call.message.edit_text(text)
    await call.answer()


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
    # Middleware commits
    
    # Add to runtime config
    config.ADMIN_IDS.append(target_id)
    
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


@router.message(InviteAdminState.waiting_for_contact)
async def admin_invite_fallback(message: Message, state: FSMContext):
    """Fallback for non-forwarded messages"""
    if message.text and message.text.startswith("/"):
        await message.answer("❌ Добавление админа отменено.")
        await state.clear()
        return
    
    await message.answer("⚠️ Перешлите мне сообщение от будущего админа или /cancel для отмены")


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
            if c.notes:
                text += f"💬 {c.notes}\n"
    
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
async def list_tenants_callback(call: CallbackQuery):
    """Forward to tenants list"""
    await list_tenants_msg(call.message)
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
    
    await call.message.edit_text(text)
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
    
    await call.message.edit_text(text)
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

