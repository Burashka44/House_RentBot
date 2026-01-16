
from datetime import date, timedelta
from typing import List, NamedTuple, Optional
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    TenantStay, RentCharge, CommCharge, PaymentAllocation,
    ChargeStatus, Payment
)
from bot.services.payment_service import allocate_payment, deallocate_payment


class RecalculationResult(NamedTuple):
    old_rent: float
    new_rent: float
    old_comm: float
    new_comm: float
    diff: float


async def recalculate_charges_for_period(
    session: AsyncSession,
    stay_id: int,
    month: date,
    charge_type: str = "all"  # "rent", "comm", "all"
) -> RecalculationResult:
    """
    Recalculate charges for a specific month based on current stay settings.
    
    Warning: This is a destructive operation. It deletes existing charges
    and re-creates them. Payments are preserved but re-allocated.
    
    Args:
        stay_id: Stay ID
        month: Month (YYYY-MM-01)
        charge_type: What to recalculate
        
    Returns:
        Summary of changes
    """
    # 1. Get Stay
    stay_stmt = select(TenantStay).where(TenantStay.id == stay_id)
    stay_result = await session.execute(stay_stmt)
    stay = stay_result.scalar_one_or_none()
    
    if not stay:
        raise ValueError(f"Stay ID {stay_id} not found")
    
    # Normalize month to 1st day
    target_month = month.replace(day=1)
    next_month = (target_month + timedelta(days=32)).replace(day=1)
    
    old_rent = 0.0
    new_rent = 0.0
    old_comm = 0.0
    new_comm = 0.0
    
    # 2. Handle Rent
    if charge_type in ["rent", "all"]:
        # Find existing rent charges
        rent_stmt = select(RentCharge).where(
            RentCharge.stay_id == stay_id,
            RentCharge.month >= target_month,
            RentCharge.month < next_month
        )
        rent_result = await session.execute(rent_stmt)
        old_charges = rent_result.scalars().all()
        
        # Calculate old total
        for c in old_charges:
            old_rent += float(c.amount)
            
            # Check for allocations pointing to this charge
            alloc_stmt = select(PaymentAllocation).where(
                PaymentAllocation.charge_id == c.id,
                PaymentAllocation.charge_type == "rent"
            )
            alloc_result = await session.execute(alloc_stmt)
            allocations = alloc_result.scalars().all()
            
            # De-allocate payments (temporarily turn them into unallocated funds)
            for alloc in allocations:
                # Add back to payment.unallocated_amount
                # Note: This is simplified. Ideally we use deallocate_payment but that does ALL allocations.
                # Here we only want to detach specific ones.
                
                payment = await session.get(Payment, alloc.payment_id)
                if payment:
                    payment.allocated_amount = float(payment.allocated_amount or 0) - float(alloc.amount)
                    payment.unallocated_amount = float(payment.unallocated_amount or 0) + float(alloc.amount)
                
                await session.delete(alloc)
            
            # Delete the charge
            await session.delete(c)
        
        # Create NEW Rent Charge based on stay.rent_amount
        # Check if stay was active in this month
        if stay.date_from <= target_month + timedelta(days=28) and (stay.date_to is None or stay.date_to >= target_month):
            base_amount = float(stay.rent_amount)
            tax_amount = base_amount * (float(stay.tax_rate) / 100.0)
            total_amount = base_amount + tax_amount
            
            new_charge = RentCharge(
                stay_id=stay.id,
                month=target_month,
                base_amount=base_amount,
                tax_amount=tax_amount,
                amount=total_amount,
                status=ChargeStatus.pending.value,
                source="recalculation"
            )
            session.add(new_charge)
            new_rent = total_amount
    
    # 3. Handle Comm (Placeholder - simpler implementation for now as tariffs missing)
    if charge_type in ["comm", "all"]:
        # Similar logic: delete old, re-create based on current rules.
        # But for comms, rules are complex (readings * tariffs).
        # For now, we SKIP comm recalculation or just preserve it.
        pass

    await session.commit()
    
    # 4. Re-allocate payments
    # Find all payments for this stay with unallocated_amount > 0
    # And run allocate_payment() on them to fill the new charges
    
    payment_stmt = (
        select(Payment)
        .where(
            Payment.stay_id == stay_id,
            Payment.unallocated_amount > 0
        )
        .order_by(Payment.created_at)
    )
    payment_result = await session.execute(payment_stmt)
    payments = payment_result.scalars().all()
    
    for payment in payments:
        await allocate_payment(session, payment.id)
        
    return RecalculationResult(
        old_rent=old_rent,
        new_rent=new_rent,
        old_comm=old_comm,
        new_comm=new_comm,
        diff=(new_rent + new_comm) - (old_rent + old_comm)
    )
