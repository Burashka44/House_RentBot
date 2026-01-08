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
    # /start code123
    args = message.text.split()
    if len(args) > 1:
        code = args[1].strip()
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

@router.message(F.text == "❔ Помощь")
@router.message(Command("help"))
async def cmd_help(message: Message):
    from bot.config import config
    from bot.utils.ui import UIMessages, UIEmojis
    
    is_admin = message.from_user.id in config.ADMIN_IDS
    
    text = UIMessages.header("Справка", UIEmojis.INFO)
    
    text += UIMessages.section("Жильцу")
    text += f"/menu — Личный кабинет\n"
    text += f"/status — Статус оплаты\n"
    text += f"Отправьте <b>фото</b> или <b>файл</b> чека для оплаты.\n"
    
    if is_admin:
        text += UIMessages.section("Администратору")
        text += f"/admin — Панель управления\n"
        text += f"/id — Узнать свой ID\n"
        text += f"Используйте кнопки меню для управления.\n"
        
    await message.answer(text)

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
