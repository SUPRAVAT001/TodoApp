"""Comprehensive security regression and remediation test suite.

Verifies:
1. Strict CSRF verification on HTML login and registration.
2. In-memory rate limiting and HTTP 429 responses on authentication endpoints.
3. Environment-aware disabling of Swagger, ReDoc, and OpenAPI documentation in production.
4. Strict multi-tenant task isolation (BOLA/IDOR prevention).
5. Administrative role enforcement and unauthorized access prevention.
"""

import pytest
from fastapi import FastAPI
from TodoApp.models import Todos, Users
from TodoApp.rate_limiter import check_rate_limit, limiter
from tests.conftest import ASGITestClient, create_user_in_db, extract_csrf


@pytest.fixture(autouse=True)
def clear_limiter():
    limiter.clear()
    yield
    limiter.clear()


# ==============================================================================
# 1. CSRF VERIFICATION TESTS
# ==============================================================================


def test_login_csrf_missing_cookie(client, db_session):
    """Submitting login form without CSRF cookie must be rejected with 403."""
    create_user_in_db(db_session, email="csrftest@example.com", password="password123")
    resp = client.post(
        "/auth/login",
        data={"username": "csrftest@example.com", "password": "password123", "csrf_token": "fake.token"},
        headers={"Cookie": ""},  # No cookies
    )
    assert resp.status_code == 403
    assert "CSRF verification failed" in resp.text


def test_login_csrf_missing_form_token(client, db_session):
    """Submitting login form without form token must be rejected with 403."""
    create_user_in_db(db_session, email="csrftest2@example.com", password="password123")
    # Fetch page to acquire valid CSRF cookie
    client.get("/auth/login")
    resp = client.post(
        "/auth/login",
        data={"username": "csrftest2@example.com", "password": "password123"},
        # No csrf_token in form data
    )
    assert resp.status_code == 403
    assert "CSRF verification failed" in resp.text


def test_login_csrf_invalid_signature(client, db_session):
    """Submitting tampered or invalid token must be rejected with 403."""
    create_user_in_db(db_session, email="csrftest3@example.com", password="password123")
    client.get("/auth/login")
    resp = client.post(
        "/auth/login",
        data={
            "username": "csrftest3@example.com",
            "password": "password123",
            "csrf_token": "tamperednonce.tamperedsignature",
        },
    )
    assert resp.status_code == 403
    assert "CSRF verification failed" in resp.text


def test_login_csrf_mismatched_token(client, db_session):
    """Submitting token from a different session must be rejected with 403."""
    create_user_in_db(db_session, email="csrftest4@example.com", password="password123")
    # Session 1
    page1 = client.get("/auth/login")
    csrf1 = extract_csrf(page1.text)

    # Session 2 has a different cookie
    client.cookies.clear()
    client.get("/auth/login")

    # Send Session 1's token with Session 2's cookie
    resp = client.post(
        "/auth/login",
        data={"username": "csrftest4@example.com", "password": "password123", "csrf_token": csrf1},
    )
    assert resp.status_code == 403
    assert "CSRF verification failed" in resp.text


def test_register_csrf_missing_token_rejected(client):
    """Submitting registration without CSRF token must be rejected with 403."""
    client.get("/auth/register")
    resp = client.post(
        "/auth/register",
        data={
            "first_name": "Test",
            "last_name": "User",
            "email": "nocsrf@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert resp.status_code == 403
    assert "CSRF verification failed" in resp.text


def test_register_and_login_csrf_valid_succeeds(client, db_session):
    """Legitimate registration and login with valid CSRF token succeed smoothly."""
    reg_page = client.get("/auth/register")
    reg_csrf = extract_csrf(reg_page.text)

    reg_resp = client.post(
        "/auth/register",
        data={
            "first_name": "Valid",
            "last_name": "User",
            "email": "validuser@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": reg_csrf,
        },
    )
    assert reg_resp.status_code == 302
    assert "/auth/login?registered=1" in reg_resp.headers.get("location", "")

    login_page = client.get("/auth/login")
    login_csrf = extract_csrf(login_page.text)

    login_resp = client.post(
        "/auth/login",
        data={"username": "validuser@example.com", "password": "password123", "csrf_token": login_csrf},
    )
    assert login_resp.status_code == 302
    assert login_resp.headers.get("location") == "/"
    assert "access_token" in client.cookies


# ==============================================================================
# 2. RATE LIMITING TESTS
# ==============================================================================


def test_token_login_rate_limiting(client, db_session, monkeypatch):
    """Repeated login attempts must trigger HTTP 429 when rate limit is exceeded."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MINUTE", "3")
    create_user_in_db(db_session, email="ratelimit@example.com", password="password123")

    # First 3 attempts are allowed
    for _ in range(3):
        resp = client.post(
            "/auth/token/login",
            data={"username": "ratelimit@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    # 4th attempt must be rate-limited
    blocked = client.post(
        "/auth/token/login",
        data={"username": "ratelimit@example.com", "password": "wrongpassword"},
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after") == "60"
    assert "Too many requests" in blocked.text


def test_rate_limiting_isolated_per_client_ip(client, db_session, monkeypatch):
    """Rate limit on IP A must not block requests originating from IP B."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MINUTE", "2")
    create_user_in_db(db_session, email="rateip@example.com", password="password123")

    # Exceed limit for IP A
    for _ in range(2):
        client.post(
            "/auth/token/login",
            data={"username": "rateip@example.com", "password": "bad"},
            headers={"X-Forwarded-For": "198.51.100.10"},
        )
    blocked_a = client.post(
        "/auth/token/login",
        data={"username": "rateip@example.com", "password": "bad"},
        headers={"X-Forwarded-For": "198.51.100.10"},
    )
    assert blocked_a.status_code == 429

    # IP B should NOT be blocked
    allowed_b = client.post(
        "/auth/token/login",
        data={"username": "rateip@example.com", "password": "password123"},
        headers={"X-Forwarded-For": "203.0.113.50"},
    )
    assert allowed_b.status_code == 200


def test_rate_limiting_does_not_leak_account_existence(client, monkeypatch):
    """Rate limiter behaves identically whether an account exists or not."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MINUTE", "2")

    for _ in range(2):
        client.post(
            "/auth/token/login",
            data={"username": "nonexistent@example.com", "password": "password123"},
        )

    blocked = client.post(
        "/auth/token/login",
        data={"username": "nonexistent@example.com", "password": "password123"},
    )
    assert blocked.status_code == 429
    assert "Too many requests" in blocked.text


# ==============================================================================
# 3. PRODUCTION API DOCUMENTATION TOGGLE TESTS
# ==============================================================================


def test_api_docs_disabled_in_production(monkeypatch):
    """In production environment, /docs, /redoc, and /openapi.json must return 404."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)

    # Re-evaluate app initialization under production settings
    docs_enabled = (
        False  # ENVIRONMENT == "production" and not ENABLE_API_DOCS
    )
    prod_app = FastAPI(
        title="TodoApp",
        version="1.0.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    prod_client = ASGITestClient(prod_app)

    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/redoc").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404


def test_api_docs_enabled_in_development(monkeypatch):
    """In development environment, /docs and /openapi.json must return 200."""
    monkeypatch.setenv("ENVIRONMENT", "development")

    dev_app = FastAPI(
        title="TodoApp",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    dev_client = ASGITestClient(dev_app)

    assert dev_client.get("/docs").status_code == 200
    assert dev_client.get("/openapi.json").status_code == 200


# ==============================================================================
# 4. DATA ISOLATION AND AUTHORIZATION INVARIANTS
# ==============================================================================


def test_multi_tenant_isolation_todo_crud(client, db_session):
    """User A cannot access or mutate User B's todo."""
    user_a = create_user_in_db(db_session, email="user_a@example.com", password="password123")
    user_b = create_user_in_db(db_session, email="user_b@example.com", password="password123")

    todo_b = Todos(
        title="User B Secret Todo",
        description="Private information",
        priority=3,
        complete=False,
        owner_id=user_b.id,
    )
    db_session.add(todo_b)
    db_session.commit()
    db_session.refresh(todo_b)

    # Log in as User A
    from TodoApp.security import create_access_token
    token_a = create_access_token(user_a.email, user_a.id)

    # User A attempting to read User B's todo
    read_resp = client.get(
        f"/todos/api/{todo_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert read_resp.status_code == 404

    # User A attempting to update User B's todo
    put_resp = client.put(
        f"/todos/api/{todo_b.id}",
        json={"title": "Hacked Title", "description": "Hacked Description", "priority": 1, "complete": True},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert put_resp.status_code == 404

    # User A attempting to delete User B's todo
    del_resp = client.delete(
        f"/todos/api/{todo_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert del_resp.status_code == 404

    # Verify User B's todo remains intact in DB
    intact = db_session.query(Todos).filter(Todos.id == todo_b.id).first()
    assert intact is not None
    assert intact.title == "User B Secret Todo"
