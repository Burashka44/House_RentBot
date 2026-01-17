# House Rent Bot - API Documentation for Web Integration

## Overview

This document provides complete API specifications and database schema for generating a web interface for the House Rent Management Bot.

---

## Database Schema

### Core Tables

#### 1. users
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    tg_id BIGINT UNIQUE NOT NULL,
    tg_username VARCHAR,
    full_name VARCHAR NOT NULL,
    role VARCHAR NOT NULL,  -- 'owner', 'admin', 'tenant'
    created_by BIGINT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 2. tenants
```sql
CREATE TABLE tenants (
    id SERIAL PRIMARY KEY,
    tg_id BIGINT UNIQUE,  -- NULL until Telegram linked
    tg_username VARCHAR,
    full_name VARCHAR NOT NULL,
    phone VARCHAR,
    email VARCHAR,
    passport_data VARCHAR,
    status VARCHAR DEFAULT 'pending',  -- 'pending', 'active', 'archived'
    consent_given BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 3. houses
```sql
CREATE TABLE houses (
    id SERIAL PRIMARY KEY,
    address VARCHAR NOT NULL,
    owner_id BIGINT NOT NULL,  -- references users.tg_id
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 4. objects (rental units)
```sql
CREATE TABLE objects (
    id SERIAL PRIMARY KEY,
    house_id INTEGER REFERENCES houses(id),
    owner_id BIGINT NOT NULL,
    address VARCHAR NOT NULL,
    unit_number VARCHAR,
    area NUMERIC(10,2),
    rooms INTEGER,
    floor INTEGER,
    status VARCHAR DEFAULT 'available',  -- 'available', 'occupied', 'archived'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 5. tenant_stays
```sql
CREATE TABLE tenant_stays (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id),
    rental_object_id INTEGER REFERENCES objects(id),
    start_date DATE NOT NULL,
    end_date DATE,
    monthly_rent NUMERIC(12,2) NOT NULL,
    deposit NUMERIC(12,2),
    status VARCHAR DEFAULT 'active',  -- 'active', 'ended', 'archived'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Financial Tables

#### 6. rent_charges
```sql
CREATE TABLE rent_charges (
    id SERIAL PRIMARY KEY,
    stay_id INTEGER REFERENCES tenant_stays(id),
    month DATE NOT NULL,  -- First day of month
    amount NUMERIC(12,2) NOT NULL,
    base_amount NUMERIC(12,2),
    tax_amount NUMERIC(12,2) DEFAULT 0,
    tax_rate_snapshot NUMERIC(5,2),
    status VARCHAR DEFAULT 'pending',  -- 'pending', 'paid'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 7. comm_providers (utility providers)
```sql
CREATE TABLE comm_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    service_type VARCHAR NOT NULL,  -- 'electricity', 'water', 'gas', 'heating'
    inn VARCHAR,
    bik VARCHAR,
    bank_account VARCHAR,
    payment_purpose_template TEXT,
    yoomoney_service_id VARCHAR,
    source VARCHAR DEFAULT 'manual',  -- 'manual', 'dadata', 'gis'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 8. comm_charges (utility charges)
```sql
CREATE TABLE comm_charges (
    id SERIAL PRIMARY KEY,
    stay_id INTEGER REFERENCES tenant_stays(id),
    provider_id INTEGER REFERENCES comm_providers(id),
    service_type VARCHAR NOT NULL,
    month DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR DEFAULT 'pending',
    source VARCHAR DEFAULT 'manual',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 9. payments
```sql
CREATE TABLE payments (
    id SERIAL PRIMARY KEY,
    stay_id INTEGER REFERENCES tenant_stays(id),
    type VARCHAR NOT NULL,  -- 'rent', 'comm'
    amount NUMERIC(12,2) NOT NULL,
    total_amount NUMERIC(12,2),
    allocated_amount NUMERIC(12,2) DEFAULT 0,
    unallocated_amount NUMERIC(12,2) DEFAULT 0,
    method VARCHAR DEFAULT 'online',
    status VARCHAR DEFAULT 'pending_manual',
    source VARCHAR DEFAULT 'photo',
    is_manual BOOLEAN DEFAULT FALSE,
    marked_by BIGINT,  -- admin who marked it
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confirmed_at TIMESTAMP WITH TIME ZONE,
    meta_json JSONB
);
```

#### 10. payment_allocations
```sql
CREATE TABLE payment_allocations (
    id SERIAL PRIMARY KEY,
    payment_id INTEGER REFERENCES payments(id) ON DELETE CASCADE,
    charge_id INTEGER NOT NULL,
    charge_type VARCHAR NOT NULL,  -- 'rent' or 'comm'
    amount NUMERIC(12,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 11. payment_receipts
```sql
CREATE TABLE payment_receipts (
    id SERIAL PRIMARY KEY,
    payment_id INTEGER REFERENCES payments(id),
    file_id VARCHAR NOT NULL,
    file_type VARCHAR,
    parsed_amount NUMERIC(12,2),
    parsed_date DATE,
    confidence NUMERIC(3,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Management Tables

#### 12. uk_companies (management companies)
```sql
CREATE TABLE uk_companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    inn VARCHAR UNIQUE,
    address VARCHAR,
    phone VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 13. object_rso_links
```sql
CREATE TABLE object_rso_links (
    id SERIAL PRIMARY KEY,
    object_id INTEGER REFERENCES objects(id),
    provider_id INTEGER REFERENCES comm_providers(id),
    personal_account VARCHAR,
    contract_number VARCHAR,
    service_code VARCHAR,
    payment_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 14. uk_rso_links
```sql
CREATE TABLE uk_rso_links (
    id SERIAL PRIMARY KEY,
    uk_id INTEGER REFERENCES uk_companies(id),
    provider_id INTEGER REFERENCES comm_providers(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Support & Invites

#### 15. invite_codes
```sql
CREATE TABLE invite_codes (
    id SERIAL PRIMARY KEY,
    code VARCHAR UNIQUE NOT NULL,
    tenant_id INTEGER REFERENCES tenants(id),
    object_id INTEGER REFERENCES objects(id),
    role VARCHAR DEFAULT 'tenant',  -- 'tenant' or 'admin'
    created_by BIGINT NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 16. support_messages
```sql
CREATE TABLE support_messages (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id),
    admin_id BIGINT,
    message_text TEXT,
    is_from_tenant BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 17. support_attachments
```sql
CREATE TABLE support_attachments (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES support_messages(id),
    file_id VARCHAR NOT NULL,
    file_type VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Settings

#### 18. tenant_settings
```sql
CREATE TABLE tenant_settings (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) UNIQUE,
    notifications_enabled BOOLEAN DEFAULT TRUE,
    language VARCHAR DEFAULT 'ru',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 19. object_settings
```sql
CREATE TABLE object_settings (
    id SERIAL PRIMARY KEY,
    object_id INTEGER REFERENCES objects(id) UNIQUE,
    auto_charge_enabled BOOLEAN DEFAULT TRUE,
    charge_day INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## REST API Endpoints (Suggested)

### Authentication
```
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

### Tenants
```
GET    /api/tenants              # List all tenants (admin only)
GET    /api/tenants/:id          # Get tenant details
POST   /api/tenants              # Create tenant (admin only)
PUT    /api/tenants/:id          # Update tenant
DELETE /api/tenants/:id          # Archive tenant
GET    /api/tenants/:id/balance  # Get tenant balance
```

### Objects
```
GET    /api/objects              # List objects
GET    /api/objects/:id          # Get object details
POST   /api/objects              # Create object (admin only)
PUT    /api/objects/:id          # Update object
DELETE /api/objects/:id          # Archive object
GET    /api/objects/:id/tenants  # Get current tenants
```

### Stays
```
GET    /api/stays                # List stays
GET    /api/stays/:id            # Get stay details
POST   /api/stays                # Create stay (admin only)
PUT    /api/stays/:id            # Update stay
POST   /api/stays/:id/end        # End stay
```

### Charges
```
GET    /api/charges              # List all charges
GET    /api/charges/rent         # List rent charges
GET    /api/charges/comm         # List utility charges
POST   /api/charges/rent         # Create rent charge
POST   /api/charges/comm         # Create utility charge
PUT    /api/charges/:type/:id    # Update charge
POST   /api/charges/:type/:id/mark-paid  # Mark as paid
```

### Payments
```
GET    /api/payments             # List payments
GET    /api/payments/:id         # Get payment details
POST   /api/payments             # Create payment
POST   /api/payments/:id/allocate  # Allocate payment
GET    /api/payments/:id/receipt # Get receipt
```

### Reports
```
GET    /api/reports/debtors      # List debtors
GET    /api/reports/monthly      # Monthly payments report
GET    /api/reports/balance      # Balance report
GET    /api/reports/analytics    # Analytics data
```

### Admin
```
GET    /api/admin/users          # List admins
POST   /api/admin/users          # Add admin
DELETE /api/admin/users/:id      # Deactivate admin
GET    /api/admin/invites        # List invite codes
POST   /api/admin/invites        # Generate invite
```

### Bot Management
```
GET    /api/bots                 # List all bots
GET    /api/bots/active          # Get active bot
GET    /api/bots/:id             # Get bot details
POST   /api/bots                 # Create new bot
PUT    /api/bots/:id             # Update bot settings
DELETE /api/bots/:id             # Delete bot (soft delete)
POST   /api/bots/:id/activate    # Activate bot
POST   /api/bots/restart         # Restart bot with new token
```

### Analytics & Statistics
```
GET    /api/analytics/overview           # Dashboard overview
GET    /api/analytics/revenue            # Revenue statistics
GET    /api/analytics/occupancy          # Occupancy rates
GET    /api/analytics/payments-timeline  # Payment history timeline
GET    /api/analytics/top-debtors        # Top debtors list
GET    /api/analytics/object-performance # Performance by object
```

### History
```
GET    /api/history/payments      # Payment history
GET    /api/history/charges       # Charge history
GET    /api/history/stays         # Rental history
GET    /api/history/support       # Support ticket history
GET    /api/history/changes       # Audit log (admin changes)
```

---

## Data Models (JSON)

### Bot Settings
```json
{
  "id": 1,
  "bot_name": "MyRentBot",
  "bot_token": "7123456789:AAH***",  // Masked
  "bot_username": "@MyRentBot",
  "webhook_url": "https://example.com/webhook",
  "is_active": true,
  "is_deleted": false,
  "created_at": "2024-01-01T10:00:00Z",
  "created_by": 123456789
}
```

### Analytics Overview
```json
{
  "period": "2024-01",
  "total_revenue": 250000.00,
  "total_payments": 45,
  "total_charges": 50,
  "occupancy_rate": 0.85,
  "active_tenants": 12,
  "pending_debt": 25000.00,
  "objects": {
    "total": 15,
    "occupied": 12,
    "available": 3
  }
}
```

### Payment History
```json
{
  "payments": [
    {
      "id": 456,
      "date": "2024-01-05",
      "tenant": "Иван Иванов",
      "object": "ул. Ленина, 10, кв. 5",
      "amount": 25000.00,
      "type": "rent",
      "method": "online",
      "status": "confirmed"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150
  }
}
```

### Revenue Statistics
```json
{
  "period": "2024",
  "monthly_data": [
    {
      "month": "2024-01",
      "revenue": 250000.00,
      "payments_count": 45,
      "average_payment": 5555.56
    }
  ],
  "total_revenue": 3000000.00,
  "growth_rate": 0.15
}
```

### Tenant
```json
{
  "id": 1,
  "tg_id": 123456789,
  "full_name": "Иван Иванов",
  "phone": "+79001234567",
  "email": "ivan@example.com",
  "status": "active",
  "current_stay": {
    "id": 5,
    "object": {
      "id": 3,
      "address": "ул. Ленина, 10, кв. 5"
    },
    "monthly_rent": 25000.00,
    "start_date": "2024-01-01"
  },
  "balance": -5000.00,
  "created_at": "2024-01-01T10:00:00Z"
}
```

### Object
```json
{
  "id": 3,
  "address": "ул. Ленина, 10, кв. 5",
  "unit_number": "5",
  "area": 45.5,
  "rooms": 2,
  "floor": 3,
  "status": "occupied",
  "current_tenant": {
    "id": 1,
    "full_name": "Иван Иванов"
  },
  "monthly_rent": 25000.00
}
```

### Charge
```json
{
  "id": 123,
  "type": "rent",
  "stay_id": 5,
  "tenant": {
    "id": 1,
    "full_name": "Иван Иванов"
  },
  "month": "2024-01-01",
  "amount": 25000.00,
  "status": "pending",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Payment
```json
{
  "id": 456,
  "stay_id": 5,
  "type": "rent",
  "amount": 25000.00,
  "method": "online",
  "status": "confirmed",
  "is_manual": false,
  "allocations": [
    {
      "charge_id": 123,
      "charge_type": "rent",
      "amount": 25000.00
    }
  ],
  "receipt": {
    "file_id": "AgACAgIAAxkBAAI...",
    "parsed_amount": 25000.00,
    "confidence": 0.95
  },
  "created_at": "2024-01-05T14:30:00Z"
}
```

---

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/rent_bot

# Authentication (for web)
JWT_SECRET=your_jwt_secret_here
SESSION_SECRET=your_session_secret_here

# Telegram Bot (optional for web)
BOT_TOKEN=your_bot_token

# Admin Access
OWNER_IDS=123456789
ADMIN_IDS=123456789,987654321

# API Keys
DADATA_API_KEY=your_dadata_key
YOOMONEY_TOKEN=your_yoomoney_token
```

---

## Integration Guide

### 1. Clone Repository
```bash
git clone https://github.com/Burashka44/House_RentBot.git
cd House_RentBot
```

### 2. Database Setup
```bash
# Use existing PostgreSQL from docker-compose
docker-compose up -d postgres

# Or connect to existing database
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
```

### 3. Run Migrations
```bash
alembic upgrade head
```

### 4. Access Database
```python
from bot.database.core import get_session
from bot.database.models import Tenant, TenantStay, Payment

async with get_session() as session:
    # Query data
    tenants = await session.execute(select(Tenant))
```

---

## Web Framework Suggestions

### Option 1: FastAPI (Recommended)
```python
from fastapi import FastAPI
from bot.database.core import get_session
from bot.database.models import Tenant

app = FastAPI()

@app.get("/api/tenants")
async def list_tenants():
    async with get_session() as session:
        result = await session.execute(select(Tenant))
        return result.scalars().all()
```

### Option 2: Flask
```python
from flask import Flask, jsonify
from bot.database.core import get_session

app = Flask(__name__)

@app.route('/api/tenants')
def list_tenants():
    # Use asyncio.run() for async queries
    pass
```

### Option 3: Next.js + API Routes
```typescript
// pages/api/tenants.ts
export default async function handler(req, res) {
  // Connect to PostgreSQL
  // Query tenants table
  res.json(tenants)
}
```

---

## Security Considerations

1. **Authentication**: Implement JWT or session-based auth
2. **Authorization**: Check user roles (owner/admin/tenant)
3. **CORS**: Configure allowed origins
4. **Rate Limiting**: Prevent API abuse
5. **Input Validation**: Validate all inputs
6. **SQL Injection**: Use ORM (SQLAlchemy) or parameterized queries

---

## Next Steps for AI Generation

1. **Provide this file** to AI service (Claude, ChatGPT, etc.)
2. **Specify framework**: "Generate FastAPI backend" or "Generate Next.js app"
3. **Request features**: "Add authentication", "Create admin dashboard"
4. **Iterate**: Review generated code and request modifications

---

## Example Prompts for AI

### For Backend:
```
Using the database schema from API_DOCUMENTATION.md, 
generate a FastAPI backend with:
- JWT authentication
- CRUD endpoints for tenants, objects, payments
- Role-based access control (owner/admin/tenant)
- PostgreSQL connection using SQLAlchemy
```

### For Frontend:
```
Using the API endpoints from API_DOCUMENTATION.md,
generate a Next.js admin dashboard with:
- Login page
- Tenant management (list, create, edit)
- Payment tracking
- Financial reports
- Responsive design with Tailwind CSS
```

---

## Support

For questions or issues:
- GitHub: https://github.com/Burashka44/House_RentBot
- Database models: `bot/database/models.py`
- Services: `bot/services/`
- Existing bot handlers: `bot/handlers/`
