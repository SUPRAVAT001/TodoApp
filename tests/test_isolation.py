"""Tests verifying strict multi-user data isolation (IDOR prevention)."""

from TodoApp.models import Todos
from tests.conftest import (
    create_user_in_db,
    extract_csrf,
    get_bearer_token,
    login_browser,
)


def test_user_a_cannot_access_modify_or_delete_user_b_todos(client, db_session):
    user_a = create_user_in_db(db_session, email="usera@example.com", password="password123")
    user_b = create_user_in_db(db_session, email="userb@example.com", password="password123")

    todo_b = Todos(
        title="User B Secret Task",
        description="Private task belonging to B",
        priority=5,
        complete=False,
        owner_id=user_b.id,
    )
    db_session.add(todo_b)
    db_session.commit()
    db_session.refresh(todo_b)

    # API isolation as User A
    token_a = get_bearer_token(client, "usera@example.com", "password123")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    assert client.get("/todos/api/", headers=headers_a).json() == []
    assert client.get(f"/todos/api/{todo_b.id}", headers=headers_a).status_code == 404
    assert (
        client.put(
            f"/todos/api/{todo_b.id}",
            headers=headers_a,
            json={
                "title": "Hijacked",
                "description": "Hijacked desc",
                "priority": 1,
                "complete": True,
            },
        ).status_code
        == 404
    )
    assert client.delete(f"/todos/api/{todo_b.id}", headers=headers_a).status_code == 404

    # User profile endpoint isolation
    assert client.get(f"/users/{user_b.id}", headers=headers_a).status_code == 403
    assert client.get(f"/users/{user_a.id}", headers=headers_a).status_code == 200

    # HTML browser isolation as User A
    login_browser(client, "usera@example.com", "password123")
    home_a = client.get("/")
    assert "User B Secret Task" not in home_a.text
    csrf_a = extract_csrf(client.get("/todos/add-todo").text)

    edit_page = client.get(f"/todos/edit-todo/{todo_b.id}")
    assert edit_page.status_code == 302
    assert "not+found" in edit_page.headers["location"].lower()

    edit_post = client.post(
        f"/todos/edit-todo/{todo_b.id}",
        data={
            "title": "Hijacked",
            "description": "Hijacked desc",
            "priority": "1",
            "complete": "true",
            "csrf_token": csrf_a,
        },
    )
    assert edit_post.status_code == 302

    complete_post = client.post(
        f"/todos/complete/{todo_b.id}",
        data={"csrf_token": csrf_a},
    )
    assert complete_post.status_code == 302

    delete_post = client.post(
        f"/todos/delete/{todo_b.id}",
        data={"csrf_token": csrf_a},
    )
    assert delete_post.status_code == 302

    # Verify User B's todo is completely untouched in the database
    db_session.refresh(todo_b)
    assert todo_b.title == "User B Secret Task"
    assert todo_b.complete is False
    assert todo_b.owner_id == user_b.id
