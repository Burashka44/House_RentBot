import asyncio
from sqlalchemy import text
from bot.database.core import AsyncSessionLocal

async def run():
    async with AsyncSessionLocal() as s:
        try:
            print("Altering table...")
            # Detect DB type first? Assuming Postgres from context.
            # SQLite uses different syntax, but project uses asyncpg in requirements.
            await s.execute(text('ALTER TABLE comm_providers ALTER COLUMN object_id DROP NOT NULL'))
            await s.commit()
            print('Successfully made object_id nullable.')
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    try:
        if asyncio.get_event_loop_policy().__class__.__name__ == 'WindowsProactorEventLoopPolicy':
             asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except:
        pass
    asyncio.run(run())
