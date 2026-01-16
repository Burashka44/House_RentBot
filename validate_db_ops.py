#!/usr/bin/env python3
"""
Database Operations Checker
Проверяет наличие CRUD операций для каждой таблицы
"""
from bot.database.models import Base
from sqlalchemy import inspect
import re
from pathlib import Path

# Получить все таблицы
tables = [table.name for table in Base.metadata.sorted_tables]

print("=" * 70)
print("ПРОВЕРКА ОПЕРАЦИЙ С БАЗОЙ ДАННЫХ")
print("=" * 70)

# Проверка каждой таблицы
services_dir = Path("bot/services")
handlers_dir = Path("bot/handlers")

def search_operations(table_name, model_name=None):
    """Поиск операций для таблицы"""
    operations = {
        'create': [],
        'read': [],
        'update': [],
        'delete': [],
        'archive': []
    }
    
    # Поиск в сервисах
    for file in services_dir.glob("*.py"):
        content = file.read_text(encoding='utf-8')
        
        # CREATE
        if re.search(rf'\b{model_name or table_name}\s*\(', content, re.IGNORECASE):
            operations['create'].append(file.name)
        
        # READ (select)
        if re.search(rf'select\({model_name or table_name}\)', content, re.IGNORECASE):
            operations['read'].append(file.name)
        
        # UPDATE
        if re.search(rf'\.update\(.*{model_name or table_name}', content, re.IGNORECASE):
            operations['update'].append(file.name)
        
        # DELETE
        if re.search(rf'delete\({model_name or table_name}\)', content, re.IGNORECASE):
            operations['delete'].append(file.name)
        
        # ARCHIVE (status change)
        if 'archived' in content and (model_name or table_name).lower() in content.lower():
            operations['archive'].append(file.name)
    
    return operations

# Маппинг таблиц к моделям
table_to_model = {
    'tenants': 'Tenant',
    'objects': 'RentalObject',
    'tenant_stays': 'TenantStay',
    'comm_providers': 'CommProvider',
    'comm_charges': 'CommCharge',
    'rent_charges': 'RentCharge',
    'payments': 'Payment',
    'payment_allocations': 'PaymentAllocation',
    'payment_receipts': 'PaymentReceipt',
    'users': 'User',
    'invite_codes': 'InviteCode',
    'admin_contacts': 'AdminContact',
    'uk_companies': 'UKCompany',
    'object_rso_links': 'ObjectRSOLink',
    'uk_rso_links': 'UKRSOLink',
    'stay_occupants': 'StayOccupant',
    'support_messages': 'SupportMessage',
    'support_attachments': 'SupportAttachment',
    'object_settings': 'ObjectSettings',
    'tenant_settings': 'TenantSettings',
    'rent_receivers': 'RentReceiver',
    'service_subscriptions': 'ServiceSubscription',
    'houses': 'House'
}

# Критичные таблицы (должны иметь все операции)
critical_tables = [
    'tenants', 'objects', 'tenant_stays', 'payments', 
    'comm_charges', 'rent_charges', 'users'
]

# Справочные таблицы (только read/create)
reference_tables = [
    'uk_companies', 'object_rso_links', 'uk_rso_links'
]

# Служебные таблицы
service_tables = [
    'invite_codes', 'support_messages', 'payment_receipts'
]

print(f"\nВсего таблиц: {len(tables)}\n")

missing_operations = []

for table in sorted(tables):
    model = table_to_model.get(table, table.title().replace('_', ''))
    ops = search_operations(table, model)
    
    has_create = len(ops['create']) > 0
    has_read = len(ops['read']) > 0
    has_update = len(ops['update']) > 0
    has_delete = len(ops['delete']) > 0
    has_archive = len(ops['archive']) > 0
    
    status = "✅"
    issues = []
    
    if table in critical_tables:
        if not has_create:
            issues.append("❌ CREATE")
            status = "⚠️"
        if not has_read:
            issues.append("❌ READ")
            status = "⚠️"
        # Archive вместо delete для некоторых
        if table in ['tenants', 'tenant_stays', 'users']:
            if not has_archive:
                issues.append("❌ ARCHIVE")
                status = "⚠️"
    
    if table in reference_tables:
        if not has_create or not has_read:
            issues.append("❌ CRUD incomplete")
            status = "⚠️"
    
    # Вывод
    ops_str = f"C:{len(ops['create'])} R:{len(ops['read'])} U:{len(ops['update'])} D:{len(ops['delete'])} A:{len(ops['archive'])}"
    
    if issues:
        print(f"{status} {table:25} [{ops_str}] - {', '.join(issues)}")
        missing_operations.append((table, issues))
    else:
        print(f"{status} {table:25} [{ops_str}]")

print("\n" + "=" * 70)
print("ИТОГ")
print("=" * 70)

if missing_operations:
    print(f"\n⚠️  Найдено {len(missing_operations)} таблиц с неполными операциями:\n")
    for table, issues in missing_operations:
        print(f"  • {table}: {', '.join(issues)}")
else:
    print("\n✅ Все критичные таблицы имеют необходимые операции!")

# Проверка лишних таблиц
print("\n" + "=" * 70)
print("АНАЛИЗ ИСПОЛЬЗОВАНИЯ ТАБЛИЦ")
print("=" * 70)

unused_tables = []
for table in tables:
    model = table_to_model.get(table, table.title().replace('_', ''))
    
    # Поиск упоминаний в коде
    found = False
    for file in list(services_dir.glob("*.py")) + list(handlers_dir.glob("*.py")):
        content = file.read_text(encoding='utf-8')
        if model in content or table in content:
            found = True
            break
    
    if not found:
        unused_tables.append(table)

if unused_tables:
    print(f"\n⚠️  Возможно неиспользуемые таблицы ({len(unused_tables)}):")
    for table in unused_tables:
        print(f"  • {table}")
else:
    print("\n✅ Все таблицы используются в коде!")
