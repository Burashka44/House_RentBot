import string
import random
from datetime import datetime, timedelta, timezone
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
        expires_at=datetime.now(timezone.utc) + timedelta(days=days_valid)
    )
    session.add(invite)
    # let middleware or caller commit
    await session.flush() 
    return code

async def redeem_invite(session: AsyncSession, code: str, tg_id: int, username: str = None, full_name: str = None) -> tuple[bool, str, any]:
    """
    Redeem an invite code with atomic update to prevent race conditions.
    Returns: (Success, Message, Object)
    Object is Tenant for role='tenant', or User for role='admin'
    """
    from bot.database.models import User, UserRole
    from bot.config import config
    from sqlalchemy import update
    
    # ATOMIC UPDATE: Mark as used only if not already used
    # This prevents race condition where two users redeem same code
    stmt = (
        update(InviteCode)
        .where(
            InviteCode.code == code,
            InviteCode.is_used == False,  # Critical: only if not used
            InviteCode.expires_at > datetime.now(timezone.utc)  # And not expired
        )
        .values(
            is_used=True,
            used_at=datetime.now(timezone.utc)
        )
        .returning(InviteCode)
    )
    
    result = await session.execute(stmt)
    invite = result.scalar_one_or_none()
    
    if not invite:
        # Code not found, already used, or expired
        # Check which one to give better error message
        check_stmt = select(InviteCode).where(InviteCode.code == code)
        check_result = await session.execute(check_stmt)
        existing = check_result.scalar_one_or_none()
        
        if not existing:
            return False, "Неверный код приглашения", None
        if existing.is_used:
            return False, "Этот код уже использован", None
        if existing.expires_at and existing.expires_at < datetime.now(timezone.utc):
            return False, "Срок действия кода истёк", None
        
        # Shouldn't reach here, but just in case
        return False, "Код недействителен", None
    
    # 2. Logic based on Role
    if invite.role == "admin":
        # Check if already admin via User table
        stmt = select(User).where(User.tg_id == tg_id)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            # Rollback invite usage
            invite.is_used = False
            invite.used_at = None
            await session.commit()
            return False, f"Вы уже зарегистрированы как {existing_user.role}", None
        
        # NEW: Check if registered as tenant
        tenant_stmt = select(Tenant).where(Tenant.tg_id == tg_id)
        tenant_result = await session.execute(tenant_stmt)
        existing_tenant = tenant_result.scalar_one_or_none()
        
        if existing_tenant:
            # Rollback invite usage
            invite.is_used = False
            invite.used_at = None
            await session.commit()
            return False, (
                f"Вы уже зарегистрированы как жилец ({existing_tenant.full_name}). "
                f"Для получения прав администратора обратитесь к владельцу системы. "
                f"Ваш Telegram ID: {tg_id}"
            ), None

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
        
        # Reload admin cache to update runtime config
        from bot.services.user_service import reload_admin_cache
        await reload_admin_cache(session)
            
        result_obj = new_admin

    else: # Tenant
        if not invite.tenant_id:
            # Rollback invite usage
            invite.is_used = False
            invite.used_at = None
            await session.commit()
            return False, "Ошибка кода: не привязан жилец", None
    
        stmt_t = select(Tenant).where(Tenant.id == invite.tenant_id)
        res_t = await session.execute(stmt_t)
        tenant = res_t.scalar_one_or_none()
        
        if not tenant:
            # Rollback invite usage
            invite.is_used = False
            invite.used_at = None
            await session.commit()
            return False, "Профиль жильца не найден", None
        
        # Check if linked (ignore negative temp IDs)
        if tenant.tg_id is not None and tenant.tg_id > 0:
            if tenant.tg_id == tg_id:
                # Already linked to this user - idempotent
                return True, "Вы уже привязаны к этому профилю.", tenant
            else:
                # Rollback invite usage
                invite.is_used = False
                invite.used_at = None
                await session.commit()
                return False, "Этот профиль уже привязан к другому Telegram аккаунту.", None

        tenant.tg_id = tg_id
        tenant.tg_username = username
        tenant.status = TenantStatus.active.value
        result_obj = tenant

    # Commit all changes
    await session.commit()
    
    welcome_name = result_obj.full_name if hasattr(result_obj, 'full_name') else "Пользователь"
    return True, f"Успешно! Добро пожаловать, {welcome_name}.", result_obj
