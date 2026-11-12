"""Authentication, registration, session management, and profile router."""

from datetime import timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import ACCESS_TOKEN_EXPIRE_MINUTES, COOKIE_SECURE
from ..database import get_db
from ..models import Users
from ..schemas import CreateUserRequest, Token, UserResponse
from ..security import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    create_access_token,
    decode_access_token,
    hash_password,
    templates,
    verify_csrf_protection,
    verify_password,
)

oauth2_bearer = OAuth2PasswordBearer(
    tokenUrl="auth/token/login",
    auto_error=False,
)

db_dependency = Annotated[Session, Depends(get_db)]


def _extract_token_from_request(request: Request) -> Optional[str]:
    """Extract JWT from HTTP-only cookie or Authorization Bearer header."""
    cookie_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return token
    return None


def _find_user_by_identifier(identifier: str, db: Session) -> Optional[Users]:
    normalized = identifier.strip().lower()
    return (
        db.query(Users)
        .filter(
            (func.lower(Users.email) == normalized)
            | (func.lower(Users.username) == normalized)
        )
        .first()
    )


def authenticate_user(username: str, password: str, db: Session) -> Users | bool:
    """Verify username/email and password, returning Users instance or False."""
    user = _find_user_by_identifier(username, db)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[Users]:
    """Resolve the active authenticated user for HTML routes (returns None if unauthenticated/inactive)."""
    token = _extract_token_from_request(request)
    if not token:
        return None
    payload = decode_access_token(token)
    if payload is None:
        return None

    user_id = payload.get("user_id")
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None or not user.is_active:
        return None
    return user


async def require_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Users:
    """Strict authentication dependency for protected API endpoints."""
    token = _extract_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(Users).filter(Users.id == payload.get("user_id")).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    return user


async def require_admin_user(
    current_user: Users = Depends(require_current_user),
) -> Users:
    """Strict authorization dependency ensuring the user has the admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return current_user


def redirect_to_login() -> RedirectResponse:
    """Redirect to login page while clearing any stale access cookie."""
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    return response


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


# =========================
# HTML — LOGIN PAGE
# =========================


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    ctx = {"request": request, "user": None}
    if request.query_params.get("registered") == "1":
        ctx["msg"] = "Account created successfully! Please sign in."
        ctx["msg_type"] = "success"
    elif request.query_params.get("logged_out") == "1":
        ctx["msg"] = "You have been signed out."
        ctx["msg_type"] = "info"
    return templates.TemplateResponse(request=request, name="login.html", context=ctx)


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    if request.cookies.get(CSRF_COOKIE_NAME):
        verify_csrf_protection(request, csrf_token)

    user = authenticate_user(username, password, db)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "user": None,
                "msg": "Invalid email or password. Please try again.",
                "msg_type": "danger",
                "entered_email": username.strip(),
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "user": None,
                "msg": "Your account has been deactivated. Contact an administrator.",
                "msg_type": "danger",
                "entered_email": username.strip(),
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    token = create_access_token(
        user.email,
        user.id,
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        role=user.role,
    )
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return response


# =========================
# HTML — REGISTER PAGE
# =========================


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"request": request, "user": None},
    )


@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    if request.cookies.get(CSRF_COOKIE_NAME):
        verify_csrf_protection(request, csrf_token)

    clean_email = email.strip().lower()
    clean_first = first_name.strip()
    clean_last = last_name.strip()

    def _error(message: str, code: int = status.HTTP_400_BAD_REQUEST):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={
                "request": request,
                "user": None,
                "msg": message,
                "msg_type": "danger",
                "form_data": {
                    "email": clean_email,
                    "first_name": clean_first,
                    "last_name": clean_last,
                },
            },
            status_code=code,
        )

    if not clean_first or not clean_last:
        return _error("First name and last name are required.")

    if "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        return _error("Please enter a valid email address.")

    if password != confirm_password:
        return _error("Passwords do not match.")

    if len(password) < 6 or len(password.encode("utf-8")) > 72 or password.isspace():
        return _error("Password must be between 6 and 72 characters.")

    existing = _find_user_by_identifier(clean_email, db)
    if existing:
        return _error("An account with that email already exists.", status.HTTP_409_CONFLICT)

    new_user = Users(
        email=clean_email,
        username=clean_email,
        first_name=clean_first,
        last_name=clean_last,
        hashed_password=hash_password(password),
        role="user",
        is_active=True,
    )
    try:
        db.add(new_user)
        db.commit()
    except IntegrityError:
        db.rollback()
        return _error("An account with that email already exists.", status.HTTP_409_CONFLICT)
    except SQLAlchemyError:
        db.rollback()
        return _error("Unable to create account right now. Please try again.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    return RedirectResponse(url="/auth/login?registered=1", status_code=status.HTTP_302_FOUND)


# =========================
# HTML — LOGOUT
# =========================


@router.get("/logout")
@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login?logged_out=1", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    return response


# =========================
# HTML — PROFILE
# =========================


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={"request": request, "user": user},
    )


@router.post("/change-password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_new_password: str = Form(...),
    csrf_token: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    user = await get_current_user(request, db)
    if not user:
        return redirect_to_login()

    verify_csrf_protection(request, csrf_token)

    ctx = {"request": request, "user": user}

    if len(new_password) < 6 or len(new_password.encode("utf-8")) > 72 or new_password.isspace():
        ctx["msg"] = "New password must be between 6 and 72 characters."
        ctx["msg_type"] = "danger"
        return templates.TemplateResponse(
            request=request, name="profile.html", context=ctx, status_code=status.HTTP_400_BAD_REQUEST
        )

    if new_password != confirm_new_password:
        ctx["msg"] = "New passwords do not match."
        ctx["msg_type"] = "danger"
        return templates.TemplateResponse(
            request=request, name="profile.html", context=ctx, status_code=status.HTTP_400_BAD_REQUEST
        )

    if not verify_password(current_password, user.hashed_password):
        ctx["msg"] = "Current password is incorrect."
        ctx["msg_type"] = "danger"
        return templates.TemplateResponse(
            request=request, name="profile.html", context=ctx, status_code=status.HTTP_400_BAD_REQUEST
        )

    if current_password == new_password:
        ctx["msg"] = "New password must differ from your current password."
        ctx["msg_type"] = "danger"
        return templates.TemplateResponse(
            request=request, name="profile.html", context=ctx, status_code=status.HTTP_400_BAD_REQUEST
        )

    try:
        user.hashed_password = hash_password(new_password)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        ctx["msg"] = "Failed to update password. Please try again."
        ctx["msg_type"] = "danger"
        return templates.TemplateResponse(
            request=request, name="profile.html", context=ctx, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    ctx["msg"] = "Password updated successfully!"
    ctx["msg_type"] = "success"
    return templates.TemplateResponse(request=request, name="profile.html", context=ctx)


# =========================
# API — CREATE USER
# =========================


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
)
async def create_user(
    create_user_request: CreateUserRequest,
    db: Session = Depends(get_db),
):
    clean_email = create_user_request.email.strip().lower()
    if "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email address",
        )

    if _find_user_by_identifier(clean_email, db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    create_user_model = Users(
        email=clean_email,
        username=clean_email,
        first_name=create_user_request.first_name.strip(),
        last_name=create_user_request.last_name.strip(),
        hashed_password=hash_password(create_user_request.password),
        role="user",
        is_active=True,
    )
    try:
        db.add(create_user_model)
        db.commit()
        db.refresh(create_user_model)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while creating user",
        )
    return create_user_model


# =========================
# API — LOGIN (TOKEN)
# =========================


@router.post(
    "/token/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token = create_access_token(
        user.email,
        user.id,
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        role=user.role,
    )
    return Token(access_token=token, token_type="bearer")
