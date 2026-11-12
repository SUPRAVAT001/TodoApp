"""Tests for Jinja2 templates, navigation links, and static asset serving."""

from TodoApp.models import Todos
from tests.conftest import create_user_in_db, login_browser


def test_public_auth_pages_and_static_assets(client):
    login_page = client.get("/auth/login")
    assert login_page.status_code == 200
    assert 'action="/auth/login"' in login_page.text
    assert 'name="csrf_token"' in login_page.text

    reg_page = client.get("/auth/register")
    assert reg_page.status_code == 200
    assert 'action="/auth/register"' in reg_page.text
    assert 'name="csrf_token"' in reg_page.text

    # Static assets load cleanly
    for asset in (
        "/static/css/base.css",
        "/static/css/bootstrap.css",
        "/static/js/todos.js",
        "/static/js/bootstrap.js",
        "/static/js/jquery-slim.js",
        "/static/js/popper.js",
    ):
        resp = client.get(asset)
        assert resp.status_code == 200, f"Expected 200 for {asset}, got {resp.status_code}"

    # Unused conflicting base.js removed
    assert client.get("/static/js/base.js").status_code == 404


def test_authenticated_dashboard_navigation_and_templates(client, db_session):
    user = create_user_in_db(
        db_session,
        email="ui@example.com",
        password="password123",
        first_name="UIFirst",
        role="user",
    )
    db_session.add(
        Todos(
            title="Test UI Todo",
            description="Verify dashboard rendering",
            priority=3,
            complete=False,
            owner_id=user.id,
        )
    )
    db_session.commit()

    login_browser(client, "ui@example.com", "password123")

    home = client.get("/")
    assert home.status_code == 200
    assert "UIFirst" in home.text
    assert "Test UI Todo" in home.text
    assert 'href="/todos/add-todo"' in home.text
    assert 'href="/auth/profile"' in home.text
    assert 'href="/auth/logout"' in home.text
    assert 'href="/admin/"' not in home.text
    assert 'data-filter="all"' in home.text
    assert 'data-filter="open"' in home.text
    assert 'data-filter="done"' in home.text
    assert 'id="deleteModal"' in home.text

    assert client.get("/todos/add-todo").status_code == 200
    assert client.get("/todos/edit-todo/1").status_code == 200
    assert client.get("/auth/profile").status_code == 200


def test_admin_navbar_link_visible_for_admin_only(client, db_session):
    create_user_in_db(
        db_session,
        email="adminui@example.com",
        password="password123",
        first_name="Chief",
        role="admin",
    )
    login_browser(client, "adminui@example.com", "password123")
    home = client.get("/")
    assert home.status_code == 200
    assert 'href="/admin/"' in home.text

