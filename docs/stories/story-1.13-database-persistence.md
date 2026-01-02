# Story 1.13: Implement Database Persistence and Migrations

**Epic**: Build Taskforce Production Framework with Clean Architecture  
**Story ID**: 1.13  
**Status**: Pending  
**Priority**: High  
**Estimated Points**: 5  
**Dependencies**: Story 1.2 (Protocol Interfaces), Story 1.9 (Factory)

---

## User Story

As a **developer**,  
I want **PostgreSQL-backed state persistence with Alembic migrations**,  
so that **Taskforce can be deployed in production with shared database**.

---

## Acceptance Criteria

1. ✅ Create `taskforce/src/taskforce/infrastructure/persistence/db_state.py` with `DbStateManager` implementing `StateManagerProtocol`
2. ✅ Create `taskforce/src/taskforce/infrastructure/persistence/db_todolist.py` with `DbTodoListManager` implementing `TodoListManagerProtocol`
3. ✅ SQLAlchemy models in `taskforce/src/taskforce/infrastructure/persistence/models.py`:
   - `Session` table (session_id PK, user_id, mission, status, timestamps)
   - `State` table (session_id FK, state_json JSONB, version, timestamp)
   - `TodoList` table (todolist_id PK, session_id FK, plan_json JSONB, status, timestamps)
   - `ExecutionHistory` table (session_id FK, step_id, thought, action, observation, timestamp)
   - `Memory` table (memory_id PK, context, lesson, tool_name, confidence, timestamp)
4. ✅ Alembic migration setup in `taskforce/alembic/`:
   - Initial migration creating all tables
   - Indexes on session_id, user_id, timestamp columns
5. ✅ Connection pooling configuration (min=5, max=20 connections)
6. ✅ Database URL configuration via environment variable or profile YAML
7. ✅ Integration tests with test PostgreSQL database verify CRUD operations

---

## Integration Verification

- **IV1: Existing Functionality Verification** - File-based persistence continues to work (dev profile)
- **IV2: Integration Point Verification** - Database persistence produces same behavior as file persistence (verified via shared test suite)
- **IV3: Performance Impact Verification** - Database operations complete in <50ms for state save/load (acceptable overhead)

---

## Technical Notes

**SQLAlchemy Models:**

```python
# taskforce/src/taskforce/infrastructure/persistence/models.py
from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Session(Base):
    """Agent session record."""
    __tablename__ = "sessions"
    
    session_id = Column(String(255), primary_key=True)
    user_id = Column(String(255), nullable=True, index=True)
    mission = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    states = relationship("State", back_populates="session", cascade="all, delete-orphan")
    todo_lists = relationship("TodoList", back_populates="session", cascade="all, delete-orphan")
    execution_history = relationship("ExecutionHistory", back_populates="session", cascade="all, delete-orphan")

class State(Base):
    """Session state snapshots."""
    __tablename__ = "states"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey("sessions.session_id"), nullable=False, index=True)
    state_json = Column(JSON, nullable=False)  # JSONB in PostgreSQL
    version = Column(Integer, nullable=False, default=1)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    session = relationship("Session", back_populates="states")

class TodoList(Base):
    """TodoList plans."""
    __tablename__ = "todo_lists"
    
    todolist_id = Column(String(255), primary_key=True)
    session_id = Column(String(255), ForeignKey("sessions.session_id"), nullable=False, index=True)
    plan_json = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    session = relationship("Session", back_populates="todo_lists")

class ExecutionHistory(Base):
    """Step-by-step execution history."""
    __tablename__ = "execution_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey("sessions.session_id"), nullable=False, index=True)
    step_id = Column(Integer, nullable=False)
    thought = Column(Text, nullable=True)
    action = Column(Text, nullable=True)
    observation = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Relationships
    session = relationship("Session", back_populates="execution_history")

class Memory(Base):
    """Cross-session learned memories."""
    __tablename__ = "memories"
    
    memory_id = Column(String(255), primary_key=True)
    context = Column(Text, nullable=False)
    lesson = Column(Text, nullable=False)
    tool_name = Column(String(100), nullable=True, index=True)
    confidence = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
```

**DbStateManager:**

```python
# taskforce/src/taskforce/infrastructure/persistence/db_state.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import Dict, Any, Optional, List
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.infrastructure.persistence.models import Session, State

class DbStateManager:
    """PostgreSQL-backed state manager.
    
    Implements StateManagerProtocol for dependency injection.
    """
    
    def __init__(self, db_url: str, pool_size: int = 20, max_overflow: int = 10):
        self.engine = create_async_engine(
            db_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            echo=False
        )
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def save_state(
        self, 
        session_id: str, 
        state_data: Dict[str, Any]
    ) -> None:
        """Save session state to database."""
        async with self.async_session() as session:
            # Check if session exists
            session_record = await session.get(Session, session_id)
            
            if not session_record:
                # Create new session
                session_record = Session(
                    session_id=session_id,
                    mission=state_data.get("mission", ""),
                    status=state_data.get("status", "pending"),
                    user_id=state_data.get("user_id")
                )
                session.add(session_record)
            else:
                # Update existing session
                session_record.status = state_data.get("status", session_record.status)
                session_record.updated_at = datetime.utcnow()
            
            # Save state snapshot
            state_record = State(
                session_id=session_id,
                state_json=state_data,
                version=state_data.get("version", 1)
            )
            session.add(state_record)
            
            await session.commit()
    
    async def load_state(
        self, 
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load latest session state from database."""
        async with self.async_session() as session:
            # Get latest state
            result = await session.execute(
                select(State)
                .where(State.session_id == session_id)
                .order_by(State.timestamp.desc())
                .limit(1)
            )
            state_record = result.scalar_one_or_none()
            
            if state_record:
                return state_record.state_json
            return None
    
    async def delete_state(self, session_id: str) -> None:
        """Delete session and all related data."""
        async with self.async_session() as session:
            session_record = await session.get(Session, session_id)
            if session_record:
                await session.delete(session_record)
                await session.commit()
    
    async def list_sessions(self) -> List[str]:
        """List all session IDs."""
        async with self.async_session() as session:
            result = await session.execute(select(Session.session_id))
            return [row[0] for row in result.all()]
```

**Alembic Setup:**

```python
# taskforce/alembic/env.py
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from taskforce.infrastructure.persistence.models import Base

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

run_migrations_online()
```

**Initial Migration:**

```bash
# Generate initial migration
cd taskforce
alembic revision --autogenerate -m "Initial schema"
```

---

## Testing Strategy

```python
# tests/integration/test_db_state_manager.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from taskforce.infrastructure.persistence.db_state import DbStateManager
from taskforce.infrastructure.persistence.models import Base

@pytest.fixture
async def db_manager():
    """Create test database and manager."""
    # Use in-memory SQLite for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    manager = DbStateManager(db_url="sqlite+aiosqlite:///:memory:")
    yield manager
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_save_and_load_state(db_manager):
    state_data = {
        "mission": "Test mission",
        "status": "in_progress",
        "version": 1
    }
    
    await db_manager.save_state("test-session", state_data)
    loaded = await db_manager.load_state("test-session")
    
    assert loaded["mission"] == state_data["mission"]
    assert loaded["status"] == state_data["status"]

@pytest.mark.asyncio
async def test_list_sessions(db_manager):
    await db_manager.save_state("session-1", {"mission": "Test 1"})
    await db_manager.save_state("session-2", {"mission": "Test 2"})
    
    sessions = await db_manager.list_sessions()
    
    assert "session-1" in sessions
    assert "session-2" in sessions
```

---

## Definition of Done

- [ ] SQLAlchemy models created with all tables
- [ ] DbStateManager implements StateManagerProtocol
- [ ] DbTodoListManager implements TodoListManagerProtocol
- [ ] Alembic migration setup complete
- [ ] Initial migration creates all tables and indexes
- [ ] Connection pooling configured
- [ ] Integration tests with test database (≥80% coverage)
- [ ] Database operations complete in <50ms
- [ ] Behavior matches file persistence (shared test suite passes)
- [ ] Code review completed
- [ ] Code committed to version control

