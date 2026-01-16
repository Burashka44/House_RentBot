#!/usr/bin/env python3
"""
Validation script for manual payment marking feature
"""
import sys
import asyncio
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

async def validate_feature():
    print("=" * 70)
    print("ВАЛИДАЦИЯ: Ручная отметка об оплате")
    print("=" * 70)
    
    # 1. Check model
    print("\n1. Проверка модели Payment...")
    try:
        from bot.database.models import Payment
        
        # Check if fields exist
        has_is_manual = hasattr(Payment, 'is_manual')
        has_marked_by = hasattr(Payment, 'marked_by')
        
        if has_is_manual and has_marked_by:
            print("   ✅ Поля is_manual и marked_by присутствуют")
        else:
            print(f"   ❌ Отсутствуют поля: is_manual={has_is_manual}, marked_by={has_marked_by}")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка импорта модели: {e}")
        return False
    
    # 2. Check service function
    print("\n2. Проверка сервисной функции...")
    try:
        from bot.services.payment_service import mark_charge_as_paid
        import inspect
        
        sig = inspect.signature(mark_charge_as_paid)
        params = list(sig.parameters.keys())
        
        required_params = ['session', 'charge_id', 'charge_type', 'admin_id']
        if all(p in params for p in required_params):
            print(f"   ✅ Функция mark_charge_as_paid найдена")
            print(f"   ✅ Параметры: {params}")
        else:
            print(f"   ❌ Отсутствуют параметры: {set(required_params) - set(params)}")
            return False
    except ImportError as e:
        print(f"   ❌ Функция не найдена: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return False
    
    # 3. Check handlers
    print("\n3. Проверка хэндлеров...")
    try:
        admin_file = Path("bot/handlers/admin.py")
        content = admin_file.read_text(encoding='utf-8')
        
        has_confirm = 'confirm_mark_paid' in content
        has_execute = 'execute_mark_paid' in content
        has_button = 'mark_paid_rent_' in content
        
        if has_confirm and has_execute and has_button:
            print("   ✅ Хэндлеры confirm_mark_paid и execute_mark_paid найдены")
            print("   ✅ Кнопки в отчёте должников добавлены")
        else:
            print(f"   ❌ Отсутствуют компоненты: confirm={has_confirm}, execute={has_execute}, button={has_button}")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка чтения файла: {e}")
        return False
    
    # 4. Check migration
    print("\n4. Проверка миграции...")
    try:
        migration_file = Path("migrations/versions/3013bcb190fa_add_manual_payment_fields.py")
        if migration_file.exists():
            content = migration_file.read_text(encoding='utf-8')
            has_is_manual = 'is_manual' in content
            has_marked_by = 'marked_by' in content
            
            if has_is_manual and has_marked_by:
                print("   ✅ Миграция 3013bcb190fa найдена")
                print("   ✅ Содержит добавление полей is_manual и marked_by")
            else:
                print(f"   ❌ Миграция неполная: is_manual={has_is_manual}, marked_by={has_marked_by}")
                return False
        else:
            print("   ❌ Файл миграции не найден")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка проверки миграции: {e}")
        return False
    
    print("\n" + "=" * 70)
    print("РЕЗУЛЬТАТ: ✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    print("=" * 70)
    print("\nФункция готова к использованию!")
    print("\nКак использовать:")
    print("1. Админ → 📊 Отчёты → 📋 Должники")
    print("2. Нажать '✅ Отметить оплаченным' у нужного начисления")
    print("3. Подтвердить действие")
    print("4. Готово! Создан виртуальный платёж с is_manual=True")
    
    return True

if __name__ == "__main__":
    result = asyncio.run(validate_feature())
    sys.exit(0 if result else 1)
