from typing import Optional, List, NamedTuple
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import (
    TenantStay, RentCharge, CommCharge, Payment, PaymentAllocation,
    PaymentStatus, StayStatus
)


class ChargeInfo(NamedTuple):
    """Individual charge details"""
    id: int
    type: str  # "rent" or "comm"
    month: date
    amount: float
    paid_amount: float  # How much paid towards this charge
    status: str


class StayBalance(NamedTuple):
    """Complete balance information for a stay"""
    stay_id: int
    total_charged: float  # All charges (rent + comm)
    total_paid: float  # All confirmed payments (allocated amount)
    balance: float  # Positive = debt, Negative = advance/overpayment
    
    # Breakdown
    rent_charged: float
    comm_charged: float
    rent_paid: float
    comm_paid: float
    
    # Details
    unpaid_charges: List[ChargeInfo]  # Charges not fully paid
    advances: float  # Overpayments (unallocated amount)


async def get_stay_balance(
    session: AsyncSession,
    stay_id: int,
    as_of_date: Optional[date] = None
) -> StayBalance:
    """
    Calculate current balance for a stay.
    
    Args:
        session: Database session
        stay_id: ID of the stay
        as_of_date: Calculate balance as of this date (default: today)
    
    Returns:
        StayBalance with complete breakdown
    """
    if as_of_date is None:
        as_of_date = date.today()
    
    # Get stay
    stay_stmt = select(TenantStay).where(TenantStay.id == stay_id)
    stay_result = await session.execute(stay_stmt)
    stay = stay_result.scalar_one_or_none()
    
    if not stay:
        raise ValueError(f"Stay ID {stay_id} not found")
    
    # 1. Sum rent charges
    rent_stmt = (
        select(func.coalesce(func.sum(RentCharge.amount), 0))
        .where(
            RentCharge.stay_id == stay_id,
            RentCharge.month <= as_of_date
        )
    )
    rent_result = await session.execute(rent_stmt)
    rent_charged = float(rent_result.scalar())
    
    # 2. Sum comm charges
    comm_stmt = (
        select(func.coalesce(func.sum(CommCharge.amount), 0))
        .where(
            CommCharge.stay_id == stay_id,
            CommCharge.month <= as_of_date
        )
    )
    comm_result = await session.execute(comm_stmt)
    comm_charged = float(comm_result.scalar())
    
    # 3. Sum confirmed payments (allocated vs unallocated)
    
    # Calculate Rent Paid based on Allocations
    rent_alloc_stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, PaymentAllocation.payment_id == Payment.id)
        .where(
            Payment.stay_id == stay_id,
            PaymentAllocation.charge_type == "rent",
            Payment.status == PaymentStatus.confirmed.value,
            func.date(Payment.confirmed_at) <= as_of_date
        )
    )
    rent_alloc_result = await session.execute(rent_alloc_stmt)
    rent_paid = float(rent_alloc_result.scalar())
    
    # Calculate Comm Paid based on Allocations
    comm_alloc_stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .join(Payment, PaymentAllocation.payment_id == Payment.id)
        .where(
            Payment.stay_id == stay_id,
            PaymentAllocation.charge_type == "comm",
            Payment.status == PaymentStatus.confirmed.value,
            func.date(Payment.confirmed_at) <= as_of_date
        )
    )
    comm_alloc_result = await session.execute(comm_alloc_stmt)
    comm_paid = float(comm_alloc_result.scalar())
    
    # Calculate Advances (Unallocated amounts)
    advance_stmt = (
        select(func.coalesce(func.sum(Payment.unallocated_amount), 0))
        .where(
            Payment.stay_id == stay_id,
            Payment.status == PaymentStatus.confirmed.value,
            func.date(Payment.confirmed_at) <= as_of_date
        )
    )
    advance_result = await session.execute(advance_stmt)
    advances = float(advance_result.scalar())
    
    total_charged = rent_charged + comm_charged
    total_paid = rent_paid + comm_paid  # FIXED: не включаем advances!
    balance = total_charged - total_paid - advances  # FIXED: вычитаем advances отдельно
    
    # 4. Find unpaid charges
    unpaid_charges = await _get_unpaid_charges(session, stay_id, as_of_date)
    
    return StayBalance(
        stay_id=stay_id,
        total_charged=total_charged,
        total_paid=total_paid,
        balance=balance,
        rent_charged=rent_charged,
        comm_charged=comm_charged,
        rent_paid=rent_paid,
        comm_paid=comm_paid,
        unpaid_charges=unpaid_charges,
        advances=advances
    )


async def _get_unpaid_charges(
    session: AsyncSession,
    stay_id: int,
    as_of_date: date
) -> List[ChargeInfo]:
    """
    Get list of charges that are not fully paid.
    """
    unpaid = []
    
    # Rent charges
    rent_stmt = (
        select(RentCharge)
        .where(
            RentCharge.stay_id == stay_id,
            RentCharge.month <= as_of_date
        )
        .order_by(RentCharge.month)
    )
    rent_result = await session.execute(rent_stmt)
    rent_charges = rent_result.scalars().all()
    
    for charge in rent_charges:
        # Sum allocations for this charge
        alloc_stmt = (
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
            .where(
                PaymentAllocation.charge_id == charge.id,
                PaymentAllocation.charge_type == "rent"
            )
        )
        alloc_result = await session.execute(alloc_stmt)
        paid_amount = float(alloc_result.scalar())
        
        if paid_amount < float(charge.amount) - 0.01:
            unpaid.append(ChargeInfo(
                id=charge.id,
                type="rent",
                month=charge.month,
                amount=float(charge.amount),
                paid_amount=paid_amount,
                status="partial" if paid_amount > 0 else "unpaid"
            ))
    
    # Comm charges
    comm_stmt = (
        select(CommCharge)
        .where(
            CommCharge.stay_id == stay_id,
            CommCharge.month <= as_of_date
        )
        .order_by(CommCharge.month)
    )
    comm_result = await session.execute(comm_stmt)
    comm_charges = comm_result.scalars().all()
    
    for charge in comm_charges:
        alloc_stmt = (
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
            .where(
                PaymentAllocation.charge_id == charge.id,
                PaymentAllocation.charge_type == "comm"
            )
        )
        alloc_result = await session.execute(alloc_stmt)
        paid_amount = float(alloc_result.scalar())
        
        if paid_amount < float(charge.amount) - 0.01:
            unpaid.append(ChargeInfo(
                id=charge.id,
                type="comm",
                month=charge.month,
                amount=float(charge.amount),
                paid_amount=paid_amount,
                status="partial" if paid_amount > 0 else "unpaid"
            ))
    
    return unpaid


async def get_object_balance(
    session: AsyncSession,
    object_id: int,
    as_of_date: Optional[date] = None
) -> StayBalance:
    """Convenience wrapper around get_stay_balance for active object stay matches."""
    stmt = (
        select(TenantStay)
        .where(
            TenantStay.object_id == object_id,
            TenantStay.status == StayStatus.active.value
        )
    )
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if not stay:
        raise ValueError(f"No active stay found for object {object_id}")
    
    return await get_stay_balance(session, stay.id, as_of_date)


async def get_tenant_total_balance(
    session: AsyncSession,
    tenant_id: int,
    as_of_date: Optional[date] = None
) -> float:
    """Calculate total balance across all active stays for a tenant."""
    stmt = (
        select(TenantStay)
        .where(
            TenantStay.tenant_id == tenant_id,
            TenantStay.status == StayStatus.active.value
        )
    )
    result = await session.execute(stmt)
    stays = result.scalars().all()
    
    total_balance = 0.0
    for stay in stays:
        balance = await get_stay_balance(session, stay.id, as_of_date)
        total_balance += balance.balance
    
    return total_balance
