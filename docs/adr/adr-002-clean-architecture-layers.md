# ADR 002: Clean Architecture Layering

## Status
Accepted

## Context
Multi-agent systems often become tightly coupled to specific LLM providers, database schemas, and external tool APIs, making them difficult to test and adapt.

## Decision
Taskforce will strictly follow **Clean Architecture** (Hexagonal) principles with four layers:
1. **Core**: Pure domain logic, zero external dependencies.
2. **Infrastructure**: Adapters for external services (DB, LLM, Tools).
3. **Application**: Orchestration via dependency injection and factory patterns.
4. **API**: Entrypoints (CLI, REST).

## Consequences
- **Testability**: Core logic can be unit-tested with 100% isolation.
- **Maintainability**: Infrastructure can be swapped (e.g., File to DB) without touching business logic.
- **Clarity**: Strict import rules (inward only) prevent circular dependencies and "spaghetti" code.

