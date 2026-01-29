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
    Uses row-level lock to prevent double allocation during concurrent calls.
    
    Algorithm:
    1. Lock payment row to prevent concurrent allocation
    2. Check if already fully allocated (idempotent)
    3. Get payment and stay
    4. Find all unpaid/partially paid charges (oldest first)
    5. For each charge:
       - Calculate remaining amount on charge
       - Allocate min(remaining_payment, remaining_on_charge)
       - Create PaymentAllocation record
       - If charge fully paid, mark as confirmed
    6. If payment > all charges: store remainder as unallocated (advance)
    
    Args:
        session: Database session
        payment_id: Payment to allocate
    
    Returns:
        List of created PaymentAllocation records
    """
    import logging
    
    # LOCK PAYMENT ROW to prevent concurrent allocation
    # This is critical for webhook scenarios where payment might be processed twice
    lock_stmt = (
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()  # Row-level lock
    )
    lock_result = await session.execute(lock_stmt)
    payment = lock_result.scalar_one_or_none()
    
    if not payment:
        raise ValueError(f"Payment ID {payment_id} not found")
    
    # Determine amount to allocate
    # If total_amount isn't set yet (migrated data), use amount
    amount_to_allocate = payment.total_amount if payment.total_amount is not None else payment.amount
    
    # Calculate how much is ALREADY allocated
    already_allocated = float(payment.allocated_amount or 0)
    remaining = float(amount_to_allocate) - already_allocated
    
    logging.info(f"Allocating payment {payment_id}. Total: {amount_to_allocate}, Already: {already_allocated}, Remaining: {remaining}")
    
    # IDEMPOTENCY CHECK: If already fully allocated, return empty list
    if remaining <= 0.01:
        logging.info(f"Payment {payment_id} already fully allocated. Skipping.")
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
    
    # Initialize allocations list
    allocations = []

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
    from bot.config import config
    
    # LOCK CHARGE ROW to prevent concurrent marking
    if charge_type == "rent":
        lock_stmt = (
            select(RentCharge)
            .where(RentCharge.id == charge_id)
            .with_for_update()
        )
        result = await session.execute(lock_stmt)
        charge = result.scalar_one_or_none()
    elif charge_type == "comm":
        lock_stmt = (
            select(CommCharge)
            .where(CommCharge.id == charge_id)
            .with_for_update()
        )
        result = await session.execute(lock_stmt)
        charge = result.scalar_one_or_none()
    else:
        raise ValueError(f"Invalid charge_type: {charge_type}")
    
    if not charge:
        raise ValueError(f"Charge {charge_type}#{charge_id} not found")
    
    # IDEMPOTENCY CHECK: If already paid, raise error
    if charge.status == ChargeStatus.paid.value:
        raise ValueError(f"Charge {charge_type}#{charge_id} is already paid")
    
    # SECURITY: Check authorization - admin can only mark their own charges
    # Load stay with rental_object to check owner_id
    from sqlalchemy.orm import selectinload
    stmt = select(TenantStay).where(TenantStay.id == charge.stay_id).options(
        selectinload(TenantStay.rental_object)
    )
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if not stay or not stay.rental_object:
        raise ValueError("Stay or rental object not found")
    
    # Only owner of the object or OWNER can mark payment
    if admin_id not in config.OWNER_IDS and stay.rental_object.owner_id != admin_id:
        raise ValueError("У вас нет прав на отметку этого начисления")
    
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


async def cancel_payment(
    session: AsyncSession,
    payment_id: int,
    admin_id: int,
    reason: str = "Отменено администратором"
) -> bool:
    """
    Cancel a payment (for erroneous uploads).
    Uses row-level lock to prevent concurrent cancellation.
    
    - Checks permissions (OWNER or object owner)
    - Rolls back allocations
    - Sets status = 'cancelled'
    - Logs to meta_json
    
    Args:
        session: Database session
        payment_id: Payment to cancel
        admin_id: Admin performing cancellation
        reason: Cancellation reason
    
    Returns:
        True if successful
    
    Raises:
        ValueError: If payment not found or already processed
        PermissionError: If admin lacks permission
    """
    import logging
    from datetime import datetime
    from bot.config import config
    from sqlalchemy import delete
    
    # LOCK PAYMENT ROW to prevent concurrent cancellation
    lock_stmt = (
        select(Payment)
        .where(Payment.id == payment_id)
        .options(
            selectinload(Payment.stay).selectinload(TenantStay.rental_object)
        )
        .with_for_update()  # Row-level lock
    )
    result = await session.execute(lock_stmt)
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise ValueError(f"Payment {payment_id} not found")
    
    # IDEMPOTENCY CHECK: If already cancelled, return success
    if payment.status == 'cancelled':
        logging.info(f"Payment {payment_id} already cancelled")
        return True
    
    # Check status - can only cancel pending payments
    if payment.status not in ['pending_manual', 'pending']:
        raise ValueError(f"Cannot cancel payment with status: {payment.status}")
    
    # Security check: OWNER or object owner
    is_owner = admin_id in config.OWNER_IDS
    is_object_owner = (
        payment.stay and 
        payment.stay.rental_object and 
        payment.stay.rental_object.owner_id == admin_id
    )
    
    if not (is_owner or is_object_owner):
        raise PermissionError("Only OWNER or object owner can cancel payments")
    
    # Rollback allocations
    alloc_stmt = select(PaymentAllocation).where(
        PaymentAllocation.payment_id == payment_id
    )
    alloc_result = await session.execute(alloc_stmt)
    allocations = alloc_result.scalars().all()
    
    # For each allocation, revert charge status to pending
    for alloc in allocations:
        if alloc.charge_type == 'rent':
            charge = await session.get(RentCharge, alloc.charge_id)
        else:
            charge = await session.get(CommCharge, alloc.charge_id)
        
        if charge:
            # Check if charge has other payments
            other_allocs_stmt = select(PaymentAllocation).where(
                PaymentAllocation.charge_id == alloc.charge_id,
                PaymentAllocation.charge_type == alloc.charge_type,
                PaymentAllocation.payment_id != payment_id
            )
            other_allocs_result = await session.execute(other_allocs_stmt)
            other_allocs = other_allocs_result.scalars().all()
            
            # If no other payments, set to pending
            if not other_allocs:
                charge.status = ChargeStatus.pending.value
    
    # Delete allocations
    await session.execute(
        delete(PaymentAllocation).where(
            PaymentAllocation.payment_id == payment_id
        )
    )
    
    # Update payment status and metadata
    payment.status = 'cancelled'
    payment.allocated_amount = 0
    payment.unallocated_amount = 0
    
    # Add cancellation info to meta_json
    if not payment.meta_json:
        payment.meta_json = {}
    
    payment.meta_json['cancelled_by'] = admin_id
    payment.meta_json['cancelled_at'] = datetime.now().isoformat()
    payment.meta_json['cancel_reason'] = reason
    payment.meta_json['original_status'] = payment.status
    
    await session.commit()
    
    import logging
    logging.info(f"Payment {payment_id} cancelled by admin {admin_id}. Reason: {reason}")
    
    return True
