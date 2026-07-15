# Dental AI Chatbot - Backup & Restore

## Overview

This guide covers backup and restore procedures for all data components.

## Components to Backup

| Component | Data | Location |
|-----------|------|----------|
| PostgreSQL | Users, documents, chats, metadata | `docker volume: postgres_data` |
| Qdrant | Vector embeddings | `docker volume: qdrant_data` |
| Redis | Cache, sessions, rate limits | `docker volume: redis_data` |
| Uploads | PDF files | `./uploads/` |
| Visuals | Extracted images | `./extracted_visuals/` |
| Config | Environment, nginx | `./.env`, `./nginx/` |

## Automated Backup

### Using SecurityManager

```python
from app.services.security import SecurityManager

sm = SecurityManager()

# Backup database (encrypted)
sm.backup_database()

# List backups
backups = sm.list_backups()

# Restore from backup
sm.restore_database("backups/backup_20240101_120000.sql.enc")
```

### Cron Job (Linux)

```bash
# Add to crontab
crontab -e

# Daily backup at 2 AM
0 2 * * * cd /path/to/Dental_AI_Chatbot && docker-compose exec -T postgres pg_dump -U dental dental_ai | gzip > backups/backup_$(date +\%Y\%m\%d).sql.gz

# Weekly full backup
0 3 * * 0 cd /path/to/Dental_AI_Chatbot && python -c "from app.services.security import SecurityManager; SecurityManager().backup_database()"
```

### Task Scheduler (Windows)

```powershell
# Create backup task
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-Command `"cd C:\Users\HP\OneDrive\Desktop\Dental_AI_chatbot\Dental_AI_Chatbot; docker-compose exec -T postgres pg_dump -U dental dental_ai | Out-File backups\backup_$(Get-Date -Format yyyyMMdd).sql`""
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -TaskName "DentalAI_Backup" -Action $action -Trigger $trigger
```

## Manual Backup

### PostgreSQL

```bash
# Full backup
docker-compose exec postgres pg_dump -U dental dental_ai > backup_$(date +%Y%m%d_%H%M%S).sql

# Compressed
docker-compose exec postgres pg_dump -U dental dental_ai | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Schema only
docker-compose exec postgres pg_dump -U dental dental_ai --schema-only > schema.sql

# Data only
docker-compose exec postgres pg_dump -U dental dental_ai --data-only > data.sql
```

### Qdrant

```bash
# Backup collection
docker-compose exec qdrant curl -X POST http://localhost:6333/collections/dental_chunks/snapshots

# Copy snapshot out
docker cp $(docker-compose ps -q qdrant):/qdrant/storage/snapshots ./qdrant_backup
```

### Redis

```bash
# Generate RDB snapshot
docker-compose exec redis redis-cli BGSAVE

# Copy dump
docker cp $(docker-compose ps -q redis):/data/dump.rdb ./redis_backup
```

### Uploads

```bash
# Copy upload directory
cp -r ./uploads ./backups/uploads_$(date +%Y%m%d)
```

## Restore

### PostgreSQL

```bash
# Stop API first
docker-compose stop api

# Drop and recreate database
docker-compose exec postgres psql -U dental -c "DROP DATABASE dental_ai;"
docker-compose exec postgres psql -U dental -c "CREATE DATABASE dental_ai;"

# Restore
cat backup_20240101.sql | docker-compose exec -T postgres psql -U dental dental_ai

# Start API
docker-compose start api
```

### Qdrant

```bash
# Stop Qdrant
docker-compose stop qdrant

# Copy backup
cp ./qdrant_backup/snapshots/* $(docker-compose ps -q qdrant):/qdrant/storage/snapshots/

# Start Qdrant
docker-compose start qdrant
```

### Redis

```bash
# Stop Redis
docker-compose stop redis

# Copy backup
cp ./redis_backup/dump.rdb $(docker-compose ps -q redis):/data/

# Start Redis
docker-compose start redis
```

## Disaster Recovery

### Complete System Restore

```bash
# 1. Stop all services
docker-compose down

# 2. Remove volumes
docker volume rm dental_ai_chatbot_postgres_data
docker volume rm dental_ai_chatbot_qdrant_data
docker volume rm dental_ai_chatbot_redis_data

# 3. Start database services
docker-compose up -d postgres qdrant redis

# 4. Wait for services
sleep 10

# 5. Restore PostgreSQL
cat backups/full_backup.sql | docker-compose exec -T postgres psql -U dental dental_ai

# 6. Restore Qdrant
docker cp backups/qdrant_snapshots/* $(docker-compose ps -q qdrant):/qdrant/storage/snapshots/

# 7. Restore Redis
docker cp backups/redis_dump.rdb $(docker-compose ps -q redis):/data/

# 8. Start all services
docker-compose up -d

# 9. Re-ingest documents if needed
python -c "
from app.services.ingestion import IngestionService
from app.core.database import SessionLocal
from app.models import Document

with SessionLocal() as db:
    docs = db.query(Document).filter(Document.status == 'ready').all()
    for doc in docs:
        try:
            IngestionService().ingest_document(db, doc)
        except Exception as e:
            print(f'Error re-ingesting {doc.original_filename}: {e}')
"
```

## Cloud Backup

### AWS S3

```python
import boto3

def backup_to_s3(file_path: str, bucket: str, key: str):
    s3 = boto3.client('s3')
    s3.upload_file(file_path, bucket, key)

def restore_from_s3(bucket: str, key: str, file_path: str):
    s3 = boto3.client('s3')
    s3.download_file(bucket, key, file_path)
```

### Google Cloud Storage

```python
from google.cloud import storage

def backup_to_gcs(file_path: str, bucket_name: str, blob_name: str):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(file_path)
```

## Monitoring Backups

### Check Backup Status

```python
import os
from datetime import datetime

def check_backup_freshness(backup_dir: str, max_age_hours: int = 25):
    backups = sorted(os.listdir(backup_dir), reverse=True)
    if not backups:
        return False, "No backups found"
    
    latest = backups[0]
    backup_time = datetime.fromtimestamp(os.path.getmtime(os.path.join(backup_dir, latest)))
    age_hours = (datetime.now() - backup_time).total_seconds() / 3600
    
    if age_hours > max_age_hours:
        return False, f"Latest backup is {age_hours:.1f} hours old"
    
    return True, f"Latest backup is {age_hours:.1f} hours old"
```

### Alerting

```python
# Send alert if backup is stale
is_fresh, message = check_backup_freshness("./backups")
if not is_fresh:
    # Send email/Slack alert
    send_alert(f"Backup warning: {message}")
```

## Security

### Encrypt Backups

```python
from cryptography.fernet import Fernet

def encrypt_file(file_path: str, key: bytes):
    fernet = Fernet(key)
    with open(file_path, 'rb') as f:
        data = f.read()
    encrypted = fernet.encrypt(data)
    with open(file_path + '.enc', 'wb') as f:
        f.write(encrypted)

def decrypt_file(file_path: str, key: bytes):
    fernet = Fernet(key)
    with open(file_path, 'rb') as f:
        encrypted = f.read()
    data = fernet.decrypt(encrypted)
    with open(file_path.replace('.enc', ''), 'wb') as f:
        f.write(data)
```

### Backup Encryption Key

```bash
# Generate key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Add to .env
BACKUP_ENCRYPTION_KEY=your_generated_key_here
```

## Best Practices

1. **Automate**: Set up scheduled backups
2. **Test**: Regularly test restore procedures
3. **Encrypt**: Always encrypt backups in production
4. **Offsite**: Store backups in separate location
5. **Monitor**: Alert on backup failures
6. **Document**: Keep backup procedures documented
7. **Retention**: Define backup retention policy
8. **Verify**: Check backup integrity regularly

## Retention Policy

```python
# Keep backups for 30 days
RETENTION_DAYS = 30

def cleanup_old_backups(backup_dir: str, retention_days: int):
    cutoff = datetime.now() - timedelta(days=retention_days)
    for filename in os.listdir(backup_dir):
        file_path = os.path.join(backup_dir, filename)
        if os.path.getmtime(file_path) < cutoff.timestamp():
            os.remove(file_path)
```
