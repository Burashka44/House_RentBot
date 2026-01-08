"""
Simple test of address normalization (no DB required)
"""

# Simulated normalize_address function (copy from address_service.py)
import re
from typing import Optional

class NormalizedAddress:
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
    """Normalize address string to structured format"""
    address = " ".join(raw_address.split())
    
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
        parts = [p.strip() for p in address.split(',')]
        street = parts[1] if len(parts) > 1 else "Неизвестно"
    
    # Extract house number
    house_match = re.search(r'д\.\s*(\d+[А-ЯЁа-яё]?(?:/\d+)?)', address, re.IGNORECASE)
    if not house_match:
        # Try without "д."
        house_match = re.search(r'\s(\d+[А-ЯЁа-яё])\s', address, re.IGNORECASE)
    house_number = house_match.group(1) if house_match else "0"
    
    # Extract region
    region_match = re.search(r'([А-ЯЁ][а-яё]+\s+(?:область|край|республика))', address, re.IGNORECASE)
    region = region_match.group(1) if region_match else None
    
    return NormalizedAddress(
        city=city,
        street=street,
        house_number=house_number,
        region=region
    )


# TEST
print("="*70)
print("🧪 ТЕСТ НОРМАЛИЗАЦИИ АДРЕСА")
print("="*70)

test_address = "Сахалинская Область город Южно-Сахалинск проспект мира 373А квартира 20"
print(f"\n📍 Исходный адрес:")
print(f"   {test_address}")

result = normalize_address(test_address)

print(f"\n✅ Результат нормализации:")
print(f"   Регион:      '{result.region}'")
print(f"   Город:       '{result.city}'")
print(f"   Улица:       '{result.street}'")
print(f"   Дом:         '{result.house_number}'")
print(f"\n📋 Полный адрес: {result}")

print("\n" + "="*70)
print("💡 АНАЛИЗ:")
print("="*70)

# Check if normalization is correct
expected = {
    'region': 'Сахалинская Область',
    'city': 'Южно-Сахалинск',
    'street': 'мира',  # Will be 'проспект мира' or just 'мира'
    'house': '373А'
}

checks = []
if result.region and 'Сахалинская' in result.region:
    checks.append("✅ Регион определен правильно")
else:
    checks.append("❌ Регион не определен или неверный")

if 'Южно-Сахалинск' in result.city or 'Южно' in result.city:
    checks.append("✅ Город определен правильно")
else:
    checks.append("❌ Город не определен или неверный")

if 'мира' in result.street.lower() or 'Мира' in result.street:
    checks.append("✅ Улица определена правильно")
else:
    checks.append("❌ Улица не определена или неверная")

if '373' in result.house_number and 'А' in result.house_number:
    checks.append("✅ Номер дома определен правильно")
else:
    checks.append("❌ Номер дома не определен или неверный")

for check in checks:
    print(check)

print("\n" + "="*70)
print("🔍 ДЛЯ ПОИСКА В БД ДОЛЖЕН БЫТЬ ЗАПИСАН ДОМ:")
print("="*70)
print(f"""
INSERT INTO houses (region, city, street, house_number, uk_id)
VALUES ('{result.region}', '{result.city}', '{result.street}', '{result.house_number}', <uk_id>);
""")

print("="*70)
