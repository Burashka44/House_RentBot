from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.handlers.admin import AdminFilter
from bot.utils.ui import UIEmojis, UIMessages, UIKeyboards

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

# --- States ---
class AddUKState(StatesGroup):
    waiting_for_name = State()
    waiting_for_inn = State()

class AddRSOState(StatesGroup):
    waiting_for_name = State()
    waiting_for_type = State()

# --- Entry Point ---
@router.callback_query(F.data == "manage_uk_rso")
async def manage_uk_rso_menu(call: CallbackQuery, session: AsyncSession):
    text = UIMessages.header("Управление УК и РСО", UIEmojis.BUILDING)
    text += "Здесь можно добавлять управляющие компании и настраивать их список РСО.\n\n"
    text += "Это нужно для того, чтобы при добавлении адресов автоматически предлагать правильных поставщиков."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Список УК", callback_data="uk_list")],
        [InlineKeyboardButton(text="➕ Добавить УК", callback_data="uk_add")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb)
# --- UK Handlers ---
from bot.database.models import UKCompany

@router.callback_query(F.data == "uk_list")
async def uk_list_handler(call: CallbackQuery, session: AsyncSession):
    stmt = select(UKCompany).order_by(UKCompany.name)
    result = await session.execute(stmt)
    uks = result.scalars().all()
    
    text = UIMessages.header("Список Управляющих Компаний", UIEmojis.BUILDING)
    
    kb_rows = []
    for uk in uks:
        kb_rows.append([InlineKeyboardButton(text=f"{uk.name}", callback_data=f"uk_manage_{uk.id}")])
    
    kb_rows.append([InlineKeyboardButton(text="➕ Добавить новую", callback_data="uk_add")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="manage_uk_rso")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@router.callback_query(F.data == "uk_add")
async def uk_add_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer(
        UIMessages.info_box("Введите название Управляющей Компании:")
    )
    await state.set_state(AddUKState.waiting_for_name)
    await call.answer()

@router.message(AddUKState.waiting_for_name)
async def uk_add_name_submitted(message: Message, state: FSMContext):
    if not message.text:
         return
    
    await state.update_data(name=message.text)
    await message.answer("Введите ИНН (или отправьте '-' чтобы пропустить):")
    await state.set_state(AddUKState.waiting_for_inn)

@router.message(AddUKState.waiting_for_inn)
async def uk_add_inn_submitted(message: Message, state: FSMContext, session: AsyncSession):
    import logging
    data = await state.get_data()
    name = data['name']
    inn = message.text.strip()
    if inn == "-": inn = None
    
    uk = UKCompany(name=name, inn=inn)
    session.add(uk)
    # Middleware commits
    
    logging.info(f"Admin {message.from_user.id} created UK '{name}' (INN: {inn})")
    
    await message.answer(UIMessages.success(f"УК <b>{name}</b> успешно добавлена!"))
    await state.clear()
    
    # Show list again? Or menu? Let's show simple text
    # Actually, let's redirect to the UK management page for the new UK? 
    # Need to flush to get ID first? DbSessionMiddleware does explicit commit/rollback AFTER handler.
    # So we don't have ID unless we flush manually.
    
    await session.flush()
    # Now we can show management menu
    await uk_manage_handler_direct(message, uk.id)

    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

async def uk_manage_handler_direct(message: Message, uk_id: int):
    # This is a bit hacky to show menu from message, reusing UI logic
    # Ideally should use state or just simple message
    text = f"Управление УК #{uk_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.SETTINGS} Привязанные РСО", callback_data=f"uk_rsos_{uk_id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="uk_list")]
    ])
    await message.answer(text, reply_markup=kb)


# --- RSO Handlers ---
from bot.database.models import CommProvider, CommServiceType, UKRSOLink
from bot.services.rso_service import get_rso_by_uk, create_uk_rso_link

@router.callback_query(F.data.startswith("uk_rsos_"))
async def uk_rsos_list(call: CallbackQuery, session: AsyncSession):
    uk_id = int(call.data.split("_")[-1])
    
    # Get assigned RSOs
    rsos = await get_rso_by_uk(session, uk_id)
    
    text = UIMessages.header("РСО этой УК", UIEmojis.SETTINGS)
    text += "Поставщики услуг, которые будут автоматически предлагаться для адресов этой УК.\n"
    
    kb_rows = []
    for rso in rsos:
        # Maybe allow unlinking later?
        kb_rows.append([InlineKeyboardButton(text=f"{rso.name} ({rso.service_type})", callback_data="ignore")])
        
    kb_rows.append([InlineKeyboardButton(text="➕ Добавить РСО", callback_data=f"uk_add_rso_{uk_id}")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад к УК", callback_data=f"uk_manage_{uk_id}")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@router.callback_query(F.data.startswith("uk_add_rso_"))
async def add_rso_start(call: CallbackQuery, state: FSMContext):
    uk_id = int(call.data.split("_")[-1])
    await state.update_data(uk_id=uk_id)
    
    text = UIMessages.info_box("Выберите тип услуги:")
    
    # Common types
    types = [
        ("⚡ Электричество", CommServiceType.electric),
        ("💧 Вода", CommServiceType.water),
        ("🔥 Отопление", CommServiceType.heating),
        ("🗑️ ТБО (Мусор)", CommServiceType.garbage),
        ("🌐 Интернет", CommServiceType.internet),
        ("🧹 Капремонт/Содерж.", CommServiceType.other)
    ]
    
    kb_rows = []
    for label, val in types:
        kb_rows.append([InlineKeyboardButton(text=label, callback_data=f"sel_rso_type_{val.value}")])
        
    kb_rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"uk_rsos_{uk_id}")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await state.set_state(AddRSOState.waiting_for_type)
    await call.answer()

@router.callback_query(AddRSOState.waiting_for_type, F.data.startswith("sel_rso_type_"))
async def add_rso_type_selected(call: CallbackQuery, state: FSMContext):
    service_type = call.data.split("_")[-1]
    await state.update_data(service_type=service_type)
    
    await call.message.edit_text(
        f"Тип: {service_type}\n\nВведите название организации (например, 'Мосэнергосбыт'):"
    )
    await state.set_state(AddRSOState.waiting_for_name)
    await call.answer()

@router.message(AddRSOState.waiting_for_name)
async def add_rso_name_submitted(message: Message, state: FSMContext, session: AsyncSession):
    import logging
    data = await state.get_data()
    uk_id = data['uk_id']
    service_type = data['service_type']
    name = message.text.strip()
    
    # 1. Create Provider (Global/Linked to UK, so object_id is None)
    provider = CommProvider(
        object_id=None,
        service_type=service_type,
        name=name,
        active=True
    )
    session.add(provider)
    await session.flush() # get ID
    
    # 2. Link to UK
    await create_uk_rso_link(session, uk_id, provider.id)
    
    logging.info(f"Admin {message.from_user.id} created RSO '{name}' ({service_type}) for UK #{uk_id}")
    
    await message.answer(UIMessages.success(f"РСО <b>{name}</b> добавлена к УК!"))
    await state.clear()
    
    # Return to RSO list
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.SETTINGS} К списку РСО", callback_data=f"uk_rsos_{uk_id}")]
    ])
    await message.answer("Вернуться к списку:", reply_markup=kb)


@router.callback_query(F.data.startswith("uk_manage_"))
async def uk_manage_handler(call: CallbackQuery, session: AsyncSession):
    uk_id = int(call.data.split("_")[-1])
    uk = await session.get(UKCompany, uk_id)
    
    if not uk:
        await call.answer("УК не найдена", show_alert=True)
        return

    text = UIMessages.header(uk.name, UIEmojis.BUILDING)
    if uk.inn: text += UIMessages.field("ИНН", uk.inn)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{UIEmojis.SETTINGS} Привязанные РСО", callback_data=f"uk_rsos_{uk_id}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="uk_list")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


# --- Object RSO Management (Account Numbers) ---
from bot.database.models import RentalObject, ObjectRSOLink
from bot.services.rso_service import get_object_rso_links, update_rso_account, assign_rso_to_object, get_all_rsos

class EditAccState(StatesGroup):
    waiting_for_acc_number = State()

@router.callback_query(F.data.startswith("obj_rso_manage_"))
async def obj_rso_manage(call: CallbackQuery, session: AsyncSession):
    obj_id = int(call.data.split("_")[-1])
    obj = await session.get(RentalObject, obj_id)
    
    if not obj:
        await call.answer("Объект не найден", show_alert=True)
        return

    # Get links
    links = await get_object_rso_links(session, obj_id)
    
    text = UIMessages.header(f"РСО объекта: {obj.address}", UIEmojis.SETTINGS)
    text += "Настройте лицевые счета дял каждого поставщика.\n"
    
    kb_rows = []
    
    if not links:
        text += f"\n{UIEmojis.WARNING} Нет привязанных поставщиков."
    else:
        for link in links:
            prov = link.provider
            acc = link.account_number if link.account_number else "❌ Не задан"
            btn_text = f"{prov.service_type}: {prov.name} | ЛС: {acc}"
            kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"edit_acc_{obj_id}_{prov.id}")])
    
    # Add new RSO logic (Simplified: Show all available global providers?)
    # For now just Back
    kb_rows.append([InlineKeyboardButton(text="➕ Добавить РСО (Все)", callback_data=f"add_obj_rso_{obj_id}")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад к объекту", callback_data=f"obj_manage_{obj_id}")])
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@router.callback_query(F.data.startswith("edit_acc_"))
async def edit_acc_start(call: CallbackQuery, state: FSMContext, session: AsyncSession):
    # data: edit_acc_{obj_id}_{prov_id}
    parts = call.data.split("_")
    obj_id = int(parts[2])
    prov_id = int(parts[3])
    
    await state.update_data(obj_id=obj_id, prov_id=prov_id)
    
    provider = await session.get(CommProvider, prov_id)
    
    await call.message.answer(
        f"Введите номер лицевого счета для <b>{provider.name}</b> ({provider.service_type}):",
        reply_markup=UIKeyboards.cancel_button() 
    )
    await state.set_state(EditAccState.waiting_for_acc_number)
    await call.answer()

@router.message(EditAccState.waiting_for_acc_number)
async def edit_acc_save(message: Message, state: FSMContext, session: AsyncSession):
    if message.text and message.text.startswith("/"):
        await message.answer("Отменено.")
        await state.clear()
        return

    data = await state.get_data()
    acc_num = message.text.strip()
    
    success = await update_rso_account(session, data['obj_id'], data['prov_id'], acc_num)
    
    if success:
        await message.answer(UIMessages.success(f"Лицевой счет <b>{acc_num}</b> сохранен!"))
    else:
        await message.answer(UIMessages.error("Ошибка сохранения."))
        
    await state.clear()
    
    # Back to menu
    await obj_rso_manage_direct(message, session, data['obj_id'])

# Helper to return to menu from message
async def obj_rso_manage_direct(message: Message, session: AsyncSession, obj_id: int):
    # Re-fetch data and show menu (Duplicate logic, ideally refactor to shared func)
    # For speed, reusing simple call to handler if we could construct CallbackQuery, but we can't easily.
    # So manual Text response.
    links = await get_object_rso_links(session, obj_id)
    obj = await session.get(RentalObject, obj_id)
    
    text = UIMessages.header(f"РСО объекта: {obj.address}", UIEmojis.SETTINGS)
    text += "Настройте лицевые счета.\n"
    
    kb_rows = []
    for link in links:
        prov = link.provider
        acc = link.account_number if link.account_number else "❌ Не задан"
        btn_text = f"{prov.service_type}: {prov.name} | ЛС: {acc}"
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"edit_acc_{obj_id}_{prov.id}")])
    
    kb_rows.append([InlineKeyboardButton(text="➕ Добавить РСО (Все)", callback_data=f"add_obj_rso_{obj_id}")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад к объекту", callback_data=f"obj_manage_{obj_id}")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


@router.callback_query(F.data.startswith("add_obj_rso_"))
async def add_obj_rso_list(call: CallbackQuery, session: AsyncSession):
    obj_id = int(call.data.split("_")[-1])
    
    # For now, list ALL available active providers (Global ones)
    stmt = select(CommProvider).where(CommProvider.active == True).order_by(CommProvider.service_type)
    result = await session.execute(stmt)
    all_providers = result.scalars().all()
    
    # Filter out already linked?
    existing_links = await get_object_rso_links(session, obj_id)
    linked_ids = [l.provider_id for l in existing_links]
    
    kb_rows = []
    for prov in all_providers:
        if prov.id in linked_ids:
            continue
        kb_rows.append([InlineKeyboardButton(text=f"➕ {prov.service_type}: {prov.name}", callback_data=f"link_rso_{obj_id}_{prov.id}")])
        
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"obj_rso_manage_{obj_id}")])
    
    await call.message.edit_text("Выберите РСО для добавления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    await call.answer()

@router.callback_query(F.data.startswith("link_rso_"))
async def link_rso_action(call: CallbackQuery, session: AsyncSession):
    # link_rso_{obj_id}_{prov_id}
    parts = call.data.split("_")
    obj_id = int(parts[2])
    prov_id = int(parts[3])
    
    await assign_rso_to_object(session, obj_id, [prov_id])
    
    await call.answer("РСО добавлено!", show_alert=False)
    # Refresh list
    await obj_rso_manage(call, session)

