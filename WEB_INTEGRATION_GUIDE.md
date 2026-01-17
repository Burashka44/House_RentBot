# Web Integration Guide

Complete guide for integrating a web interface with the House Rent Bot database.

---

## Quick Start

The Telegram bot and web interface share the **same PostgreSQL database**. All data is accessible through both interfaces.

**Architecture:**
```
PostgreSQL Database (Single Source of Truth)
    ↑                    ↑
Telegram Bot          Web API
```

---

## 1. Authentication (JWT)

### Setup

```python
# web/auth.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import os

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    from bot.database.core import get_session
    from bot.database.models import User
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise credentials_exception
        return user
```

### Login Endpoint

```python
# web/main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

app = FastAPI()

class Token(BaseModel):
    access_token: str
    token_type: str

@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Authenticate against database
    from bot.database.core import get_session
    from bot.database.models import User
    from sqlalchemy import select
    
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.tg_username == form_data.username)
        )
        user = result.scalar_one_or_none()
        
        if not user or not verify_password(form_data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        access_token = create_access_token(
            data={"sub": user.tg_id},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me")
async def get_me(current_user = Depends(get_current_user)):
    return {
        "id": current_user.tg_id,
        "username": current_user.tg_username,
        "full_name": current_user.full_name,
        "role": current_user.role
    }
```

### Protected Endpoints

```python
@app.get("/api/tenants")
async def list_tenants(current_user = Depends(get_current_user)):
    # Check role
    if current_user.role not in ['owner', 'admin']:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Use existing service
    from bot.database.core import get_session
    from bot.services.tenant_service import get_all_tenants
    
    async with get_session() as session:
        tenants = await get_all_tenants(session)
        return tenants
```

---

## 2. CORS Configuration

### For Development

```python
# web/main.py
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS - Allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://localhost:5173",  # Vite dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### For Production

```python
import os

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://yourdomain.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

---

## 3. Database Connection

### Reuse Existing Connection

```python
# web/database.py
from bot.database.core import get_session, engine

# Use the same session factory
async def get_db():
    async with get_session() as session:
        yield session

# Example usage
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/api/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    from bot.database.models import Tenant
    from sqlalchemy import select
    
    result = await db.execute(select(Tenant))
    return result.scalars().all()
```

---

## 4. Validation Schemas

### Pydantic Models

```python
# web/schemas.py
from pydantic import BaseModel, EmailStr
from datetime import date
from typing import Optional

class TenantCreate(BaseModel):
    full_name: str
    phone: str
    email: Optional[EmailStr] = None
    passport_data: Optional[str] = None

class TenantResponse(BaseModel):
    id: int
    full_name: str
    phone: str
    email: Optional[str]
    status: str
    
    class Config:
        from_attributes = True

class PaymentCreate(BaseModel):
    stay_id: int
    amount: float
    type: str  # 'rent' or 'comm'
    method: str = 'online'
```

### Usage

```python
@app.post("/api/tenants", response_model=TenantResponse)
async def create_tenant(
    tenant_data: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from bot.database.models import Tenant
    
    tenant = Tenant(**tenant_data.dict())
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant
```

---

## 5. Pagination

```python
from typing import List

class PaginatedResponse(BaseModel):
    items: List[TenantResponse]
    total: int
    page: int
    per_page: int
    pages: int

@app.get("/api/tenants", response_model=PaginatedResponse)
async def list_tenants(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db)
):
    from bot.database.models import Tenant
    from sqlalchemy import select, func
    
    # Count total
    count_result = await db.execute(select(func.count(Tenant.id)))
    total = count_result.scalar()
    
    # Get page
    offset = (page - 1) * per_page
    result = await db.execute(
        select(Tenant).offset(offset).limit(per_page)
    )
    tenants = result.scalars().all()
    
    return {
        "items": tenants,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page
    }
```

---

## 6. Error Handling

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )
```

---

## 7. Environment Variables

### .env for Web

```bash
# Database (same as bot)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/rent_bot

# JWT Authentication
JWT_SECRET=your-super-secret-jwt-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# CORS
FRONTEND_URL=http://localhost:3000

# File Upload
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE=20971520  # 20MB

# Admin Access (same as bot)
OWNER_IDS=123456789
ADMIN_IDS=123456789,987654321
```

---

## 8. Deployment

### Option 1: Docker Compose (Recommended)

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASS}
      POSTGRES_DB: ${DB_NAME}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app_network

  telegram-bot:
    build: .
    depends_on:
      - postgres
    env_file: .env
    networks:
      - app_network

  web-api:
    build:
      context: .
      dockerfile: Dockerfile.web
    ports:
      - "8000:8000"
    depends_on:
      - postgres
    env_file: .env
    networks:
      - app_network

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://web-api:8000
    depends_on:
      - web-api
    networks:
      - app_network

volumes:
  postgres_data:

networks:
  app_network:
```

### Dockerfile.web

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Option 2: Separate Deployment

**Telegram Bot:**
```bash
# Deploy bot to server
docker-compose up -d telegram-bot
```

**Web API:**
```bash
# Deploy API separately
uvicorn web.main:app --host 0.0.0.0 --port 8000
```

---

## 9. Production Checklist

### Security
- [ ] Change `JWT_SECRET` to strong random value
- [ ] Use HTTPS only (SSL certificate)
- [ ] Set strong database passwords
- [ ] Enable rate limiting
- [ ] Configure firewall rules

### Performance
- [ ] Add Redis for caching
- [ ] Configure connection pooling
- [ ] Enable gzip compression
- [ ] Set up CDN for static files

### Monitoring
- [ ] Add health check endpoint
- [ ] Configure logging
- [ ] Set up error tracking (Sentry)
- [ ] Monitor database performance

### Backup
- [ ] Automated database backups
- [ ] Backup retention policy
- [ ] Test restore procedures

---

## 10. Example: Complete FastAPI App

```python
# web/main.py
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.core import get_session
from bot.database.models import Tenant, Payment, RentCharge
from web.auth import get_current_user
from web.schemas import TenantResponse, PaymentResponse

app = FastAPI(title="House Rent Bot API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Tenants
@app.get("/api/tenants", response_model=list[TenantResponse])
async def list_tenants(current_user = Depends(get_current_user)):
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Tenant))
        return result.scalars().all()

# Payments
@app.get("/api/payments")
async def list_payments(current_user = Depends(get_current_user)):
    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Payment))
        return result.scalars().all()

# Analytics
@app.get("/api/analytics/overview")
async def analytics_overview(current_user = Depends(get_current_user)):
    async with get_session() as session:
        from sqlalchemy import select, func
        
        # Total revenue
        revenue_result = await session.execute(
            select(func.sum(Payment.amount)).where(Payment.status == 'confirmed')
        )
        total_revenue = revenue_result.scalar() or 0
        
        # Pending charges
        charges_result = await session.execute(
            select(func.sum(RentCharge.amount)).where(RentCharge.status == 'pending')
        )
        pending_debt = charges_result.scalar() or 0
        
        return {
            "total_revenue": float(total_revenue),
            "pending_debt": float(pending_debt)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 11. Frontend Integration

### Next.js Example

```typescript
// lib/api.ts
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function login(username: string, password: string) {
  const formData = new FormData();
  formData.append('username', username);
  formData.append('password', password);
  
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    body: formData,
  });
  
  if (!response.ok) throw new Error('Login failed');
  return response.json();
}

export async function getTenants(token: string) {
  const response = await fetch(`${API_URL}/api/tenants`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });
  
  if (!response.ok) throw new Error('Failed to fetch tenants');
  return response.json();
}
```

---

## Resources

- **API Documentation:** `API_DOCUMENTATION.md`
- **Database Schema:** `DATABASE_SCHEMA.md`
- **Architecture:** `ARCHITECTURE.md`
- **Bot Services:** `bot/services/` (reusable!)
- **Database Models:** `bot/database/models.py`

---

## Support

For questions:
- GitHub: https://github.com/Burashka44/House_RentBot
- Check existing bot implementation in `bot/` directory
