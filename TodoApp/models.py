"""SQLAlchemy ORM models for Users and Todos."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship

from .database import Base


class Users(Base):
    """Registered application user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    role = Column(String, default="user", server_default=text("'user'"), nullable=False)

    todos = relationship(
        "Todos",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class Todos(Base):
    """User-owned Todo item."""

    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(String, index=True, nullable=False)
    priority = Column(Integer, nullable=False)
    complete = Column(Boolean, default=False, server_default=text("false"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    owner = relationship("Users", back_populates="todos")
