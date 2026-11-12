# Testing Guide

## Test Architecture

All tests live under `/home/sdash/Todo-app/FASTAPI_PRAC/tests/` and are configured via `/home/sdash/Todo-app/FASTAPI_PRAC/pytest.ini`.

- **Isolated Unit & Functional Tests**: Use an in-memory SQLite database per test function (`tests/conftest.py`) with `PRAGMA foreign_keys=ON` and an isolated `SECRET_KEY`.
- **PostgreSQL Integration Tests**: `tests/test_postgres_integration.py` connects to a dedicated PostgreSQL test database specified via `TEST_DATABASE_URL` (refusing to run against `TodoApplicationDB`) to verify live PostgreSQL connectivity, unique/foreign-key constraints, cascade deletes, and FastAPI persistence.

## Running Tests

Activate the single project-level `.venv`:

```bash
cd /home/sdash/Todo-app/FASTAPI_PRAC
source .venv/bin/activate
```

### Run Unit & Functional Tests

```bash
python -m pytest -v
```

### Run Including PostgreSQL Integration Test

```bash
TEST_DATABASE_URL="postgresql://postgres:your_password@localhost:5432/TodoTestDB" python -m pytest -v
```
