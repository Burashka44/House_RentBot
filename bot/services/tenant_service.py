from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Tenant, TenantStatus

async def get_tenant_by_tg_id(session: AsyncSession, tg_id: int) -> Tenant | None:
    stmt = select(Tenant).where(Tenant.tg_id == tg_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_or_create_tenant(session: AsyncSession, tg_user) -> Tenant:
    tenant = await get_tenant_by_tg_id(session, tg_user.id)
    if not tenant:
        tenant = Tenant(
            tg_id=tg_user.id,
            tg_username=tg_user.username,
            full_name=tg_user.full_name,
            status=TenantStatus.active.value,
            personal_data_consent=False
        )
        session.add(tenant)
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
