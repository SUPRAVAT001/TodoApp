"""Database engine, session factory, and FastAPI session dependency."""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import DATABASE_URL

SQLALCHEMY_DATABASE_URL = DATABASE_URL

_engine_kwargs: dict = {"pool_pre_ping": True}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and roll back automatically on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()



def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and roll back automatically on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()