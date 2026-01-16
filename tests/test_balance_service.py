
import pytest
from datetime import date
from decimal import Decimal

from bot.services.balance_service import get_stay_balance
from bot.services.payment_service import allocate_payment
from bot.database.models import (
    TenantStay, RentCharge, CommCharge, Payment,
    Tenant, RentalObject, PaymentStatus, StayStatus
)


@pytest.mark.asyncio
async def test_balance_simple(async_session):
    """Test basic balance: 1 charge, 1 full payment"""
    # Setup
    tenant = Tenant(full_name="Test Tenant", phone="+1234567890")
    async_session.add(tenant)
    
    obj = RentalObject(owner_id=1, address="Test St 1")
    async_session.add(obj)
    await async_session.flush()
    
    stay = TenantStay(
        tenant_id=tenant.id,
        object_id=obj.id,
        date_from=date(2026, 1, 1),
        rent_amount=30000,
        rent_day=5,
        comm_day=10,
        status=StayStatus.active.value
    )
    async_session.add(stay)
    await async_session.flush()
    
    charge = RentCharge(
        stay_id=stay.id,
        month=date(2026, 1, 1),
        base_amount=30000,
        tax_amount=0,
        amount=30000
    )
    async_session.add(charge)
    await async_session.flush()
    
    payment = Payment(
        stay_id=stay.id,
        # NO charge_id!
        amount=30000,
        total_amount=30000,
        status=PaymentStatus.confirmed.value,
        type="rent",
        confirmed_at=date(2026, 1, 6)
    )
    async_session.add(payment)
    await async_session.commit()
    
    # Explicitly allocate payment
    await allocate_payment(async_session, payment.id)
    
    # Test
    balance = await get_stay_balance(async_session, stay.id)
    
    assert balance.total_charged == 30000
    assert balance.total_paid == 30000
    assert balance.balance == 0
    assert len(balance.unpaid_charges) == 0


@pytest.mark.asyncio
async def test_balance_partial_payment(async_session):
    """Test partial payment: charge 30k, paid 20k, debt 10k"""
    tenant = Tenant(full_name="Test Tenant", phone="+1234567890")
    async_session.add(tenant)
    
    obj = RentalObject(owner_id=1, address="Test St 1")
    async_session.add(obj)
    await async_session.flush()
    
    stay = TenantStay(
        tenant_id=tenant.id,
        object_id=obj.id,
        date_from=date(2026, 1, 1),
        rent_amount=30000,
        rent_day=5,
        comm_day=10,
        status=StayStatus.active.value
    )
    async_session.add(stay)
    await async_session.flush()
    
    charge = RentCharge(
        stay_id=stay.id,
        month=date(2026, 1, 1),
        base_amount=30000,
        tax_amount=0,
        amount=30000
    )
    async_session.add(charge)
    await async_session.flush()
    
    payment = Payment(
        stay_id=stay.id,
        amount=20000, 
        total_amount=20000,
        status=PaymentStatus.confirmed.value,
        type="rent",
        confirmed_at=date(2026, 1, 6)
    )
    async_session.add(payment)
    await async_session.commit()
    
    await allocate_payment(async_session, payment.id)
    
    # Test
    balance = await get_stay_balance(async_session, stay.id)
    
    assert balance.total_charged == 30000
    assert balance.total_paid == 20000
    assert balance.balance == 10000  # Debt
    assert len(balance.unpaid_charges) == 1
    assert balance.unpaid_charges[0].paid_amount == 20000
    assert balance.unpaid_charges[0].status == "partial"


@pytest.mark.asyncio
async def test_balance_overpayment(async_session):
    """Test overpayment: charge 30k, paid 40k, advance 10k"""
    tenant = Tenant(full_name="Test Tenant", phone="+1234567890")
    async_session.add(tenant)
    
    obj = RentalObject(owner_id=1, address="Test St 1")
    async_session.add(obj)
    await async_session.flush()
    
    stay = TenantStay(
        tenant_id=tenant.id,
        object_id=obj.id,
        date_from=date(2026, 1, 1),
        rent_amount=30000,
        rent_day=5,
        comm_day=10,
        status=StayStatus.active.value
    )
    async_session.add(stay)
    await async_session.flush()
    
    charge = RentCharge(
        stay_id=stay.id,
        month=date(2026, 1, 1),
        base_amount=30000,
        tax_amount=0,
        amount=30000
    )
    async_session.add(charge)
    await async_session.flush()
    
    # Two payments totaling 40k
    payment1 = Payment(
        stay_id=stay.id,
        amount=30000,
        total_amount=30000,
        status=PaymentStatus.confirmed.value,
        type="rent",
        confirmed_at=date(2026, 1, 6)
    )
    payment2 = Payment(
        stay_id=stay.id,
        amount=10000,
        total_amount=10000,
        status=PaymentStatus.confirmed.value,
        type="rent",
        confirmed_at=date(2026, 1, 7)
    )
    async_session.add_all([payment1, payment2])
    await async_session.commit()
    
    await allocate_payment(async_session, payment1.id)
    await allocate_payment(async_session, payment2.id)
    
    # Test
    balance = await get_stay_balance(async_session, stay.id)
    
    assert balance.total_charged == 30000
    assert balance.total_paid == 40000
    assert balance.balance == -10000  # Negative = advance
    assert balance.advances == 10000


@pytest.mark.asyncio
async def test_balance_no_payments(async_session):
    """Test with charge but no payments"""
    tenant = Tenant(full_name="Test Tenant", phone="+1234567890")
    async_session.add(tenant)
    
    obj = RentalObject(owner_id=1, address="Test St 1")
    async_session.add(obj)
    await async_session.flush()
    
    stay = TenantStay(
        tenant_id=tenant.id,
        object_id=obj.id,
        date_from=date(2026, 1, 1),
        rent_amount=30000,
        rent_day=5,
        comm_day=10,
        status=StayStatus.active.value
    )
    async_session.add(stay)
    await async_session.flush()
    
    charge = RentCharge(
        stay_id=stay.id,
        month=date(2026, 1, 1),
        base_amount=30000,
        tax_amount=0,
        amount=30000
    )
    async_session.add(charge)
    await async_session.commit()
    
    # Test
    balance = await get_stay_balance(async_session, stay.id)
    
    assert balance.total_charged == 30000
    assert balance.total_paid == 0
    assert balance.balance == 30000  # Full debt
    assert len(balance.unpaid_charges) == 1
    assert balance.unpaid_charges[0].status == "unpaid"


# Fixture for async session
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from bot.database.core import Base

@pytest_asyncio.fixture
async def async_session():
    # Use in-memory SQLite for tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        # Note: We need to enable foreign keys in SQLite for cascade delete logic,
        # but for unit tests simple logic is enough
        yield session
    
    await engine.dispose()
