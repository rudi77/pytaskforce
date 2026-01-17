# Long-Running Multi-Agent Orchestration Plan

**Version:** 1.0
**Datum:** 2026-01-13
**Basierend auf:** Cursor's "Scaling long-running autonomous coding" Erkenntnisse

---

## 🎯 Vision

Ermögliche **hunderte concurrent Agents** an einem einzelnen Projekt über **Wochen** zu arbeiten, mit klarer Rollen-Trennung und robuster Koordination.

**Inspiration**: Cursor's Browser-Projekt (1M LoC, 1 Woche, 1000 Files, hunderte Workers)

---

## 📊 Aktuelle Situation vs. Ziel

### ✅ Was wir haben (AgentTool)

- Sub-Agent Spawning (coding, rag, wiki, custom)
- Session-Isolation
- Parallele Ausführung (`supports_parallelism=True`)
- Custom Agents via `configs/custom/`

### ❌ Was wir brauchen

- **Rollen-Trennung**: Planner vs. Worker vs. Judge
- **Task Queue**: Shared State für Task-Management
- **Long-Running**: Wochen statt Minuten
- **Optimistic Concurrency**: Statt Locks
- **Cycle Management**: Iteration-based Execution
- **Drift Prevention**: Fresh Starts & Checkpointing

---

## 🏗️ Architektur-Design

### Rollen-Hierarchie

```
Master Orchestrator (Outer Loop)
    ├─> Planner Agents (Task Creation)
    │   └─> Sub-Planners (Recursive, für Sub-Bereiche)
    │
    ├─> Worker Agents (Task Execution)
    │   ├─> Worker 1 (Task A)
    │   ├─> Worker 2 (Task B)
    │   └─> Worker N (Task N)
    │
    └─> Judge Agent (Progress Evaluation)
        └─> Decision: Continue / Fresh Start / Complete
```

### Task Flow

```
1. Master spawns Planners → Explore codebase → Create Tasks → Push to Queue
2. Master spawns Workers → Pull from Queue → Execute → Push Changes → Mark Complete
3. Master spawns Judge → Evaluate Progress → Decide next cycle
4. Repeat (Weeks)
```

---

## 📦 Komponenten-Design

### 1. Task Queue System

**Datei**: `src/taskforce/infrastructure/task_queue/`

#### Task Model

```python
@dataclass
class Task:
    """Represents a single work item."""

    id: str  # UUID
    type: TaskType  # CODING, TESTING, DOCUMENTATION, REFACTORING
    title: str
    description: str
    priority: int  # 1-10

    # Status
    status: TaskStatus  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    assigned_to: Optional[str]  # Worker session ID

    # Metadata
    created_by: str  # Planner session ID
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    # Context
    files: List[str]  # Relevant files
    dependencies: List[str]  # Other task IDs

    # Versioning (Optimistic Concurrency)
    version: int  # Increment on every update


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskType(str, Enum):
    CODING = "coding"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    REFACTORING = "refactoring"
    ARCHITECTURE = "architecture"
```

#### Task Queue (mit Optimistic Concurrency)

```python
class TaskQueue:
    """
    Thread-safe task queue with optimistic concurrency control.

    No locks! Uses version-based conflict detection instead.
    """

    def __init__(self, state_manager: StateManagerProtocol):
        self._state_manager = state_manager
        self._queue_key = "global_task_queue"

    async def add_task(self, task: Task) -> bool:
        """Add task to queue (idempotent)."""
        while True:
            # Read current state
            state = await self._state_manager.load_state(self._queue_key)
            tasks = state.get("tasks", {})
            version = state.get("version", 0)

            # Add task
            tasks[task.id] = asdict(task)

            # Try to save with version check
            try:
                await self._state_manager.save_state_with_version(
                    session_id=self._queue_key,
                    state_data={"tasks": tasks, "version": version + 1},
                    expected_version=version,
                )
                return True
            except VersionConflictError:
                # Retry if someone else updated simultaneously
                await asyncio.sleep(random.uniform(0.1, 0.5))
                continue

    async def claim_task(self, worker_id: str, task_types: List[TaskType]) -> Optional[Task]:
        """
        Claim next available task (optimistic concurrency).

        Returns None if no tasks available or all attempts failed.
        """
        MAX_RETRIES = 5

        for attempt in range(MAX_RETRIES):
            # Read current state
            state = await self._state_manager.load_state(self._queue_key)
            tasks = state.get("tasks", {})
            version = state.get("version", 0)

            # Find pending task matching types
            available_tasks = [
                Task(**t) for t in tasks.values()
                if t["status"] == TaskStatus.PENDING
                and TaskType(t["type"]) in task_types
            ]

            if not available_tasks:
                return None  # No tasks available

            # Sort by priority (higher first)
            available_tasks.sort(key=lambda t: t.priority, reverse=True)
            task = available_tasks[0]

            # Update task status
            task.status = TaskStatus.IN_PROGRESS
            task.assigned_to = worker_id
            task.started_at = datetime.now()
            task.version += 1

            tasks[task.id] = asdict(task)

            # Try to save with version check
            try:
                await self._state_manager.save_state_with_version(
                    session_id=self._queue_key,
                    state_data={"tasks": tasks, "version": version + 1},
                    expected_version=version,
                )
                return task
            except VersionConflictError:
                # Another worker claimed task, retry
                await asyncio.sleep(random.uniform(0.1, 0.5))
                continue

        return None  # All retries exhausted

    async def complete_task(self, task_id: str, result: dict) -> bool:
        """Mark task as completed."""
        # Similar optimistic update pattern
        pass

    async def fail_task(self, task_id: str, error: str) -> bool:
        """Mark task as failed."""
        pass

    async def get_stats(self) -> dict:
        """Get queue statistics."""
        state = await self._state_manager.load_state(self._queue_key)
        tasks = state.get("tasks", {})

        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks.values() if t["status"] == "pending"),
            "in_progress": sum(1 for t in tasks.values() if t["status"] == "in_progress"),
            "completed": sum(1 for t in tasks.values() if t["status"] == "completed"),
            "failed": sum(1 for t in tasks.values() if t["status"] == "failed"),
        }
```

---

### 2. Agent-Rollen

#### Planner Agent

**Datei**: `configs/roles/planner.yaml`

```yaml
agent:
  type: custom
  planning_strategy: plan_and_react
  max_steps: 100  # Longer for exploration

system_prompt: |
  You are a PLANNER agent in a multi-agent coding system.

  Your ONLY job is to:
  1. Explore the codebase thoroughly
  2. Understand the mission goal
  3. Break it down into concrete, actionable tasks
  4. Create tasks in the task queue
  5. Spawn sub-planners for complex areas (optional)

  DO NOT implement anything yourself!
  DO NOT worry about execution details!

  Focus on:
  - High-level architecture
  - Task decomposition
  - Dependency identification
  - Priority assignment

  Create tasks that are:
  - Self-contained (can be done by one worker)
  - Specific (clear acceptance criteria)
  - Prioritized (1-10, higher = more important)
  - Well-described (includes context & files)

  Use the create_task tool to add tasks to the queue.
  Use the spawn_sub_planner tool for complex sub-areas.

tool_allowlist:
  - file_read
  - web_search
  - create_task  # NEW: Custom tool for task creation
  - spawn_sub_planner  # NEW: Spawn sub-planner
  - list_tasks  # See current queue state
```

#### Worker Agent

**Datei**: `configs/roles/worker.yaml`

```yaml
agent:
  type: custom
  planning_strategy: native_react
  max_steps: 200  # Can take longer to implement

system_prompt: |
  You are a WORKER agent in a multi-agent coding system.

  Your ONLY job is to:
  1. Claim a task from the queue
  2. Implement it completely and correctly
  3. Run tests to verify
  4. Push changes when done
  5. Mark task as completed

  DO NOT coordinate with other workers!
  DO NOT worry about the big picture!
  DO NOT create new tasks!

  Focus ONLY on:
  - Completing your assigned task
  - Writing high-quality code
  - Ensuring tests pass
  - Handling conflicts (rebase if needed)

  Work until the task is DONE, then exit.
  If you encounter a blocker, mark task as blocked and explain why.

tool_allowlist:
  - file_read
  - file_write
  - python
  - shell_tool
  - git_tool
  - claim_task  # NEW: Get next task from queue
  - complete_task  # NEW: Mark task done
  - fail_task  # NEW: Mark task failed
```

#### Judge Agent

**Datei**: `configs/roles/judge.yaml`

```yaml
agent:
  type: custom
  planning_strategy: plan_and_execute
  max_steps: 50

system_prompt: |
  You are a JUDGE agent in a multi-agent coding system.

  Your job is to evaluate progress at the end of each cycle:

  1. Review completed tasks
  2. Check code quality (tests, coverage, architecture)
  3. Assess overall progress toward mission goal
  4. Detect drift or tunnel vision
  5. Decide: CONTINUE, FRESH_START, or COMPLETE

  Decision criteria:
  - CONTINUE: Good progress, tasks aligned with goal
  - FRESH_START: Drift detected, agents stuck, quality issues
  - COMPLETE: Mission goal achieved, ready for review

  Use the evaluate_progress tool to analyze the codebase.

tool_allowlist:
  - file_read
  - python
  - shell_tool  # Run tests
  - git_tool  # Review commits
  - evaluate_progress  # NEW: Analysis tool
```

---

### 3. Master Orchestrator

**Datei**: `src/taskforce/core/domain/master_orchestrator.py`

```python
class MasterOrchestrator:
    """
    Long-running master orchestrator for multi-agent projects.

    Manages cycles of planner → worker → judge loops.
    """

    def __init__(
        self,
        agent_factory: AgentFactory,
        task_queue: TaskQueue,
        config: dict,
    ):
        self.factory = agent_factory
        self.task_queue = task_queue
        self.config = config

        self.max_cycles = config.get("max_cycles", 100)
        self.max_concurrent_workers = config.get("max_concurrent_workers", 20)
        self.planner_count = config.get("planner_count", 3)

        self.logger = structlog.get_logger().bind(component="master_orchestrator")

    async def execute(self, mission: str, project_dir: str) -> dict:
        """
        Execute long-running multi-agent mission.

        Runs for potentially weeks, managing hundreds of agents.
        """
        self.logger.info(
            "master_orchestrator_started",
            mission=mission,
            project_dir=project_dir,
            max_cycles=self.max_cycles,
        )

        for cycle in range(self.max_cycles):
            self.logger.info("cycle_start", cycle=cycle)

            # Phase 1: Planning
            await self._run_planners(mission, project_dir, cycle)

            # Phase 2: Execution (concurrent workers)
            await self._run_workers(project_dir, cycle)

            # Phase 3: Evaluation
            decision = await self._run_judge(mission, project_dir, cycle)

            if decision == "COMPLETE":
                self.logger.info("mission_complete", cycle=cycle)
                break
            elif decision == "FRESH_START":
                self.logger.warning("fresh_start_triggered", cycle=cycle)
                await self._fresh_start(project_dir)

            # Brief pause between cycles
            await asyncio.sleep(5)

        return {"cycles": cycle, "status": "completed"}

    async def _run_planners(self, mission: str, project_dir: str, cycle: int):
        """Spawn planner agents to create tasks."""
        self.logger.info("planning_phase", planners=self.planner_count)

        planner_tasks = []
        for i in range(self.planner_count):
            planner_mission = f"""
            Cycle {cycle}: Plan tasks for mission: {mission}

            Project directory: {project_dir}

            Explore the codebase, understand current state, and create tasks
            for what needs to be done next.
            """

            # Spawn planner agent
            planner = await self.factory.create_agent(
                profile="planner",
                work_dir=project_dir,
            )

            task = asyncio.create_task(
                planner.execute(
                    mission=planner_mission,
                    session_id=f"cycle-{cycle}-planner-{i}",
                )
            )
            planner_tasks.append(task)

        # Wait for all planners to finish
        results = await asyncio.gather(*planner_tasks)

        self.logger.info(
            "planning_phase_complete",
            planners_completed=len(results),
            queue_stats=await self.task_queue.get_stats(),
        )

    async def _run_workers(self, project_dir: str, cycle: int):
        """Spawn worker agents to execute tasks."""
        self.logger.info(
            "execution_phase",
            max_workers=self.max_concurrent_workers,
        )

        # Spawn workers concurrently
        worker_tasks = []
        for i in range(self.max_concurrent_workers):
            worker = await self.factory.create_agent(
                profile="worker",
                work_dir=project_dir,
            )

            task = asyncio.create_task(
                self._worker_loop(worker, cycle, i)
            )
            worker_tasks.append(task)

        # Wait for all workers to finish (when queue is empty)
        await asyncio.gather(*worker_tasks)

        self.logger.info(
            "execution_phase_complete",
            queue_stats=await self.task_queue.get_stats(),
        )

    async def _worker_loop(self, worker: Agent, cycle: int, worker_id: int):
        """
        Worker loop: claim task → execute → mark complete → repeat.
        """
        session_id = f"cycle-{cycle}-worker-{worker_id}"

        while True:
            # Try to claim a task
            task = await self.task_queue.claim_task(
                worker_id=session_id,
                task_types=[TaskType.CODING, TaskType.TESTING],
            )

            if task is None:
                # No more tasks, worker done
                self.logger.debug("worker_no_tasks", worker_id=worker_id)
                break

            self.logger.info(
                "worker_claimed_task",
                worker_id=worker_id,
                task_id=task.id,
                task_title=task.title,
            )

            # Execute task
            worker_mission = f"""
            Task: {task.title}

            Description:
            {task.description}

            Relevant files:
            {', '.join(task.files)}

            Complete this task fully. Write code, tests, and push changes.
            """

            result = await worker.execute(
                mission=worker_mission,
                session_id=session_id,
            )

            # Mark task complete/failed
            if result.status == "completed":
                await self.task_queue.complete_task(task.id, result=asdict(result))
                self.logger.info("worker_completed_task", task_id=task.id)
            else:
                await self.task_queue.fail_task(task.id, error=result.final_message)
                self.logger.error("worker_failed_task", task_id=task.id)

    async def _run_judge(self, mission: str, project_dir: str, cycle: int) -> str:
        """
        Run judge agent to evaluate progress.

        Returns: "CONTINUE", "FRESH_START", or "COMPLETE"
        """
        self.logger.info("evaluation_phase")

        judge = await self.factory.create_agent(
            profile="judge",
            work_dir=project_dir,
        )

        judge_mission = f"""
        Evaluate progress for mission: {mission}

        Cycle: {cycle}
        Project: {project_dir}

        Review:
        1. Completed tasks (check git commits)
        2. Code quality (run tests)
        3. Overall progress toward goal

        Decide: CONTINUE, FRESH_START, or COMPLETE

        Respond with ONLY one word.
        """

        result = await judge.execute(
            mission=judge_mission,
            session_id=f"cycle-{cycle}-judge",
        )

        decision = result.final_message.strip().upper()

        if decision not in ["CONTINUE", "FRESH_START", "COMPLETE"]:
            # Default to continue if unclear
            decision = "CONTINUE"

        self.logger.info("evaluation_complete", decision=decision)
        return decision

    async def _fresh_start(self, project_dir: str):
        """
        Trigger fresh start to combat drift.

        Clears task queue and resets state.
        """
        self.logger.warning("triggering_fresh_start")

        # Clear task queue
        await self.task_queue.clear()

        # Could also: reset branches, checkpoint state, etc.
```

---

### 4. Custom Tools für Task Management

**Datei**: `src/taskforce/infrastructure/tools/task_management/`

```python
class CreateTaskTool(ToolProtocol):
    """Tool for planner agents to create tasks."""

    def __init__(self, task_queue: TaskQueue):
        self._queue = task_queue

    @property
    def name(self) -> str:
        return "create_task"

    @property
    def description(self) -> str:
        return (
            "Create a new task in the task queue. "
            "Use this to break down work for worker agents."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "task_type": {
                    "type": "string",
                    "enum": ["coding", "testing", "documentation", "refactoring"],
                },
                "priority": {"type": "integer", "minimum": 1, "maximum": 10},
                "files": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "description", "task_type"],
        }

    async def execute(self, **kwargs) -> dict:
        task = Task(
            id=str(uuid.uuid4()),
            title=kwargs["title"],
            description=kwargs["description"],
            type=TaskType(kwargs["task_type"]),
            priority=kwargs.get("priority", 5),
            status=TaskStatus.PENDING,
            created_by=kwargs.get("_planner_id", "unknown"),
            created_at=datetime.now(),
            files=kwargs.get("files", []),
            dependencies=[],
            version=0,
        )

        success = await self._queue.add_task(task)

        return {
            "success": success,
            "task_id": task.id,
            "message": f"Task '{task.title}' created",
        }


class ClaimTaskTool(ToolProtocol):
    """Tool for worker agents to claim tasks."""

    def __init__(self, task_queue: TaskQueue):
        self._queue = task_queue

    async def execute(self, **kwargs) -> dict:
        worker_id = kwargs.get("_worker_id")
        task_types = kwargs.get("task_types", ["coding", "testing"])

        task = await self._queue.claim_task(
            worker_id=worker_id,
            task_types=[TaskType(t) for t in task_types],
        )

        if task:
            return {
                "success": True,
                "task": asdict(task),
            }
        else:
            return {
                "success": False,
                "message": "No tasks available",
            }
```

---

## 🗺️ Implementation Roadmap

### Phase 1: Task Queue Foundation (Week 1-2)

**Goals**:
- ✅ Task Model & TaskStatus/TaskType enums
- ✅ TaskQueue with Optimistic Concurrency
- ✅ StateManager extension für version-based updates
- ✅ Unit Tests (optimistic concurrency scenarios)

**Deliverables**:
- `src/taskforce/infrastructure/task_queue/task.py`
- `src/taskforce/infrastructure/task_queue/queue.py`
- `tests/unit/infrastructure/test_task_queue.py`

---

### Phase 2: Agent Roles (Week 3-4)

**Goals**:
- ✅ Planner Agent Config & Prompt
- ✅ Worker Agent Config & Prompt
- ✅ Judge Agent Config & Prompt
- ✅ Custom Tools (CreateTaskTool, ClaimTaskTool, etc.)

**Deliverables**:
- `configs/roles/planner.yaml`
- `configs/roles/worker.yaml`
- `configs/roles/judge.yaml`
- `src/taskforce/infrastructure/tools/task_management/`

---

### Phase 3: Master Orchestrator (Week 5-6)

**Goals**:
- ✅ MasterOrchestrator Implementation
- ✅ Cycle Management (planner → worker → judge)
- ✅ Concurrent Worker Spawning
- ✅ Fresh Start Mechanism
- ✅ Progress Tracking & Metrics

**Deliverables**:
- `src/taskforce/core/domain/master_orchestrator.py`
- `configs/master_orchestrator.yaml`
- CLI Command: `taskforce master-run`

---

### Phase 4: Long-Running Support (Week 7-8)

**Goals**:
- ✅ Checkpointing (save/resume state)
- ✅ Drift Detection
- ✅ Failure Recovery
- ✅ Monitoring & Observability

**Deliverables**:
- Checkpoint System
- Drift Detector
- Dashboard (optional)

---

### Phase 5: Testing & Optimization (Week 9-10)

**Goals**:
- ✅ Integration Tests (full cycles)
- ✅ Performance Testing (100+ concurrent workers)
- ✅ Model Selection per Role
- ✅ Prompt Tuning

**Deliverables**:
- Comprehensive Test Suite
- Benchmarks
- Production-Ready Config

---

## 🔬 Key Technical Challenges

### 1. Optimistic Concurrency Implementation

**Problem**: Hundreds of workers updating shared task queue simultaneously.

**Solution**: Version-based conflict detection + retry with exponential backoff.

```python
# StateManager extension needed
async def save_state_with_version(
    self,
    session_id: str,
    state_data: dict,
    expected_version: int,
) -> None:
    """
    Save state only if version matches (optimistic concurrency).

    Raises VersionConflictError if version mismatch.
    """
    current = await self.load_state(session_id)
    if current and current.get("version") != expected_version:
        raise VersionConflictError(
            f"Version mismatch: expected {expected_version}, "
            f"got {current.get('version')}"
        )

    await self.save_state(session_id, state_data)
```

---

### 2. Model Selection per Role

**Problem**: Different models excel at different roles.

**Solution**: Role-specific model configs.

```yaml
# configs/roles/planner.yaml
llm:
  default_model: "powerful"  # GPT-5.2 for planning

# configs/roles/worker.yaml
llm:
  default_model: "codex"  # GPT-5.1-codex for coding
```

---

### 3. Drift Detection

**Problem**: Agents can drift over weeks of execution.

**Solution**: Judge agent + periodic fresh starts.

```python
def detect_drift(self, commits: list, tasks: list) -> bool:
    """
    Detect if agents are drifting from goal.

    Signals:
    - Many commits but few completed tasks
    - Repeated changes to same files
    - Low test coverage
    - No progress on high-priority tasks
    """
    pass
```

---

### 4. Conflict Resolution

**Problem**: Workers push to same branch, conflicts inevitable.

**Solution**: Workers handle conflicts themselves (rebase).

```python
# Worker system prompt includes:
"""
If your push fails due to conflicts:
1. Pull latest changes
2. Rebase your changes
3. Resolve conflicts
4. Push again
5. If still failing after 3 attempts, mark task as blocked
"""
```

---

## 📊 Success Metrics

### Performance Targets

- **Throughput**: 100+ concurrent workers
- **Duration**: Projects running 1-4 weeks
- **Codebase Size**: 100K-1M+ LoC
- **Conflict Rate**: < 10% of pushes fail
- **Task Completion**: > 80% of tasks completed (not failed/blocked)

### Quality Metrics

- **Test Coverage**: Maintained > 80%
- **Code Quality**: Passes linting
- **Architecture**: Clean, maintainable
- **Drift**: Fresh starts < 10% of cycles

---

## 🚧 Open Questions

1. **Planner Wake-up**: Should planners wake when tasks complete? (Cursor mentioned this)
2. **Task Timeout**: Max duration before worker is killed?
3. **Sub-Planner Depth**: Max recursion for sub-planners?
4. **Judge Frequency**: Every cycle? Every N cycles?
5. **Model Costs**: How to manage costs for weeks-long runs?

---

## 🔄 Integration with Existing System

### Backward Compatibility

- ✅ Existing AgentTool still works
- ✅ Single-agent missions unchanged
- ✅ Master Orchestrator is opt-in (`taskforce master-run`)

### Migration Path

1. **Phase 1**: Implement Task Queue (no breaking changes)
2. **Phase 2**: Add Roles as new configs (optional)
3. **Phase 3**: Add MasterOrchestrator (new CLI command)
4. **Phase 4**: Dogfood on internal projects
5. **Phase 5**: Production release

---

## 📝 Next Steps

1. **Review & Feedback**: Diskutieren mit Team
2. **Spike**: Proof-of-Concept für Task Queue (2-3 Tage)
3. **Phase 1 Start**: Task Queue Implementation
4. **Iterative Rollout**: Phase für Phase

---

**Ende des Plans**
