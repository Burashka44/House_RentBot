import string
import random
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import InviteCode, Tenant, TenantStatus
from bot.database.models import InviteCode, Tenant, TenantStatus

def _generate_random_code(length=8) -> str:
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

async def generate_invite(session: AsyncSession, admin_id: int, tenant_id: int = None, object_id: int = None, days_valid: int = 7, role: str = "tenant") -> str:
    """
    Generate a new unique invite code for a tenant or admin.
    """
    code = _generate_random_code()
    
    # Check uniqueness
    while True:
        stmt = select(InviteCode).where(InviteCode.code == code)
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            break
        code = _generate_random_code()
    
    invite = InviteCode(
        code=code,
        tenant_id=tenant_id,
        object_id=object_id,
        role=role,
        created_by=admin_id,
        expires_at=datetime.now() + timedelta(days=days_valid)
    )
    session.add(invite)
    # let middleware or caller commit
    await session.flush() 
    return code

async def redeem_invite(session: AsyncSession, code: str, tg_id: int, username: str = None, full_name: str = None) -> tuple[bool, str, any]:
    """
    Redeem an invite code.
    Returns: (Success, Message, Object)
    Object is Tenant for role='tenant', or User for role='admin'
    """
    from bot.database.models import User, UserRole
    from bot.config import config
    
    # 1. Find Code
    stmt = select(InviteCode).where(InviteCode.code == code)
    result = await session.execute(stmt)
    invite = result.scalar_one_or_none()
    
    if not invite:
        return False, "Неверный код приглашения", None
        
    if invite.is_used:
            return False, "Этот код уже использован", None
            
    if invite.expires_at and invite.expires_at < datetime.now():
        return False, "Срок действия кода истёк", None
    
    # 2. Logic based on Role
    if invite.role == "admin":
        # Check if already admin via User table
        stmt = select(User).where(User.tg_id == tg_id)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            return False, f"Вы уже зарегистрированы как {existing_user.role}", None

        # Create Admin User
        new_admin = User(
            tg_id=tg_id,
            tg_username=username,
            full_name=full_name or f"Admin {tg_id}",
            role=UserRole.admin.value,
            created_by=invite.created_by,
            is_active=True
        )
        session.add(new_admin)
        
        # Update Runtime Config (IMPORTANT)
        if tg_id not in config.ADMIN_IDS:
            config.ADMIN_IDS.append(tg_id)
            
        result_obj = new_admin

    else: # Tenant
        if not invite.tenant_id:
            return False, "Ошибка кода: не привязан жилец", None
    
        stmt_t = select(Tenant).where(Tenant.id == invite.tenant_id)
        res_t = await session.execute(stmt_t)
        tenant = res_t.scalar_one_or_none()
        
        if not tenant:
            return False, "Профиль жильца не найден", None
        
        # Check if linked (ignore negative temp IDs)
        if tenant.tg_id is not None and tenant.tg_id > 0:
            if tenant.tg_id == tg_id:
                return True, "Вы уже привязаны к этому профилю.", tenant
            else:
                return False, "Этот профиль уже привязан к другому Telegram аккаунту.", None

        tenant.tg_id = tg_id
        tenant.tg_username = username
        tenant.status = TenantStatus.active.value
        result_obj = tenant

    # 3. Link & Mark Used
    invite.is_used = True
    invite.used_at = datetime.now()
    
    # caller middleware commits
    
    welcome_name = result_obj.full_name if hasattr(result_obj, 'full_name') else "Пользователь"
    return True, f"Успешно! Добро пожаловать, {welcome_name}.", result_obj
