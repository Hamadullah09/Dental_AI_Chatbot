# Dental AI Chatbot - Production Deployment Guide

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [System Requirements](#2-system-requirements)
3. [Install Docker Desktop](#3-install-docker-desktop)
4. [Install NVIDIA Container Toolkit](#4-install-nvidia-container-toolkit)
5. [Install Ollama](#5-install-ollama)
6. [Pull AI Models](#6-pull-ai-models)
7. [Clone Repository](#7-clone-repository)
8. [Configure Environment](#8-configure-environment)
9. [Start All Services](#9-start-all-services)
10. [Verify Installation](#10-verify-installation)
11. [Access Services](#11-access-services)
12. [Upload Dental Documents](#12-upload-dental-documents)
13. [Configure Cloudflare Tunnel](#13-configure-cloudflare-tunnel)
14. [GPU Optimization](#14-gpu-optimization)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Prerequisites

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | RTX 3060 (12GB VRAM) | **RTX 5060Ti (16GB VRAM)** |
| RAM | 16GB | 32GB+ |
| Storage | 100GB free SSD | 500GB+ NVMe SSD |
| CPU | 4 cores | 8+ cores |
| Network | 10 Mbps | 100 Mbps+ |

### Software Requirements

- Windows 10/11 (64-bit)
- Docker Desktop 4.x
- NVIDIA GPU Drivers (latest)
- Git
- PowerShell 5.1+

---

## 2. System Requirements

### Check Your GPU

Open PowerShell and run:

```powershell
nvidia-smi
```

Expected output should show:
- GPU Name: NVIDIA GeForce RTX 5060Ti
- VRAM: 16384 MiB
- CUDA Version: 12.x

### Check Docker

```powershell
docker --version
# Expected: Docker version 24.x or higher

docker-compose --version
# Expected: Docker Compose version 2.x or higher
```

---

## 3. Install Docker Desktop

### Step 1: Download Docker Desktop

1. Go to https://www.docker.com/products/docker-desktop/
2. Click **"Download for Windows"**
3. Run the installer `Docker Desktop Installer.exe`

### Step 2: Install Docker Desktop

1. Check **"Use WSL 2 instead of Hyper-V"** (recommended)
2. Click **"OK"** and wait for installation
3. Restart your computer when prompted

### Step 3: Configure Docker Desktop

1. Open Docker Desktop
2. Go to **Settings** (gear icon)
3. Go to **Resources** -> **WSL Integration
4. Enable **"Enable integration with my default WSL distro"**
5. Click **"Apply & Restart"**

### Step 4: Verify Docker

Open PowerShell:

```powershell
docker run hello-world
```

Should output: "Hello from Docker!"

---

## 4. Install NVIDIA Container Toolkit

### Step 1: Install NVIDIA GPU Drivers

1. Go to https://www.nvidia.com/Download/index.aspx
2. Select:
   - Product Type: GeForce
   - Product Series: GeForce RTX 50 Series
   - Product: GeForce RTX 5060Ti
   - Operating System: Windows 11 64-bit
3. Download and install the driver
4. Restart your computer

### Step 2: Install NVIDIA Container Toolkit

Open PowerShell as Administrator:

```powershell
# Add NVIDIA package repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

# Or on Windows, download from:
# https://github.com/NVIDIA/nvidia-docker/releases

# Install using winget
winget install NVIDIA.NVIDIAContainerToolkit
```

### Step 3: Configure Docker for GPU

Create or edit `%USERPROFILE%\.docker\daemon.json`:

```json
{
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  },
  "default-runtime": "nvidia"
}
```

### Step 4: Restart Docker

```powershell
# Restart Docker Desktop
# Or run:
docker restart
```

### Step 5: Verify GPU Access

```powershell
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

Should show your RTX 5060Ti GPU info.

---

## 5. Install Ollama

### Step 1: Download Ollama

1. Go to https://ollama.com/download
2. Click **"Download for Windows"**
3. Run the installer

### Step 2: Verify Ollama

```powershell
ollama --version
# Expected: ollama version 0.3.x or higher
```

### Step 3: Start Ollama Service

```powershell
# Start Ollama service
ollama serve

# Or run in background
Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
```

### Step 4: Configure Ollama for GPU

Set environment variable for GPU offloading:

```powershell
# Set GPU layers (for 16GB VRAM, use 35 layers)
$env:OLLAMA_NUM_GPU_LAYERS=35

# Or make it permanent:
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_GPU_LAYERS", "35", "User")
```

---

## 6. Pull AI Models

Open PowerShell and run:

```powershell
# Pull the text model (Qwen3:14b) - ~9GB download
ollama pull qwen3:14b

# Pull the vision model (Qwen2.5-VL:7b) - ~4GB download
ollama pull qwen2.5vl:7b

# Verify models are installed
ollama list
```

Expected output:
```
NAME              SIZE      MODIFIED
qwen3:14b         9.0 GB    5 minutes ago
qwen2.5vl:7b      4.4 GB    2 minutes ago
```

### Test Models

```powershell
# Test text model
ollama run qwen3:14b "What is dental caries?"

# Test vision model (basic test)
ollama run qwen2.5vl:7b "Describe what you see" --image test.jpg
```

---

## 7. Clone Repository

```powershell
# Navigate to your project directory
cd C:\Users\HP\OneDrive\Desktop

# Clone the repository
git clone https://github.com/Hamadullah09/Dental_AI_Chatbot.git

# Enter the directory
cd Dental_AI_Chatbot\Dental_AI_Chatbot
```

---

## 8. Configure Environment

### Step 1: Copy Environment File

```powershell
Copy-Item .env.example .env
```

### Step 2: Edit Environment File

Open `.env` in your editor (VS Code recommended):

```powershell
code .env
```

### Step 3: Configure Critical Values

**Generate a secure JWT secret:**

```powershell
# Generate a random secret
python -c "import secrets; print(secrets.token_urlsafe(64))"
# Copy the output
```

**Update these values in `.env`:**

```env
# === SECURITY (CRITICAL) ===
JWT_SECRET_KEY=paste-your-generated-secret-here
ADMIN_EMAIL=admin@yourclinic.com
ADMIN_PASSWORD=your-strong-password-here
POSTGRES_PASSWORD=your-strong-postgres-password

# === DATABASE ===
DATABASE_URL=postgresql+psycopg://dental:your-strong-postgres-password@postgres:5432/dental_ai

# === REDIS ===
REDIS_URL=redis://redis:6379/0

# === QDRANT ===
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=dental_docs_clean

# === OLLAMA (GPU Server) ===
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:14b
OLLAMA_VISION_MODEL=qwen2.5vl:7b
LLM_PROVIDER=ollama

# === EMBEDDING ===
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2

# === RAG SETTINGS ===
RAG_MODE=simple
RETRIEVAL_TOP_K=5
ENABLE_KEYWORD_SEARCH=true
ENABLE_MEMORY=true
ENABLE_QUERY_REWRITING=true
ENABLE_ADJACENT_CHUNK_EXPANSION=true
ENABLE_MULTIMODAL_RAG=true

# === RATE LIMITING ===
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_CHAT_PER_MINUTE=20
RATE_LIMIT_AUTH_PER_MINUTE=10

# === STREAMING ===
STREAMING_ENABLED=true

# === LOGGING ===
LOG_LEVEL=INFO
LOG_FORMAT=json

# === MONITORING ===
PROMETHEUS_ENABLED=true
GRAFANA_PASSWORD=admin
```

### Step 4: Save and Close

Save the `.env` file.

---

## 9. Start All Services

### Step 1: Start Docker Desktop

Make sure Docker Desktop is running (check system tray).

### Step 2: Start All Services

```powershell
# Navigate to project directory
cd C:\Users\HP\OneDrive\Desktop\Dental_AI_chatbot\Dental_AI_Chatbot

# Start all services
docker-compose up -d
```

This will start 8 services:
- **api** - FastAPI backend (port 8000)
- **frontend** - Next.js frontend (port 3000)
- **postgres** - PostgreSQL database (port 5432)
- **qdrant** - Vector database (port 6333)
- **redis** - Cache and session store (port 6379)
- **nginx** - Reverse proxy (port 80)
- **prometheus** - Metrics collection (port 9090)
- **grafana** - Monitoring dashboards (port 3001)

### Step 3: Wait for Services

```powershell
# Watch service status
docker-compose ps

# Watch logs
docker-compose logs -f

# Watch specific service
docker-compose logs -f api
```

### Step 4: Verify All Services Are Healthy

```powershell
# Check all services
docker-compose ps

# Expected output should show "healthy" for all services
```

---

## 10. Verify Installation

### Step 1: Check Health Endpoint

Open browser or use curl:

```
http://localhost:8000/api/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "Dental AI Chatbot",
  "environment": "development",
  "checks": {
    "database": {"status": "ok"},
    "qdrant": {"status": "ok"},
    "ollama": {"status": "ok"},
    "redis": {"status": "ok"}
  }
}
```

### Step 2: Check Frontend

Open browser:
```
http://localhost:3000
```

Should show the login page.

### Step 3: Check API Docs

Open browser:
```
http://localhost:8000/docs
```

Should show Swagger UI.

### Step 4: Check Grafana

Open browser:
```
http://localhost:3001
```

Login:
- Username: `admin`
- Password: `admin` (or your GRAFANA_PASSWORD)

---

## 11. Access Services

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | Chat UI |
| API | http://localhost:8000 | Backend API |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Grafana | http://localhost:3001 | Monitoring |
| Prometheus | http://localhost:9090 | Metrics |
| Qdrant | http://localhost:6333 | Vector DB UI |

### Create Admin Account

The admin account is auto-created from your `.env` settings.

### Create User Accounts

1. Open http://localhost:3000/register
2. Register as Patient or Student
3. Login with your credentials

---

## 12. Upload Dental Documents

### Step 1: Login as Admin

1. Go to http://localhost:3000/login
2. Login with admin credentials from `.env`

### Step 2: Navigate to Admin Panel

1. Click the sidebar menu
2. Click **"Admin workspace"**

### Step 3: Upload PDFs

1. Click **"Upload Document"**
2. Select PDF files (textbooks, guidelines, research articles)
3. Fill in metadata:
   - Title
   - Author
   - Year
   - Document Type (textbook, guideline, research_article)
   - Trust Level (high, medium, low)
   - Dental Specialty
4. Click **"Upload"**

### Step 4: Wait for Ingestion

- Watch the progress bar
- Ingestion includes: OCR, chunking, embedding, vector indexing
- Time varies by document size (5-30 minutes for large PDFs)

### Step 5: Start Chatting

1. Go to http://localhost:3000/chat
2. Ask dental questions
3. Get AI-powered answers with citations

---

## 13. Configure Cloudflare Tunnel

### Step 1: Install Cloudflare Tunnel

```powershell
# Download cloudflared
Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile "tools\cloudflared.exe"
```

### Step 2: Login to Cloudflare

```powershell
tools\cloudflared.exe tunnel login
```

This opens a browser. Select your domain.

### Step 3: Create Tunnel

```powershell
tools\cloudflared.exe tunnel create dental-ai-chatbot
```

Copy the tunnel ID from output.

### Step 4: Configure Tunnel

Create `C:\Users\HP\.cloudflared\config.yml`:

```yaml
tunnel: your-tunnel-id
credentials-file: C:\Users\HP\.cloudflared\your-tunnel-id.json

ingress:
  - hostname: api.yourdomain.com
    service: http://localhost:8000
    originRequest:
      noTLSVerify: true
  - hostname: www.yourdomain.com
    service: http://localhost:3000
    originRequest:
      noTLSVerify: true
  - service: http_status:404
```

### Step 5: Route DNS

```powershell
tools\cloudflared.exe tunnel route dns dental-ai-chatbot api.yourdomain.com
tools\cloudflared.exe tunnel route dns dental-ai-chatbot www.yourdomain.com
```

### Step 6: Run Tunnel

```powershell
tools\cloudflared.exe tunnel run dental-ai-chatbot
```

### Step 7: Update CORS

Update `.env`:

```env
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com,http://localhost:3000
```

Restart services:

```powershell
docker-compose down
docker-compose up -d
```

---

## 14. GPU Optimization

### RTX 5060Ti (16GB VRAM) Optimal Settings

Update `.env`:

```env
# === GPU OPTIMIZATION ===
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=1024
OLLAMA_TOP_P=0.85
OLLAMA_KEEP_ALIVE=30m

# === EMBEDDING BATCH SIZE ===
EMBEDDING_BATCH_SIZE=128
VECTOR_UPSERT_BATCH_SIZE=256
```

### Monitor GPU Usage

```powershell
# Real-time GPU monitoring
nvidia-smi -l 1

# Or in PowerShell
while ($true) { nvidia-smi; Start-Sleep 2; Clear-Host }
```

### GPU Memory Management

If Ollama uses too much VRAM:

```powershell
# Set GPU layers (35 layers for 16GB VRAM)
$env:OLLAMA_NUM_GPU_LAYERS=35

# Or reduce context window
# In .env: OLLAMA_NUM_CTX=4096
```

### Multi-Model GPU Sharing

For running both text and vision models:

```env
# Text model uses ~9GB VRAM
OLLAMA_MODEL=qwen3:14b

# Vision model uses ~4GB VRAM
OLLAMA_VISION_MODEL=qwen2.5vl:7b

# Total: ~13GB VRAM (fits in 16GB)
```

---

## 15. Troubleshooting

### Common Issues

#### 1. Docker Fails to Start

```powershell
# Check WSL2 is installed
wsl --status

# If not installed:
wsl --install

# Restart Docker Desktop
```

#### 2. GPU Not Detected

```powershell
# Check NVIDIA driver
nvidia-smi

# If not working, reinstall driver from nvidia.com

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

#### 3. Ollama Model Not Found

```powershell
# Check models
ollama list

# Pull missing model
ollama pull qwen3:14b
ollama pull qwen2.5vl:7b

# Restart Ollama
ollama serve
```

#### 4. Port Already in Use

```powershell
# Find process using port
netstat -ano | findstr :8000

# Kill process
taskkill /PID <PID> /F
```

#### 5. Database Connection Failed

```powershell
# Check PostgreSQL container
docker-compose logs postgres

# Restart PostgreSQL
docker-compose restart postgres
```

#### 6. Redis Connection Failed

```powershell
# Check Redis container
docker-compose logs redis

# Restart Redis
docker-compose restart redis
```

#### 7. Out of GPU Memory

```powershell
# Check GPU memory
nvidia-smi

# Kill Ollama process
taskkill /F /IM ollama.exe

# Restart Ollama with fewer layers
$env:OLLAMA_NUM_GPU_LAYERS=25
ollama serve
```

#### 8. Slow Responses

```powershell
# Check Ollama is using GPU
nvidia-smi

# Should show ollama process using GPU memory

# If using CPU only, check:
$env:CUDA_VISIBLE_DEVICES=0
```

### Reset Everything

```powershell
# Stop all services
docker-compose down

# Remove volumes
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Start fresh
docker-compose up -d --build
```

### View Logs

```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f frontend
docker-compose logs -f postgres
docker-compose logs -f qdrant
docker-compose logs -f redis
```

---

## Quick Start Commands

```powershell
# 1. Navigate to project
cd C:\Users\HP\OneDrive\Desktop\Dental_AI_chatbot\Dental_AI_Chatbot

# 2. Start everything
docker-compose up -d

# 3. Wait 2 minutes for services to start

# 4. Open browser
start http://localhost:3000

# 5. Login and start chatting!
```

---

## Architecture

```
Internet
    │
    ▼
Cloudflare CDN
    │
    ▼
Nginx Reverse Proxy (port 80)
    │
    ├──► Frontend (Next.js, port 3000)
    │
    └──► Backend API (FastAPI, port 8000)
              │
              ├──► Redis (Cache, port 6379)
              ├──► PostgreSQL (Database, port 5432)
              ├──► Qdrant (Vectors, port 6333)
              ├──► Prometheus (Metrics, port 9090)
              └──► Grafana (Dashboards, port 3001)
                          │
                          ▼
                    LangGraph Agent
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
         Retrieval    Visual    Citation
              │           │           │
              └─────┬─────┴───────────┘
                    ▼
              Hybrid Retrieval
              ┌─────┴─────┐
              ▼           ▼
         Qdrant Text  Qdrant Visual
              │           │
              └─────┬─────┘
                    ▼
              Context Builder
                    ▼
              Office GPU Server (RTX 5060Ti)
                    ▼
              Ollama (Qwen3:14b + Qwen2.5-VL:7b)
                    ▼
              Final Response
```

---

## Performance Benchmarks

| Metric | Target | Expected (RTX 5060Ti) |
|--------|--------|----------------------|
| Text Generation | < 5s | 2-4s |
| Vision Analysis | < 10s | 5-8s |
| RAG Retrieval | < 500ms | 200-400ms |
| Embedding | < 100ms | 30-80ms |
| API Response | < 200ms | 50-150ms |
| Concurrent Users | 50+ | 100+ |

---

## Support

For issues or questions:

1. Check [Troubleshooting](#15-troubleshooting) section
2. Check GitHub Issues: https://github.com/Hamadullah09/Dental_AI_Chatbot/issues
3. Contact: your-email@domain.com

---

## License

MIT License - See LICENSE file for details.
