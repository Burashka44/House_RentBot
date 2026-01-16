"""
Migration script to transfer data from SQLite (bot.db) to PostgreSQL (Docker)
"""
import sqlite3
import asyncio
import sys
from sqlalchemy import text
from bot.database.core import AsyncSessionLocal

async def migrate_data():
    """Migrate all data from SQLite to PostgreSQL"""
    
    # Connect to SQLite
    sqlite_conn = sqlite3.connect('bot.db')
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()
    
    async with AsyncSessionLocal() as session:
        print("🔄 Starting data migration...")
        
        # 1. Migrate Tenants
        print("\n📋 Migrating tenants...")
        cursor.execute("SELECT * FROM tenants")
        tenants = cursor.fetchall()
        
        for tenant in tenants:
            await session.execute(text("""
                INSERT INTO tenants (id, tg_id, tg_username, full_name, phone, status, 
                                     personal_data_consent, consent_date, consent_version, created_at)
                VALUES (:id, :tg_id, :tg_username, :full_name, :phone, :status,
                        :personal_data_consent, :consent_date, :consent_version, :created_at)
                ON CONFLICT (id) DO NOTHING
            """), dict(tenant))
        
        await session.commit()
        print(f"✅ Migrated {len(tenants)} tenants")
        
        # 2. Migrate Objects (Addresses)
        print("\n🏠 Migrating objects...")
        cursor.execute("SELECT * FROM objects")
        objects = cursor.fetchall()
        
        for obj in objects:
            await session.execute(text("""
                INSERT INTO objects (id, owner_id, address, status, created_at)
                VALUES (:id, :owner_id, :address, :status, :created_at)
                ON CONFLICT (id) DO NOTHING
            """), dict(obj))
        
        await session.commit()
        print(f"✅ Migrated {len(objects)} objects")
        
        # 3. Migrate Tenant Stays
        print("\n🔑 Migrating tenant stays...")
        cursor.execute("SELECT * FROM tenant_stays")
        stays = cursor.fetchall()
        
        for stay in stays:
            stay_dict = dict(stay)
            # Handle tax_rate if it doesn't exist in old DB
            if 'tax_rate' not in stay_dict:
                stay_dict['tax_rate'] = 0.0
            # Handle notifications_mode - new field in PostgreSQL
            if 'notifications_mode' not in stay_dict:
                stay_dict['notifications_mode'] = 'all'  # Default value
                
            await session.execute(text("""
                INSERT INTO tenant_stays (id, tenant_id, object_id, date_from, date_to,
                                          rent_amount, rent_day, comm_day, status, tax_rate, 
                                          notifications_mode, created_at)
                VALUES (:id, :tenant_id, :object_id, :date_from, :date_to,
                        :rent_amount, :rent_day, :comm_day, :status, :tax_rate,
                        :notifications_mode, :created_at)
                ON CONFLICT (id) DO NOTHING
            """), stay_dict)
        
        await session.commit()
        print(f"✅ Migrated {len(stays)} stays")
        
        # 4. Migrate Payments
        print("\n💰 Migrating payments...")
        cursor.execute("SELECT * FROM payments")
        payments = cursor.fetchall()
        
        for payment in payments:
            payment_dict = dict(payment)
            # Add new fields with defaults if they don't exist
            if 'total_amount' not in payment_dict:
                payment_dict['total_amount'] = payment_dict.get('amount', 0)
            if 'allocated_amount' not in payment_dict:
                payment_dict['allocated_amount'] = 0
            if 'unallocated_amount' not in payment_dict:
                payment_dict['unallocated_amount'] = payment_dict.get('amount', 0)
            if 'method' not in payment_dict:
                payment_dict['method'] = 'manual'  # Default payment method
                
            await session.execute(text("""
                INSERT INTO payments (id, stay_id, amount, type, status, source, method,
                                      confirmed_at, created_at, total_amount, allocated_amount, unallocated_amount)
                VALUES (:id, :stay_id, :amount, :type, :status, :source, :method,
                        :confirmed_at, :created_at, :total_amount, :allocated_amount, :unallocated_amount)
                ON CONFLICT (id) DO NOTHING
            """), payment_dict)
        
        await session.commit()
        print(f"✅ Migrated {len(payments)} payments")
        
        # 5. Migrate Rent Charges (if exist)
        print("\n📊 Migrating rent charges...")
        try:
            cursor.execute("SELECT * FROM rent_charges")
            charges = cursor.fetchall()
            
            for charge in charges:
                charge_dict = dict(charge)
                # Add new tax fields with defaults
                if 'base_amount' not in charge_dict:
                    charge_dict['base_amount'] = charge_dict.get('amount', 0)
                if 'tax_amount' not in charge_dict:
                    charge_dict['tax_amount'] = 0
                if 'tax_rate_snapshot' not in charge_dict:
                    charge_dict['tax_rate_snapshot'] = 0
                    
                await session.execute(text("""
                    INSERT INTO rent_charges (id, stay_id, month, amount, status, created_at,
                                              base_amount, tax_amount, tax_rate_snapshot)
                    VALUES (:id, :stay_id, :month, :amount, :status, :created_at,
                            :base_amount, :tax_amount, :tax_rate_snapshot)
                    ON CONFLICT (id) DO NOTHING
                """), charge_dict)
            
            await session.commit()
            print(f"✅ Migrated {len(charges)} rent charges")
        except sqlite3.OperationalError:
            print("⚠️ No rent_charges table in old DB")
        
        # 6. Update sequences - PostgreSQL will auto-increment from max values
        print("\n🔢 PostgreSQL sequences will auto-increment from current max IDs")
        
        # 7. Verify migration
        print("\n✅ Verifying migration...")
        result = await session.execute(text("SELECT COUNT(*) FROM tenants"))
        print(f"   Tenants in PostgreSQL: {result.scalar()}")
        
        result = await session.execute(text("SELECT COUNT(*) FROM objects"))
        print(f"   Objects in PostgreSQL: {result.scalar()}")
        
        result = await session.execute(text("SELECT COUNT(*) FROM tenant_stays"))
        print(f"   Stays in PostgreSQL: {result.scalar()}")
        
        result = await session.execute(text("SELECT COUNT(*) FROM payments"))
        print(f"   Payments in PostgreSQL: {result.scalar()}")
        
        print("\n🎉 Migration completed successfully!")
    
    sqlite_conn.close()

if __name__ == "__main__":
    try:
        asyncio.run(migrate_data())
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
