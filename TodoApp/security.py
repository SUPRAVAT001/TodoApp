"""Security utilities: password hashing, JWT creation/verification, CSRF protection, and Jinja2 templates."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY, TEMPLATES_DIR

CSRF_COOKIE_NAME = "csrf_token"
ACCESS_COOKIE_NAME = "access_token"

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt_context.hash(password)


def create_access_token(
    username: str,
    user_id: int,
    expires_delta: Optional[timedelta] = None,
    role: str = "user",
) -> str:
    """Create a signed HS256 JWT access token with expiration."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expires = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "exp": expires,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate an HS256 JWT access token, returning payload or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") is None or payload.get("user_id") is None:
            return None
        return payload
    except JWTError:
        return None


def _sign_csrf_nonce(nonce: str) -> str:
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        nonce.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_csrf_token() -> str:
    """Generate a random nonce paired with an HMAC-SHA256 signature."""
    nonce = secrets.token_urlsafe(24)
    sig = _sign_csrf_nonce(nonce)
    return f"{nonce}.{sig}"


def is_valid_csrf_token(token: Optional[str]) -> bool:
    """Verify the structural integrity and HMAC signature of a CSRF token."""
    if not token or "." not in token:
        return False
    nonce, sig = token.split(".", 1)
    if not nonce or not sig:
        return False
    expected = _sign_csrf_nonce(nonce)
    return hmac.compare_digest(sig, expected)


def get_csrf_token(request: Request) -> str:
    """Retrieve the active CSRF token for the current request, generating one if needed."""
    token = getattr(request.state, "csrf_token", None)
    if token and is_valid_csrf_token(token):
        return token
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if is_valid_csrf_token(cookie_token):
        request.state.csrf_token = cookie_token
        return cookie_token  # type: ignore[return-value]
    new_token = generate_csrf_token()
    request.state.csrf_token = new_token
    return new_token


def verify_csrf_protection(request: Request, form_token: Optional[str]) -> None:
    """Validate double-submit HMAC-signed CSRF token on cookie-authenticated form requests."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if (
        not cookie_token
        or not form_token
        or not is_valid_csrf_token(cookie_token)
        or not hmac.compare_digest(cookie_token, form_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF verification failed. Please refresh the page and try again.",
        )


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["csrf_token"] = get_csrf_token

