# Monitoring & Error Tracking Setup

## 🔍 Sentry Integration

### 1. Install Sentry SDK
```bash
pip install sentry-sdk
```

### 2. Add to requirements.txt
```
sentry-sdk>=1.40.0
```

### 3. Configure in .env
```bash
# Monitoring (optional)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
SENTRY_ENVIRONMENT=production  # or development, staging
```

### 4. Initialize in bot/main.py
```python
import sentry_sdk
from bot.config import config

# Initialize Sentry (if configured)
if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.SENTRY_ENVIRONMENT,
        traces_sample_rate=0.1,  # 10% of transactions
        profiles_sample_rate=0.1,
        
        # Set release version
        release=f"house-rentbot@{config.VERSION}",
        
        # Filter sensitive data
        before_send=filter_sensitive_data,
    )
    logging.info(f"Sentry initialized: {config.SENTRY_ENVIRONMENT}")
```

---

## 📊 What You Get

### Error Tracking
- ✅ Automatic error capture
- ✅ Stack traces
- ✅ User context (tg_id, username)
- ✅ Breadcrumbs (what user did before error)

### Performance Monitoring
- ✅ Slow database queries
- ✅ API call latency
- ✅ OCR processing time

### Alerts
- ✅ Email notifications
- ✅ Telegram alerts
- ✅ Slack integration

---

## 🔒 Privacy & Security

### Filter Sensitive Data
```python
def filter_sensitive_data(event, hint):
    """Remove sensitive data before sending to Sentry."""
    
    # Remove passwords, tokens, API keys
    if 'request' in event:
        if 'data' in event['request']:
            data = event['request']['data']
            if isinstance(data, dict):
                for key in ['password', 'token', 'api_key', 'secret']:
                    if key in data:
                        data[key] = '[FILTERED]'
    
    # Remove personal data from breadcrumbs
    if 'breadcrumbs' in event:
        for crumb in event['breadcrumbs']:
            if 'message' in crumb:
                # Filter phone numbers, emails
                crumb['message'] = filter_personal_data(crumb['message'])
    
    return event
```

### User Context
```python
# Add user context to errors
sentry_sdk.set_user({
    "id": str(user.tg_id),
    "username": user.tg_username,
    "role": user.role
})

# Add custom tags
sentry_sdk.set_tag("tenant_id", tenant.id)
sentry_sdk.set_tag("stay_id", stay.id)
```

---

## 📈 Usage Examples

### Manual Error Capture
```python
try:
    result = await risky_operation()
except Exception as e:
    sentry_sdk.capture_exception(e)
    logging.error(f"Operation failed: {e}")
```

### Custom Events
```python
# Track important business events
sentry_sdk.capture_message(
    "Large payment received",
    level="info",
    extras={
        "amount": payment.amount,
        "tenant_id": payment.tenant_id
    }
)
```

### Performance Tracking
```python
with sentry_sdk.start_transaction(op="ocr", name="parse_receipt"):
    with sentry_sdk.start_span(op="ai", description="Ollama OCR"):
        result = await ollama_ocr(image)
    
    with sentry_sdk.start_span(op="db", description="Save payment"):
        await save_payment(result)
```

---

## 🎯 Alternative: Self-Hosted Monitoring

### Option 1: Prometheus + Grafana
```python
# bot/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Metrics
payments_total = Counter('payments_total', 'Total payments')
payment_amount = Histogram('payment_amount', 'Payment amounts')
active_stays = Gauge('active_stays', 'Number of active stays')

# Usage
payments_total.inc()
payment_amount.observe(payment.amount)
active_stays.set(len(active_stays_list))
```

### Option 2: Custom Logging
```python
# Structured logging to file
import json

def log_event(event_type, data):
    event = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "data": data
    }
    with open("events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")

# Usage
log_event("payment_received", {
    "amount": 10000,
    "tenant_id": 5,
    "method": "receipt_upload"
})
```

---

## ✅ Quick Setup (5 minutes)

### 1. Create Sentry Account
- Go to https://sentry.io
- Create free account (50k events/month)
- Create new project (Python)
- Copy DSN

### 2. Add to .env
```bash
SENTRY_DSN=https://xxx@sentry.io/xxx
SENTRY_ENVIRONMENT=production
```

### 3. Add to config.py
```python
SENTRY_DSN = os.getenv("SENTRY_DSN", None)
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "development")
VERSION = "1.0.0"
```

### 4. Initialize in main.py
```python
if config.SENTRY_DSN:
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.SENTRY_ENVIRONMENT,
        traces_sample_rate=0.1
    )
```

### 5. Test
```python
# Trigger test error
sentry_sdk.capture_message("Test from House RentBot!")
```

---

## 📊 Monitoring Checklist

- [ ] Sentry configured
- [ ] Error alerts enabled
- [ ] Performance tracking enabled
- [ ] User context added
- [ ] Sensitive data filtered
- [ ] Test error sent
- [ ] Alerts received

---

## 🎯 Benefits

**Without Monitoring:**
- ❌ Learn about errors from users
- ❌ No visibility into production
- ❌ Hard to debug issues
- ❌ Don't know error frequency

**With Monitoring:**
- ✅ Instant error notifications
- ✅ Full stack traces
- ✅ User context
- ✅ Error trends and patterns
- ✅ Performance insights

---

## 💡 Recommendation

**For MVP/Small Scale:**
- Use Sentry free tier (50k events/month)
- Enable error tracking only
- Add user context

**For Production/Scale:**
- Upgrade Sentry plan
- Enable performance monitoring
- Add custom metrics
- Set up alerts

**Self-Hosted Alternative:**
- GlitchTip (Sentry-compatible, open source)
- Prometheus + Grafana
- ELK Stack (Elasticsearch, Logstash, Kibana)
