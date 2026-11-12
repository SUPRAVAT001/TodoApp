"""Reconcile NOT NULL constraints, server defaults, owner_id index, and CASCADE FK.

Revision ID: 0002_reconcile_schema
Revises: 0001_initial_schema
Create Date: 2026-11-12 13:46:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_reconcile_schema"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Non-destructively tighten constraints, defaults, index, and FK cascade."""
    # 1. Backfill any NULL values for fields that carry defaults.
    op.execute(sa.text("UPDATE users SET is_active = true WHERE is_active IS NULL"))
    op.execute(sa.text("UPDATE users SET role = 'user' WHERE role IS NULL"))
    op.execute(sa.text("UPDATE todos SET complete = false WHERE complete IS NULL"))

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_todo_indexes = {idx["name"] for idx in inspector.get_indexes("todos")}

    # 2. Enforce server defaults and NOT NULL on users.
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("email", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("username", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("first_name", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("last_name", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("hashed_password", existing_type=sa.String(), nullable=False)
        batch_op.alter_column(
            "is_active",
            existing_type=sa.Boolean(),
            nullable=False,
            existing_server_default=None,
            server_default=sa.text("true"),
        )
        batch_op.alter_column(
            "role",
            existing_type=sa.String(),
            nullable=False,
            existing_server_default=None,
            server_default=sa.text("'user'"),
        )

    # 3. Enforce server defaults, NOT NULL, and ON DELETE CASCADE FK on todos.
    with op.batch_alter_table("todos") as batch_op:
        batch_op.alter_column("title", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("description", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("priority", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "complete",
            existing_type=sa.Boolean(),
            nullable=False,
            existing_server_default=None,
            server_default=sa.text("false"),
        )
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint("todos_owner_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "todos_owner_id_fkey",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if "ix_todos_owner_id" not in existing_todo_indexes:
        op.create_index(op.f("ix_todos_owner_id"), "todos", ["owner_id"], unique=False)


def downgrade() -> None:
    """Revert constraints, server defaults, index, and FK cascade to baseline 0001."""
    op.drop_index(op.f("ix_todos_owner_id"), table_name="todos")

    with op.batch_alter_table("todos") as batch_op:
        batch_op.drop_constraint("todos_owner_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "todos_owner_id_fkey",
            "users",
            ["owner_id"],
            ["id"],
        )
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column(
            "complete",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column("priority", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("description", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("title", existing_type=sa.String(), nullable=True)

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "role",
            existing_type=sa.String(),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column(
            "is_active",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )
        batch_op.alter_column("hashed_password", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("last_name", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("first_name", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("username", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("email", existing_type=sa.String(), nullable=True)

