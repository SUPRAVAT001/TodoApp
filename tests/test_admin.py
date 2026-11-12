"""Tests for admin authorization, stats, user management, and privilege-escalation prevention."""

from TodoApp.models import Todos, Users
from tests.conftest import (
    create_user_in_db,
    extract_csrf,
    get_bearer_token,
    login_browser,
)


def test_registration_cannot_create_admin_account(client, db_session):
    resp = client.post(
        "/auth/",
        json={
            "email": "attacker@example.com",
            "password": "password123",
            "first_name": "Bad",
            "last_name": "Actor",
            "role": "admin",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"

    user = db_session.query(Users).filter(Users.email == "attacker@example.com").first()
    assert user.role == "user"


def test_normal_user_cannot_access_admin_routes(client, db_session):
    normal = create_user_in_db(db_session, email="normal@example.com", password="password123", role="user")
    token = get_bearer_token(client, "normal@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/admin/api/stats", headers=headers).status_code == 403
    assert client.get("/admin/api/users", headers=headers).status_code == 403
    assert client.get("/admin/api/todos", headers=headers).status_code == 403
    assert (
        client.patch(
            f"/admin/api/users/{normal.id}/status",
            headers=headers,
            json={"is_active": False},
        ).status_code
        == 403
    )
    assert client.get("/users/", headers=headers).status_code == 403

    login_browser(client, "normal@example.com", "password123")
    admin_html = client.get("/admin/")
    assert admin_html.status_code == 403
    assert "Access Denied" in admin_html.text


def test_admin_dashboard_stats_and_user_activation(client, db_session):
    admin = create_user_in_db(
        db_session,
        email="admin@example.com",
        password="password123",
        first_name="Admin",
        role="admin",
    )
    member = create_user_in_db(
        db_session,
        email="member@example.com",
        password="password123",
        first_name="Member",
        role="user",
    )
    db_session.add_all(
        [
            Todos(title="T1", description="Desc 1", priority=3, complete=True, owner_id=member.id),
            Todos(title="T2", description="Desc 2", priority=4, complete=False, owner_id=member.id),
        ]
    )
    db_session.commit()

    token = get_bearer_token(client, "admin@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    # API stats
    stats = client.get("/admin/api/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json() == {
        "total_users": 2,
        "active_users": 2,
        "inactive_users": 0,
        "total_todos": 2,
        "completed_todos": 1,
        "pending_todos": 1,
        "message": None,
    }

    # API users list excludes password hashes
    users_list = client.get("/admin/api/users", headers=headers)
    assert users_list.status_code == 200
    assert len(users_list.json()) == 2
    for item in users_list.json():
        assert "hashed_password" not in item

    # Cannot deactivate own admin account
    self_deact = client.patch(
        f"/admin/api/users/{admin.id}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert self_deact.status_code == 400

    # Deactivate member via API
    deact = client.patch(
        f"/admin/api/users/{member.id}/status",
        headers=headers,
        json={"is_active": False},
    )
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False

    # Deactivated member cannot log in
    assert (
        client.post(
            "/auth/token/login",
            data={"username": "member@example.com", "password": "password123"},
        ).status_code
        == 403
    )

    # Reactivate member via HTML Admin Dashboard (with CSRF)
    login_browser(client, "admin@example.com", "password123")
    dash = client.get("/admin/")
    assert dash.status_code == 200
    assert "member@example.com" in dash.text
    csrf = extract_csrf(dash.text)

    toggle_resp = client.post(
        f"/admin/users/{member.id}/toggle-active",
        data={"csrf_token": csrf},
    )
    assert toggle_resp.status_code == 302
    db_session.refresh(member)
    assert member.is_active is True

