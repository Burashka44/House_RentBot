"""
YooMoney (Яндекс.Деньги) Payment Integration Service

Provides integration with YooMoney API for automatic bill payments.

Features:
- Generate payment links for utilities (ЖКХ)
- Check payment status
- Auto-pay from wallet (if enabled)

API Docs: https://yoomoney.ru/docs/wallet/using-api/quickstart
Registration: https://yoomoney.ru/myservices/

Alternative: QIWI, SberPay, Tinkoff
"""
import aiohttp
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PaymentLink:
    """Ссылка на оплату в ЮMoney"""
    url: str
    payment_id: str
    amount: Decimal
    rso_name: str
    service_type: str


class YooMoneyService:
    """
    Service for YooMoney API integration.
    
    Usage:
        service = YooMoneyService(api_token="your_token")
        link = await service.create_utility_payment_link(
            rso_inn="1234567890",
            personal_account="12345",
            amount=1500.00,
            service_name="Электроэнергия"
        )
        
        # Send link to user
        await bot.send_message(user_id, f"Оплатите: {link.url}")
    """
    
    BASE_URL = "https://yoomoney.ru/api"
    
    # Service codes for utilities (примерные, нужно уточнять)
    SERVICE_CODES = {
        "Электроснабжение": "electric",
        "Водоснабжение": "water",
        "Водоотведение": "sewage",
        "Отопление": "heating",
        "Газоснабжение": "gas",
        "Вывоз мусора": "trash",
        "Капремонт": "capital_repair",
        "Аренда": "rent"
    }
    
    def __init__(self, api_token: Optional[str] = None, client_id: Optional[str] = None):
        """
        Initialize YooMoney service.
        
        Args:
            api_token: User access token (for wallet payments)
            client_id: Application client ID
        """
        self.api_token = api_token
        self.client_id = client_id
    
    async def create_utility_payment_link(
        self,
        rso_inn: str,
        personal_account: str,
        amount: Decimal,
        service_name: str,
        period: Optional[str] = None  # "2026-01"
    ) -> PaymentLink:
        """
        Create payment link for utility bill.
        
        Args:
            rso_inn: ИНН РСО
            personal_account: Лицевой счет
            amount: Сумма платежа
            service_name: Название услуги
            period: Период оплаты (опционально)
        
        Returns:
            PaymentLink with URL to pay
        """
        
        # YooMoney Form API endpoint
        url = "https://yoomoney.ru/quickpay/confirm"
        
        params = {
            "receiver": rso_inn,  # ИНН получателя
            "quickpay-form": "shop",
            "targets": f"Оплата {service_name}",
            "paymentType": "AC",  # Bank card
            "sum": float(amount),
            "label": personal_account,  # Лицевой счет
        }
        
        if period:
            params["comment"] = f"Период: {period}"
        
        # Build URL
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        payment_url = f"{url}?{query_string}"
        
        return PaymentLink(
            url=payment_url,
            payment_id=personal_account,  # или генерировать уник ID
            amount=amount,
            rso_name=rso_inn,
            service_type=service_name
        )
    
    async def check_payment_status(self, payment_id: str) -> Dict:
        """
        Check if payment was completed.
        
        Requires API token.
        """
        if not self.api_token:
            logging.error("API token required for check_payment_status")
            return {"status": "unknown"}
        
        url = f"{self.BASE_URL}/operation-history"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        params = {
            "label": payment_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return {"status": "error"}
                    
                    data = await resp.json()
                    
                    # Check if payment exists
                    operations = data.get("operations", [])
                    if operations:
                        return {
                            "status": "success",
                            "amount": operations[0].get("amount"),
                            "datetime": operations[0].get("datetime")
                        }
                    
                    return {"status": "not_found"}
        
        except Exception as e:
            logging.error(f"YooMoney status check failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def create_payment_for_all_rso(
        self,
        tenant,
        rental_object,
        rso_list: List[Dict]
    ) -> List[PaymentLink]:
        """
        Create payment links for ALL RSO providers for a tenant.
        
        Args:
            tenant: Tenant object
            rental_object: RentalObject
            rso_list: List of RSO with amounts
                [{"rso_id": 1, "personal_account": "123", "amount": 500.00, ...}, ...]
        
        Returns:
            List of PaymentLink objects
        """
        links = []
        
        for rso_data in rso_list:
            try:
                link = await self.create_utility_payment_link(
                    rso_inn=rso_data.get("inn"),
                    personal_account=rso_data.get("personal_account"),
                    amount=Decimal(str(rso_data.get("amount", 0))),
                    service_name=rso_data.get("service_name"),
                    period=rso_data.get("period")
                )
                links.append(link)
            except Exception as e:
                logging.error(f"Failed to create payment for RSO {rso_data.get('rso_id')}: {e}")
        
        return links


# ===== Alternative: QIWI Integration =====

class QIWIService:
    """
    QIWI Wallet integration (alternative to YooMoney).
    
    Similar API, different endpoints.
    """
    pass


# ===== Integration with Bot =====

async def generate_payment_links_for_tenant(session, tenant_id: int, period: str) -> List[PaymentLink]:
    """
    Generate payment links for ALL utilities for tenant in a specific period.
    
    Workflow:
    1. Get tenant's rental object
    2. Get all RSO links for object
    3. Calculate amounts due for each RSO
    4. Generate payment links
    
    Args:
        session: DB session
        tenant_id: Tenant ID
        period: Payment period (e.g., "2026-01")
    
    Returns:
        List of PaymentLink objects
    """
    from bot.database.models import Tenant, TenantStay, RentalObject, ObjectRSOLink
    from bot.config import config
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    # Get tenant's active stay
    stmt = select(TenantStay).where(
        TenantStay.tenant_id == tenant_id,
        TenantStay.status == "active"
    ).options(
        selectinload(TenantStay.rental_object).selectinload(RentalObject.comm_providers)
    )
    
    result = await session.execute(stmt)
    stay = result.scalar_one_or_none()
    
    if not stay:
        return []
    
    # Get RSO links
    rso_links_stmt = select(ObjectRSOLink).where(
        ObjectRSOLink.object_id == stay.object_id
    ).options(selectinload(ObjectRSOLink.provider))
    
    rso_result = await session.execute(rso_links_stmt)
    rso_links = rso_result.scalars().all()
    
    # Get YooMoney service
    yoomoney_token = getattr(config, 'YOOMONEY_TOKEN', None)
    yoomoney = YooMoneyService(api_token=yoomoney_token)
    
    # Generate links
    payment_links = []
    
    for link in rso_links:
        provider = link.provider
        
        # TODO: Calculate exact amount from charges
        # For now, use placeholder
        amount = Decimal("1500.00")
        
        payment_link = await yoomoney.create_utility_payment_link(
            rso_inn=provider.inn or "0000000000",
            personal_account=link.personal_account or link.account_number or "unknown",
            amount=amount,
            service_name=provider.name,
            period=period
        )
        
        payment_links.append(payment_link)
    
    return payment_links


# ===== Configuration =====

"""
Add to bot/config.py:

class Config:
    ...
    # YooMoney Settings
    YOOMONEY_TOKEN = os.getenv("YOOMONEY_TOKEN")
    YOOMONEY_CLIENT_ID = os.getenv("YOOMONEY_CLIENT_ID")
    
    # QIWI Settings (alternative)
    QIWI_TOKEN = os.getenv("QIWI_TOKEN")

Add to .env:

YOOMONEY_TOKEN=your_yoomoney_token
YOOMONEY_CLIENT_ID=your_client_id
"""
