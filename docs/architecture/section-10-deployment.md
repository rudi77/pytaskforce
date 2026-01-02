# Section 10: Deployment

Deployment architecture, infrastructure setup, and operational procedures for Taskforce:

---

### **Deployment Environments**

#### **Environment Strategy**

**Three-tier deployment:**

1. **Development (Local)**
   - Purpose: Individual developer workstations
   - Deployment: Docker Compose
   - Persistence: File-based state (`FileStateManager`)
   - LLM: OpenAI API (personal keys)
   - Database: Optional PostgreSQL container (for testing DB features)

2. **Staging**
   - Purpose: Pre-production testing, integration testing
   - Deployment: Docker Compose on dedicated VM/server
   - Persistence: PostgreSQL container with persistent volume
   - LLM: Shared OpenAI or Azure OpenAI account
   - Database: PostgreSQL 15 in Docker with backups
   - URL: `https://staging.taskforce.internal`

3. **Production (Future)**
   - Purpose: Live user-facing environment
   - Deployment: Kubernetes cluster (Azure AKS or on-premise)
   - Persistence: Managed PostgreSQL (Azure Database for PostgreSQL)
   - LLM: Azure OpenAI with private endpoint
   - Database: Managed service with high availability
   - URL: `https://api.taskforce.example.com`

---

### **Docker Compose Setup (Development & Staging)**

#### **Docker Compose Architecture**

```yaml
# docker-compose.yml
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    container_name: taskforce-postgres
    environment:
      POSTGRES_DB: taskforce
      POSTGRES_USER: taskforce
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --locale=en_US.utf8"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taskforce"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Taskforce API Service
  taskforce-api:
    build:
      context: .
      dockerfile: Dockerfile
    image: taskforce:latest
    container_name: taskforce-api
    environment:
      # Database
      DATABASE_URL: postgresql+asyncpg://taskforce:${DB_PASSWORD}@postgres:5432/taskforce
      
      # LLM Configuration
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      AZURE_OPENAI_API_KEY: ${AZURE_OPENAI_API_KEY:-}
      AZURE_OPENAI_ENDPOINT: ${AZURE_OPENAI_ENDPOINT:-}
      
      # RAG Configuration (optional)
      AZURE_SEARCH_ENDPOINT: ${AZURE_SEARCH_ENDPOINT:-}
      AZURE_SEARCH_API_KEY: ${AZURE_SEARCH_API_KEY:-}
      
      # API Configuration
      TASKFORCE_API_KEY: ${TASKFORCE_API_KEY}
      PROFILE: ${PROFILE:-staging}
      LOG_LEVEL: ${LOG_LEVEL:-info}
      
      # Work Directory
      WORK_DIR: /app/data
    volumes:
      - taskforce_data:/app/data
      - ./configs:/app/configs:ro
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  # Nginx Reverse Proxy (Staging only)
  nginx:
    image: nginx:alpine
    container_name: taskforce-nginx
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro  # SSL certificates
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - taskforce-api
    restart: unless-stopped
    profiles:
      - staging  # Only run in staging

volumes:
  postgres_data:
    driver: local
  taskforce_data:
    driver: local

networks:
  default:
    name: taskforce-network
```

#### **Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 taskforce && \
    mkdir -p /app/data && \
    chown -R taskforce:taskforce /app

# Set working directory
WORKDIR /app

# Copy dependency files
COPY --chown=taskforce:taskforce pyproject.toml uv.lock ./

# Install uv and dependencies
RUN pip install --no-cache-dir uv && \
    uv sync --frozen

# Copy application code
COPY --chown=taskforce:taskforce . .

# Switch to non-root user
USER taskforce

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uv", "run", "uvicorn", "taskforce.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### **Environment Variables (.env)**

```bash
# .env (not committed to git)
# Database
DB_PASSWORD=change_me_in_production

# LLM Providers
OPENAI_API_KEY=sk-...
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=

# RAG (optional)
AZURE_SEARCH_ENDPOINT=
AZURE_SEARCH_API_KEY=

# API Security
TASKFORCE_API_KEY=secure_random_key_here

# Configuration
PROFILE=staging
LOG_LEVEL=info
```

---

### **Deployment Procedures**

#### **Initial Deployment (Staging)**

**Prerequisites:**
- Docker and Docker Compose installed
- `.env` file configured with secrets
- SSL certificates (for HTTPS) in `./ssl/` directory

**Steps:**

```powershell
# 1. Clone repository
git clone https://github.com/yourorg/taskforce.git
cd taskforce

# 2. Configure environment
Copy-Item .env.example .env
# Edit .env with your secrets

# 3. Build images
docker-compose build

# 4. Initialize database (run migrations)
docker-compose run --rm taskforce-api uv run alembic upgrade head

# 5. Start services
docker-compose --profile staging up -d

# 6. Verify deployment
docker-compose ps
curl http://localhost:8000/health
```

**Expected Output:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "timestamp": "2025-11-22T10:00:00Z"
}
```

#### **Updates and Rollbacks**

**Deployment Update:**
```powershell
# 1. Pull latest changes
git pull origin main

# 2. Rebuild images
docker-compose build

# 3. Rolling restart (zero downtime with multiple replicas)
docker-compose up -d --no-deps --build taskforce-api

# 4. Verify health
docker-compose exec taskforce-api curl http://localhost:8000/health
```

**Database Migration:**
```powershell
# Run migrations (before deploying new code)
docker-compose run --rm taskforce-api uv run alembic upgrade head

# Rollback migration if needed
docker-compose run --rm taskforce-api uv run alembic downgrade -1
```

**Rollback Procedure:**
```powershell
# 1. Identify previous working version
git log --oneline -10

# 2. Checkout previous version
git checkout <commit-hash>

# 3. Rebuild and restart
docker-compose build
docker-compose up -d

# 4. Rollback database if needed
docker-compose run --rm taskforce-api uv run alembic downgrade <revision>
```

---

### **Database Migrations (Alembic)**

#### **Alembic Configuration**

```python
# alembic.ini
[alembic]
script_location = taskforce/migrations
sqlalchemy.url = # Set via env var

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

```python
# taskforce/migrations/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os

# Import your models
from taskforce.infrastructure.persistence.models import Base

config = context.config

# Override sqlalchemy.url from environment
config.set_main_option(
    "sqlalchemy.url",
    os.getenv("DATABASE_URL", "postgresql://taskforce:password@localhost/taskforce")
)

fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
```

#### **Creating Migrations**

```powershell
# Auto-generate migration from model changes
docker-compose run --rm taskforce-api uv run alembic revision --autogenerate -m "Add memory table"

# Manually create migration
docker-compose run --rm taskforce-api uv run alembic revision -m "Custom change"

# Apply migrations
docker-compose run --rm taskforce-api uv run alembic upgrade head

# Check current version
docker-compose run --rm taskforce-api uv run alembic current

# Show migration history
docker-compose run --rm taskforce-api uv run alembic history
```

---

### **Backup & Recovery**

#### **Database Backups**

**Automated Backup Script:**
```powershell
# scripts/backup-db.ps1
$BACKUP_DIR = "backups"
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"
$BACKUP_FILE = "$BACKUP_DIR/taskforce_backup_$TIMESTAMP.sql"

# Create backup directory
New-Item -ItemType Directory -Force -Path $BACKUP_DIR

# Run pg_dump
docker-compose exec -T postgres pg_dump -U taskforce taskforce > $BACKUP_FILE

# Compress backup
Compress-Archive -Path $BACKUP_FILE -DestinationPath "$BACKUP_FILE.zip"
Remove-Item $BACKUP_FILE

Write-Host "Backup created: $BACKUP_FILE.zip"

# Delete backups older than 30 days
Get-ChildItem -Path $BACKUP_DIR -Filter "*.zip" | 
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | 
    Remove-Item
```

**Schedule Backups (Windows Task Scheduler):**
- Frequency: Daily at 2 AM
- Retention: 30 days
- Storage: Local disk + offsite copy (Azure Blob Storage)

**Restore from Backup:**
```powershell
# Extract backup
Expand-Archive -Path backups/taskforce_backup_20251122.sql.zip -DestinationPath temp/

# Stop services
docker-compose stop taskforce-api

# Drop and recreate database
docker-compose exec postgres psql -U taskforce -c "DROP DATABASE IF EXISTS taskforce;"
docker-compose exec postgres psql -U taskforce -c "CREATE DATABASE taskforce;"

# Restore backup
Get-Content temp/taskforce_backup_20251122.sql | docker-compose exec -T postgres psql -U taskforce taskforce

# Restart services
docker-compose start taskforce-api
```

#### **State Data Backups**

**File-based State (Development):**
```powershell
# Backup work directory
Compress-Archive -Path data/states -DestinationPath backups/states_$(Get-Date -Format 'yyyyMMdd').zip
```

**Database State (Staging/Production):**
Included in PostgreSQL backups (states table)

---

### **Monitoring & Health Checks**

#### **Health Check Endpoints**

**Liveness Probe:**
```python
# api/routes/health.py
@app.get("/health")
async def health_check():
    """Basic liveness probe."""
    return {
        "status": "healthy",
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat()
    }
```

**Readiness Probe:**
```python
@app.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db_session)
):
    """Readiness probe - checks database connectivity."""
    try:
        # Test database connection
        await db.execute(text("SELECT 1"))
        
        # Test LLM provider (future)
        # llm_status = await llm_service.health_check()
        
        return {
            "status": "ready",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service not ready: {str(e)}"
        )
```

#### **Docker Healthchecks**

Configured in `docker-compose.yml`:
- API: `curl -f http://localhost:8000/health`
- PostgreSQL: `pg_isready -U taskforce`
- Frequency: Every 30 seconds
- Restart policy: `unless-stopped`

---

### **Logging & Log Aggregation**

#### **Structured Logging Configuration**

```python
# infrastructure/logging/config.py
import structlog
import logging

def configure_logging(log_level: str = "INFO"):
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()  # JSON output for production
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

**Log Output (JSON):**
```json
{
  "event": "agent.execution.started",
  "level": "info",
  "timestamp": "2025-11-22T10:30:00.123Z",
  "session_id": "abc-123",
  "mission": "Create hello world",
  "profile": "staging"
}
```

#### **Log Collection (Docker)**

```yaml
# docker-compose.yml (add to services)
services:
  taskforce-api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**View Logs:**
```powershell
# Follow logs
docker-compose logs -f taskforce-api

# Last 100 lines
docker-compose logs --tail=100 taskforce-api

# Export logs
docker-compose logs --no-color taskforce-api > taskforce.log
```

---

### **SSL/TLS Configuration (Staging)**

#### **Nginx SSL Termination**

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream taskforce_backend {
        server taskforce-api:8000;
    }

    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name staging.taskforce.internal;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name staging.taskforce.internal;

        # SSL certificates
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        
        # SSL configuration
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Security headers
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;

        # Proxy configuration
        location /api/ {
            proxy_pass http://taskforce_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # Streaming support
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
        }

        # Health check (no auth required)
        location /health {
            proxy_pass http://taskforce_backend;
            access_log off;
        }
    }
}
```

---

### **Kubernetes Deployment (Future)**

#### **Kubernetes Manifests**

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: taskforce-api
  namespace: taskforce
spec:
  replicas: 3
  selector:
    matchLabels:
      app: taskforce-api
  template:
    metadata:
      labels:
        app: taskforce-api
    spec:
      containers:
      - name: taskforce
        image: taskforce:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: taskforce-secrets
              key: database-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: taskforce-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: taskforce-api
  namespace: taskforce
spec:
  selector:
    app: taskforce-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: taskforce-ingress
  namespace: taskforce
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - api.taskforce.example.com
    secretName: taskforce-tls
  rules:
  - host: api.taskforce.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: taskforce-api
            port:
              number: 80
```

**Horizontal Pod Autoscaler:**
```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: taskforce-api-hpa
  namespace: taskforce
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: taskforce-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

### **CI/CD Pipeline (Future)**

#### **GitHub Actions Workflow**

```yaml
# .github/workflows/deploy.yml
name: Build and Deploy

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run tests
        run: uv run pytest
      
      - name: Run linters
        run: |
          uv run ruff check .
          uv run black --check .

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/staging'
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Docker image
        run: docker build -t taskforce:${{ github.sha }} .
      
      - name: Push to registry
        run: |
          docker tag taskforce:${{ github.sha }} registry.example.com/taskforce:latest
          docker push registry.example.com/taskforce:latest

  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/staging'
    steps:
      - name: Deploy to staging
        run: |
          ssh staging-server "cd /app/taskforce && docker-compose pull && docker-compose up -d"
```

---

### **Operational Procedures**

#### **Daily Operations**

**Morning Checks:**
- Check service health: `docker-compose ps`
- Review logs for errors: `docker-compose logs --tail=100 taskforce-api | grep -i error`
- Check disk space: `docker system df`
- Verify backups completed: `Get-ChildItem backups | Sort-Object LastWriteTime -Descending | Select-Object -First 1`

**Incident Response:**
1. Check service status: `docker-compose ps`
2. Review recent logs: `docker-compose logs --tail=500 taskforce-api`
3. Check resource usage: `docker stats`
4. Restart service if needed: `docker-compose restart taskforce-api`
5. Escalate if issue persists

#### **Maintenance Windows**

**Scheduled Maintenance:**
- Frequency: Monthly (last Sunday, 2-4 AM)
- Activities:
  - OS updates
  - Docker image updates
  - Database maintenance (VACUUM, ANALYZE)
  - Certificate renewals

**Maintenance Procedure:**
```powershell
# 1. Notify users (if applicable)
# 2. Stop services
docker-compose stop taskforce-api

# 3. Backup database
.\scripts\backup-db.ps1

# 4. Apply updates
docker-compose pull
docker-compose build --pull

# 5. Run migrations
docker-compose run --rm taskforce-api uv run alembic upgrade head

# 6. Start services
docker-compose up -d

# 7. Verify health
Start-Sleep -Seconds 30
curl http://localhost:8000/health

# 8. Monitor for issues
docker-compose logs -f taskforce-api
```

---

### **Rationale:**

**Deployment Design Decisions:**

1. **Docker Compose First, Kubernetes Later**: Start with Docker Compose for simplicity. Rationale: Faster iteration during initial development. Many organizations don't need Kubernetes complexity. Trade-off: Less auto-scaling vs. operational simplicity.

2. **PostgreSQL in Docker (Staging)**: Containerized database for staging. Rationale: Simplifies setup, good enough for staging load. Trade-off: Not production-grade (managed service better) but acceptable for staging.

3. **File-based State for Dev**: FileStateManager for local development. Rationale: Zero setup, no database required. Trade-off: Not multi-instance safe vs. developer experience.

4. **Alembic for Migrations**: SQLAlchemy migration tool. Rationale: Standard Python ecosystem tool, version control for schema. Trade-off: Learning curve vs. database reliability.

5. **Nginx for SSL Termination**: Reverse proxy handles HTTPS. Rationale: Offload SSL from Python app, battle-tested, efficient. Trade-off: Additional component vs. security/performance.

**Key Assumptions:**
- Docker Compose sufficient for staging (<100 concurrent users) - validated by common practice
- Daily backups acceptable (RPO = 24 hours) - needs validation based on business requirements
- Single region deployment acceptable initially - needs validation for disaster recovery

---
