"""
Debug script - check what happens when you press a button
"""
import asyncio
from bot.database.core import AsyncSessionLocal
from bot.database.models import User, Tenant
from sqlalchemy import select

async def check_user_status():
    print("Enter your Telegram ID:")
    tg_id = int(input().strip())
    
    async with AsyncSessionLocal() as session:
        # Check User table
        stmt = select(User).where(User.tg_id == tg_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        print(f"\n=== USER TABLE ===")
        if user:
            print(f"✅ Found: {user.full_name}")
            print(f"   Role: {user.role}")
            print(f"   Active: {user.is_active}")
        else:
            print(f"❌ Not found in users table")
        
        # Check Tenant table
        stmt = select(Tenant).where(Tenant.tg_id == tg_id)
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()
        
        print(f"\n=== TENANT TABLE ===")
        if tenant:
            print(f"✅ Found: {tenant.full_name}")
            print(f"   Status: {tenant.status}")
            print(f"   Consent: {tenant.personal_data_consent}")
        else:
            print(f"❌ Not found in tenants table")
        
        print(f"\n=== RECOMMENDATION ===")
        if not user and not tenant:
            print("❌ You need to be added to database!")
            print("   Run: python add_admin.py")
        elif user and not tenant:
            print("✅ You are admin - menu should work")
        elif tenant and not user:
            print("✅ You are tenant - menu should work")
        else:
            print("✅ You are both admin and tenant")

if __name__ == "__main__":
    asyncio.run(check_user_status())
