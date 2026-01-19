from datetime import date
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import (
    RentalObject, ObjectSettings, TenantStay, StayStatus, 
    ObjectStatus, StayOccupant, Tenant
)

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
    """
    Create a new stay (tenant moves in).
    Validates that no other active stay exists for this object.
    Uses row-level lock to prevent concurrent stay creation.
    Automatically creates a primary StayOccupant entry.
    """
    
    # LOCK THE OBJECT ROW to prevent concurrent stay creation
    # This is critical to prevent race condition where two admins
    # create stays for the same object simultaneously
    lock_stmt = (
        select(RentalObject)
        .where(RentalObject.id == object_id)
        .with_for_update()  # Row-level lock
    )
    lock_result = await session.execute(lock_stmt)
    rental_object = lock_result.scalar_one_or_none()
    
    if not rental_object:
        raise ValueError(f"Объект ID {object_id} не найден")
    
    # VALIDATION: Check for existing active stay (with lock held)
    check_stmt = select(TenantStay).where(
        TenantStay.object_id == object_id,
        TenantStay.status == StayStatus.active.value
    )
    check_result = await session.execute(check_stmt)
    existing_stay = check_result.scalar_one_or_none()
    
    if existing_stay:
        raise ValueError(
            f"Объект уже занят! Активное заселение ID {existing_stay.id} "
            f"для жильца ID {existing_stay.tenant_id}. Сначала выселите текущего жильца."
        )
    
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
    await session.flush()  # Get stay.id
    
    # Create primary occupant
    primary_occupant = StayOccupant(
        stay_id=stay.id,
        tenant_id=tenant_id,
        role="primary",
        joined_date=date_from,
        receive_rent_notifications=True,
        receive_comm_notifications=True,
        receive_meter_reminders=True
    )
    session.add(primary_occupant)
    
    await session.execute(
        update(RentalObject)
        .where(RentalObject.id == object_id)
        .values(status=ObjectStatus.occupied.value)
    )
    
    await session.commit()
    return stay

async def end_stay(session: AsyncSession, stay_id: int) -> TenantStay:
    """
    End a stay (tenant moves out).
    Uses row-level lock to prevent concurrent archiving.
    """
    import logging
    
    # LOCK STAY ROW to prevent concurrent end_stay calls
    lock_stmt = (
        select(TenantStay)
        .where(TenantStay.id == stay_id)
        .with_for_update()
    )
    result = await session.execute(lock_stmt)
    stay = result.scalar_one_or_none()
    
    if not stay:
        raise ValueError(f"Stay {stay_id} not found")
    
    # IDEMPOTENCY CHECK: If already archived, return
    if stay.status == StayStatus.archived.value:
        logging.info(f"Stay {stay_id} already archived")
        return stay
    
    # End the stay
    stay.date_to = date.today()
    stay.status = StayStatus.archived.value
    
    # Mark all occupants as left
    await session.execute(
        update(StayOccupant)
        .where(StayOccupant.stay_id == stay_id, StayOccupant.left_date.is_(None))
        .values(left_date=date.today())
    )
    
    # Free the object
    await session.execute(
        update(RentalObject)
        .where(RentalObject.id == stay.object_id)
        .values(status=ObjectStatus.free.value)
    )
    
    await session.commit()
    
    return stay


# --- Occupant Management ---

async def add_occupant(
    session: AsyncSession,
    stay_id: int,
    tenant_id: int,
    role: str = "co-tenant",
    joined_date: Optional[date] = None,
    receive_rent: bool = True,
    receive_comm: bool = True,
    receive_meter: bool = True
) -> StayOccupant:
    """
    Add a co-tenant to an existing stay.
    Validates that stay is active and tenant not already in stay.
    """
    # Validation: stay exists and is active
    stay_stmt = select(TenantStay).where(TenantStay.id == stay_id)
    stay_result = await session.execute(stay_stmt)
    stay = stay_result.scalar_one_or_none()
    
    if not stay:
        raise ValueError(f"Stay ID {stay_id} not found")
    
    if stay.status != StayStatus.active.value:
        raise ValueError(f"Stay ID {stay_id} is not active (status: {stay.status})")
    
    # Validation: tenant not already in stay
    existing_stmt = select(StayOccupant).where(
        StayOccupant.stay_id == stay_id,
        StayOccupant.tenant_id == tenant_id
    )
    existing_result = await session.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        raise ValueError(f"Tenant ID {tenant_id} already in Stay ID {stay_id}")
    
    occupant = StayOccupant(
        stay_id=stay_id,
        tenant_id=tenant_id,
        role=role,
        joined_date=joined_date or date.today(),
        receive_rent_notifications=receive_rent,
        receive_comm_notifications=receive_comm,
        receive_meter_reminders=receive_meter
    )
    session.add(occupant)
    await session.commit()
    return occupant


async def remove_occupant(
    session: AsyncSession,
    occupant_id: int,
    promote_new_primary: bool = False
) -> None:
    """
    Remove an occupant from a stay (mark as left).
    If removing primary and promote_new_primary=True, promotes oldest co-tenant.
    """
    stmt = select(StayOccupant).where(StayOccupant.id == occupant_id)
    result = await session.execute(stmt)
    occupant = result.scalar_one_or_none()
    
    if not occupant:
        raise ValueError(f"Occupant ID {occupant_id} not found")
    
    if occupant.left_date is not None:
        raise ValueError(f"Occupant ID {occupant_id} already left on {occupant.left_date}")
    
    # Mark as left
    occupant.left_date = date.today()
    
    # If primary is leaving and promotion requested
    if occupant.role == "primary" and promote_new_primary:
        # Find oldest active co-tenant
        co_tenant_stmt = (
            select(StayOccupant)
            .where(
                StayOccupant.stay_id == occupant.stay_id,
                StayOccupant.role == "co-tenant",
                StayOccupant.left_date.is_(None)
            )
            .order_by(StayOccupant.joined_date)
            .limit(1)
        )
        co_tenant_result = await session.execute(co_tenant_stmt)
        co_tenant = co_tenant_result.scalar_one_or_none()
        
        if co_tenant:
            co_tenant.role = "primary"
    
    await session.commit()


async def get_active_occupants(
    session: AsyncSession,
    stay_id: int
) -> List[StayOccupant]:
    """Get all active occupants for a stay."""
    stmt = (
        select(StayOccupant)
        .where(
            StayOccupant.stay_id == stay_id,
            StayOccupant.left_date.is_(None)
        )
        .options(selectinload(StayOccupant.tenant))
        .order_by(StayOccupant.role.desc(), StayOccupant.joined_date)  # primary first
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_occupant_preferences(
    session: AsyncSession,
    occupant_id: int,
    receive_rent: Optional[bool] = None,
    receive_comm: Optional[bool] = None,
    receive_meter: Optional[bool] = None
) -> StayOccupant:
    """Update notification preferences for an occupant."""
    stmt = select(StayOccupant).where(StayOccupant.id == occupant_id)
    result = await session.execute(stmt)
    occupant = result.scalar_one_or_none()
    
    if not occupant:
        raise ValueError(f"Occupant ID {occupant_id} not found")
    
    if receive_rent is not None:
        occupant.receive_rent_notifications = receive_rent
    if receive_comm is not None:
        occupant.receive_comm_notifications = receive_comm
    if receive_meter is not None:
        occupant.receive_meter_reminders = receive_meter
    
    await session.commit()
    return occupant
