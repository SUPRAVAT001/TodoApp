"""FastAPI TodoApp entrypoint, middleware, home route, and router wiring."""

import os
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import COOKIE_SECURE, ENVIRONMENT, STATIC_DIR
from .database import get_db
from .models import Todos
from .routers import admin, auth, todos, users
from .routers.auth import get_current_user, redirect_to_login
from .security import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    is_valid_csrf_token,
    templates,
)

docs_enabled: bool = (ENVIRONMENT != "production") or (
    os.getenv("ENABLE_API_DOCS", "false").lower() in ("true", "1", "yes")
)

app = FastAPI(
    title="TodoApp",
    version="1.0.0",
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def csrf_cookie_middleware(request: Request, call_next):
    """Ensure every browser session holds a valid HMAC-signed CSRF cookie."""
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    if is_valid_csrf_token(existing):
        request.state.csrf_token = existing
        should_set_cookie = False
    else:
        token = generate_csrf_token()
        request.state.csrf_token = token
        should_set_cookie = True

    response = await call_next(request)
    if should_set_cookie:
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=request.state.csrf_token,
            httponly=True,
            samesite="lax",
            secure=COOKIE_SECURE,
            path="/",
        )
    return response


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    """Render the authenticated user's todo dashboard."""
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()

    user_todos = (
        db.query(Todos)
        .filter(Todos.owner_id == user.id)
        .order_by(Todos.complete.asc(), Todos.priority.desc(), Todos.id.asc())
        .all()
    )

    msg = request.query_params.get("msg")
    msg_type = request.query_params.get("msg_type", "info")
    if msg_type not in ("info", "success", "danger", "warning"):
        msg_type = "info"

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "request": request,
            "user": user,
            "todos": user_todos,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


app.include_router(auth.router)
app.include_router(todos.router)
app.include_router(admin.router)
app.include_router(users.router)
