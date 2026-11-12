"""Tests for authentication, registration, sessions, JWT expiration, and profile management."""

from datetime import timedelta

from TodoApp.models import Users
from TodoApp.security import ACCESS_COOKIE_NAME, create_access_token
from tests.conftest import (
    create_user_in_db,
    extract_csrf,
    get_bearer_token,
    login_browser,
)


def test_successful_registration_api_and_login(client, db_session):
    resp = client.post(
        "/auth/",
        json={
            "email": "alice@example.com",
            "password": "password123",
            "first_name": "Alice",
            "last_name": "Smith",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert "hashed_password" not in data

    token = get_bearer_token(client, "alice@example.com", "password123")
    assert isinstance(token, str) and len(token) > 20


def test_successful_registration_html_flow(client, db_session):
    reg_page = client.get("/auth/register")
    assert reg_page.status_code == 200
    csrf = extract_csrf(reg_page.text)

    resp = client.post(
        "/auth/register",
        data={
            "first_name": "Bob",
            "last_name": "Jones",
            "email": "bob@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": csrf,
        },
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/auth/login?registered=1"

    user = db_session.query(Users).filter(Users.email == "bob@example.com").first()
    assert user is not None
    assert user.role == "user"


def test_duplicate_registration_prevented(client, db_session):
    create_user_in_db(db_session, email="dup@example.com")

    api_resp = client.post(
        "/auth/",
        json={
            "email": "DUP@example.com",
            "password": "password123",
            "first_name": "Dup",
            "last_name": "User",
        },
    )
    assert api_resp.status_code == 409

    reg_page = client.get("/auth/register")
    csrf = extract_csrf(reg_page.text)
    html_resp = client.post(
        "/auth/register",
        data={
            "first_name": "Dup",
            "last_name": "User",
            "email": "dup@example.com",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": csrf,
        },
    )
    assert html_resp.status_code == 409
    assert "already exists" in html_resp.text


def test_registration_password_validation(client):
    reg_page = client.get("/auth/register")
    csrf = extract_csrf(reg_page.text)

    mismatch = client.post(
        "/auth/register",
        data={
            "first_name": "A",
            "last_name": "B",
            "email": "ab@example.com",
            "password": "password123",
            "confirm_password": "different123",
            "csrf_token": csrf,
        },
    )
    assert mismatch.status_code == 400
    assert "do not match" in mismatch.text

    short = client.post(
        "/auth/register",
        data={
            "first_name": "A",
            "last_name": "B",
            "email": "ab@example.com",
            "password": "123",
            "confirm_password": "123",
            "csrf_token": csrf,
        },
    )
    assert short.status_code == 400


def test_login_success_incorrect_password_and_logout(client, db_session):
    create_user_in_db(db_session, email="carol@example.com", password="password123")

    bad_api = client.post(
        "/auth/token/login",
        data={"username": "carol@example.com", "password": "wrongpassword"},
    )
    assert bad_api.status_code == 401

    bad_html = login_browser(client, "carol@example.com", "wrongpassword")
    assert bad_html.status_code == 401
    assert "Invalid email or password" in bad_html.text

    good_html = login_browser(client, "carol@example.com", "password123")
    assert good_html.status_code == 302
    assert good_html.headers["location"] == "/"
    assert ACCESS_COOKIE_NAME in client.cookies

    home = client.get("/")
    assert home.status_code == 200

    logout_resp = client.get("/auth/logout")
    assert logout_resp.status_code == 302
    assert logout_resp.headers["location"] == "/auth/login?logged_out=1"
    assert ACCESS_COOKIE_NAME not in client.cookies

    after_logout = client.get("/")
    assert after_logout.status_code == 302
    assert after_logout.headers["location"] == "/auth/login"


def test_expired_and_invalid_jwt_rejected(client, db_session):
    user = create_user_in_db(db_session, email="dave@example.com", password="password123")
    expired_token = create_access_token(
        user.email,
        user.id,
        expires_delta=timedelta(minutes=-5),
    )

    api_resp = client.get(
        "/todos/api/",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert api_resp.status_code == 401

    bad_api_resp = client.get(
        "/todos/api/",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert bad_api_resp.status_code == 401

    client.cookies[ACCESS_COOKIE_NAME] = expired_token
    html_resp = client.get("/")
    assert html_resp.status_code == 302
    assert html_resp.headers["location"] == "/auth/login"


def test_inactive_user_cannot_login_or_access_routes(client, db_session):
    user = create_user_in_db(
        db_session,
        email="inactive@example.com",
        password="password123",
        is_active=False,
    )

    api_login = client.post(
        "/auth/token/login",
        data={"username": "inactive@example.com", "password": "password123"},
    )
    assert api_login.status_code == 403

    html_login = login_browser(client, "inactive@example.com", "password123")
    assert html_login.status_code == 403
    assert "deactivated" in html_login.text

    forged_valid_token = create_access_token(user.email, user.id)
    api_resp = client.get(
        "/todos/api/",
        headers={"Authorization": f"Bearer {forged_valid_token}"},
    )
    assert api_resp.status_code == 403


def test_unauthorized_access_blocked(client):
    assert client.get("/").status_code == 302
    assert client.get("/auth/profile").status_code == 302
    assert client.get("/todos/add-todo").status_code == 302
    assert client.get("/todos/api/").status_code == 401
    assert client.get("/users/me").status_code == 401


def test_profile_and_password_change_with_csrf(client, db_session):
    create_user_in_db(db_session, email="eve@example.com", password="password123", first_name="Eve")
    login_browser(client, "eve@example.com", "password123")

    profile = client.get("/auth/profile")
    assert profile.status_code == 200
    assert "eve@example.com" in profile.text
    assert "Active" in profile.text
    csrf = extract_csrf(profile.text)

    # Missing CSRF rejected
    no_csrf = client.post(
        "/auth/change-password",
        data={
            "current_password": "password123",
            "new_password": "newpassword123",
            "confirm_new_password": "newpassword123",
        },
    )
    assert no_csrf.status_code == 403

    # Wrong current password rejected
    wrong_cur = client.post(
        "/auth/change-password",
        data={
            "current_password": "wrongpassword",
            "new_password": "newpassword123",
            "confirm_new_password": "newpassword123",
            "csrf_token": csrf,
        },
    )
    assert wrong_cur.status_code == 400
    assert "Current password is incorrect" in wrong_cur.text

    # Valid update succeeds
    ok = client.post(
        "/auth/change-password",
        data={
            "current_password": "password123",
            "new_password": "newpassword123",
            "confirm_new_password": "newpassword123",
            "csrf_token": csrf,
        },
    )
    assert ok.status_code == 200
    assert "Password updated successfully!" in ok.text

    # New password works for login
    token = get_bearer_token(client, "eve@example.com", "newpassword123")
    assert token

