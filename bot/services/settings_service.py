"""
Tenant Settings Service - Manage tenant preferences
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import TenantSettings, ServiceSubscription, CommProvider



async def get_tenant_settings(session: AsyncSession, tenant_id: int) -> TenantSettings:
    """Get or create tenant settings"""
    stmt = select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    result = await session.execute(stmt)
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = TenantSettings(tenant_id=tenant_id)
        session.add(settings)
        await session.commit()
    
    return settings


async def update_tenant_settings(
    session: AsyncSession,
    tenant_id: int,
    notifications_enabled: bool = None,
    rent_notifications: bool = None,
    comm_notifications: bool = None,
    reminder_days: int = None
) -> TenantSettings:
    """Update tenant settings"""
    settings = await get_tenant_settings(session, tenant_id)
    
    if notifications_enabled is not None:
        settings.notifications_enabled = notifications_enabled
    if rent_notifications is not None:
        settings.rent_notifications = rent_notifications
    if comm_notifications is not None:
        settings.comm_notifications = comm_notifications
    if reminder_days is not None:
        settings.reminder_days = reminder_days
    
    await session.commit()
    return settings


async def get_service_subscriptions(session: AsyncSession, stay_id: int) -> list:
    """Get all service subscriptions for a stay"""
    stmt = (
        select(ServiceSubscription)
        .where(ServiceSubscription.stay_id == stay_id)
        .join(CommProvider)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def toggle_service(session: AsyncSession, stay_id: int, provider_id: int, enabled: bool) -> ServiceSubscription:
    """Enable/disable a service for tenant"""
    stmt = select(ServiceSubscription).where(
        ServiceSubscription.stay_id == stay_id,
        ServiceSubscription.provider_id == provider_id
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()
    
    if not sub:
        sub = ServiceSubscription(
            stay_id=stay_id,
            provider_id=provider_id,
            enabled=enabled
        )
        session.add(sub)
    else:
        sub.enabled = enabled
    
    await session.commit()
    return sub


async def create_default_subscriptions(session: AsyncSession, stay_id: int, object_id: int):
    """Create default subscriptions for all providers of the object"""
    stmt = select(CommProvider).where(CommProvider.object_id == object_id, CommProvider.active == True)
    result = await session.execute(stmt)
    providers = result.scalars().all()
    
    for provider in providers:
        sub = ServiceSubscription(
            stay_id=stay_id,
            provider_id=provider.id,
            enabled=True,
            account_number=provider.account_number
        )
        session.add(sub)
    
    await session.commit()
