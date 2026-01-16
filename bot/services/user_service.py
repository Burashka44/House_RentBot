"""
User Service - Manage admins/owners/managers
"""
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import User, UserRole
from bot.database.core import AsyncSessionLocal


async def get_user_by_tg_id(session: AsyncSession, tg_id: int) -> Optional[User]:
    """Get user by Telegram ID"""
    stmt = select(User).where(User.tg_id == tg_id, User.is_active == True)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_admins(session: AsyncSession) -> List[User]:
    """Get all active admins/managers"""
    stmt = select(User).where(User.is_active == True).order_by(User.role, User.full_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_admin(
    session: AsyncSession,
    tg_id: int,
    full_name: str,
    role: UserRole = UserRole.admin,
    created_by: int = None,
    username: str = None
) -> User:
    """Create new admin/manager"""
    user = User(
        tg_id=tg_id,
        tg_username=username,
        full_name=full_name,
        role=role.value,
        created_by=created_by,
        is_active=True
    )
    session.add(user)
    await session.commit()
    return user


async def deactivate_admin(session: AsyncSession, tg_id: int) -> bool:
    """Deactivate admin (soft delete)"""
    from bot.config import config
    
    # SECURITY: Cannot deactivate OWNER
    if tg_id in config.OWNER_IDS:
        return False
    
    user = await get_user_by_tg_id(session, tg_id)
    if user:
        user.is_active = False
        await session.commit()
        return True
    return False


async def is_owner(tg_id: int) -> bool:
    """Check if user is owner"""
    async with AsyncSessionLocal() as session:
        user = await get_user_by_tg_id(session, tg_id)
        return user is not None and user.role == UserRole.owner.value


async def is_admin_or_owner(tg_id: int) -> bool:
    """Check if user is admin or owner"""
    async with AsyncSessionLocal() as session:
        user = await get_user_by_tg_id(session, tg_id)
        return user is not None and user.role in [UserRole.owner.value, UserRole.admin.value]


async def get_admin_ids() -> List[int]:
    """Get list of all active admin Telegram IDs"""
    async with AsyncSessionLocal() as session:
        admins = await get_all_admins(session)
        return [admin.tg_id for admin in admins]


async def reload_admin_cache(session: AsyncSession = None) -> int:
    """
    Reload admin list in runtime config from DB.
    
    This is the ONLY function that should modify config.ADMIN_IDS/OWNER_IDS
    after bot startup. Call this after adding/removing admins.
    
    Returns:
        Number of admins loaded
    """
    from bot.config import config
    from bot.database.core import AsyncSessionLocal
    
    if session is None:
        async with AsyncSessionLocal() as session:
            return await reload_admin_cache(session)
    
    admins = await get_all_admins(session)
    
    # Collect new lists from DB
    db_admin_ids = []
    db_owner_ids = []
    
    for user in admins:
        if user.role == 'owner':
            db_owner_ids.append(user.tg_id)
        db_admin_ids.append(user.tg_id)  # All users (including owners) are admins
    
    # Update config (preserve env-defined IDs, add DB IDs)
    config.ADMIN_IDS = list(set(config._env_admin_ids + db_admin_ids))
    config.OWNER_IDS = list(set(config._env_owner_ids + db_owner_ids))
    
    return len(admins)
