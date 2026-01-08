from datetime import date
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import RentalObject, ObjectSettings, TenantStay, StayStatus, ObjectStatus

async def create_object(session: AsyncSession, owner_id: int, address: str) -> RentalObject:
    """Create a new rental object with default settings."""
    # Check if exists? schema doesn't enforce unique address, but logical check might be good.
    # For MVP, just create.
    obj = RentalObject(owner_id=owner_id, address=address)
    session.add(obj)
    await session.flush() # to get ID
    
    # Create default settings
    settings = ObjectSettings(object_id=obj.id)
    session.add(settings)
    await session.commit()
    return obj

async def get_all_objects(session: AsyncSession, owner_id: Optional[int] = None) -> List[RentalObject]:
    stmt = select(RentalObject)
    if owner_id:
        stmt = stmt.where(RentalObject.owner_id == owner_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

async def create_stay(
    session: AsyncSession, 
    tenant_id: int, 
    object_id: int, 
    date_from: date, 
    rent_amount: float,
    rent_day: int,
    comm_day: int,
    tax_rate: float = 0.0
) -> TenantStay:
    
    # Check if object is free?
    # For MVP, assume Admin knows what they are doing, or just warn.
    # Let's set object status to occupied.
    
    stay = TenantStay(
        tenant_id=tenant_id,
        object_id=object_id,
        date_from=date_from,
        rent_amount=rent_amount,
        rent_day=rent_day,
        comm_day=comm_day,
        tax_rate=tax_rate
    )
    session.add(stay)
    
    await session.execute(
        update(RentalObject)
        .where(RentalObject.id == object_id)
        .values(status=ObjectStatus.occupied.value)
    )
    
    await session.commit()
    return stay

async def end_stay(session: AsyncSession, stay_id: int) -> TenantStay:
    stmt = select(TenantStay).where(TenantStay.id == stay_id)
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if stay:
        stay.date_to = date.today()
        stay.status = StayStatus.archived.value
        
        # Free the object
        await session.execute(
            update(RentalObject)
            .where(RentalObject.id == stay.object_id)
            .values(status=ObjectStatus.free.value)
        )
        
        await session.commit()
        
    return stay
