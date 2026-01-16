# HouseBot - Аренда и Коммунальные Платежи / Rental & Utility Management Bot

Telegram-бот для управления арендой недвижимости, жильцами, платежами и коммунальными услугами (УК/РСО).

**Telegram bot for rental property management, tenants, payments, and utility providers (UK/RSO).**

---

## 🚀 Возможности / Features

- 📋 Учёт арендаторов и заселений / Tenant & stay management
- 💰 Аренда и коммунальные платежи / Rent & utility bill tracking
- 📸 Приём чеков с автопроверкой / Payment receipt verification via photos  
- 🏢 **Управление УК и РСО** / UK & RSO provider management
- 📨 Автоуведомления / Automated rent/utility reminders
- 💬 Переписка арендатор ↔ админ / Tenant-admin messaging

---

## 📋 Требования / Requirements

- Python 3.11+
- PostgreSQL 13+ или SQLite (для разработки / for development)
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

---

## 🛠️ Установка / Installation

### 1. Клонировать репозиторий / Clone repository
```bash
git clone https://github.com/Burashka44/House_RentBot.git
cd House_RentBot
```

### 2. Виртуальное окружение / Virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Зависимости / Dependencies
```bash
pip install -r requirements.txt
```

### 4. Настройка .env / Configure .env
Скопируйте `.env.example` в `.env` и заполните:
```bash
cp .env.example .env
```

Пример / Example:
```env
BOT_TOKEN=your_bot_token_here
DB_USER=postgres
DB_PASS=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=rent_bot
ADMIN_IDS=123456789,987654321
```

### 5. Инициализация БД / Initialize database
```bash
alembic upgrade head
```

### 6. Запуск / Start bot
```bash
python bot/main.py
```

---

## 📚 Использование / Usage

### Для администраторов / For Admins
1. `/start` → Админ-панель / Admin panel
2. **🏠 Мои адреса** → Управление объектами / Manage rental objects
3. **🏢 Управление УК/РСО** → УК и поставщики / UK & RSO providers
4. **👥 Список жильцов** → Жильцы / View tenants
5. **💳 Проверка платежей** → Проверка чеков / Review payments

### Для арендаторов / For Tenants
1. Введите invite-код от админа / Redeem invite code from admin
2. **📊 Мой статус** → Баланс / View balance
3. **📸 Загрузить чек** → Оплата / Upload payment
4. **💬 Поддержка** → Связь с админом / Contact admin

---

## 🗄️ Миграции БД / Database Migrations

```bash
# Создать миграцию / Create migration
alembic revision --autogenerate -m "description"

# Применить / Apply
alembic upgrade head

# Откат / Rollback
alembic downgrade -1
```

---

## 🏗️ Структура / Project Structure

```
bot/
├── database/          # SQLAlchemy models
├── handlers/          # Telegram handlers (admin, tenant, admin_rso)
├── middlewares/       # Session, error handling
├── services/          # Business logic (billing, RSO, stays)
├── schemas/           # Pydantic validation
├── utils/             # UI helpers
├── config.py
├── cron.py            # Background tasks (billing, notifications)
└── main.py
migrations/            # Alembic
tests/
```

---

## 🔧 Особенности / Key Features

### УК/РСО Интеграция / UK/RSO Integration
- Создание Управляющих Компаний (УК) / Create Management Companies
- Добавление поставщиков (РСО) к УК / Add utility providers (RSO) to UK
- Привязка РСО к объектам / Link RSOs to rental objects
- Лицевые счета для каждого объекта / Account numbers per object

### Автоматизация / Automation
- **Ежедневная задача (9:00)**: Начисление аренды, напоминания / Daily rent charges & reminders
- **20-го числа**: Напоминание о показаниях счётчиков / Meter reading reminder
- Настраиваемые дни напоминаний, налоги / Configurable reminder days, taxes

---

## 🐳 Docker (опционально / Optional)

```bash
docker-compose up -d
docker-compose logs -f bot
```

---

## 🛡️ Безопасность / Security

- `.env` в `.gitignore` (никогда не коммитьте / never commit credentials)
- Роли через `AdminFilter` middleware
- ORM защищает от SQL-инъекций / ORM prevents SQL injection
- Pydantic валидация входных данных / Pydantic input validation

---

## 📝 Лицензия / License

Open-source. Используй и модифицируй свободно. / Open-source. Use and modify freely.

---

## 🤝 Участие / Contributing

1. Fork
2. Branch: `git checkout -b feature/name`
3. Commit: `git commit -m 'Add feature'`
4. Push: `git push origin feature/name`
5. Pull Request

---

**Made with ❤️ using Python & aiogram 3.x**
