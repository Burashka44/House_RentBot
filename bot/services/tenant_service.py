from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Tenant, TenantStatus

async def get_tenant_by_tg_id(session: AsyncSession, tg_id: int) -> Tenant | None:
    stmt = select(Tenant).where(Tenant.tg_id == tg_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_or_create_tenant(session: AsyncSession, tg_user) -> Tenant:
    """
    Get or create tenant with atomic upsert to prevent race conditions.
    Uses INSERT ... ON CONFLICT to handle concurrent creation attempts.
    """
    from sqlalchemy.dialects.postgresql import insert
    
    # First try to get existing tenant
    tenant = await get_tenant_by_tg_id(session, tg_user.id)
    if tenant:
        return tenant
    
    # Use INSERT ... ON CONFLICT for atomic upsert
    stmt = insert(Tenant).values(
        tg_id=tg_user.id,
        tg_username=tg_user.username,
        full_name=tg_user.full_name,
        status=TenantStatus.active.value,
        personal_data_consent=False
    ).on_conflict_do_update(
        index_elements=['tg_id'],  # Unique constraint on tg_id
        set_={
            'tg_username': tg_user.username,  # Update username if changed
            'full_name': tg_user.full_name  # Update name if changed
        }
    ).returning(Tenant)
    
    result = await session.execute(stmt)
    tenant = result.scalar_one()
    await session.commit()
    
    return tenant

async def set_tenant_consent(session: AsyncSession, tenant_id: int, status: bool) -> Tenant:
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant:
        tenant.personal_data_consent = status
        if status:
            tenant.consent_date = datetime.now(timezone.utc)
            tenant.consent_version = "1.0"
        await session.commit()
    return tenant
