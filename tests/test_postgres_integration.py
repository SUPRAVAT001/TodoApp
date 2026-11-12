"""PostgreSQL integration tests against an isolated TEST_DATABASE_URL."""

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from TodoApp.database import get_db
from TodoApp.main import app
from TodoApp.models import Base, Todos, Users
from TodoApp.security import hash_password
from tests.conftest import ASGITestClient, get_bearer_token

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")


@pytest.mark.skipif(
    not TEST_DATABASE_URL or not TEST_DATABASE_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL (PostgreSQL) not configured; skipping live PostgreSQL test",
)
def test_postgresql_connectivity_constraints_and_api_lifecycle():
    """Verify PostgreSQL connectivity, schema constraints, cascade delete, and FastAPI CRUD."""
    if "TodoApplicationDB" in TEST_DATABASE_URL:
        pytest.fail("Refusing to run destructive integration test against TodoApplicationDB")

    pg_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)

    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1

    Base.metadata.drop_all(bind=pg_engine)
    Base.metadata.create_all(bind=pg_engine)

    inspector = inspect(pg_engine)
    tables = set(inspector.get_table_names())
    assert {"users", "todos"}.issubset(tables)

    def override_get_db():
        db = Session()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db = Session()
    try:
        # 1. Unique constraint check on email/username
        u1 = Users(
            email="pguser@example.com",
            username="pguser@example.com",
            first_name="PG",
            last_name="One",
            hashed_password=hash_password("password123"),
            role="user",
            is_active=True,
        )
        db.add(u1)
        db.commit()
        db.refresh(u1)

        dup = Users(
            email="pguser@example.com",
            username="pguser@example.com",
            first_name="PG",
            last_name="Dup",
            hashed_password=hash_password("password123"),
            role="user",
            is_active=True,
        )
        db.add(dup)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 2. Foreign key constraint check on owner_id
        orphan_todo = Todos(
            title="Orphan Todo",
            description="Invalid owner id",
            priority=3,
            complete=False,
            owner_id=999999,
        )
        db.add(orphan_todo)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 3. End-to-end FastAPI API CRUD over PostgreSQL
        client = ASGITestClient(app)
        token = get_bearer_token(client, "pguser@example.com", "password123")
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/todos/api/",
            headers=headers,
            json={
                "title": "PostgreSQL Todo",
                "description": "Persisted in PostgreSQL",
                "priority": 4,
                "complete": False,
            },
        )
        assert created.status_code == 201
        todo_id = created.json()["id"]

        listed = client.get("/todos/api/", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert listed.json()[0]["id"] == todo_id

        # 4. Cascade delete check
        db.query(Users).filter(Users.id == u1.id).delete()
        db.commit()
        assert db.query(Todos).filter(Todos.id == todo_id).count() == 0
    finally:
        db.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=pg_engine)
        pg_engine.dispose()
