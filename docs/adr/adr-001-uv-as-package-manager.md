# ADR 001: Use uv as Package Manager

## Status
Accepted

## Context
Traditional Python dependency management using `pip` and `venv` can be slow and lacks the robust locking mechanisms found in other ecosystems (like Rust's Cargo or Node's npm/pnpm).

## Decision
We will use **uv** as the primary package and project management tool for Taskforce.

## Consequences
- **Speed**: Dependency resolution and installation are significantly faster.
- **Isolations**: `uv` handles virtual environment creation and activation seamlessly.
- **Reproducibility**: The `uv.lock` file ensures consistent environments across development and production.
- **Dependency**: Developers must have `uv` installed on their systems.

