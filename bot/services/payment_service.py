"""
Payment allocation service for distributing payments across charges.

Implements FIFO (First In, First Out) allocation strategy.
"""
from typing import List
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import (
    Payment, PaymentAllocation, RentCharge, CommCharge,
    TenantStay, ChargeStatus, PaymentStatus
)


async def allocate_payment(
    session: AsyncSession,
    payment_id: int
) -> List[PaymentAllocation]:
    """
    Distribute payment amount across pending charges using FIFO.
    
    Algorithm:
    1. Get payment and stay
    2. Find all unpaid/partially paid charges (oldest first)
    3. For each charge:
       - Calculate remaining amount on charge
       - Allocate min(remaining_payment, remaining_on_charge)
       - Create PaymentAllocation record
       - If charge fully paid, mark as confirmed
    4. If payment > all charges: store remainder as unallocated (advance)
    
    Args:
        session: Database session
        payment_id: Payment to allocate
    
    Returns:
        List of created PaymentAllocation records
    """
    import logging
    
    # Get payment
    payment_stmt = select(Payment).where(Payment.id == payment_id)
    payment_result = await session.execute(payment_stmt)
    payment = payment_result.scalar_one_or_none()
    
    if not payment:
        raise ValueError(f"Payment ID {payment_id} not found")
    
    # Determine amount to allocate
    # If total_amount isn't set yet (migrated data), use amount
    amount_to_allocate = payment.total_amount if payment.total_amount is not None else payment.amount
    
    # Calculate how much is ALREADY allocated from THIS payment to avoid double counting if re-run
    # But wait, allocate_payment logic assumes we are allocating "remaining" capacity.
    # Current logic: takes TOTAL amount, and subtracts... wait.
    # The logic below subtracts 'to_allocate' from 'remaining'.
    # But 'remaining' starts as FULL amount.
    # If we run allocate_payment twice, we might re-allocate.
    # We should check payment.allocated_amount too.
    
    already_allocated = float(payment.allocated_amount or 0)
    remaining = float(amount_to_allocate) - already_allocated
    
    logging.info(f"Allocating payment {payment_id}. Total: {amount_to_allocate}, Already: {already_allocated}, Remaining: {remaining}")
    
    allocations = []
    
    if remaining <= 0.01:
        logging.info(f"Payment {payment_id} fully allocated.")
        return []

    # Get all charges for stay (rent + comm), ordered by month (FIFO)
    rent_charges = await _get_unpaid_rent_charges(session, payment.stay_id)
    comm_charges = await _get_unpaid_comm_charges(session, payment.stay_id)
    
    logging.info(f"Found {len(rent_charges)} rent charges and {len(comm_charges)} comm charges for stay {payment.stay_id}")
    
    # Combine and sort by month
    all_charges = []
    for charge in rent_charges:
        all_charges.append(("rent", charge))
    for charge in comm_charges:
        all_charges.append(("comm", charge))
    
    all_charges.sort(key=lambda x: x[1].month)
    
    # Allocate
    for charge_type, charge in all_charges:
        if remaining <= 0.01:
            break
        
        # How much still owed on this charge?
        paid_so_far = await _get_paid_amount_for_charge(session, charge.id, charge_type)
        charge_amount = float(charge.amount)
        charge_remaining = charge_amount - paid_so_far
        
        logging.info(f"Checking charge {charge.id} ({charge_type}, {charge.month}): Amount={charge_amount}, Paid={paid_so_far}, Rem={charge_remaining}")
        
        if charge_remaining <= 0.01: # Check for floating point epsilon
            continue  # Already fully paid
        
        # Allocate
        to_allocate = min(remaining, charge_remaining)
        
        logging.info(f"Allocating {to_allocate} to charge {charge.id}")
        
        allocation = PaymentAllocation(
            payment_id=payment_id,
            charge_id=charge.id,
            charge_type=charge_type,
            amount=to_allocate
        )
        session.add(allocation)
        allocations.append(allocation)
        
        remaining -= to_allocate
        
        # If charge now fully paid, mark as confirmed
        if paid_so_far + to_allocate >= charge_amount - 0.01:
            charge.status = ChargeStatus.paid.value
    
    # Update payment fields
    payment.allocated_amount = float(payment.allocated_amount or 0) + (float(amount_to_allocate) - already_allocated - remaining)
    payment.unallocated_amount = remaining
    
    await session.commit()
    return allocations


async def _get_unpaid_rent_charges(
    session: AsyncSession,
    stay_id: int
) -> List[RentCharge]:
    """Get rent charges that are not fully paid, oldest first"""
    stmt = (
        select(RentCharge)
        .where(
            RentCharge.stay_id == stay_id
            # We fetch ALL charges and filter by remaining amount in Python
            # This is safer in case status sync is broken
        )
        .order_by(RentCharge.month)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_unpaid_comm_charges(
    session: AsyncSession,
    stay_id: int
) -> List[CommCharge]:
    """Get comm charges that are not fully paid, oldest first"""
    stmt = (
        select(CommCharge)
        .where(
            CommCharge.stay_id == stay_id
            # Fetch all, actual check in allocation loop
        )
        .order_by(CommCharge.month)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_paid_amount_for_charge(
    session: AsyncSession,
    charge_id: int,
    charge_type: str
) -> float:
    """Get total amount already allocated to this charge"""
    stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), 0))
        .where(
            PaymentAllocation.charge_id == charge_id,
            PaymentAllocation.charge_type == charge_type
        )
    )
    result = await session.execute(stmt)
    return float(result.scalar())


async def get_payment_allocations(
    session: AsyncSession,
    payment_id: int
) -> List[PaymentAllocation]:
    """Get all allocations for a payment"""
    stmt = (
        select(PaymentAllocation)
        .where(PaymentAllocation.payment_id == payment_id)
        .order_by(PaymentAllocation.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_charge_allocations(
    session: AsyncSession,
    charge_id: int,
    charge_type: str
) -> List[PaymentAllocation]:
    """Get all payment allocations to a specific charge"""
    stmt = (
        select(PaymentAllocation)
        .where(
            PaymentAllocation.charge_id == charge_id,
            PaymentAllocation.charge_type == charge_type
        )
        .options(selectinload(PaymentAllocation.payment))
        .order_by(PaymentAllocation.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def deallocate_payment(
    session: AsyncSession,
    payment_id: int
) -> None:
    """
    Remove all allocations for a payment (e.g., if payment rejected).
    Reverts charges to pending status if needed.
    """
    # Get allocations
    allocations = await get_payment_allocations(session, payment_id)
    
    # For each allocation, check if charge should revert to pending
    for alloc in allocations:
        charge_type = alloc.charge_type
        charge_id = alloc.charge_id
        
        # Get charge
        if charge_type == "rent":
            stmt = select(RentCharge).where(RentCharge.id == charge_id)
        else:
            stmt = select(CommCharge).where(CommCharge.id == charge_id)
        
        result = await session.execute(stmt)
        charge = result.scalar_one_or_none()
        
        if charge and charge.status == ChargeStatus.paid.value:
            # Check if still fully paid after removing this allocation
            paid = await _get_paid_amount_for_charge(session, charge_id, charge_type)
            paid -= float(alloc.amount)  # Subtract this allocation
            
            if paid < float(charge.amount) - 0.01:
                charge.status = ChargeStatus.pending.value
        
        # Delete allocation
        await session.delete(alloc)
    
    # Reset payment fields
    payment_stmt = select(Payment).where(Payment.id == payment_id)
    payment_result = await session.execute(payment_stmt)
    payment = payment_result.scalar_one_or_none()
    
    if payment:
        payment.allocated_amount = 0.0
        # If total_amount was migrated, restore from it
        total = payment.total_amount if payment.total_amount is not None else payment.amount
        payment.unallocated_amount = float(total)
    
    await session.commit()


async def mark_charge_as_paid(
    session: AsyncSession,
    charge_id: int,
    charge_type: str,  # "rent" or "comm"
    admin_id: int,
    admin_name: str = "Admin",
    note: str = None
) -> Payment:
    """
    Manually mark a charge as paid by creating a virtual payment.
    
    This creates a Payment record without a receipt, marked as manual,
    and allocates it to the specific charge.
    
    Args:
        session: Database session
        charge_id: ID of the charge to mark as paid
        charge_type: "rent" or "comm"
        admin_id: Telegram ID of admin marking the payment
        admin_name: Name of admin for notes
        note: Optional custom note
    
    Returns:
        Created Payment record
    
    Raises:
        ValueError: If charge not found or already paid
    """
    from datetime import datetime, timezone
    
    # Get the charge
    if charge_type == "rent":
        charge = await session.get(RentCharge, charge_id)
    elif charge_type == "comm":
        charge = await session.get(CommCharge, charge_id)
    else:
        raise ValueError(f"Invalid charge_type: {charge_type}")
    
    if not charge:
        raise ValueError(f"Charge {charge_type}#{charge_id} not found")
    
    if charge.status == ChargeStatus.paid.value:
        raise ValueError(f"Charge {charge_type}#{charge_id} is already paid")
    
    # Create virtual payment
    payment = Payment(
        stay_id=charge.stay_id,
        type="rent" if charge_type == "rent" else "comm",
        amount=float(charge.amount),
        total_amount=float(charge.amount),
        allocated_amount=float(charge.amount),
        unallocated_amount=0.0,
        method="manual",
        status=PaymentStatus.confirmed.value,
        source="manual",
        is_manual=True,
        marked_by=admin_id,
        created_at=datetime.now(timezone.utc),
        confirmed_at=datetime.now(timezone.utc),
        meta_json={"note": note or f"Отмечено вручную админом {admin_name}"}
    )
    
    session.add(payment)
    await session.flush()  # Get payment.id
    
    # Create allocation
    allocation = PaymentAllocation(
        payment_id=payment.id,
        charge_id=charge_id,
        charge_type=charge_type,
        amount=float(charge.amount)
    )
    session.add(allocation)
    
    # Mark charge as paid
    charge.status = ChargeStatus.paid.value
    
    await session.commit()
    
    return payment

