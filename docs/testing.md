# Testing Guide

Taskforce maintains high code quality through a comprehensive suite of unit and integration tests.

## 🧪 Running Tests

All tests are run via **pytest**.

```powershell
# Run all tests
uv run pytest

# Run only unit tests
uv run pytest tests/unit

# Run only integration tests
uv run pytest tests/integration
```

## 📊 Coverage Reports
To generate an HTML coverage report:
```powershell
uv run pytest --cov=taskforce --cov-report=html
# Open htmlcov/index.html to view results
```

## 🏗 Test Structure
The test directory mirrors the `src/taskforce` structure:

- `tests/unit/core/`: Tests for pure domain logic (uses mocks for all I/O).
- `tests/unit/infrastructure/`: Tests for specific adapters (DB, Tools, LLM).
- `tests/integration/`: End-to-end tests for the full framework.

---
*For the full testing strategy, see [docs/architecture/section-11-testing-strategy.md](architecture/section-11-testing-strategy.md).*

