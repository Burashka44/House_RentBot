from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Tuple

# ========== UI Constants ==========
class UIEmojis:
    # Main Icons
    HOME = "🏠"
    MONEY = "💰"
    CHECK = "✅"
    CANCEL = "❌"
    BACK = "◀️"
    INFO = "ℹ️"
    SETTINGS = "⚙️"
    
    # Actions
    ADD = "➕"
    EDIT = "✏️"
    DELETE = "🗑️"
    SEARCH = "🔍"
    
    # Status
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    PENDING = "⏳"
    PROCESSING = "🔄"
    
    # People
    ADMIN = "👨‍💼"
    TENANT = "👤"
    GROUP = "👥"
    
    # Documents
    RECEIPT = "🧾"
    DOCUMENT = "📄"
    PHOTO = "📸"
    
    # Communication
    MESSAGE = "💬"
    BELL = "🔔"
    MAIL = "📧"
    
    # Finance
    PAYMENT = "💳"
    INVOICE = "🧾"
    WALLET = "💼"
    
    # Buildings
    BUILDING = "🏢"
    APARTMENT = "🏘️"
    KEY = "🔑"
    
    # Utilities/Services
    ELECTRIC = "⚡"
    WATER = "💧"
    HEATING = "🔥"
    INTERNET = "🌐"
    TRASH = "🗑️"
    TV = "📺"
    PHONE = "📞"
    GAS = "🔥"
    
    # Roles
    OWNER = "👑"
    MANAGER = "👔"
    
    # Reports
    CHART = "📊"
    CALENDAR = "📅"
    HISTORY = "📜"
    ARCHIVE = "📦"


class UIMessages:
    """Formatted message templates"""
    
    DIVIDER_FULL = "━" * 30
    DIVIDER_HALF = "─" * 15
    
    @staticmethod
    def header(title: str, emoji: str = "") -> str:
        """Create a formatted header"""
        if emoji:
            return f"\n{emoji} <b>{title}</b>\n{UIMessages.DIVIDER_FULL}\n"
        return f"\n<b>{title}</b>\n{UIMessages.DIVIDER_FULL}\n"
    
    @staticmethod
    def section(title: str) -> str:
        """Create a section title"""
        return f"\n<b>▪️ {title}</b>\n"
    
    @staticmethod
    def field(name: str, value: str, emoji: str = "") -> str:
        """Create a formatted field"""
        prefix = f"{emoji} " if emoji else "• "
        return f"{prefix}<b>{name}:</b> {value}\n"
    
    @staticmethod
    def info_box(text: str) -> str:
        """Create an info box"""
        return f"ℹ️ <i>{text}</i>"
    
    @staticmethod
    def success(text: str) -> str:
        """Success message"""
        return f"✅ {text}"
    
    @staticmethod
    def error(text: str) -> str:
        """Error message"""
        return f"❌ {text}"
    
    @staticmethod
    def warning(text: str) -> str:
        """Warning message"""
        return f"⚠️ {text}"


class UIKeyboards:
    """Common keyboard layouts"""
    
    @staticmethod
    def back_button(callback_data: str = "back") -> InlineKeyboardMarkup:
        """Single back button"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{UIEmojis.BACK} Назад", callback_data=callback_data)]
        ])
    
    @staticmethod
    def confirm_cancel(
        confirm_text: str = "Подтвердить",
        cancel_text: str = "Отмена",
        confirm_callback: str = "confirm",
        cancel_callback: str = "cancel"
    ) -> InlineKeyboardMarkup:
        """Confirm/Cancel buttons"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{UIEmojis.CHECK} {confirm_text}", callback_data=confirm_callback),
                InlineKeyboardButton(text=f"{UIEmojis.CANCEL} {cancel_text}", callback_data=cancel_callback)
            ]
        ])
    
    @staticmethod
    def menu_grid(items: List[Tuple[str, str]], columns: int = 2) -> InlineKeyboardMarkup:
        """Create a grid menu from list of (text, callback_data) tuples"""
        keyboard = []
        row = []
        
        for text, callback in items:
            row.append(InlineKeyboardButton(text=text, callback_data=callback))
            if len(row) == columns:
                keyboard.append(row)
                row = []
        
        if row:  # Add remaining buttons
            keyboard.append(row)
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    @staticmethod
    def main_reply_keyboard(is_admin: bool = False, is_owner: bool = False) -> ReplyKeyboardMarkup:
        """Create persistent main menu keyboard"""
        if is_owner:
            # Owner: Full access, clean layout
            keyboard = [
                [KeyboardButton(text="🏠 Адреса"), KeyboardButton(text="👥 Жильцы")],
                [KeyboardButton(text="💳 Платежи"), KeyboardButton(text="📊 Отчёты")],
                [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❔ Помощь")]
            ]
        elif is_admin:
            # Admin: Core operations
            keyboard = [
                [KeyboardButton(text="🏠 Адреса"), KeyboardButton(text="👥 Жильцы")],
                [KeyboardButton(text="💳 Платежи"), KeyboardButton(text="❔ Помощь")],
                [KeyboardButton(text="⚙️ Настройки")]
            ]
        else:
            # Tenant: Simple user-focused menu
            keyboard = [
                [KeyboardButton(text="📸 Загрузить чек")],
                [KeyboardButton(text="🏠 Моя квартира"), KeyboardButton(text="💰 Мои платежи")],
                [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="💬 Поддержка")]
            ]
        
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# === Helper Functions ===

def format_amount(amount: float) -> str:
    """Format amount with currency symbol"""
    if amount is None:
        return "—"
    return f"{amount:,.2f} ₽".replace(",", " ")


def format_date(date_obj) -> str:
    """Format date in Russian locale"""
    if not date_obj:
        return "—"
    months = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
    return f"{date_obj.day} {months[date_obj.month - 1]} {date_obj.year}"


def get_service_icon(service_type: str) -> str:
    """Get emoji icon for service type"""
    icons = {
        "electric": UIEmojis.ELECTRIC,
        "water": UIEmojis.WATER,
        "heating": UIEmojis.HEATING,
        "garbage": UIEmojis.TRASH,
        "internet": UIEmojis.INTERNET,
        "tv": UIEmojis.TV,
        "phone": UIEmojis.PHONE,
        "gas": UIEmojis.GAS,
        "other": "📦"
    }
    return icons.get(service_type, "📦")


def get_status_badge(status: str) -> str:
    """Get status badge emoji"""
    badges = {
        "active": "🟢",
        "pending": "🟡",
        "paid": "✅",
        "rejected": "❌",
        "archived": "📦",
        "overdue": "🔴"
    }
    return badges.get(status, "⚪")

