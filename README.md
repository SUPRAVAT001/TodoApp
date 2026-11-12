# TodoApp — Full-Stack Multi-User Todo Application

A Linux-first full-stack multi-user Todo application built with **FastAPI**, **PostgreSQL**, **SQLAlchemy 2**, **Alembic**, **Jinja2**, and **Bootstrap 4.3.1**. It serves both a server-rendered browser interface (HTTP-only JWT cookies + HMAC-signed CSRF protection) and a Bearer-token JSON REST API.

---

## Architecture

```text
FASTAPI_PRAC/
├── .venv/                 # Single project-level Linux virtual environment
├── TodoApp/
│   ├── __init__.py
│   ├── config.py          # Environment-variable & .env configuration
│   ├── database.py        # SQLAlchemy engine, SessionLocal, get_db dependency
│   ├── main.py            # FastAPI app, CSRF middleware, static files, home route
│   ├── models.py          # Users and Todos ORM models
│   ├── schemas.py         # Pydantic v2 request/response schemas
│   ├── security.py        # bcrypt hashing, HS256 JWT, CSRF tokens, Jinja2 globals
│   ├── routers/
│   │   ├── auth.py        # Login, register, logout, profile, password change, token API
│   │   ├── todos.py       # HTML Todo CRUD + /todos/api/ JSON endpoints
│   │   ├── users.py       # Authorized user lookup endpoints
│   │   └── admin.py       # Admin dashboard, stats, account activation/deactivation
│   ├── templates/         # Jinja2 templates
│   ├── static/            # Bootstrap 4.3.1 CSS/JS, jQuery Slim, Popper.js, base.css, todos.js
│   ├── alembic/           # Alembic migration environment and version scripts
│   └── alembic.ini
├── tests/                 # Pytest unit & PostgreSQL integration suite
├── pytest.ini
├── .env.example
├── requirements.txt
├── README.md
└── TESTING.md
```

---

## Setup & Development Workflow (Linux)

### 1. Activate Virtual Environment & Install Dependencies

```bash
cd /home/sdash/Todo-app/FASTAPI_PRAC
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with real values:
- `ENVIRONMENT`: `development` or `production`
- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql://postgres:your_password@localhost:5432/TodoApplicationDB`)
- `SECRET_KEY`: Long random secret for JWT and CSRF signing
- `ACCESS_TOKEN_EXPIRE_MINUTES`: JWT lifetime in minutes (default `60`)
- `COOKIE_SECURE`: `false` for local HTTP development, `true` in HTTPS production

### 3. Apply Database Migrations (PostgreSQL)

Ensure PostgreSQL is running and `TodoApplicationDB` exists, then run:

```bash
cd /home/sdash/Todo-app/FASTAPI_PRAC/TodoApp
alembic -c alembic.ini upgrade head
```

### 4. Run Tests

```bash
cd /home/sdash/Todo-app/FASTAPI_PRAC
python -m pytest -v
```

See [TESTING.md](TESTING.md) for PostgreSQL integration testing via `TEST_DATABASE_URL`.

### 5. Start the Application

```bash
cd /home/sdash/Todo-app/FASTAPI_PRAC
uvicorn TodoApp.main:app --host 127.0.0.1 --port 8001 --reload
```

Open:
- Web UI: `http://127.0.0.1:8001/`
- Interactive API Docs: `http://127.0.0.1:8001/docs`

---

## Authentication & Security

- **Passwords**: Hashed with `bcrypt` via `passlib`.
- **Browser Sessions**: HS256 JWT stored in an `httponly`, `samesite="lax"` cookie (`access_token`).
- **API Authentication**: `Authorization: Bearer <token>` header via `POST /auth/token/login`.
- **CSRF Protection**: Double-submit HMAC-SHA256 `csrf_token` cookie validated against hidden form inputs on cookie-authenticated browser `POST` routes.
- **Authorization & Isolation**:
  - Public registration always assigns `role="user"`.
  - Every Todo query and mutation is scoped to `Todos.owner_id == current_user.id`.
  - Deactivated users (`is_active=False`) are blocked from logging in and accessing protected routes.
  - Admin endpoints (`/admin/...` and `GET /users/`) require `role="admin"`.
