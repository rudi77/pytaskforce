# Section 1: Introduction

Based on the comprehensive PRD and Agent V2 brownfield analysis, here's the introductory section:

---

### **Taskforce Architecture Document**

**Version:** 1.0  
**Date:** 2025-11-22  
**Author:** Winston (Architect Agent)

This document outlines the overall project architecture for **Taskforce**, a production-ready ReAct agent framework implementing Clean Architecture principles. Its primary goal is to serve as the guiding architectural blueprint for AI-driven development, ensuring consistency and adherence to chosen patterns and technologies.

**Relationship to Frontend Architecture:** Taskforce is a backend framework/microservice platform with CLI and REST API interfaces. There is no traditional frontend UI component. The "user interface" consists of:
- **Typer-based CLI** for direct command-line interaction
- **FastAPI REST API** for programmatic access and potential future web UI integration

Core technology stack choices documented herein are definitive for the entire project.

---

### **Starter Template or Existing Project**

**Source Project:** Agent V2 (`capstone/agent_v2`)

**Relationship:** Taskforce is **NOT a refactoring** of Agent V2, but rather a **greenfield implementation** in a new directory (`taskforce/`) that **reuses proven code** (≥75% of working logic) from Agent V2 by relocating and adapting it into Clean Architecture layers.

**Key Constraints from Agent V2:**
- **Technology Stack**: Python 3.11, LiteLLM, Typer, Rich, structlog, FastAPI, SQLAlchemy, Alembic (inherited from Agent V2)
- **Package Manager**: `uv` (NOT pip/venv) - this is a hard constraint
- **Platform**: Windows-first development with PowerShell 7+ support
- **Core Algorithm**: ReAct (Reason + Act) execution loop - proven implementation to be extracted and refactored
- **Tool Semantics**: Isolated Python execution namespaces, retry logic, timeout handling - must be preserved
- **Configuration Format**: YAML-based configuration files - maintain compatibility

**What Changes Architecturally:**
- **Four-Layer Structure**: Core → Infrastructure → Application → API (replacing flat PoC structure)
- **Protocol-Based Interfaces**: All cross-layer dependencies via Python protocols (PEP 544)
- **Swappable Adapters**: File-based (dev) and PostgreSQL (prod) persistence via shared protocols
- **Microservice Ready**: FastAPI REST API for stateless deployment with horizontal scaling
- **Dependency Injection**: AgentFactory wires domain objects with infrastructure adapters based on configuration profiles

**What Doesn't Change:**
- ReAct loop algorithm and execution semantics
- TodoList planning logic and LLM prompts
- Tool implementations and parameter schemas
- LLM service integration (LiteLLM abstraction)
- CLI command structure (similar to Agent V2 for user familiarity)

---

### **Change Log**

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2025-11-22 | 1.0 | Initial architecture document for Taskforce Clean Architecture implementation | Winston (Architect) |

---

### **Rationale:**

**Trade-offs:**
1. **Greenfield vs. Refactoring**: Chose greenfield in new directory to eliminate risk to operational Agent V2, but requires code relocation effort
2. **Code Reuse Target (≥75%)**: Aggressive reuse goal to accelerate delivery, but may carry forward some Agent V2 technical debt (mitigated by planned layer boundaries)
3. **Protocol-Based Interfaces**: More flexible than abstract base classes (duck typing) but less explicit in class hierarchies

**Key Assumptions:**
- Agent V2 architecture doc and PRD provide complete requirements specification
- Python 3.11 protocols (PEP 544) are well-understood by development team
- PostgreSQL is acceptable production database (per PRD)
- ≥75% code reuse is achievable while maintaining architectural boundaries

**Decisions Requiring Validation:**
- Four-layer Clean Architecture vs. three-layer (could merge application and API) - chose four for maximum separation
- Protocol vs. ABC for interfaces - chose protocols for flexibility
- Monorepo at taskforce/ root vs. separate repos - chose single repo for simplicity

---
