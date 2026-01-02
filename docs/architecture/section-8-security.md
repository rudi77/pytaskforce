# Section 8: Security

Security considerations and implementation strategies for Taskforce:

---

### **Authentication & Authorization**

#### **API Authentication**

**Current Implementation (MVP):**
- **API Key Authentication** for FastAPI REST endpoints
- Simple bearer token validation: `Authorization: Bearer {API_KEY}`
- API keys stored in environment variable `TASKFORCE_API_KEY`
- No per-user authentication in MVP (single-tenant)

**Code Pattern:**
```python
# api/deps.py
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

security = HTTPBearer()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> None:
    """Verify API key from Authorization header."""
    api_key = os.getenv("TASKFORCE_API_KEY")
    if not api_key:
        # Allow access if no API key configured (dev mode)
        return
    
    if credentials.credentials != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
```

**Future Enhancements (Post-MVP):**
- **OAuth 2.0 / JWT**: For multi-tenant deployments
- **Role-Based Access Control (RBAC)**: Admin, user, read-only roles
- **Per-user session isolation**: User ID attached to sessions for auditing
- **API key rotation**: Automated key rotation with grace periods

#### **CLI Authentication**

**Current Implementation:**
- No authentication required (local development tool)
- Assumes trusted execution environment

**Future Enhancements:**
- Local credential storage for remote API calls
- SSH key-based authentication for remote agents

---

### **Secret Management**

#### **Current Strategy (Environment Variables)**

**API Keys and Credentials:**
All sensitive credentials stored as environment variables:
- `OPENAI_API_KEY` - OpenAI API access
- `AZURE_OPENAI_API_KEY` - Azure OpenAI API access
- `AZURE_OPENAI_ENDPOINT` - Azure OpenAI endpoint URL
- `AZURE_SEARCH_API_KEY` - Azure AI Search API key
- `AZURE_SEARCH_ENDPOINT` - Azure AI Search endpoint URL
- `GITHUB_TOKEN` - GitHub API access (optional)
- `TASKFORCE_API_KEY` - FastAPI authentication key
- `DATABASE_URL` - PostgreSQL connection string (contains password)

**Environment Variable Loading:**
```python
# application/profiles.py
import os
from typing import Dict, Any

def merge_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Override config with environment variables."""
    env_mappings = {
        "OPENAI_API_KEY": "llm.openai_api_key",
        "DATABASE_URL": "persistence.database_url",
        "TASKFORCE_API_KEY": "api.auth_key",
    }
    
    for env_var, config_path in env_mappings.items():
        value = os.getenv(env_var)
        if value:
            set_nested_config(config, config_path, value)
    
    return config
```

**Security Measures:**
- ✅ Never log API keys (filtered from structured logs)
- ✅ Never commit to version control (.env files in .gitignore)
- ✅ Never pass secrets via command line arguments (visible in process list)
- ✅ Use environment variables for Docker containers (via docker-compose secrets)

#### **Future Strategy (Production)**

**Kubernetes Secrets / Azure Key Vault:**
```python
# Future: infrastructure/secrets/key_vault.py
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

class KeyVaultSecretProvider:
    """Azure Key Vault integration for production secrets."""
    
    async def get_secret(self, secret_name: str) -> str:
        """Retrieve secret from Azure Key Vault."""
        credential = DefaultAzureCredential()
        client = SecretClient(
            vault_url=os.getenv("AZURE_KEYVAULT_URL"),
            credential=credential
        )
        secret = client.get_secret(secret_name)
        return secret.value
```

**Planned Enhancements:**
- Azure Key Vault integration for production
- Kubernetes secrets for container deployments
- Secret rotation monitoring and alerts
- Separate secrets for dev/staging/prod environments

---

### **Data Security**

#### **Data at Rest**

**PostgreSQL Encryption:**
- **Database Level**: PostgreSQL Transparent Data Encryption (TDE) enabled on production instances
- **Connection Encryption**: SSL/TLS required for all database connections
  ```python
  # Connection string example
  DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db?ssl=require"
  ```
- **Backup Encryption**: Automated backups encrypted with AES-256
- **State Data**: Session state stored as JSONB (may contain sensitive user inputs)
  - Future: Field-level encryption for sensitive state data (e.g., API tokens in state)

**File System (Development Mode):**
- File-based state stored in `{work_dir}/states/` directory
- Permissions: 600 (owner read/write only) on state files
- Recommendation: Work directory on encrypted volume

**Docker Volumes:**
- State volumes mounted with appropriate permissions
- Avoid mounting sensitive directories into containers

#### **Data in Transit**

**HTTPS/TLS Requirements:**
- **Production**: HTTPS mandatory for FastAPI endpoints (enforced via reverse proxy/ingress)
- **Development**: HTTP acceptable for localhost
- **API Calls**: All external API calls (OpenAI, Azure) use HTTPS

**TLS Configuration (Reverse Proxy):**
```yaml
# Example nginx configuration (not in Taskforce repo)
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/taskforce.crt;
    ssl_certificate_key /etc/ssl/private/taskforce.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    location /api/ {
        proxy_pass http://taskforce:8000;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

**Database Connections:**
- SSL required for PostgreSQL connections in staging/prod profiles
- Certificate verification enabled

---

### **Input Validation & Sanitization**

#### **API Input Validation**

**Pydantic Request Models:**
```python
# api/models.py
from pydantic import BaseModel, Field, validator
from typing import Optional

class ExecuteRequest(BaseModel):
    """Mission execution request."""
    mission: str = Field(..., min_length=1, max_length=10000)
    profile: str = Field(default="dev", regex="^(dev|staging|prod)$")
    session_id: Optional[str] = Field(default=None, regex="^[a-f0-9-]{36}$")
    
    @validator("mission")
    def validate_mission(cls, v: str) -> str:
        """Prevent excessively long missions."""
        if len(v.strip()) == 0:
            raise ValueError("Mission cannot be empty")
        return v.strip()
```

**Benefits:**
- Type safety (Pydantic enforces types)
- Automatic validation before handler execution
- Clear error messages for invalid requests

#### **Prompt Injection Prevention**

**LLM Security Considerations:**
Taskforce sends user-provided mission text directly to LLMs. Potential risks:
1. **Prompt Injection**: User crafts mission to manipulate agent behavior
2. **Data Exfiltration**: User tricks agent into leaking system prompts or state
3. **Jailbreaking**: User bypasses safety restrictions

**Mitigation Strategies:**

1. **System Prompt Protection:**
   ```python
   # Separate system and user messages clearly
   messages = [
       {"role": "system", "content": SYSTEM_PROMPT},
       {"role": "user", "content": f"Mission: {user_mission}"}
   ]
   ```

2. **Input Sanitization:**
   ```python
   def sanitize_mission(mission: str) -> str:
       """Remove potentially harmful content from mission text."""
       # Strip markdown code blocks that might confuse LLM
       mission = re.sub(r"```.*?```", "", mission, flags=re.DOTALL)
       # Limit length
       return mission[:10000]
   ```

3. **Output Validation:**
   - Validate tool parameters before execution
   - Prevent file operations outside work directory
   - Reject shell commands with suspicious patterns (e.g., `rm -rf /`)

4. **Least Privilege Execution:**
   - Python tool runs in restricted namespace (no `os`, `sys` imports by default)
   - File tools reject absolute paths outside work directory
   - Shell tools run with timeout limits

**Example: File Path Validation:**
```python
# infrastructure/tools/native/file_tools.py
import os
from pathlib import Path

def validate_file_path(file_path: str, work_dir: str) -> Path:
    """Ensure file path is within work directory."""
    resolved = Path(file_path).resolve()
    work_dir_resolved = Path(work_dir).resolve()
    
    if not resolved.is_relative_to(work_dir_resolved):
        raise SecurityError(
            f"File path {file_path} is outside work directory"
        )
    
    return resolved
```

---

### **Dependency Security**

#### **Dependency Management**

**Package Security:**
- **uv** package manager with lock file (`uv.lock`)
- Dependency pinning for reproducible builds
- Regular security audits via `pip-audit` or GitHub Dependabot

**Automated Scanning:**
```yaml
# .github/workflows/security.yml (future)
name: Security Scan
on: [push, pull_request]
jobs:
  dependency-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install pip-audit
      - run: pip-audit --requirement pyproject.toml
```

**Known Security Considerations:**
- **LiteLLM**: Keep updated for API security patches
- **FastAPI**: Keep updated for web framework vulnerabilities
- **SQLAlchemy**: Keep updated for SQL injection mitigations
- **aiohttp**: Keep updated for HTTP client vulnerabilities

#### **Docker Image Security**

**Base Image Selection:**
- Use official Python slim images: `python:3.11-slim`
- Avoid `latest` tags (use specific versions)
- Regular base image updates

**Non-Root User:**
```dockerfile
# Dockerfile
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 taskforce
USER taskforce

WORKDIR /app
COPY --chown=taskforce:taskforce . .
RUN uv sync

CMD ["uvicorn", "taskforce.api.server:app", "--host", "0.0.0.0"]
```

**Image Scanning:**
- Trivy or Snyk for vulnerability scanning
- Scan images in CI/CD pipeline before deployment

---

### **Audit Logging**

#### **Structured Logging with structlog**

**Log All Security Events:**
```python
# infrastructure/logging/security_logger.py
import structlog

logger = structlog.get_logger()

# Authentication events
logger.info(
    "auth.api_key.success",
    endpoint="/api/v1/execute",
    client_ip=request.client.host
)

logger.warning(
    "auth.api_key.failed",
    endpoint="/api/v1/execute",
    client_ip=request.client.host,
    reason="invalid_key"
)

# Tool execution events
logger.info(
    "tool.execution.started",
    tool_name="shell",
    session_id=session_id,
    parameters=sanitized_params  # Sensitive params redacted
)

# State access events
logger.info(
    "state.loaded",
    session_id=session_id,
    user_id=user_id
)
```

**Log Retention:**
- Development: 7 days
- Staging: 30 days
- Production: 90 days (compliance requirement)

**Log Analysis:**
- Centralized logging via ELK stack or Azure Application Insights (future)
- Anomaly detection for suspicious patterns (future)

---

### **Rate Limiting & DDoS Protection**

#### **API Rate Limiting**

**FastAPI Middleware:**
```python
# api/middleware/rate_limit.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from fastapi import Request

limiter = Limiter(key_func=get_remote_address)

# Apply to routes
@app.post("/api/v1/execute")
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def execute_mission(request: Request, data: ExecuteRequest):
    ...
```

**External API Rate Limiting:**
- Respect OpenAI/Azure rate limits (tracked in LLM service)
- Implement backoff and circuit breaker patterns
- Queue requests if approaching rate limits

#### **DDoS Protection**

**Infrastructure Level:**
- Reverse proxy rate limiting (nginx, Traefik)
- Cloud provider DDoS protection (Azure DDoS Protection, Cloudflare)
- Request size limits (max 10MB payload)

---

### **Kubernetes Security (Future)**

**When migrating from Docker Compose to Kubernetes:**

**Pod Security Standards:**
- Run as non-root user (UID > 1000)
- Read-only root filesystem where possible
- Drop all capabilities except required ones
- Network policies to restrict inter-pod communication

**Secrets Management:**
- Use Kubernetes secrets (not environment variables in manifests)
- Azure Key Vault CSI driver for production secrets
- Rotate secrets regularly

**RBAC:**
- Service accounts with minimal permissions
- No cluster-admin access for applications

---

### **Compliance Considerations**

**GDPR (if handling EU user data):**
- Right to be forgotten: Delete session state API endpoint
- Data minimization: Don't log user inputs unnecessarily
- Audit trail: Track all data access

**SOC 2 Type II (future):**
- Comprehensive audit logging
- Access control policies documented
- Incident response procedures

---

### **Security Checklist (Pre-Production)**

**Before deploying to production:**

- [ ] All API keys stored in environment variables (not code)
- [ ] HTTPS enforced on all API endpoints
- [ ] PostgreSQL SSL connections required
- [ ] Database credentials rotated from defaults
- [ ] API authentication enabled (`TASKFORCE_API_KEY` set)
- [ ] Rate limiting configured
- [ ] Dependency security scan passed
- [ ] Docker images scanned for vulnerabilities
- [ ] Audit logging enabled and tested
- [ ] File path validation prevents directory traversal
- [ ] Python tool sandbox prevents dangerous imports
- [ ] Shell command validation prevents injection
- [ ] Log retention policy configured
- [ ] Backup encryption verified
- [ ] Incident response plan documented

---

### **Rationale:**

**Security Design Decisions:**

1. **API Key over OAuth for MVP**: Simple bearer token authentication initially. Rationale: Faster to implement, sufficient for single-tenant. Trade-off: Less granular access control vs. time to market.

2. **Environment Variables for Secrets**: Standard 12-factor app pattern. Rationale: Simple, works across Docker and Kubernetes. Trade-off: Less secure than Key Vault, but acceptable with proper ops practices.

3. **No Field-Level Encryption (MVP)**: Session state stored as plaintext JSONB. Rationale: Simplifies queries and debugging. Trade-off: Sensitive data visible to DB admins. Mitigated by database encryption at rest and access controls.

4. **Prompt Injection Mitigation (Not Prevention)**: Input sanitization reduces but doesn't eliminate prompt injection risk. Rationale: Complete prevention requires constrained LLM usage that limits flexibility. Trade-off: Security vs. agent capability.

5. **Defensive Tool Validation**: Every tool validates inputs and restricts operations. Rationale: Defense in depth - even if agent is compromised, damage is limited.

**Key Assumptions:**
- Users trust the agent with tool access (validated: this is an automation agent, trust is required)
- Docker/Compose environment is reasonably secure (needs validation: network isolation, host hardening)
- OpenAI API keys treated as highly sensitive (validated: compromise = cost + data leak)

**Known Limitations (MVP):**
- No multi-tenancy (single shared agent)
- No fine-grained RBAC
- No field-level encryption
- Limited prompt injection prevention

---

🏗️ **Proceeding to Performance & Scalability...**

---
