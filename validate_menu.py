#!/usr/bin/env python3
"""
Menu Button Validator
Проверяет, что для каждой кнопки в меню есть соответствующий handler
"""
import re
from pathlib import Path
from collections import defaultdict

def extract_callbacks_from_file(filepath):
    """Извлекает все callback_data из файла"""
    content = Path(filepath).read_text(encoding='utf-8')
    
    # Найти все callback_data="..."
    callbacks_defined = re.findall(r'callback_data=["\']([^"\']+)["\']', content)
    
    # Найти все хэндлеры @router.callback_query(F.data == "...")
    handlers_exact = re.findall(r'@router\.callback_query\(F\.data\s*==\s*["\']([^"\']+)["\']', content)
    
    # Найти хэндлеры с startswith
    handlers_prefix = re.findall(r'@router\.callback_query\(F\.data\.startswith\(["\']([^"\']+)["\']', content)
    
    return callbacks_defined, handlers_exact, handlers_prefix

def check_admin_menu():
    """Проверка admin.py"""
    print("=" * 60)
    print("ПРОВЕРКА: bot/handlers/admin.py")
    print("=" * 60)
    
    filepath = r"f:\Work\work8\bot\handlers\admin.py"
    callbacks, handlers_exact, handlers_prefix = extract_callbacks_from_file(filepath)
    
    print(f"\n📋 Найдено кнопок: {len(set(callbacks))}")
    print(f"✅ Найдено exact handlers: {len(set(handlers_exact))}")
    print(f"🔍 Найдено prefix handlers: {len(set(handlers_prefix))}")
    
    # Группировка по типу
    callback_groups = defaultdict(list)
    for cb in callbacks:
        if '_' in cb:
            prefix = cb.split('_')[0]
            callback_groups[prefix].append(cb)
        else:
            callback_groups['single'].append(cb)
    
    # Проверка покрытия
    missing = []
    covered = []
    
    for cb in set(callbacks):
        # Проверка exact match
        if cb in handlers_exact:
            covered.append(cb)
            continue
        
        # Проверка prefix match
        matched = False
        for prefix in handlers_prefix:
            if cb.startswith(prefix):
                covered.append(cb)
                matched = True
                break
        
        if not matched:
            missing.append(cb)
    
    print(f"\n✅ Покрыто handlers: {len(covered)}")
    print(f"❌ БЕЗ handlers: {len(missing)}")
    
    if missing:
        print("\n⚠️  КНОПКИ БЕЗ ХЭНДЛЕРОВ:")
        for cb in sorted(missing):
            print(f"   - {cb}")
    
    # Показать основные меню
    print("\n📊 ОСНОВНЫЕ МЕНЮ:")
    main_menus = ['list_objects', 'list_tenants', 'list_payments', 'reports_menu', 
                  'manage_admins', 'manage_uk_rso', 'add_object', 'add_stay_start']
    
    for menu in main_menus:
        if menu in handlers_exact:
            print(f"   ✅ {menu}")
        elif any(menu.startswith(p) for p in handlers_prefix):
            print(f"   🔍 {menu} (prefix)")
        else:
            print(f"   ❌ {menu} - ОТСУТСТВУЕТ!")
    
    return missing

def check_common_menu():
    """Проверка common.py"""
    print("\n" + "=" * 60)
    print("ПРОВЕРКА: bot/handlers/common.py")
    print("=" * 60)
    
    filepath = r"f:\Work\work8\bot\handlers\common.py"
    callbacks, handlers_exact, handlers_prefix = extract_callbacks_from_file(filepath)
    
    print(f"\n📋 Найдено кнопок: {len(set(callbacks))}")
    print(f"✅ Найдено handlers: {len(set(handlers_exact))}")
    
    missing = []
    for cb in set(callbacks):
        if cb not in handlers_exact and not any(cb.startswith(p) for p in handlers_prefix):
            missing.append(cb)
    
    if missing:
        print("\n⚠️  КНОПКИ БЕЗ ХЭНДЛЕРОВ:")
        for cb in sorted(missing):
            print(f"   - {cb}")
    
    return missing

if __name__ == "__main__":
    print("\n🔍 ВАЛИДАЦИЯ МЕНЮ БОТА\n")
    
    admin_missing = check_admin_menu()
    common_missing = check_common_menu()
    
    print("\n" + "=" * 60)
    print("ИТОГ")
    print("=" * 60)
    
    total_missing = len(admin_missing) + len(common_missing)
    
    if total_missing == 0:
        print("✅ ВСЕ КНОПКИ ИМЕЮТ ХЭНДЛЕРЫ!")
    else:
        print(f"❌ Найдено {total_missing} кнопок без хэндлеров")
        print("\nРекомендация: Добавить недостающие хэндлеры или удалить кнопки")
