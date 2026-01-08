from datetime import date
from decimal import Decimal
from typing import Optional, Dict

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import RentCharge, TenantStay, ChargeStatus

class FinancialStats:
    def __init__(self, billed_total, billed_tax, collected_total, collected_tax):
        self.billed_total = float(billed_total or 0)
        self.billed_tax = float(billed_tax or 0)
        self.billed_base = self.billed_total - self.billed_tax
        
        self.collected_total = float(collected_total or 0)
        self.collected_tax = float(collected_tax or 0)
        self.collected_base = self.collected_total - self.collected_tax

async def get_object_stats(session: AsyncSession, object_id: int, year: int) -> FinancialStats:
    """
    Get financial statistics for a specific object for a given year.
    Aggregates RentCharges linked to TenantStays of this object.
    """
    
    # 1. Billed (Total accrued)
    # We query RentCharges where stay.object_id == object_id AND year matches
    
    billed_stmt = (
        select(
            func.sum(RentCharge.amount),
            func.sum(RentCharge.tax_amount)
        )
        .join(TenantStay, RentCharge.stay_id == TenantStay.id)
        .where(
            TenantStay.object_id == object_id,
            func.extract('year', RentCharge.month) == year
        )
    )
    
    billed_res = await session.execute(billed_stmt)
    billed_total, billed_tax = billed_res.one()
    
    # 2. Collected (Status = paid)
    # Ideally we should look at Payments, but checking ChargeStatus.paid is a good proxy for "fully paid"
    # For partial payments, it's more complex, but let's stick to ChargeStatus.paid for MVP correctness.
    
    collected_stmt = (
        select(
            func.sum(RentCharge.amount),
            func.sum(RentCharge.tax_amount)
        )
        .join(TenantStay, RentCharge.stay_id == TenantStay.id)
        .where(
            TenantStay.object_id == object_id,
            func.extract('year', RentCharge.month) == year,
            RentCharge.status == ChargeStatus.paid.value
        )
    )
    
    collected_res = await session.execute(collected_stmt)
    collected_total, collected_tax = collected_res.one()
    
    return FinancialStats(billed_total, billed_tax, collected_total, collected_tax)
