"""Shared Pytest fixtures using an isolated SQLite database and ASGI client."""

import asyncio
import json as json_lib
import os
import re
from http.cookies import SimpleCookie
from typing import Any, Optional
from urllib.parse import urlencode

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Configure isolated test environment BEFORE importing TodoApp modules.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "pytest-isolated-secret-key-0123456789abcdef"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["COOKIE_SECURE"] = "false"

from TodoApp.database import Base, get_db  # noqa: E402
from TodoApp.main import app  # noqa: E402
from TodoApp.models import Users  # noqa: E402
from TodoApp.security import hash_password  # noqa: E402


class ASGIResponse:
    """Minimal HTTP response object compatible with TestClient assertions."""

    def __init__(self, status_code: int, headers: list[tuple[str, str]], body: bytes):
        self.status_code = status_code
        self.raw_headers = headers
        self.headers: dict[str, str] = {}
        for k, v in headers:
            self.headers[k.lower()] = v
        self.content = body
        self.text = body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json_lib.loads(self.text)


class ASGITestClient:
    """Self-contained ASGI client with cookie persistence (works without httpx)."""

    def __init__(self, asgi_app):
        self.app = asgi_app
        self.cookies: dict[str, str] = {}

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        json: Any = None,
        headers: Optional[dict[str, str]] = None,
        follow_redirects: bool = False,
    ) -> ASGIResponse:
        return asyncio.run(
            self._arequest(
                method,
                url,
                params=params,
                data=data,
                json=json,
                headers=headers,
                follow_redirects=follow_redirects,
            )
        )

    async def _arequest(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        json: Any = None,
        headers: Optional[dict[str, str]] = None,
        follow_redirects: bool = False,
    ) -> ASGIResponse:
        path = url
        query_string = ""
        if "?" in url:
            path, query_string = url.split("?", 1)
        if params:
            extra = urlencode(params)
            query_string = f"{query_string}&{extra}" if query_string else extra

        body = b""
        req_headers: list[tuple[bytes, bytes]] = [(b"host", b"testserver")]
        if json is not None:
            body = json_lib.dumps(json).encode("utf-8")
            req_headers.append((b"content-type", b"application/json"))
            req_headers.append((b"content-length", str(len(body)).encode("ascii")))
        elif data is not None:
            body = urlencode(data).encode("utf-8")
            req_headers.append((b"content-type", b"application/x-www-form-urlencoded"))
            req_headers.append((b"content-length", str(len(body)).encode("ascii")))

        if headers:
            for k, v in headers.items():
                req_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

        if self.cookies:
            cookie_header = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            req_headers.append((b"cookie", cookie_header.encode("latin-1")))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query_string.encode("ascii"),
            "headers": req_headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }

        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        status_code = 500
        raw_resp_headers: list[tuple[str, str]] = []
        chunks: list[bytes] = []

        async def send(message):
            nonlocal status_code, raw_resp_headers
            if message["type"] == "http.response.start":
                status_code = message["status"]
                raw_resp_headers = [
                    (k.decode("latin-1").lower(), v.decode("latin-1"))
                    for k, v in message.get("headers", [])
                ]
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        await self.app(scope, receive, send)

        for k, v in raw_resp_headers:
            if k == "set-cookie":
                cookie = SimpleCookie()
                cookie.load(v)
                for name, morsel in cookie.items():
                    if morsel["max-age"] == "0" or morsel.value == "":
                        self.cookies.pop(name, None)
                    else:
                        self.cookies[name] = morsel.value

        resp = ASGIResponse(status_code, raw_resp_headers, b"".join(chunks))
        if follow_redirects and status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if location:
                next_method = "GET" if status_code in (301, 302, 303) else method
                return await self._arequest(
                    next_method,
                    location,
                    follow_redirects=True,
                )
        return resp

    def get(self, url: str, **kwargs) -> ASGIResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> ASGIResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> ASGIResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs) -> ASGIResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs) -> ASGIResponse:
        return self.request("DELETE", url, **kwargs)


@pytest.fixture()
def db_session():
    """Create a fresh isolated in-memory SQLite database for each test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture()
def client(db_session) -> ASGITestClient:
    """Return an isolated ASGI test client."""
    return ASGITestClient(app)


def extract_csrf(html_text: str) -> str:
    """Extract the hidden csrf_token input value from rendered HTML."""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_text)
    assert match, "Expected csrf_token hidden input in HTML form"
    return match.group(1)


def create_user_in_db(
    db_session,
    *,
    email: str,
    password: str = "secret123",
    first_name: str = "Test",
    last_name: str = "User",
    role: str = "user",
    is_active: bool = True,
) -> Users:
    """Insert a user directly into the test database."""
    user = Users(
        email=email.lower(),
        username=email.lower(),
        first_name=first_name,
        last_name=last_name,
        hashed_password=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login_browser(client: ASGITestClient, email: str, password: str) -> ASGIResponse:
    """Perform a full browser-style login including CSRF token."""
    page = client.get("/auth/login")
    csrf = extract_csrf(page.text)
    return client.post(
        "/auth/login",
        data={"username": email, "password": password, "csrf_token": csrf},
    )


def get_bearer_token(client: ASGITestClient, email: str, password: str) -> str:
    """Obtain a JWT Bearer token via /auth/token/login."""
    resp = client.post(
        "/auth/token/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]

