"""
Quick script to check and add admin user
"""
import asyncio
from bot.database.core import AsyncSessionLocal
from bot.database.models import User, UserRole
from sqlalchemy import select

async def check_and_add_admin():
    print("Enter your Telegram ID:")
    tg_id = int(input().strip())
    
    async with AsyncSessionLocal() as session:
        # Check if user exists
        stmt = select(User).where(User.tg_id == tg_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            print(f"✅ User found: {user.full_name} ({user.role})")
        else:
            print("❌ User not found. Creating admin...")
            
            print("Enter your full name:")
            full_name = input().strip()
            
            new_user = User(
                tg_id=tg_id,
                full_name=full_name,
                role=UserRole.owner.value,
                is_active=True
            )
            session.add(new_user)
            await session.commit()
            print(f"✅ Admin created: {full_name}")
        
        # Show all users
        stmt = select(User)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        print("\n📋 All users in database:")
        for u in users:
            print(f"  - {u.full_name} (ID: {u.tg_id}, Role: {u.role})")

if __name__ == "__main__":
    asyncio.run(check_and_add_admin())
