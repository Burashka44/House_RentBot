"""
Test script for UK/RSO address detection system
Tests with Sakhalin address: Южно-Сахалинск, проспект Мира, 373А
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bot.database.core import AsyncSessionLocal
from bot.database.models import UKCompany, House, CommProvider, UKRSOLink, CommServiceType
from bot.services.address_service import normalize_address, find_house, get_uk_by_house
from bot.services.rso_service import get_rso_by_uk


async def create_test_data():
    """Create test data for Sakhalin address"""
    print("Creating test data...")
    
    async with AsyncSessionLocal() as session:
        # 1. Create UK Company
        uk = UKCompany(
            name='ООО "Управление ЖКХ Южно-Сахалинск"',
            inn="6501234567",
            phone="+7 (4242) 12-34-56",
            email="uk@yuzhno.ru",
            address="г. Южно-Сахалинск, ул. Ленина, 1"
        )
        session.add(uk)
        await session.flush()
        print(f"✅ Created UK: {uk.name} (ID: {uk.id})")
        
        # 2. Create House
        house = House(
            region="Сахалинская область",
            city="Южно-Сахалинск",
            street="проспект Мира",
            house_number="373А",
            uk_id=uk.id
        )
        session.add(house)
        await session.flush()
        print(f"✅ Created House: {house.city}, {house.street}, {house.house_number} (ID: {house.id})")
        
        # 3. Create RSO Providers (for this UK)
        providers = [
            CommProvider(
                object_id=1,  # Will be replaced with real object later
                service_type=CommServiceType.electric,
                name="РАО Энергетические системы Востока",
                short_keywords=["рао", "энергия", "электр"],
                account_number="123456789"
            ),
            CommProvider(
                object_id=1,
                service_type=CommServiceType.water,
                name="МУП Водоканал Южно-Сахалинск",
                short_keywords=["водоканал", "вода"],
                account_number="987654321"
            ),
            CommProvider(
                object_id=1,
                service_type=CommServiceType.heating,
                name="ПАО Сахалинская ТЭЦ",
                short_keywords=["тэц", "тепло", "отопление"],
                account_number="555666777"
            ),
        ]
        
        for provider in providers:
            session.add(provider)
        
        await session.flush()
        print(f"✅ Created {len(providers)} RSO providers")
        
        # 4. Link RSO to UK
        for provider in providers:
            link = UKRSOLink(uk_id=uk.id, provider_id=provider.id)
            session.add(link)
        
        await session.commit()
        print(f"✅ Linked {len(providers)} RSO providers to UK")
        print("\n" + "="*60)


async def test_address_normalization():
    """Test address normalization"""
    print("\n📝 Testing Address Normalization")
    print("="*60)
    
    test_address = "Сахалинская Область город Южно-Сахалинск проспект мира 373А квартира 20"
    print(f"Input: {test_address}")
    
    norm = normalize_address(test_address)
    print(f"\nNormalized:")
    print(f"  Region: {norm.region}")
    print(f"  City: {norm.city}")
    print(f"  Street: {norm.street}")
    print(f"  House: {norm.house_number}")
    print("\n" + "="*60)
    
    return norm


async def test_house_lookup(norm_addr):
    """Test house lookup in database"""
    print("\n🔍 Testing House Lookup")
    print("="*60)
    
    async with AsyncSessionLocal() as session:
        house = await find_house(session, norm_addr)
        
        if house:
            print(f"✅ House FOUND!")
            print(f"  ID: {house.id}")
            print(f"  Address: {house.region}, {house.city}, {house.street}, {house.house_number}")
            print(f"  UK ID: {house.uk_id}")
            
            if house.uk_id:
                uk = await get_uk_by_house(session, house)
                if uk:
                    print(f"\n🏢 UK Company:")
                    print(f"  Name: {uk.name}")
                    print(f"  INN: {uk.inn}")
                    print(f"  Phone: {uk.phone}")
                    
                    # Get RSO
                    rso_list = await get_rso_by_uk(session, uk.id)
                    if rso_list:
                        print(f"\n⚡ RSO Providers ({len(rso_list)}):")
                        for rso in rso_list:
                            print(f"  • {rso.service_type.value}: {rso.name}")
                    else:
                        print("\n⚠️ No RSO providers linked to this UK")
            else:
                print("\n⚠️ House has no UK assigned")
        else:
            print("❌ House NOT FOUND in database")
            print("\nPossible reasons:")
            print("  1. Address normalization didn't match")
            print("  2. House not in database")
            print(f"\nSearched for:")
            print(f"  City: {norm_addr.city}")
            print(f"  Street: {norm_addr.street}")
            print(f"  House: {norm_addr.house_number}")
    
    print("\n" + "="*60)


async def main():
    print("\n" + "="*60)
    print("🧪 UK/RSO System Test")
    print("="*60)
    
    # Step 1: Create test data
    await create_test_data()
    
    # Step 2: Test normalization
    norm_addr = await test_address_normalization()
    
    # Step 3: Test lookup
    await test_house_lookup(norm_addr)
    
    print("\n✅ Test completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
