"""Application configuration loaded from environment variables and optional .env file."""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def _load_dotenv_file(env_path: Path) -> None:
    """Load key=value pairs from a .env file without overriding existing env vars."""
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_path, override=False)
        return
    except ImportError:
        pass

    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_file(PROJECT_ROOT / ".env")
_load_dotenv_file(BASE_DIR / ".env")

ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres@localhost:5432/TodoApplicationDB",
)

# Ephemeral runtime secret fallback prevents hardcoded secrets in source control.
_EPHEMERAL_SECRET = secrets.token_urlsafe(32)
SECRET_KEY: str = os.getenv("SECRET_KEY") or _EPHEMERAL_SECRET

ALGORITHM: str = "HS256"

try:
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60

COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
TEMPLATES_DIR: Path = BASE_DIR / "templates"
STATIC_DIR: Path = BASE_DIR / "static"

