# Section 11: Testing Strategy

Comprehensive testing approach ensuring quality, reliability, and maintainability:

---

### **Testing Pyramid**

```
         /\
        /E2E\        ← 5-10% - End-to-End (Slow, Fragile)
       /------\
      /  API   \     ← 15-20% - Integration Tests (Moderate)
     /----------\
    /   Unit     \   ← 70-80% - Unit Tests (Fast, Isolated)
   /--------------\
```

**Testing Philosophy:**
- **Fast feedback**: Most tests should run in seconds
- **Isolated**: Unit tests don't touch database/network
- **Realistic**: Integration tests use real adapters (PostgreSQL, not mocks)
- **Automated**: All tests run in CI/CD pipeline
- **Maintainable**: Tests document expected behavior

---

### **Unit Tests (Core Layer)**

#### **Scope**

Test pure business logic in `core/` layer:
- Agent ReAct loop logic
- PlanGenerator decomposition
- Domain event creation
- Validation logic

**Key Characteristic**: Zero infrastructure dependencies (no database, no HTTP, no LLM calls)

#### **Example: Agent Core Logic Tests**

```python
# tests/unit/core/test_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from taskforce.core.domain.agent import Agent
from taskforce.core.domain.events import Thought, Action, Observation
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.tools import ToolProtocol

@pytest.fixture
def mock_state_manager():
    """Mock state manager for testing."""
    mock = AsyncMock(spec=StateManagerProtocol)
    mock.load_state.return_value = None
    mock.save_state.return_value = None
    return mock

@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing."""
    mock = AsyncMock(spec=LLMProviderProtocol)
    mock.complete.return_value = {
        "choices": [{"message": {"content": "Test thought"}}]
    }
    return mock

@pytest.fixture
def mock_tool():
    """Mock tool for testing."""
    tool = MagicMock(spec=ToolProtocol)
    tool.name = "test_tool"
    tool.execute = AsyncMock(return_value={"success": True, "output": "Done"})
    return tool

@pytest.mark.asyncio
async def test_agent_execute_simple_mission(
    mock_state_manager,
    mock_llm_provider,
    mock_tool
):
    """Test agent executes a simple mission successfully."""
    # Arrange
    agent = Agent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools={"test_tool": mock_tool}
    )
    mission = "Test mission"
    session_id = "test-session-123"
    
    # Act
    result = await agent.execute(mission, session_id)
    
    # Assert
    assert result.status == "completed"
    assert mock_state_manager.save_state.called
    assert mock_llm_provider.complete.called

@pytest.mark.asyncio
async def test_agent_handles_tool_failure(
    mock_state_manager,
    mock_llm_provider,
    mock_tool
):
    """Test agent handles tool execution failures gracefully."""
    # Arrange
    mock_tool.execute.return_value = {
        "success": False, 
        "error": "Tool failed"
    }
    agent = Agent(
        state_manager=mock_state_manager,
        llm_provider=mock_llm_provider,
        tools={"test_tool": mock_tool}
    )
    
    # Act
    result = await agent.execute("Test mission", "test-session")
    
    # Assert
    assert result.status in ["failed", "completed"]  # May retry or complete
    # Verify error was logged in observations
    assert any("error" in obs.lower() for obs in result.observations)

@pytest.mark.asyncio
async def test_agent_respects_max_iterations():
    """Test agent stops after max iterations to prevent infinite loops."""
    # Arrange
    mock_state = AsyncMock(spec=StateManagerProtocol)
    mock_llm = AsyncMock(spec=LLMProviderProtocol)
    
    # LLM never returns "complete" action
    mock_llm.complete.return_value = {
        "choices": [{"message": {"content": "Keep working"}}]
    }
    
    agent = Agent(
        state_manager=mock_state,
        llm_provider=mock_llm,
        tools={},
        max_iterations=5  # Force limit
    )
    
    # Act
    result = await agent.execute("Infinite mission", "test-session")
    
    # Assert
    assert result.iteration_count == 5
    assert result.status == "max_iterations_reached"
```

#### **Example: PlanGenerator Tests**

```python
# tests/unit/core/test_plan.py
import pytest
from unittest.mock import AsyncMock
from taskforce.core.domain.plan import PlanGenerator, TodoList, TodoItem, TaskStatus

@pytest.fixture
def mock_llm_provider():
    """Mock LLM that returns valid plan JSON."""
    mock = AsyncMock()
    mock.complete.return_value = {
        "choices": [{
            "message": {
                "content": """
                {
                    "items": [
                        {
                            "position": 0,
                            "description": "Step 1",
                            "acceptance_criteria": ["Done"],
                            "dependencies": []
                        },
                        {
                            "position": 1,
                            "description": "Step 2",
                            "acceptance_criteria": ["Completed"],
                            "dependencies": [0]
                        }
                    ]
                }
                """
            }
        }]
    }
    return mock

@pytest.mark.asyncio
async def test_plan_generator_creates_valid_plan(mock_llm_provider):
    """Test plan generator creates TodoList from mission."""
    # Arrange
    planner = PlanGenerator(llm_provider=mock_llm_provider)
    mission = "Create a web app"
    
    # Act
    plan = await planner.generate_plan(mission)
    
    # Assert
    assert isinstance(plan, TodoList)
    assert len(plan.items) == 2
    assert plan.items[0].status == TaskStatus.PENDING
    assert plan.items[1].dependencies == [0]

def test_plan_validation_detects_circular_dependencies():
    """Test plan validation catches circular dependencies."""
    # Arrange
    planner = PlanGenerator(llm_provider=None)
    
    # Create circular dependency: 0 -> 1 -> 2 -> 0
    plan = TodoList(
        todolist_id="test",
        session_id="test",
        mission="Test",
        items=[
            TodoItem(position=0, description="A", acceptance_criteria=[], dependencies=[2]),
            TodoItem(position=1, description="B", acceptance_criteria=[], dependencies=[0]),
            TodoItem(position=2, description="C", acceptance_criteria=[], dependencies=[1])
        ]
    )
    
    # Act & Assert
    with pytest.raises(ValueError, match="circular dependency"):
        planner.validate_dependencies(plan)

def test_plan_validation_accepts_valid_dag():
    """Test plan validation accepts valid DAG structure."""
    # Arrange
    planner = PlanGenerator(llm_provider=None)
    
    # Valid DAG: 0 <- 1, 0 <- 2, 1 <- 3
    plan = TodoList(
        todolist_id="test",
        session_id="test",
        mission="Test",
        items=[
            TodoItem(position=0, description="A", acceptance_criteria=[], dependencies=[]),
            TodoItem(position=1, description="B", acceptance_criteria=[], dependencies=[0]),
            TodoItem(position=2, description="C", acceptance_criteria=[], dependencies=[0]),
            TodoItem(position=3, description="D", acceptance_criteria=[], dependencies=[1])
        ]
    )
    
    # Act & Assert (should not raise)
    planner.validate_dependencies(plan)
```

#### **Running Unit Tests**

```powershell
# Run all unit tests
uv run pytest tests/unit/ -v

# Run with coverage
uv run pytest tests/unit/ --cov=taskforce.core --cov-report=html

# Run specific test file
uv run pytest tests/unit/core/test_agent.py -v

# Run tests matching pattern
uv run pytest tests/unit/ -k "test_agent" -v
```

**Coverage Target**: ≥80% for core layer

---

### **Integration Tests (Infrastructure Layer)**

#### **Scope**

Test infrastructure adapters with real dependencies:
- Database operations (actual PostgreSQL)
- LLM service (mocked HTTP, not real API)
- Tool execution (actual subprocess/filesystem)
- State persistence round-trips

**Key Characteristic**: Uses real infrastructure, but may mock external APIs

#### **Example: DbStateManager Integration Tests**

```python
# tests/integration/infrastructure/test_db_state.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from taskforce.infrastructure.persistence.db_state import DbStateManager
from taskforce.infrastructure.persistence.models import Base

@pytest_asyncio.fixture
async def test_db():
    """Create test database."""
    # Use in-memory SQLite for fast tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    
    # Create schema
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()

@pytest_asyncio.fixture
async def db_state_manager(test_db):
    """Create DbStateManager with test database."""
    return DbStateManager(engine=test_db)

@pytest.mark.asyncio
async def test_save_and_load_state(db_state_manager):
    """Test state persistence round-trip."""
    # Arrange
    session_id = "test-session-123"
    state_data = {
        "mission": "Test mission",
        "status": "in_progress",
        "answers": {"question1": "answer1"}
    }
    
    # Act - Save
    await db_state_manager.save_state(session_id, state_data)
    
    # Act - Load
    loaded_state = await db_state_manager.load_state(session_id)
    
    # Assert
    assert loaded_state is not None
    assert loaded_state["mission"] == "Test mission"
    assert loaded_state["answers"]["question1"] == "answer1"

@pytest.mark.asyncio
async def test_state_versioning(db_state_manager):
    """Test state version increments on each save."""
    # Arrange
    session_id = "test-session-version"
    
    # Act - Save multiple versions
    await db_state_manager.save_state(session_id, {"version": 1})
    await db_state_manager.save_state(session_id, {"version": 2})
    await db_state_manager.save_state(session_id, {"version": 3})
    
    # Assert - Latest version loaded
    loaded = await db_state_manager.load_state(session_id)
    assert loaded["version"] == 3
    
    # Assert - Can query version history
    history = await db_state_manager.get_state_history(session_id)
    assert len(history) == 3

@pytest.mark.asyncio
async def test_concurrent_state_updates_conflict_detection(db_state_manager):
    """Test optimistic locking detects concurrent modifications."""
    # Arrange
    session_id = "test-concurrent"
    await db_state_manager.save_state(session_id, {"value": 1})
    
    # Act - Simulate two instances updating same session
    # Instance 1 updates
    state1 = await db_state_manager.load_state(session_id)
    state1["value"] = 2
    await db_state_manager.save_state(session_id, state1)
    
    # Instance 2 tries to update with stale version
    state2 = {"value": 3}  # Stale version
    
    # Assert - Should detect conflict
    with pytest.raises(Exception, match="conflict|version"):
        await db_state_manager.save_state(
            session_id, 
            state2, 
            expected_version=1  # Stale version
        )
```

#### **Example: Tool Integration Tests**

```python
# tests/integration/infrastructure/test_python_tool.py
import pytest
from taskforce.infrastructure.tools.native.python_tool import PythonTool

@pytest.mark.asyncio
async def test_python_tool_executes_valid_code():
    """Test Python tool executes code successfully."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test")
    code = """
result = 2 + 2
print(f"Result: {result}")
    """
    
    # Act
    result = await tool.execute(code=code)
    
    # Assert
    assert result["success"] is True
    assert "Result: 4" in result["output"]

@pytest.mark.asyncio
async def test_python_tool_handles_syntax_errors():
    """Test Python tool catches syntax errors."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test")
    code = "print(unclosed string"  # Syntax error
    
    # Act
    result = await tool.execute(code=code)
    
    # Assert
    assert result["success"] is False
    assert "SyntaxError" in result["error"]

@pytest.mark.asyncio
async def test_python_tool_namespace_isolation():
    """Test Python tool runs each execution in isolated namespace."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test")
    
    # Act - First execution defines variable
    result1 = await tool.execute(code="x = 42")
    assert result1["success"] is True
    
    # Act - Second execution should not see 'x'
    result2 = await tool.execute(code="print(x)")
    
    # Assert
    assert result2["success"] is False
    assert "NameError" in result2["error"]

@pytest.mark.asyncio
async def test_python_tool_respects_timeout():
    """Test Python tool times out infinite loops."""
    # Arrange
    tool = PythonTool(work_dir="/tmp/test", timeout=2)  # 2 second timeout
    code = "while True: pass"  # Infinite loop
    
    # Act
    result = await tool.execute(code=code)
    
    # Assert
    assert result["success"] is False
    assert "timeout" in result["error"].lower()
```

#### **Running Integration Tests**

```powershell
# Run all integration tests
uv run pytest tests/integration/ -v

# Run with test database
uv run pytest tests/integration/ -v --db-url=postgresql://test:test@localhost/taskforce_test

# Run specific integration test
uv run pytest tests/integration/infrastructure/test_db_state.py -v

# Run with real PostgreSQL (requires Docker)
docker-compose -f docker-compose.test.yml up -d postgres-test
uv run pytest tests/integration/ --db-url=postgresql://taskforce:test@localhost:5433/taskforce_test
docker-compose -f docker-compose.test.yml down
```

**Coverage Target**: ≥70% for infrastructure layer

---

### **API Tests (FastAPI Endpoints)**

#### **Scope**

Test HTTP API endpoints with real FastAPI test client:
- Request/response validation
- Authentication
- Error handling
- Streaming endpoints

#### **Example: FastAPI Endpoint Tests**

```python
# tests/api/test_execution_routes.py
import pytest
from httpx import AsyncClient
from taskforce.api.server import app
from unittest.mock import AsyncMock, patch

@pytest.fixture
def api_key():
    """Test API key."""
    return "test-api-key-123"

@pytest.fixture
def auth_headers(api_key):
    """Authorization headers."""
    return {"Authorization": f"Bearer {api_key}"}

@pytest.mark.asyncio
async def test_execute_mission_endpoint(auth_headers):
    """Test POST /api/v1/execute endpoint."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {
            "mission": "Create hello world",
            "profile": "dev"
        }
        
        # Act
        with patch.dict("os.environ", {"TASKFORCE_API_KEY": "test-api-key-123"}):
            response = await client.post(
                "/api/v1/execute",
                json=payload,
                headers=auth_headers
            )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] in ["completed", "in_progress"]

@pytest.mark.asyncio
async def test_execute_mission_requires_authentication():
    """Test endpoint rejects requests without API key."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {"mission": "Test", "profile": "dev"}
        
        # Act
        with patch.dict("os.environ", {"TASKFORCE_API_KEY": "secret-key"}):
            response = await client.post("/api/v1/execute", json=payload)
        
        # Assert
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_execute_mission_validates_input():
    """Test endpoint validates request payload."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        invalid_payload = {
            "mission": "",  # Empty mission
            "profile": "invalid-profile"  # Invalid profile
        }
        
        # Act
        response = await client.post(
            "/api/v1/execute",
            json=invalid_payload,
            headers={"Authorization": "Bearer test-key"}
        )
        
        # Assert
        assert response.status_code == 422  # Validation error

@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Test GET /health endpoint."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        
        # Act
        response = await client.get("/health")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

@pytest.mark.asyncio
async def test_streaming_execution_endpoint(auth_headers):
    """Test POST /api/v1/execute/stream with SSE."""
    # Arrange
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {"mission": "Simple task", "profile": "dev"}
        
        # Act
        with patch.dict("os.environ", {"TASKFORCE_API_KEY": "test-api-key-123"}):
            async with client.stream(
                "POST",
                "/api/v1/execute/stream",
                json=payload,
                headers=auth_headers
            ) as response:
                # Assert
                assert response.status_code == 200
                assert "text/event-stream" in response.headers["content-type"]
                
                # Read events
                events = []
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        events.append(line[6:])
                
                # Verify event types
                assert len(events) > 0
                # Should have thought, action, observation, complete events
```

#### **Running API Tests**

```powershell
# Run API tests
uv run pytest tests/api/ -v

# Run with coverage
uv run pytest tests/api/ --cov=taskforce.api --cov-report=html
```

**Coverage Target**: ≥80% for API layer

---

### **End-to-End (E2E) Tests**

#### **Scope**

Test complete user workflows with all components:
- CLI command execution
- Full ReAct loop with real tools
- Database persistence verification
- Multi-step missions

#### **Example: E2E CLI Tests**

```python
# tests/e2e/test_cli_workflows.py
import pytest
import subprocess
import json
from pathlib import Path

@pytest.fixture
def temp_work_dir(tmp_path):
    """Create temporary work directory."""
    work_dir = tmp_path / "taskforce_test"
    work_dir.mkdir()
    return work_dir

def test_cli_run_simple_mission(temp_work_dir):
    """Test 'taskforce run mission' command end-to-end."""
    # Arrange
    mission = "Create a Python file hello.py with a hello function"
    
    # Act
    result = subprocess.run(
        [
            "taskforce", "run", "mission", mission,
            "--profile", "dev",
            "--work-dir", str(temp_work_dir)
        ],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    # Assert
    assert result.returncode == 0
    assert "completed" in result.stdout.lower()
    
    # Verify file was created
    hello_file = temp_work_dir / "hello.py"
    assert hello_file.exists()
    
    # Verify file content
    content = hello_file.read_text()
    assert "def hello" in content

def test_cli_session_persistence(temp_work_dir):
    """Test session state persists across commands."""
    # Act - Start mission
    result1 = subprocess.run(
        [
            "taskforce", "run", "mission", "Start work",
            "--profile", "dev",
            "--work-dir", str(temp_work_dir)
        ],
        capture_output=True,
        text=True
    )
    
    # Extract session ID from output
    output = result1.stdout
    session_id = None
    for line in output.split("\n"):
        if "session_id" in line.lower():
            # Parse session ID from output
            session_id = line.split(":")[-1].strip()
    
    assert session_id is not None
    
    # Act - List sessions
    result2 = subprocess.run(
        ["taskforce", "sessions", "list", "--work-dir", str(temp_work_dir)],
        capture_output=True,
        text=True
    )
    
    # Assert - Session appears in list
    assert session_id in result2.stdout
    
    # Act - Get session details
    result3 = subprocess.run(
        ["taskforce", "sessions", "show", session_id, "--work-dir", str(temp_work_dir)],
        capture_output=True,
        text=True
    )
    
    # Assert - Details include mission
    assert "Start work" in result3.stdout

@pytest.mark.slow
def test_cli_complex_mission_with_tools(temp_work_dir):
    """Test complex mission requiring multiple tools."""
    # Arrange
    mission = """
    1. Create a Python script that generates 10 random numbers
    2. Save the numbers to a file numbers.txt
    3. Read the file and calculate the average
    """
    
    # Act
    result = subprocess.run(
        [
            "taskforce", "run", "mission", mission,
            "--profile", "dev",
            "--work-dir", str(temp_work_dir)
        ],
        capture_output=True,
        text=True,
        timeout=120
    )
    
    # Assert
    assert result.returncode == 0
    
    # Verify artifacts
    assert (temp_work_dir / "numbers.txt").exists()
    assert "average" in result.stdout.lower()
```

#### **Example: E2E API Tests**

```python
# tests/e2e/test_api_workflows.py
import pytest
import httpx
import time

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_mission_execution_workflow():
    """Test full mission execution via API."""
    # Arrange
    base_url = "http://localhost:8000"
    api_key = "test-api-key"
    headers = {"Authorization": f"Bearer {api_key}"}
    
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        # Act - Submit mission
        response = await client.post(
            "/api/v1/execute",
            json={
                "mission": "Create a hello world Python script",
                "profile": "dev"
            },
            headers=headers
        )
        
        assert response.status_code == 200
        data = response.json()
        session_id = data["session_id"]
        
        # Poll for completion
        max_attempts = 30
        for _ in range(max_attempts):
            response = await client.get(
                f"/api/v1/sessions/{session_id}",
                headers=headers
            )
            
            session_data = response.json()
            if session_data["status"] == "completed":
                break
            
            time.sleep(2)
        
        # Assert
        assert session_data["status"] == "completed"
        assert "mission" in session_data
```

#### **Running E2E Tests**

```powershell
# Run E2E tests (requires full environment)
docker-compose up -d
uv run pytest tests/e2e/ -v -m e2e
docker-compose down

# Run with real services
uv run pytest tests/e2e/ -v --base-url=http://localhost:8000

# Skip slow tests
uv run pytest tests/e2e/ -v -m "not slow"
```

**Coverage Target**: Key user workflows covered (not code coverage metric)

---

### **Performance/Load Tests**

#### **Scope**

Test system performance under load:
- Concurrent request handling
- Database connection pool exhaustion
- Memory leaks over time
- Response time degradation

#### **Example: Locust Load Tests**

```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between
import random

class TaskforceUser(HttpUser):
    """Simulated user for load testing."""
    wait_time = between(1, 5)
    
    def on_start(self):
        """Setup: authenticate."""
        self.headers = {"Authorization": "Bearer test-api-key"}
    
    @task(3)
    def health_check(self):
        """Lightweight health check (most common)."""
        self.client.get("/health")
    
    @task(2)
    def list_sessions(self):
        """List sessions."""
        self.client.get("/api/v1/sessions", headers=self.headers)
    
    @task(1)
    def execute_mission(self):
        """Execute a simple mission (slowest)."""
        missions = [
            "Create a hello world script",
            "Calculate 2+2",
            "List files in current directory"
        ]
        
        response = self.client.post(
            "/api/v1/execute",
            json={
                "mission": random.choice(missions),
                "profile": "dev"
            },
            headers=self.headers,
            timeout=60
        )
        
        if response.status_code == 200:
            session_id = response.json()["session_id"]
            # Optionally poll for completion
            self.client.get(
                f"/api/v1/sessions/{session_id}",
                headers=self.headers
            )
```

#### **Running Load Tests**

```powershell
# Start services
docker-compose up -d

# Run load test (10 users, spawn 1/sec)
locust -f tests/performance/locustfile.py --host=http://localhost:8000 --users 10 --spawn-rate 1

# Run headless (no web UI)
locust -f tests/performance/locustfile.py --host=http://localhost:8000 --users 50 --spawn-rate 5 --run-time 5m --headless

# View results at http://localhost:8089
```

**Performance Targets**:
- **Health endpoint**: <100ms p95, 1000 RPS
- **Execute endpoint**: <10s p95, 10 concurrent
- **No memory leaks**: Stable memory over 1 hour test

---

### **Test Data Management**

#### **Fixtures and Factories**

```python
# tests/conftest.py
import pytest
from faker import Faker

fake = Faker()

@pytest.fixture
def sample_mission():
    """Generate sample mission text."""
    return f"Create a script that {fake.sentence()}"

@pytest.fixture
def sample_todolist():
    """Generate sample TodoList."""
    from taskforce.core.domain.plan import TodoList, TodoItem, TaskStatus
    
    return TodoList(
        todolist_id=fake.uuid4(),
        session_id=fake.uuid4(),
        mission="Test mission",
        items=[
            TodoItem(
                position=0,
                description=f"Step 1: {fake.sentence()}",
                acceptance_criteria=[fake.sentence()],
                dependencies=[],
                status=TaskStatus.PENDING
            ),
            TodoItem(
                position=1,
                description=f"Step 2: {fake.sentence()}",
                acceptance_criteria=[fake.sentence()],
                dependencies=[0],
                status=TaskStatus.PENDING
            )
        ]
    )

@pytest.fixture
def sample_session_state():
    """Generate sample session state."""
    return {
        "session_id": fake.uuid4(),
        "mission": fake.sentence(),
        "status": "in_progress",
        "answers": {},
        "todolist_id": fake.uuid4(),
        "current_step": 0
    }
```

---

### **Continuous Integration (CI) Testing**

#### **GitHub Actions Test Workflow**

```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      
      - name: Run unit tests
        run: uv run pytest tests/unit/ -v --cov=taskforce.core --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: taskforce_test
          POSTGRES_USER: taskforce
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
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
      
      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://taskforce:test@localhost:5432/taskforce_test
        run: uv run pytest tests/integration/ -v

  api-tests:
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
      
      - name: Run API tests
        run: uv run pytest tests/api/ -v

  lint:
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
      
      - name: Run linters
        run: |
          uv run ruff check .
          uv run black --check .
          uv run mypy taskforce/
```

---

### **Test Organization**

```
tests/
├── unit/                          # Unit tests (fast, isolated)
│   ├── core/
│   │   ├── test_agent.py
│   │   ├── test_plan.py
│   │   └── test_events.py
│   └── application/
│       ├── test_factory.py
│       └── test_profiles.py
│
├── integration/                   # Integration tests (real dependencies)
│   ├── infrastructure/
│   │   ├── test_db_state.py
│   │   ├── test_file_state.py
│   │   ├── test_llm_service.py
│   │   └── tools/
│   │       ├── test_python_tool.py
│   │       ├── test_file_tools.py
│   │       └── test_git_tools.py
│   └── application/
│       └── test_executor.py
│
├── api/                           # API tests (FastAPI)
│   ├── test_execution_routes.py
│   ├── test_session_routes.py
│   └── test_health.py
│
├── e2e/                           # End-to-end tests (full workflows)
│   ├── test_cli_workflows.py
│   └── test_api_workflows.py
│
├── performance/                   # Load tests
│   ├── locustfile.py
│   └── test_stress.py
│
├── conftest.py                    # Shared fixtures
└── pytest.ini                     # Pytest configuration
```

#### **pytest.ini Configuration**

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (real dependencies)
    e2e: End-to-end tests (full workflows)
    slow: Slow tests (skip by default)
    performance: Performance/load tests

# Coverage
addopts =
    --strict-markers
    --verbose
    --color=yes
    --tb=short

# Asyncio
asyncio_mode = auto

# Logging
log_cli = true
log_cli_level = INFO
```

---

### **Test Execution Strategy**

**Development (Pre-commit)**:
```powershell
# Fast feedback (<30 seconds)
uv run pytest tests/unit/ -v
```

**Pull Request (CI)**:
```powershell
# Comprehensive (<5 minutes)
uv run pytest tests/unit/ tests/integration/ tests/api/ -v --cov
```

**Pre-Release (Staging)**:
```powershell
# Full suite including E2E (<30 minutes)
uv run pytest tests/ -v -m "not performance"
```

**Production Readiness**:
```powershell
# Load testing (hours)
locust -f tests/performance/locustfile.py --users 100 --spawn-rate 10 --run-time 2h
```

---

### **Rationale:**

**Testing Strategy Decisions:**

1. **Test Pyramid Structure**: 70% unit, 20% integration, 10% E2E. Rationale: Fast feedback from unit tests, realistic validation from integration tests, confidence from E2E tests. Trade-off: E2E tests are slow and fragile vs. confidence in full system.

2. **Real Dependencies in Integration Tests**: Use actual PostgreSQL, not mocks. Rationale: Mocks can hide integration issues (SQL syntax, connection pooling). Trade-off: Slower tests vs. realistic validation.

3. **Mock LLM Calls**: Don't call real OpenAI API in tests. Rationale: Expensive, slow, non-deterministic, rate-limited. Trade-off: May miss API changes vs. test speed and reliability.

4. **Async Tests Throughout**: All tests use `pytest-asyncio`. Rationale: Application is async, tests should match. Trade-off: Slightly more complex test setup vs. realistic testing.

5. **Fixtures Over Hardcoded Data**: Use pytest fixtures and Faker. Rationale: Reusable, randomized data catches edge cases. Trade-off: Less predictable vs. better coverage.

**Key Assumptions:**
- Unit test coverage >80% sufficient (validated: industry standard)
- Integration tests with SQLite adequate for most DB logic (needs validation: may miss PostgreSQL-specific issues)
- Mocked LLM responses representative (needs validation: actual API may behave differently)

---
