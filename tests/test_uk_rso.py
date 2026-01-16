import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from bot.database.core import Base
from bot.database.models import UKCompany, CommProvider, CommServiceType, RentalObject, ObjectRSOLink, UKRSOLink
from bot.services.rso_service import (
    create_uk_rso_link, 
    get_rso_by_uk, 
    assign_rso_to_object, 
    get_object_rso_links, 
    update_rso_account
)

async def test_uk_rso_flow():
    print("🚀 Starting UK/RSO Service Test...")
    
    # 1. Setup In-Memory DB
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    
    async with SessionLocal() as session:
        # 2. Create UK
        print("Step 1: Creating UK Company...")
        uk = UKCompany(name="Test UK", inn="1234567890")
        session.add(uk)
        await session.commit()
        print(f"✅ UK Created: {uk.id} - {uk.name}")
        
        # 3. Create Global RSO
        print("Step 2: Creating Global RSO...")
        provider = CommProvider(
            object_id=None, # Global
            service_type=CommServiceType.electric,
            name="Global Electric Co",
            active=True
        )
        session.add(provider)
        await session.commit()
        print(f"✅ Provider Created: {provider.id} - {provider.name}")
        
        # 4. Link RSO to UK
        print("Step 3: Linking RSO to UK...")
        await create_uk_rso_link(session, uk.id, provider.id)
        
        links = await get_rso_by_uk(session, uk.id)
        assert len(links) == 1
        assert links[0].id == provider.id
        print(f"✅ RSO linked to UK successfully.")
        
        # 5. Create Object
        print("Step 4: Creating Rental Object...")
        obj = RentalObject(
            owner_id=1,
            address="Test Street 1",
            status="free"
        )
        session.add(obj)
        await session.commit()
        print(f"✅ Object Created: {obj.id}")
        
        # 6. Link RSO to Object (Assign)
        print("Step 5: Assigning RSO to Object...")
        await assign_rso_to_object(session, obj.id, [provider.id])
        
        obj_links = await get_object_rso_links(session, obj.id)
        assert len(obj_links) == 1
        assert obj_links[0].provider_id == provider.id
        assert obj_links[0].account_number is None
        print(f"✅ RSO assigned to Object.")
        
        # 7. Update Account Number
        print("Step 6: Updating Account Number...")
        new_acc = "100-200-300"
        success = await update_rso_account(session, obj.id, provider.id, new_acc)
        assert success is True
        
        # Verify
        obj_links_updated = await get_object_rso_links(session, obj.id)
        assert obj_links_updated[0].account_number == new_acc
        print(f"✅ Account Number updated to {obj_links_updated[0].account_number}")

    print("🎉 All Tests Passed!")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_uk_rso_flow())
