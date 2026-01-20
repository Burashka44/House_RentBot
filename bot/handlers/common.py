from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from bot.services.tenant_service import set_tenant_consent
from sqlalchemy.ext.asyncio import AsyncSession
from bot.states import GuestState

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, tenant=None):
    from bot.utils.ui import UIEmojis, UIMessages, UIKeyboards
    from bot.config import config
    from bot.services.invite_service import redeem_invite
    
    user_id = message.from_user.id
    
    # Check for invite code in command args (deep linking)
    # When user clicks t.me/bot?start=CODE, Telegram sends "/start CODE"
    code = None
    if message.text and ' ' in message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            code = parts[1].strip()
    
    if code:
        username = message.from_user.username
        full_name = message.from_user.full_name
        
        success, msg, result_obj = await redeem_invite(session, code, user_id, username, full_name)
        
        if success:
            await message.answer(UIMessages.success(msg))
            # Refresh context (tenant or admin role might have changed)
            # We can't easily force-refresh middleware context here, so proper handling relies on the user continuing interaction
            
            # If it was admin invite
            from bot.database.models import User
            if isinstance(result_obj, User):
                is_admin = True
                is_owner = result_obj.role == "owner"
                
                text = UIMessages.header("Добро пожаловать!", UIEmojis.HOME)
                text += UIMessages.section("👨‍💼 Администратор")
                text += f"Вы успешно активировали права администратора.\n"
                text += UIMessages.section("Быстрые действия")
                text += f"Панель управления доступна по кнопке ниже.\n"
                
                await message.answer(text, reply_markup=UIKeyboards.main_reply_keyboard(is_admin, is_owner))
                await state.clear()
                return

            # If it was tenant invite
            elif result_obj: # Tenant
                tenant = result_obj # Use the freshly linked tenant
                # Fallthrough to standard tenant logic
        else:
            await message.answer(UIMessages.error(msg))
            # Fallthrough to normal check
            
    is_owner = user_id in config.OWNER_IDS
    is_admin = user_id in config.ADMIN_IDS or is_owner
    
    # Admin/Owner WITHOUT tenant record - show admin menu directly
    if is_admin and not tenant:
        text = UIMessages.header("Добро пожаловать!", UIEmojis.HOME)
        
        if is_owner:
            text += UIMessages.section("👑 Владелец")
            text += f"У вас полный доступ к системе.\n"
        else:
            text += UIMessages.section("👨‍💼 Администратор")
            text += f"Панель управления активна.\n"
        
        text += UIMessages.section("Быстрые действия")
        text += f"Используйте меню внизу экрана для навигации.\n"
        
        await message.answer(text, reply_markup=UIKeyboards.main_reply_keyboard(is_admin, is_owner))
        await state.clear()
        return
    
    # Guest (no tenant, not admin)
    if not tenant:
        text = UIMessages.header("Добро пожаловать!", UIEmojis.HOME)
        text += "Для доступа к системе требуется <b>Код приглашения</b>.\n"
        text += "Если у вас его нет, обратитесь к администратору.\n\n"
        text += "🔑 <b>Введите ваш код приглашения:</b>"
        
        await message.answer(text)
        await state.set_state(GuestState.waiting_for_code)
        return
    
    # Existing tenant with consent
    if tenant.personal_data_consent:
        text = UIMessages.header("Добро пожаловать!", UIEmojis.HOME)
        text += f"Здравствуйте, <b>{tenant.full_name}</b>!\n\n"
        
        if is_owner:
            text += UIMessages.section("👑 Владелец")
            text += f"У вас полный доступ к системе.\n"
        elif is_admin:
            text += UIMessages.section("👨‍💼 Администратор")
            text += f"Панель управления доступна по кнопке ниже.\n"

        text += UIMessages.section("Быстрые действия")
        text += f"Используйте меню внизу экрана для навигации.\n"
        
        await message.answer(text, reply_markup=UIKeyboards.main_reply_keyboard(is_admin, is_owner))
    else:
        await message.answer(UIMessages.warning("Требуется согласие на обработку данных"))

@router.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")

@router.message(Command("tenant_mode"))
async def cmd_tenant_mode(message: Message, state: FSMContext):
    """Switch to tenant mode (admins only - for testing UI)"""
    from bot.utils.ui import UIKeyboards, UIMessages
    from bot.config import config
    
    user_id = message.from_user.id
    is_admin = user_id in config.ADMIN_IDS or user_id in config.OWNER_IDS
    
    if not is_admin:
        await message.answer(
            UIMessages.error("Эта команда доступна только администраторам") + "\n\n" +
            UIMessages.info_box("Вы уже в режиме жильца. Используйте /help для справки.")
        )
        return
    
    await state.update_data(role_mode="tenant")
    await message.answer("🔄 Переключено на меню жильца", reply_markup=UIKeyboards.main_reply_keyboard(is_admin=False))

@router.message(Command("admin_mode"))
async def cmd_admin_mode(message: Message, state: FSMContext):
    """Switch to admin mode (admins only)"""
    from bot.utils.ui import UIKeyboards, UIMessages
    from bot.config import config
    
    user_id = message.from_user.id
    is_owner = user_id in config.OWNER_IDS
    is_admin = user_id in config.ADMIN_IDS or is_owner
    
    if not is_admin:
        await message.answer(
            UIMessages.error("У вас нет прав администратора") + "\n\n" +
            UIMessages.info_box("Эта команда доступна только для админов системы.")
        )
        return
    
    await state.update_data(role_mode="admin")
    await message.answer("🔄 Переключено на меню администратора", reply_markup=UIKeyboards.main_reply_keyboard(is_admin=is_admin, is_owner=is_owner))

@router.message(F.text == "❔ Помощь")
@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    from bot.config import config
    from bot.utils.ui import UIMessages, UIEmojis
    
    user_id = message.from_user.id
    is_admin = user_id in config.ADMIN_IDS
    is_owner = user_id in config.OWNER_IDS
    
    # Check current mode from state
    data = await state.get_data()
    current_mode = data.get("role_mode", "admin" if is_admin else "tenant")
    
    # Build help text based on current mode
    if current_mode == "tenant" or not is_admin:
        text = _build_tenant_help()
    else:
        text = _build_admin_help(is_owner)
    
    # Add mode switching buttons for admins
    kb_rows = []
    if is_admin:
        if current_mode == "admin":
            kb_rows.append([InlineKeyboardButton(text="👤 Переключиться на режим жильца", callback_data="switch_to_tenant")])
        else:
            kb_rows.append([InlineKeyboardButton(text="👨‍💼 Вернуться в режим админа", callback_data="switch_to_admin")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
    await message.answer(text, reply_markup=kb)


def _build_tenant_help() -> str:
    """Build comprehensive help for tenants"""
    from bot.utils.ui import UIMessages
    
    text = UIMessages.header("Справка для жильцов", "❔")
    
    text += UIMessages.section("📸 Загрузка чеков")
    text += "• Отправьте фото или файл чека боту\n"
    text += "• Бот распознает сумму и дату автоматически\n"
    text += "• После проверки платёж будет зачислен\n\n"
    
    text += UIMessages.section("💰 Мои платежи")
    text += "• Просмотр истории платежей\n"
    text += "• Статус каждого платежа (ожидает/подтверждён)\n"
    text += "• Остаток долга по аренде и ЖКХ\n\n"
    
    text += UIMessages.section("🏠 Моя квартира")
    text += "• Информация о квартире\n"
    text += "• Условия аренды (сумма, день оплаты)\n"
    text += "• Контакты управляющей компании\n\n"
    
    text += UIMessages.section("⚙️ Настройки")
    text += "• Уведомления о платежах\n"
    text += "• Напоминания об оплате\n"
    text += "• Управление данными\n\n"
    
    text += UIMessages.section("💬 Поддержка")
    text += "• Написать администратору\n"
    text += "• Сообщить о проблеме\n"
    text += "• Задать вопрос\n\n"
    
    text += UIMessages.section("🔑 Полезные команды")
    text += "<code>/menu</code> — Главное меню\n"
    text += "<code>/status</code> — Статус платежей\n"
    text += "<code>/id</code> — Узнать свой Telegram ID\n"
    text += "<code>/help</code> — Эта справка\n"
    
    return text


def _build_admin_help(is_owner: bool) -> str:
    """Build comprehensive help for admins"""
    from bot.utils.ui import UIMessages, UIEmojis
    
    text = UIMessages.header("Справка для администраторов", "👨‍💼")
    
    text += UIMessages.section("🏠 Управление адресами")
    text += "• Добавление новых объектов недвижимости\n"
    text += "• Редактирование информации об адресах\n"
    text += "• Просмотр списка всех объектов\n"
    text += "• Статус заселённости (🟢 оплачено | 🔴 долг | ➖ свободно)\n\n"
    
    text += UIMessages.section("👥 Управление жильцами")
    text += "• Создание профилей жильцов\n"
    text += "• Генерация invite-ссылок для активации\n"
    text += "• Заселение жильцов в объекты\n"
    text += "• Редактирование данных жильцов\n"
    text += "• Архивация неактивных жильцов\n\n"
    
    text += UIMessages.section("💳 Проверка платежей")
    text += "• Просмотр всех поступивших чеков\n"
    text += "• Подтверждение или отклонение платежей\n"
    text += "• Автоматическое распределение по начислениям (FIFO)\n"
    text += "• Ручная корректировка платежей\n\n"
    
    text += UIMessages.section("🏢 Управление УК/РСО")
    text += "• Добавление управляющих компаний (УК)\n"
    text += "• Справочник ресурсоснабжающих организаций (РСО)\n"
    text += "• Привязка РСО к УК и объектам\n"
    text += "• Указание лицевых счётов\n\n"
    
    if is_owner:
        text += UIMessages.section("👔 Управление админами (только для владельцев)")
        text += "• Список всех администраторов\n"
        text += "• Добавление админов (по ID, пересылка, invite)\n"
        text += "• Просмотр информации об админах\n"
        text += "• Деактивация админов\n\n"
    
    text += UIMessages.section("🔑 Полезные команды")
    text += "<code>/admin</code> — Панель администратора\n"
    text += "<code>/tenant_mode</code> — Переключиться в режим жильца (для тестирования)\n"
    text += "<code>/admin_mode</code> — Вернуться в режим админа\n"
    text += "<code>/id</code> — Узнать Telegram ID пользователя\n"
    text += "<code>/help</code> — Эта справка\n\n"
    
    text += UIMessages.info_box(
        "Используйте /tenant_mode чтобы протестировать интерфейс жильца. "
        "Это полезно для проверки UX без создания тестового аккаунта."
    )
    
    return text


@router.callback_query(F.data == "switch_to_tenant")
async def switch_to_tenant_mode(call: CallbackQuery, state: FSMContext):
    """Switch admin to tenant mode for testing"""
    from bot.utils.ui import UIKeyboards, UIMessages
    
    await state.update_data(role_mode="tenant")
    
    text = UIMessages.success("Режим жильца активирован")
    text += "\n\n" + UIMessages.info_box(
        "Теперь вы видите интерфейс так, как его видят жильцы. "
        "Это полезно для тестирования UX.\n\n"
        "Вернуться: /admin_mode или кнопка ниже."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💼 Вернуться в режим админа", callback_data="switch_to_admin")]
    ])
    
    await call.message.edit_text(text, reply_markup=kb)
    await call.bot.send_message(
        call.from_user.id,
        "🔄 Меню обновлено",
        reply_markup=UIKeyboards.main_reply_keyboard(is_admin=False)
    )
    await call.answer()


@router.callback_query(F.data == "switch_to_admin")
async def switch_to_admin_mode(call: CallbackQuery, state: FSMContext):
    """Switch back to admin mode (admins only)"""
    from bot.utils.ui import UIKeyboards, UIMessages
    from bot.config import config
    
    user_id = call.from_user.id
    is_owner = user_id in config.OWNER_IDS
    is_admin = user_id in config.ADMIN_IDS or is_owner
    
    # Security check: only admins can switch to admin mode
    if not is_admin:
        await call.answer("❌ У вас нет прав администратора", show_alert=True)
        return
    
    await state.update_data(role_mode="admin")
    
    text = UIMessages.success("Режим администратора активирован")
    text += "\n\n" + UIMessages.info_box("Вы вернулись в полнофункциональный режим админа.")
    
    await call.message.edit_text(text)
    await call.bot.send_message(
        call.from_user.id,
        "🔄 Меню обновлено",
        reply_markup=UIKeyboards.main_reply_keyboard(is_admin=is_admin, is_owner=is_owner)
    )
    await call.answer()




@router.callback_query(F.data == "accept_consent")
async def on_consent_accept(callback: CallbackQuery, tenant, session: AsyncSession):
    from bot.utils.ui import UIMessages, UIEmojis
    
    await set_tenant_consent(session, tenant.id, True)
    
    text = UIMessages.success("Спасибо! Ваше согласие принято")
    text += "\n\n" + UIMessages.info_box("Теперь вы можете пользоваться всеми функциями бота")
    text += f"\n\nИспользуйте команду /menu для начала работы"
    
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(GuestState.waiting_for_code)
async def process_invite_code(message: Message, state: FSMContext, session: AsyncSession):
    from bot.services.invite_service import redeem_invite
    from bot.utils.ui import UIMessages, UIEmojis, UIKeyboards
    
    code = message.text.strip() # Don't upper() automatically, codes might be case sensitive or custom
    tg_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    success, msg, result_obj = await redeem_invite(session, code, tg_id, username, full_name)
    
    if not success:
        await message.answer(UIMessages.error(msg))
        return
        
    await state.clear()
    
    # Success!
    await message.answer(UIMessages.success(msg))

    # Check if admin
    from bot.database.models import User
    if isinstance(result_obj, User):
        is_admin = True
        is_owner = result_obj.role == "owner"
        
        text = UIMessages.header("Добро пожаловать!", UIEmojis.HOME)
        text += UIMessages.section("👨‍💼 Администратор")
        text += f"Вы успешно активировали права администратора.\n"
        text += UIMessages.section("Быстрые действия")
        text += f"Панель управления доступна по кнопке ниже.\n"
        
        await message.answer(text, reply_markup=UIKeyboards.main_reply_keyboard(is_admin, is_owner))
        return

    # If Tenant
    tenant = result_obj
    if tenant and not tenant.personal_data_consent:
        # Trigger consent request manually (similar to middleware)
        from bot.middlewares.consent import ConsentMiddleware
        # Hacky way to reuse logic or just duplicate simple text
        # Let's duplicate simple text for robustness
        text = (
            "Для использования сервиса требуется ваше согласие\n"
            "на обработку персональных данных.\n\n"
            "• ФИО, телефон, фото, платежи\n\n"
            "Данные используются строго для работы сервиса."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="☑ Я согласен", callback_data="accept_consent")]
        ])
        await message.answer(text, reply_markup=kb)
    else:
        # Already consented (re-linking?)
        text = UIMessages.header("Главное меню", UIEmojis.HOME)
        text += "Добро пожаловать домой!"
        await message.answer(text, reply_markup=UIKeyboards.main_reply_keyboard(False))
