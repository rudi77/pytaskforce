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

The React UI has its own tests under `ui/`.

```powershell
cd ui
npm run test
npm run test:e2e
```

`npm run test:e2e` runs Playwright smoke tests from `ui/e2e/`. The tests start
the Vite dev server automatically and mock Taskforce API responses so they are
repeatable without requiring a local backend state.

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

