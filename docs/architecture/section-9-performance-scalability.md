# Section 9: Performance & Scalability

Performance targets, bottleneck analysis, and scalability strategies for Taskforce:

---

### **Performance Targets**

#### **Latency Requirements**

**API Response Times (p95):**
- **Health Check**: < 100ms
- **Session List/Get**: < 200ms (database query)
- **Mission Start (non-streaming)**: < 500ms (initial setup, before ReAct loop)
- **Streaming Event Delivery**: < 100ms per event (SSE latency)
- **ReAct Loop Iteration**: 2-10 seconds (dominated by LLM latency)
  - Thought generation: 1-5 seconds (OpenAI API call)
  - Tool execution: 0.1-5 seconds (tool-dependent)
  - State persistence: < 100ms

**CLI Response Times:**
- **Command startup**: < 500ms (Python import overhead)
- **Interactive chat**: Same as ReAct loop iteration (2-10s)
- **Session list**: < 1 second

**Database Query Performance:**
- **State load/save**: < 50ms (single row lookup with index)
- **Session list with pagination**: < 100ms (indexed query)
- **TodoList load**: < 50ms (JSONB retrieval)

#### **Throughput Targets**

**API Throughput (per instance):**
- **Concurrent missions**: 10-50 concurrent agent executions per instance
  - Limited by: CPU (JSON parsing), memory (agent state), I/O (database connections)
- **Requests per second**: 100 RPS for read-only endpoints (health, session get)
- **Database connections**: 20 connections per instance (asyncpg pool)

**LLM API Throughput:**
- **OpenAI rate limits**: 500 RPM (requests per minute) for GPT-4
- **Azure OpenAI**: Configured per deployment (typically 240K TPM)
- **Mitigation**: Queue requests, implement circuit breaker, multi-instance deployment

#### **Resource Utilization**

**Memory per Agent Instance:**
- **Baseline**: 200 MB (Python runtime + libraries)
- **Per active session**: +10-50 MB (agent state, message history, tool instances)
- **Target**: Support 50 concurrent sessions on 4 GB instance

**CPU Utilization:**
- **Async I/O bound**: Low CPU during LLM/database waits
- **JSON parsing**: High CPU during JSONB deserialization (large states)
- **Target**: < 70% average CPU utilization

**Database Storage:**
- **Per session**: ~10-100 KB (state + execution history)
- **Per TodoList**: ~5-20 KB (plan data)
- **Growth rate**: Depends on retention policy
  - Example: 1000 sessions/day × 50 KB = 50 MB/day = 18 GB/year

---

### **Bottleneck Analysis**

#### **Primary Bottlenecks (MVP)**

**1. LLM API Latency (Dominant)**
- **Impact**: 80% of total execution time
- **Characteristics**: 
  - High variability (1-10 seconds)
  - Rate limits constrain throughput
  - Not horizontally scalable (external service)
- **Mitigation**:
  - Use faster models (GPT-4-mini) for simple reasoning
  - Implement caching for repeated prompts (future)
  - Parallel tool execution where possible (future)

**2. Database Connection Pool Exhaustion**
- **Impact**: When concurrent sessions > connection pool size
- **Characteristics**:
  - Fixed pool size (default: 20 connections)
  - Connection acquisition timeout under load
  - Symptoms: 429 errors, increased latency
- **Mitigation**:
  ```python
  # Database pool configuration
  asyncpg_pool = await asyncpg.create_pool(
      dsn=DATABASE_URL,
      min_size=10,
      max_size=50,  # Increased for high load
      command_timeout=30,
      max_queries=50000,
      max_inactive_connection_lifetime=300
  )
  ```

**3. State Serialization (JSONB)**
- **Impact**: Increases with state size (large execution history)
- **Characteristics**:
  - CPU-bound JSON encoding/decoding
  - Large JSONB columns slow down queries
  - Symptom: High CPU, slow database queries
- **Mitigation**:
  - Paginate execution history (don't load all steps)
  - Compress large state fields (gzip)
  - Archive old sessions to separate table

**4. Memory Leaks (Long-Running Agents)**
- **Impact**: Memory growth over time
- **Characteristics**:
  - Unclosed aiohttp sessions
  - Retained message history
  - Large tool output accumulation
- **Mitigation**:
  - Explicit resource cleanup (async context managers)
  - Message history window limit (keep last N messages)
  - Tool output truncation (max 10 KB per observation)

---

### **Caching Strategy**

#### **LLM Response Caching (Future Enhancement)**

**Semantic Caching:**
```python
# infrastructure/llm/cache.py
import hashlib
from typing import Optional

class LLMCache:
    """Cache LLM responses for repeated prompts."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def get_cached_response(
        self, 
        model: str, 
        messages: list
    ) -> Optional[str]:
        """Retrieve cached response if available."""
        cache_key = self._generate_key(model, messages)
        return await self.redis.get(cache_key)
    
    async def cache_response(
        self, 
        model: str, 
        messages: list, 
        response: str,
        ttl_seconds: int = 3600
    ):
        """Cache LLM response with TTL."""
        cache_key = self._generate_key(model, messages)
        await self.redis.setex(cache_key, ttl_seconds, response)
    
    def _generate_key(self, model: str, messages: list) -> str:
        """Generate cache key from model and messages."""
        content = f"{model}:{str(messages)}"
        return f"llm:cache:{hashlib.sha256(content.encode()).hexdigest()}"
```

**Benefits:**
- Reduce LLM API costs for repeated missions
- Faster response times for cached queries
- Lower rate limit pressure

**Trade-offs:**
- Non-deterministic responses (LLM outputs vary)
- Cache invalidation complexity
- Redis dependency

#### **State Caching (In-Memory)**

**Agent State Cache:**
```python
# infrastructure/persistence/cached_state.py
from functools import lru_cache
from typing import Optional, Dict, Any

class CachedStateManager:
    """In-memory cache layer over DbStateManager."""
    
    def __init__(self, db_state_manager: DbStateManager):
        self.db = db_state_manager
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load from cache first, fallback to database."""
        if session_id in self.cache:
            return self.cache[session_id]
        
        state = await self.db.load_state(session_id)
        if state:
            self.cache[session_id] = state
        return state
    
    async def save_state(self, session_id: str, state_data: Dict[str, Any]):
        """Write to cache and database."""
        self.cache[session_id] = state_data
        await self.db.save_state(session_id, state_data)
```

**Benefits:**
- Faster state access for active sessions
- Reduced database load

**Trade-offs:**
- Memory usage scales with active sessions
- Cache consistency with multi-instance deployments

---

### **Horizontal Scalability**

#### **Stateless API Design**

**Scalability Characteristics:**
- **FastAPI instances**: Stateless (session state in database, not memory)
- **Load balancing**: Round-robin or least-connections
- **Session affinity**: Not required (any instance can handle any session)

**Docker Compose Scaling (Development/Staging):**
```yaml
# docker-compose.yml
services:
  taskforce-api:
    image: taskforce:latest
    deploy:
      replicas: 3  # Run 3 instances
    environment:
      - DATABASE_URL=postgresql://...
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - postgres
    
  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - taskforce-api
```

**Load Balancer Configuration (nginx):**
```nginx
# nginx.conf
upstream taskforce_backend {
    least_conn;  # Route to instance with fewest connections
    server taskforce-api:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    
    location /api/ {
        proxy_pass http://taskforce_backend;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Streaming support
        proxy_buffering off;
        proxy_cache off;
    }
}
```

#### **Database Scalability**

**PostgreSQL Optimization:**

**Connection Pooling (PgBouncer):**
```yaml
# docker-compose.yml
services:
  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    environment:
      - DATABASES_HOST=postgres
      - DATABASES_PORT=5432
      - DATABASES_USER=taskforce
      - DATABASES_PASSWORD=${DB_PASSWORD}
      - PGBOUNCER_POOL_MODE=transaction
      - PGBOUNCER_MAX_CLIENT_CONN=1000
      - PGBOUNCER_DEFAULT_POOL_SIZE=25
    ports:
      - "6432:6432"
```

**Benefits:**
- Support many more clients than direct database connections
- Reduce connection overhead

**Read Replicas (Future):**
- PostgreSQL streaming replication
- Route read queries (session list, state load) to replicas
- Write queries (state save) to primary
- Trade-off: Eventual consistency (replication lag)

**Indexing Strategy:**
```sql
-- Critical indexes for performance
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX idx_states_session_id_version ON states(session_id, version DESC);
CREATE INDEX idx_execution_history_session_step ON execution_history(session_id, step_id);

-- JSONB indexes for state queries (if needed)
CREATE INDEX idx_states_json_todolist ON states USING GIN ((state_json->'todolist_id'));
```

---

### **Async I/O Optimization**

#### **Async Throughout the Stack**

**Benefits of Async Architecture:**
- **Non-blocking I/O**: One thread handles many concurrent requests
- **Efficient resource usage**: Minimal memory overhead per request
- **Scalability**: 10-100x more concurrent connections than sync

**Key Async Patterns:**

**1. Async Database Queries:**
```python
# All database operations use asyncpg
async def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT state_json FROM states WHERE session_id = $1 ORDER BY version DESC LIMIT 1",
            session_id
        )
        return row['state_json'] if row else None
```

**2. Async LLM Calls:**
```python
# LiteLLM with async
response = await litellm.acompletion(
    model=model_name,
    messages=messages,
    timeout=30.0
)
```

**3. Async Tool Execution:**
```python
# All tools implement async execute
async def execute(self, **params) -> Dict[str, Any]:
    # Use asyncio.subprocess for shell commands
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return {"output": stdout.decode()}
```

**4. Async File Operations:**
```python
# aiofiles for async file I/O
async with aiofiles.open(state_file, "w") as f:
    await f.write(json.dumps(state_data))
```

#### **Concurrency Control**

**Semaphore for Rate Limiting:**
```python
# Limit concurrent LLM calls
class RateLimitedLLMService:
    def __init__(self, max_concurrent: int = 10):
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def complete(self, **kwargs):
        async with self.semaphore:
            return await litellm.acompletion(**kwargs)
```

**Task Groups for Parallel Execution:**
```python
# Execute multiple tools in parallel (future)
async def execute_parallel_tools(self, tools: List[ToolCall]):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(tool.execute(**params)) for tool in tools]
    return [task.result() for task in tasks]
```

---

### **Resource Limits & Guardrails**

#### **Execution Timeouts**

**Per-Request Timeouts:**
```python
# FastAPI timeout middleware
from starlette.middleware.base import BaseHTTPMiddleware

class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=300.0  # 5 minute max per request
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"error": "Request timeout"}
            )
```

**Tool Execution Timeouts:**
```python
# Per-tool timeout configuration
TOOL_TIMEOUTS = {
    "python": 60,  # 1 minute
    "shell": 300,  # 5 minutes
    "web_search": 30,  # 30 seconds
    "llm": 60,  # 1 minute
}

async def execute_with_timeout(tool: Tool, **params):
    timeout = TOOL_TIMEOUTS.get(tool.name, 60)
    try:
        return await asyncio.wait_for(
            tool.execute(**params),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        return {"success": False, "error": f"Tool timeout after {timeout}s"}
```

#### **Memory Limits**

**Message History Window:**
```python
class MessageHistory:
    MAX_MESSAGES = 50  # Keep last 50 message pairs
    
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        
        # Trim old messages
        if len(self.messages) > self.MAX_MESSAGES:
            # Keep system prompt (first message)
            self.messages = [self.messages[0]] + self.messages[-self.MAX_MESSAGES:]
```

**Tool Output Truncation:**
```python
MAX_TOOL_OUTPUT_SIZE = 10 * 1024  # 10 KB

def truncate_output(output: str) -> str:
    """Truncate large tool outputs."""
    if len(output) > MAX_TOOL_OUTPUT_SIZE:
        return output[:MAX_TOOL_OUTPUT_SIZE] + "\n... (truncated)"
    return output
```

---

### **Performance Monitoring**

#### **Instrumentation Points**

**Key Metrics to Track:**
```python
# infrastructure/monitoring/metrics.py
import structlog
from time import perf_counter

logger = structlog.get_logger()

async def track_latency(operation: str):
    """Context manager for latency tracking."""
    start = perf_counter()
    try:
        yield
    finally:
        duration_ms = (perf_counter() - start) * 1000
        logger.info(
            "performance.latency",
            operation=operation,
            duration_ms=duration_ms
        )

# Usage
async with track_latency("agent.execute"):
    await agent.execute(mission, session_id)
```

**Tracked Operations:**
- Agent execution (total)
- LLM thought generation
- Tool execution (per tool)
- State load/save
- Database queries
- API request handling

#### **Performance Dashboards (Future)**

**Grafana Dashboard Metrics:**
- Request latency (p50, p95, p99)
- Throughput (requests/second)
- Error rate (4xx, 5xx)
- Database connection pool utilization
- LLM API latency
- Active sessions count
- Memory usage per instance

---

### **Scalability Roadmap**

**Phase 1: MVP (Docker Compose)**
- Single instance deployment
- File or database persistence
- No caching
- Target: 10 concurrent sessions

**Phase 2: Multi-Instance (Docker Compose with Nginx)**
- 3-5 API instances behind load balancer
- Database persistence required
- PgBouncer connection pooling
- Target: 50 concurrent sessions

**Phase 3: Production (Kubernetes)**
- Horizontal pod autoscaling (HPA) based on CPU/memory
- PostgreSQL with read replicas
- Redis for LLM caching
- Target: 500+ concurrent sessions

**Phase 4: Optimization (Post-Launch)**
- CDN for static content
- Response caching (Redis)
- Parallel tool execution
- Circuit breaker for external APIs
- Target: 1000+ concurrent sessions

---

### **Rationale:**

**Performance Design Decisions:**

1. **Async-First Architecture**: All I/O operations async. Rationale: LLM calls dominate latency (5-10s), async enables efficient concurrent request handling during waits. Trade-off: Complexity vs. throughput.

2. **Database for Production State**: PostgreSQL over in-memory. Rationale: Durability required for production, supports multi-instance deployments. Trade-off: Latency (~50ms) vs. durability.

3. **No LLM Caching (MVP)**: Deferred to future. Rationale: Cache invalidation complex, non-deterministic responses reduce value. Trade-off: Cost/latency vs. complexity.

4. **Connection Pooling**: PgBouncer for database connections. Rationale: PostgreSQL max_connections limited (~100-200), pooling enables 1000+ clients. Trade-off: Transaction mode limitations vs. scalability.

5. **Aggressive Timeouts**: 5-minute max per request, 1-minute per tool. Rationale: Prevent resource exhaustion from hung operations. Trade-off: May interrupt long-running legitimate operations.

**Key Assumptions:**
- LLM latency is acceptable (5-10s per iteration) - validated by Agent V2 usage
- Database can handle 100 sessions/second write load - needs validation via load testing
- Async architecture provides sufficient concurrency - validated by FastAPI benchmarks (10K+ concurrent connections possible)

🏗️ **Proceeding to Deployment...**

---
