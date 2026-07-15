# Dental AI Chatbot - Deployment Guide

## Prerequisites

### Office PC (GPU Server)
- **OS**: Windows 10/11 or Ubuntu 22.04
- **GPU**: NVIDIA RTX 5060Ti (16GB VRAM)
- **RAM**: 32GB+ recommended
- **Storage**: 100GB+ free space
- **Software**: Docker Desktop, NVIDIA Container Toolkit

### Network
- Static IP or Dynamic DNS (e.g., DuckDNS)
- Port forwarding: 80, 443
- Cloudflare account (for SSL)

## Step 1: Install Docker Desktop

1. Download Docker Desktop for Windows
2. Enable WSL 2 backend
3. Install NVIDIA Container Toolkit:
   ```bash
   # Run in PowerShell as Administrator
   wsl --install
   # Restart computer
   # Then in WSL:
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

## Step 2: Clone Repository

```bash
git clone https://github.com/Hamadullah09/Dental_AI_Chatbot.git
cd Dental_AI_Chatbot
```

## Step 3: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env
```

### Critical Environment Variables

```bash
# Database
DATABASE_URL=postgresql+psycopg://dental:YOUR_PASSWORD@postgres:5432/dental_ai
POSTGRES_PASSWORD=YOUR_STRONG_PASSWORD

# JWT
JWT_SECRET_KEY=YOUR_32_CHAR_SECRET

# Admin
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=YOUR_ADMIN_PASSWORD

# CORS (add your domains)
CORS_ORIGINS=https://yourdomain.com,http://localhost:3000

# Ollama (office PC IP)
OLLAMA_BASE_URL=http://HOST_IP:11434
```

## Step 4: Start Services

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

## Step 5: Pull Ollama Models

```bash
# On the office PC with GPU
docker exec -it ollama ollama pull qwen2.5-vl:7b
docker exec -it ollama ollama pull qwen3:14b
```

## Step 6: Configure Cloudflare

1. Add domain to Cloudflare
2. Enable SSL (Full mode)
3. Create DNS A record pointing to your public IP
4. Enable Page Rules for caching

## Step 7: Port Forwarding

On your router:
1. Forward port 80 → office PC IP:80
2. Forward port 443 → office PC IP:443

## Step 8: Verify Deployment

```bash
# Check health endpoint
curl https://yourdomain.com/api/health

# Should return:
# {"status": "healthy", "database": "connected", "qdrant": "connected"}
```

## Troubleshooting

### Docker Won't Start
```bash
# Check Docker service
Get-Service docker

# Restart Docker
Restart-Service docker
```

### GPU Not Detected
```bash
# Verify NVIDIA driver
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### API Not Responding
```bash
# Check API logs
docker-compose logs api

# Common issues:
# - Database connection failed
# - Qdrant not ready
# - Redis connection refused
```

### Frontend Can't Connect
```bash
# Check CORS settings in .env
# Ensure your domain is in CORS_ORIGINS

# Check Nginx config
docker-compose logs nginx
```

## Backup & Restore

### Backup
```bash
# Database backup
docker-compose exec postgres pg_dump -U dental dental_ai > backup_$(date +%Y%m%d).sql

# Full backup script
python -c "
from app.services.security import SecurityManager
sm = SecurityManager()
sm.backup_database()
"
```

### Restore
```bash
# Database restore
cat backup_20240101.sql | docker-compose exec -T postgres psql -U dental dental_ai
```

## Performance Tuning

### GPU Memory
```bash
# Monitor GPU usage
nvidia-smi

# Adjust Ollama model layers
# In .env:
OLLAMA_NUM_GPU_LAYERS=35  # For RTX 5060Ti
```

### Database
```bash
# Optimize PostgreSQL
# In docker-compose.yml, add to postgres command:
command: >
  --shared_buffers=4GB
  --effective_cache_size=12GB
  --work_mem=16MB
  --maintenance_work_mem=1GB
```

### Redis
```bash
# Monitor Redis
docker-compose exec redis redis-cli info memory
```

## Scaling

For multiple users:
1. Increase `DB_POOL_SIZE` in .env
2. Add Redis cluster
3. Use multiple Ollama instances behind load balancer
4. Consider Kubernetes for high availability
