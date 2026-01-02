# Section 4: Data Models (REVISED - Python)

Based on the PRD requirements and ReAct agent architecture, here are the core data models for Taskforce:

---

### **Session**

**Purpose:** Represents a single agent execution session with a specific mission. Sessions track the overall state of mission execution and serve as the primary organizational unit for agent work.

**Key Attributes:**
- `session_id`: str (UUID) - Unique identifier for the session
- `user_id`: Optional[str] - User who initiated the session (for multi-tenant scenarios)
- `mission`: str - The mission description provided by the user
- `status`: str - Current status (pending, in_progress, completed, failed)
- `created_at`: datetime - When the session was created
- `updated_at`: datetime - Last modification timestamp
- `profile`: str - Configuration profile used (dev, staging, prod)

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

class SessionStatus(Enum):
    """Session execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Session:
    """Agent execution session."""
    session_id: str
    mission: str
    status: SessionStatus
    profile: str = "dev"
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- One-to-many with State (session has multiple state snapshots)
- One-to-many with TodoList (session has multiple plans, typically one active)
- One-to-many with ExecutionHistory (session has multiple execution steps)

---

### **State**

**Purpose:** Represents a versioned snapshot of session state at a point in time. Enables state recovery, auditing, and supports optimistic locking for concurrent access.

**Key Attributes:**
- `state_id`: int (auto-increment) - Internal database identifier
- `session_id`: str (FK) - Associated session
- `state_json`: Dict[str, Any] - Complete state data as flexible JSONB
- `version`: int - State version number for optimistic locking
- `timestamp`: datetime - When this state snapshot was created

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

@dataclass
class State:
    """Versioned session state snapshot."""
    session_id: str
    state_json: Dict[str, Any]
    version: int = 1
    state_id: Optional[int] = None  # Assigned by database
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Common state_json structure (not enforced, flexible JSONB):
    # {
    #     "mission": str,
    #     "status": str,
    #     "answers": dict,
    #     "pending_question": Optional[str],
    #     "todolist_id": Optional[str],
    #     "current_step": Optional[int],
    #     ... extensible
    # }
```

**Relationships:**
- Many-to-one with Session (multiple states belong to one session)

---

### **TodoList**

**Purpose:** Represents a generated plan for accomplishing a mission. Contains structured task decomposition with dependencies and acceptance criteria.

**Key Attributes:**
- `todolist_id`: str (UUID) - Unique identifier for the plan
- `session_id`: str (FK) - Associated session
- `mission`: str - Mission this plan addresses
- `items`: List[TodoItem] - List of tasks (stored as JSONB in database)
- `status`: str - Plan status (active, completed, abandoned)
- `created_at`: datetime - When plan was generated
- `updated_at`: datetime - Last modification timestamp

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List
from enum import Enum

class PlanStatus(Enum):
    """TodoList plan status."""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

@dataclass
class TodoList:
    """Mission execution plan."""
    todolist_id: str
    session_id: str
    mission: str
    items: List['TodoItem']
    status: PlanStatus = PlanStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- Many-to-one with Session (plan belongs to one session)
- One-to-many with TodoItem (conceptually, stored as JSONB array)

---

### **TodoItem**

**Purpose:** Individual task within a TodoList. Represents a single executable step with clear acceptance criteria and dependency tracking.

**Key Attributes:**
- `position`: int - Ordinal position in the plan (0-indexed)
- `description`: str - Human-readable task description
- `acceptance_criteria`: List[str] - Criteria for task completion
- `dependencies`: List[int] - Positions of tasks this depends on
- `status`: TaskStatus - Task execution status
- `chosen_tool`: Optional[str] - Tool selected for execution
- `execution_result`: Optional[Dict] - Tool execution result details

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class ExecutionResult:
    """Result of tool execution."""
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None

@dataclass
class TodoItem:
    """Single task in a TodoList."""
    position: int
    description: str
    acceptance_criteria: List[str]
    dependencies: List[int] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    chosen_tool: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
```

**Relationships:**
- Many-to-one with TodoList (stored as part of plan JSONB)
- Self-referential dependencies (one TodoItem depends on others via position indices)

---

### **ExecutionHistory**

**Purpose:** Detailed step-by-step record of ReAct loop execution. Captures thought (reasoning), action (decision), and observation (result) for each iteration.

**Key Attributes:**
- `history_id`: int (auto-increment) - Internal identifier
- `session_id`: str (FK) - Associated session
- `step_id`: int - Step number in execution sequence
- `thought`: Optional[str] - LLM-generated reasoning/rationale
- `action`: Optional[str] - Action decision (tool name, ask_user, complete)
- `observation`: Optional[str] - Result of action execution
- `timestamp`: datetime - When this step occurred

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class ExecutionHistory:
    """ReAct loop execution step record."""
    session_id: str
    step_id: int
    thought: Optional[str] = None
    action: Optional[str] = None
    observation: Optional[str] = None
    history_id: Optional[int] = None  # Assigned by database
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- Many-to-one with Session (execution steps belong to one session)

---

### **Memory**

**Purpose:** Cross-session learned lessons extracted from successful task executions. Enables agent to learn from experience and improve over time.

**Key Attributes:**
- `memory_id`: str (UUID) - Unique identifier
- `context`: str - Description of situation type (2-3 sentences)
- `what_failed`: Optional[str] - What approach didn't work
- `what_worked`: str - What approach succeeded
- `lesson`: str - Generalizable takeaway for future tasks
- `tool_name`: Optional[str] - Primary tool involved (if relevant)
- `confidence`: float - Confidence score (0.0-1.0)
- `created_at`: datetime - When memory was extracted

**Python Dataclass:**
```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Memory:
    """Cross-session learned lesson."""
    memory_id: str
    context: str
    what_worked: str
    lesson: str
    confidence: float  # 0.0 to 1.0
    what_failed: Optional[str] = None
    tool_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
```

**Relationships:**
- No direct relationships (cross-session knowledge base)
- Queried by tool_name or context similarity for retrieval

---

### **Domain Events (ReAct Loop)**

**Purpose:** Immutable domain events representing key moments in ReAct execution. Used for progress tracking and streaming updates.

**Python Dataclasses:**
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

@dataclass(frozen=True)
class Thought:
    """LLM-generated reasoning event."""
    session_id: str
    step_id: int
    content: str
    timestamp: datetime

@dataclass(frozen=True)
class Action:
    """Action decision event."""
    session_id: str
    step_id: int
    action_type: str  # tool_call, ask_user, complete, replan
    action_data: dict
    timestamp: datetime

@dataclass(frozen=True)
class Observation:
    """Action result event."""
    session_id: str
    step_id: int
    result: Any
    success: bool
    error: Optional[str] = None
    timestamp: datetime
```

---

### **Rationale:**

**Design Decisions:**

1. **Dataclasses over Plain Dicts**: Chose dataclasses for type safety and IDE support. Rationale: Modern Python (3.11) makes dataclasses zero-overhead. Better than plain dicts for catching errors early.

2. **Enums for Status Fields**: Used Enum classes for status values rather than strings. Rationale: Type-safe, prevents typos, enables exhaustive checking in match statements.

3. **JSONB for Flexibility**: State and TodoList stored as JSONB in PostgreSQL, deserialized to dataclasses. Rationale: Schema evolution without migrations. Preserves Agent V2 JSON format compatibility.

4. **Immutable Domain Events**: Domain events (Thought, Action, Observation) are frozen dataclasses. Rationale: Immutability prevents accidental modification of execution history. Enables event replay for debugging.

5. **Optional Fields with Defaults**: Used Optional + default None for fields not always present. Rationale: Explicit about what's required vs. optional. Better than relying on database NULL semantics.

6. **Separate ExecutionResult Dataclass**: Extracted execution result into own dataclass rather than plain dict. Rationale: Reusable across different tool implementations. Type-safe result handling.

**Trade-offs:**

- **Dataclasses vs Pydantic Models**: Chose dataclasses over Pydantic. Trade-off: Less validation power (Pydantic better), but lighter weight and standard library. Can add Pydantic for API layer validation if needed.

- **JSONB Flexibility vs Schema Enforcement**: JSONB allows schema changes without migrations but loses database-level validation. Trade-off: Flexibility vs. safety. Mitigated by dataclass validation in application code.

**Key Assumptions:**

- Python dataclasses sufficient for domain modeling (validated: they are)
- JSONB performance acceptable for state/plan sizes (typical: <1MB) (needs validation in load testing)
- Enum overhead acceptable (validated: zero runtime cost)

---

**Advanced Elicitation Options**

Data models now using Python dataclasses. Please review:

**0.** Tree of Thoughts - Explore alternative modeling approaches (Pydantic, attrs, plain classes)
**1.** **Proceed to next section**
**2.** Critique and Refine - Challenge data model design choices
**3.** Identify Potential Risks - JSONB flexibility risks, versioning concerns
**4.** Assess Alignment with Goals - Verify models support all PRD requirements
**5.** Stakeholder Roundtable - Dev, DBA perspectives on data models
**6.** Red Team vs Blue Team - Attack dataclass choice, defend simplicity
**7.** Hindsight Reflection - 6 months in: were these the right modeling choices?
**8.** Meta-Prompting - Generate questions about specific model attributes

**Select 0-9 or just type your question/feedback:**


🏗️ **Proceeding to Components...**

---
