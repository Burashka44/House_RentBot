#!/usr/bin/env python3
"""
Comprehensive Project Audit
Проверяет весь проект на потенциальные проблемы
"""
import re
from pathlib import Path
from collections import defaultdict

print("=" * 80)
print("КОМПЛЕКСНЫЙ АУДИТ ПРОЕКТА")
print("=" * 80)

# === 1. ПОИСК TODO И FIXME ===
print("\n📝 1. TODO И FIXME КОММЕНТАРИИ")
print("-" * 80)

todos = []
for file in Path("bot").rglob("*.py"):
    content = file.read_text(encoding='utf-8')
    for i, line in enumerate(content.split('\n'), 1):
        if 'TODO' in line or 'FIXME' in line or 'XXX' in line:
            todos.append((str(file), i, line.strip()))

if todos:
    print(f"Найдено {len(todos)} TODO/FIXME:\n")
    for file, line, text in todos[:15]:  # Первые 15
        print(f"  {file}:{line}")
        print(f"    {text}")
else:
    print("✅ TODO/FIXME не найдены")

# === 2. НЕИСПОЛЬЗУЕМЫЕ ФАЙЛЫ ===
print("\n\n📁 2. ПОТЕНЦИАЛЬНО НЕИСПОЛЬЗУЕМЫЕ ФАЙЛЫ")
print("-" * 80)

# Список всех .py файлов в bot/
all_files = list(Path("bot").rglob("*.py"))
imported_files = set()

# Поиск импортов
for file in all_files:
    content = file.read_text(encoding='utf-8')
    # Найти все импорты вида "from bot.xxx import"
    imports = re.findall(r'from bot\.([a-z_\.]+) import', content)
    for imp in imports:
        imported_files.add(imp.replace('.', '/') + '.py')

unused = []
for file in all_files:
    rel_path = str(file.relative_to('bot'))
    if rel_path not in imported_files and '__init__' not in rel_path and '__pycache__' not in str(file):
        # Проверка, что это не entry point
        if 'main.py' not in rel_path and 'cron.py' not in rel_path:
            unused.append(rel_path)

if unused:
    print(f"Найдено {len(unused)} потенциально неиспользуемых файлов:\n")
    for f in unused[:10]:
        print(f"  ⚠️  bot/{f}")
else:
    print("✅ Все файлы используются")

# === 3. ДУБЛИРОВАНИЕ ХЭНДЛЕРОВ ===
print("\n\n🔄 3. ДУБЛИРОВАНИЕ ХЭНДЛЕРОВ")
print("-" * 80)

handlers = defaultdict(list)
for file in Path("bot/handlers").glob("*.py"):
    content = file.read_text(encoding='utf-8')
    # Найти все @router.callback_query и @router.message
    matches = re.findall(r'@router\.(callback_query|message)\([^)]+\)\s*async def (\w+)', content)
    for _, func_name in matches:
        handlers[func_name].append(file.name)

duplicates = {name: files for name, files in handlers.items() if len(files) > 1}

if duplicates:
    print(f"Найдено {len(duplicates)} дублирующихся хэндлеров:\n")
    for name, files in list(duplicates.items())[:10]:
        print(f"  ⚠️  {name}: {', '.join(files)}")
else:
    print("✅ Дублирующихся хэндлеров не найдено")

# === 4. НЕИСПОЛЬЗУЕМЫЕ СОСТОЯНИЯ ===
print("\n\n🔀 4. НЕИСПОЛЬЗУЕМЫЕ СОСТОЯНИЯ (FSM)")
print("-" * 80)

# Получить все состояния из states.py
states_file = Path("bot/states.py")
if states_file.exists():
    states_content = states_file.read_text(encoding='utf-8')
    # Найти все классы State
    state_classes = re.findall(r'class (\w+State)\(StatesGroup\)', states_content)
    
    # Проверить использование каждого
    unused_states = []
    for state_class in state_classes:
        used = False
        for file in Path("bot/handlers").glob("*.py"):
            content = file.read_text(encoding='utf-8')
            if state_class in content:
                used = True
                break
        if not used:
            unused_states.append(state_class)
    
    if unused_states:
        print(f"Найдено {len(unused_states)} неиспользуемых состояний:\n")
        for state in unused_states:
            print(f"  ⚠️  {state}")
    else:
        print("✅ Все состояния используются")

# === 5. DEPRECATED ИМПОРТЫ ===
print("\n\n📦 5. УСТАРЕВШИЕ/НЕИСПОЛЬЗУЕМЫЕ ИМПОРТЫ")
print("-" * 80)

# Проверка на неиспользуемые импорты (простая эвристика)
import_issues = []
for file in list(Path("bot/handlers").glob("*.py")) + list(Path("bot/services").glob("*.py")):
    content = file.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # Найти импорты
    for i, line in enumerate(lines, 1):
        if line.strip().startswith('from ') or line.strip().startswith('import '):
            # Проверить, используется ли
            imports = re.findall(r'import (\w+)', line)
            for imp in imports:
                # Простая проверка: есть ли это слово в коде после импортов
                code_after_imports = '\n'.join(lines[i:])
                if imp not in code_after_imports and imp != 'typing':
                    import_issues.append((str(file.relative_to('bot')), i, imp))

if import_issues:
    print(f"Найдено {len(import_issues)} потенциально неиспользуемых импортов:\n")
    for file, line, imp in import_issues[:10]:
        print(f"  ⚠️  {file}:{line} - {imp}")
else:
    print("✅ Явных проблем с импортами не найдено")

# === 6. ДЛИННЫЕ ФУНКЦИИ ===
print("\n\n📏 6. ДЛИННЫЕ ФУНКЦИИ (>100 строк)")
print("-" * 80)

long_functions = []
for file in list(Path("bot/handlers").glob("*.py")) + list(Path("bot/services").glob("*.py")):
    content = file.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    current_func = None
    func_start = 0
    
    for i, line in enumerate(lines):
        if line.strip().startswith('async def ') or line.strip().startswith('def '):
            if current_func and (i - func_start) > 100:
                long_functions.append((str(file.relative_to('bot')), current_func, i - func_start))
            
            match = re.search(r'def (\w+)', line)
            if match:
                current_func = match.group(1)
                func_start = i

if long_functions:
    print(f"Найдено {len(long_functions)} длинных функций:\n")
    for file, func, length in sorted(long_functions, key=lambda x: x[2], reverse=True)[:10]:
        print(f"  ⚠️  {file}::{func} - {length} строк")
else:
    print("✅ Все функции разумной длины")

# === 7. HARDCODED ЗНАЧЕНИЯ ===
print("\n\n🔢 7. HARDCODED ЗНАЧЕНИЯ")
print("-" * 80)

hardcoded = []
for file in list(Path("bot/handlers").glob("*.py")) + list(Path("bot/services").glob("*.py")):
    content = file.read_text(encoding='utf-8')
    
    # Поиск магических чисел (кроме 0, 1, -1)
    magic_numbers = re.findall(r'\b(\d{2,})\b', content)
    if magic_numbers:
        # Фильтр: только уникальные и > 10
        unique = set(int(n) for n in magic_numbers if int(n) > 10)
        if unique:
            hardcoded.append((str(file.relative_to('bot')), len(unique)))

if hardcoded:
    print(f"Найдено файлов с hardcoded значениями: {len(hardcoded)}\n")
    for file, count in sorted(hardcoded, key=lambda x: x[1], reverse=True)[:5]:
        print(f"  ⚠️  {file} - {count} уникальных чисел")
    print("\n  💡 Рекомендация: вынести в config или константы")
else:
    print("✅ Hardcoded значения в норме")

# === ИТОГ ===
print("\n" + "=" * 80)
print("ИТОГОВАЯ СВОДКА")
print("=" * 80)

total_issues = len(todos) + len(unused) + len(duplicates) + len(unused_states) + len(import_issues) + len(long_functions)

if total_issues == 0:
    print("\n🎉 ПРОЕКТ В ОТЛИЧНОМ СОСТОЯНИИ!")
    print("   Критичных проблем не найдено.")
else:
    print(f"\n⚠️  Найдено {total_issues} потенциальных улучшений:")
    print(f"   • TODO/FIXME: {len(todos)}")
    print(f"   • Неиспользуемые файлы: {len(unused)}")
    print(f"   • Дублирующиеся хэндлеры: {len(duplicates)}")
    print(f"   • Неиспользуемые состояния: {len(unused_states)}")
    print(f"   • Проблемные импорты: {len(import_issues)}")
    print(f"   • Длинные функции: {len(long_functions)}")
    print("\n   💡 Большинство из них не критичны и могут быть исправлены постепенно.")

print("\n" + "=" * 80)
