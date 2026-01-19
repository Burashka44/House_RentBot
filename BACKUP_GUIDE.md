# Database Backup & Restore Guide

## 📦 Automated Backups

### Configuration
Backup service runs daily at 3 AM and keeps last 7 days of backups.

**Location:** `./backups/` directory

**Format:** `backup_YYYYMMDD_HHMMSS.dump` (PostgreSQL custom format)

**Retention:** 7 days (older backups auto-deleted)

---

## 🔄 Manual Backup

### Create Backup Now
```bash
# From host machine
docker exec rentbot_postgres pg_dump -U postgres -Fc rent_bot > backups/manual_backup_$(date +%Y%m%d_%H%M%S).dump

# Or enter backup container
docker exec -it rentbot_backup sh
pg_dump -Fc -f /backups/manual_backup_$(date +%Y%m%d_%H%M%S).dump
```

---

## 📥 Restore from Backup

### 1. Stop the bot
```bash
docker-compose stop bot
```

### 2. Restore database
```bash
# List available backups
ls -lh backups/

# Restore from specific backup
docker exec -i rentbot_postgres pg_restore \
  -U postgres \
  -d rent_bot \
  --clean \
  --if-exists \
  < backups/backup_20260119_030000.dump
```

### 3. Restart bot
```bash
docker-compose start bot
```

---

## ⚠️ Important Notes

### Backup File Format
- **Custom format** (`-Fc`): Compressed, allows selective restore
- **Plain SQL** (`-Fp`): Human-readable, larger size
- **Directory** (`-Fd`): Parallel dump, fastest

### Restore Options
```bash
# Clean restore (drop existing objects)
pg_restore --clean --if-exists

# Data only (no schema)
pg_restore --data-only

# Schema only (no data)
pg_restore --schema-only

# Specific tables
pg_restore -t payments -t tenants
```

---

## 🔒 Security

### Backup Encryption (Optional)
```bash
# Encrypt backup
gpg --symmetric --cipher-algo AES256 backups/backup.dump

# Decrypt
gpg --decrypt backups/backup.dump.gpg > backup.dump
```

### Off-site Backup
```bash
# Upload to S3 (example)
aws s3 cp backups/backup_$(date +%Y%m%d).dump \
  s3://my-bucket/rentbot-backups/

# Or rsync to remote server
rsync -avz backups/ user@remote:/backups/rentbot/
```

---

## 📊 Monitoring

### Check Backup Status
```bash
# View backup logs
docker logs rentbot_backup

# List backups
ls -lh backups/

# Check backup size
du -sh backups/
```

### Verify Backup Integrity
```bash
# Test restore to temp database
docker exec rentbot_postgres createdb -U postgres test_restore
docker exec -i rentbot_postgres pg_restore \
  -U postgres -d test_restore \
  < backups/latest_backup.dump
docker exec rentbot_postgres dropdb -U postgres test_restore
```

---

## 🚨 Disaster Recovery

### Full Recovery Steps

1. **Stop all services**
   ```bash
   docker-compose down
   ```

2. **Remove old data**
   ```bash
   docker volume rm rentbot_postgres_data
   ```

3. **Start database only**
   ```bash
   docker-compose up -d postgres
   ```

4. **Wait for postgres to be ready**
   ```bash
   docker exec rentbot_postgres pg_isready -U postgres
   ```

5. **Restore from backup**
   ```bash
   docker exec -i rentbot_postgres pg_restore \
     -U postgres -d rent_bot --clean --if-exists \
     < backups/backup_YYYYMMDD_HHMMSS.dump
   ```

6. **Start all services**
   ```bash
   docker-compose up -d
   ```

---

## 📅 Backup Schedule

**Daily:** 3:00 AM (automated)  
**Retention:** 7 days  
**Manual:** As needed before major changes

### Recommended Additional Backups
- Before migrations: `alembic upgrade head`
- Before major updates
- Before data imports
- Weekly off-site backup

---

## 💾 Backup Size Estimates

| Records | Database Size | Backup Size (compressed) |
|---------|---------------|--------------------------|
| 100     | ~5 MB         | ~1 MB                    |
| 1,000   | ~50 MB        | ~10 MB                   |
| 10,000  | ~500 MB       | ~100 MB                  |
| 100,000 | ~5 GB         | ~1 GB                    |

**Note:** Actual sizes depend on data complexity and compression.

---

## ✅ Best Practices

1. **Test restores regularly** (monthly)
2. **Keep off-site backups** (S3, remote server)
3. **Monitor backup logs** for failures
4. **Verify backup integrity** before deleting old backups
5. **Document restore procedures**
6. **Encrypt sensitive backups**
7. **Set up alerts** for backup failures

---

## 🔧 Troubleshooting

### Backup fails
```bash
# Check logs
docker logs rentbot_backup

# Check disk space
df -h

# Check permissions
ls -la backups/
```

### Restore fails
```bash
# Check backup file
pg_restore --list backups/backup.dump

# Restore with verbose output
pg_restore -v --clean --if-exists ...
```

### Out of disk space
```bash
# Clean old backups manually
find backups/ -name "*.dump" -mtime +3 -delete

# Compress old backups
gzip backups/*.dump
```
