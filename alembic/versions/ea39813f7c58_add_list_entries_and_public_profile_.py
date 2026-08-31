"""add list entries and public profile default

Revision ID: ea39813f7c58
Revises: 4cf4354b2928
Create Date: 2026-08-31 05:38:16.007197

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ea39813f7c58'
down_revision: Union[str, Sequence[str], None] = '4cf4354b2928'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bio", sa.String(length=280), nullable=True))
    op.add_column("users", sa.Column("avatar", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("backdrop", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("username_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "profile_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.create_table(
        "list_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("position >= 1 AND position <= 5", name="position_range"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "type", "position"),
        sa.UniqueConstraint("user_id", "type", "item_id"),
    )
    op.create_index(
        op.f("ix_list_entries_user_id"), "list_entries", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_list_entries_type"), "list_entries", ["type"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_list_entries_type"), table_name="list_entries")
    op.drop_index(op.f("ix_list_entries_user_id"), table_name="list_entries")
    op.drop_table("list_entries")
    op.drop_column("users", "profile_public")
    op.drop_column("users", "username_changed_at")
    op.drop_column("users", "backdrop")
    op.drop_column("users", "avatar")
    op.drop_column("users", "bio")
