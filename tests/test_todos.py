"""Tests for Todo CRUD (HTML & JSON API), validation, stats, and CSRF protection."""

from tests.conftest import (
    create_user_in_db,
    extract_csrf,
    get_bearer_token,
    login_browser,
)


def test_todo_json_api_crud_and_validation(client, db_session):
    create_user_in_db(db_session, email="todo@example.com", password="password123")
    token = get_bearer_token(client, "todo@example.com", "password123")
    headers = {"Authorization": f"Bearer {token}"}

    # Empty list initially
    assert client.get("/todos/api/", headers=headers).json() == []

    # Invalid priority (0 or 6) -> 422
    bad_prio = client.post(
        "/todos/api/",
        headers=headers,
        json={"title": "Test", "description": "Valid desc", "priority": 6, "complete": False},
    )
    assert bad_prio.status_code == 422

    bad_prio_low = client.post(
        "/todos/api/",
        headers=headers,
        json={"title": "Test", "description": "Valid desc", "priority": 0, "complete": False},
    )
    assert bad_prio_low.status_code == 422

    # Create valid todo
    created = client.post(
        "/todos/api/",
        headers=headers,
        json={
            "title": "Write tests",
            "description": "Cover CRUD and auth",
            "priority": 5,
            "complete": False,
        },
    )
    assert created.status_code == 201
    todo_id = created.json()["id"]
    assert created.json()["title"] == "Write tests"

    # Retrieve single & list
    fetched = client.get(f"/todos/api/{todo_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["priority"] == 5

    listing = client.get("/todos/api/", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    # Update todo
    updated = client.put(
        f"/todos/api/{todo_id}",
        headers=headers,
        json={
            "title": "Write thorough tests",
            "description": "Cover CRUD, isolation, admin",
            "priority": 4,
            "complete": True,
        },
    )
    assert updated.status_code == 202
    assert updated.json()["complete"] is True
    assert updated.json()["title"] == "Write thorough tests"

    # Delete todo
    deleted = client.delete(f"/todos/api/{todo_id}", headers=headers)
    assert deleted.status_code == 204

    # Missing record -> 404
    assert client.get(f"/todos/api/{todo_id}", headers=headers).status_code == 404
    assert client.put(
        f"/todos/api/{todo_id}",
        headers=headers,
        json={"title": "Missing", "description": "Missing desc", "priority": 2, "complete": False},
    ).status_code == 404
    assert client.delete(f"/todos/api/{todo_id}", headers=headers).status_code == 404


def test_todo_html_crud_toggle_and_csrf(client, db_session):
    create_user_in_db(db_session, email="htmltodo@example.com", password="password123")
    login_browser(client, "htmltodo@example.com", "password123")

    # Add todo page & CSRF failure check
    add_page = client.get("/todos/add-todo")
    assert add_page.status_code == 200
    csrf = extract_csrf(add_page.text)

    no_csrf = client.post(
        "/todos/add-todo",
        data={
            "title": "No CSRF",
            "description": "Should fail",
            "priority": "3",
            "complete": "false",
        },
    )
    assert no_csrf.status_code == 403

    # Invalid title (<3 chars) returns 400 and preserves input
    bad_form = client.post(
        "/todos/add-todo",
        data={
            "title": "Hi",
            "description": "Valid description",
            "priority": "3",
            "complete": "false",
            "csrf_token": csrf,
        },
    )
    assert bad_form.status_code == 400
    assert "Valid description" in bad_form.text

    # Valid add
    ok_add = client.post(
        "/todos/add-todo",
        data={
            "title": "Buy milk",
            "description": "Whole milk 2L",
            "priority": "4",
            "complete": "false",
            "csrf_token": csrf,
        },
    )
    assert ok_add.status_code == 302

    home = client.get("/")
    assert home.status_code == 200
    assert "Buy milk" in home.text
    assert 'id="statTotal">1<' in home.text
    assert 'id="statCompleted" style="color:#22c55e;">0<' in home.text
    assert 'id="statPending" style="color:#f59e0b;">1<' in home.text

    # Toggle completion
    home_csrf = extract_csrf(home.text)
    toggle = client.post("/todos/complete/1", data={"csrf_token": home_csrf})
    assert toggle.status_code == 302

    home_after_toggle = client.get("/")
    assert 'id="statCompleted" style="color:#22c55e;">1<' in home_after_toggle.text
    assert 'id="statPending" style="color:#f59e0b;">0<' in home_after_toggle.text

    # Edit todo
    edit_page = client.get("/todos/edit-todo/1")
    assert edit_page.status_code == 200
    edit_csrf = extract_csrf(edit_page.text)
    edit_resp = client.post(
        "/todos/edit-todo/1",
        data={
            "title": "Buy oat milk",
            "description": "Unsweetened oat milk",
            "priority": "2",
            "complete": "false",
            "csrf_token": edit_csrf,
        },
    )
    assert edit_resp.status_code == 302

    home_after_edit = client.get("/")
    assert "Buy oat milk" in home_after_edit.text

    # Delete todo
    del_csrf = extract_csrf(home_after_edit.text)
    del_resp = client.post("/todos/delete/1", data={"csrf_token": del_csrf})
    assert del_resp.status_code == 302

    home_after_del = client.get("/")
    assert "No todos yet!" in home_after_del.text
    assert 'id="statTotal">0<' in home_after_del.text
