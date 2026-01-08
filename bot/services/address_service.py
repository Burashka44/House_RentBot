import re
from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import House, UKCompany

class NormalizedAddress:
    """Normalized address structure"""
    def __init__(self, city: str, street: str, house_number: str, region: Optional[str] = None):
        self.region = region
        self.city = city
        self.street = street
        self.house_number = house_number
    
    def __str__(self):
        parts = []
        if self.region:
            parts.append(self.region)
        parts.extend([self.city, self.street, self.house_number])
        return ", ".join(parts)


def normalize_address(raw_address: str) -> NormalizedAddress:
    """
    Normalize address string to structured format.
    This is a simple implementation. In production, use FIAS/DaData/etc.
    
    Example input: "Москва, ул. Ленина, д. 12А"
    Returns: NormalizedAddress(city="Москва", street="ул. Ленина", house_number="12А")
    """
    # Remove extra spaces
    address = " ".join(raw_address.split())
    
    # Simple regex patterns (very basic, real implementation needs more sophistication)
    # Extract city
    city_match = re.search(r'г\.\s*([^,]+)|([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?),', address)
    city = city_match.group(1) or city_match.group(2) if city_match else "Неизвестно"
    city = city.strip()
    
    # Extract street
    street_patterns = [
        r'ул\.\s*([^,]+)',
        r'проспект\s+([^,]+)',
        r'пр-т\s+([^,]+)',
        r'пер\.\s*([^,]+)',
        r'наб\.\s*([^,]+)',
    ]
    street = None
    for pattern in street_patterns:
        match = re.search(pattern, address, re.IGNORECASE)
        if match:
            street = match.group(1).strip()
            break
    
    if not street:
        # Fallback: take second part between commas
        parts = [p.strip() for p in address.split(',')]
        street = parts[1] if len(parts) > 1 else "Неизвестно"
    
    # Extract house number
    house_match = re.search(r'д\.\s*(\d+[А-ЯЁа-яё]?(?:/\d+)?)', address, re.IGNORECASE)
    if not house_match:
        # Try pattern without "д." - number followed by letter at word boundary
        house_match = re.search(r'\b(\d+[А-ЯЁа-яё])\b', address)
    if not house_match:
        # Last resort: just a number
        house_match = re.search(r'\b(\d+)\b(?!\s*(?:квартира|кв\.|этаж))', address, re.IGNORECASE)
    house_number = house_match.group(1) if house_match else "0"
    
    # Extract region (optional)
    region_match = re.search(r'([А-ЯЁ][а-яё]+\s+(?:область|край|республика))', address)
    region = region_match.group(1) if region_match else None
    
    return NormalizedAddress(
        city=city,
        street=street,
        house_number=house_number,
        region=region
    )


async def find_house(session: AsyncSession, norm_addr: NormalizedAddress) -> Optional[House]:
    """
    Find house in database by normalized address.
    Returns House object if found, None otherwise.
    """
    stmt = select(House).where(
        House.city == norm_addr.city,
        House.street == norm_addr.street,
        House.house_number == norm_addr.house_number
    )
    
    if norm_addr.region:
        stmt = stmt.where(House.region == norm_addr.region)
    
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_uk_by_house(session: AsyncSession, house: House) -> Optional[UKCompany]:
    """Get UK company associated with a house"""
    if not house.uk_id:
        return None
    
    stmt = select(UKCompany).where(UKCompany.id == house.uk_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
