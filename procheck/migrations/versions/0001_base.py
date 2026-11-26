"""Create accounts, issues and events."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(40), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
    )
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Unicode(120), nullable=False),
        sa.Column("description", sa.Unicode(4000), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("assignee", sa.Unicode(80), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_issue_severity"),
        sa.CheckConstraint("status IN ('new','in_progress','testing','closed')", name="ck_issue_status"),
    )
    op.create_index("ix_issue_status_severity", "issues", ["status", "severity"])
    op.create_table(
        "issue_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("issue_id", sa.Integer, sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("action", sa.String(12), nullable=False),
        sa.Column("previous_status", sa.String(16)),
        sa.Column("next_status", sa.String(16)),
        sa.Column("note", sa.Unicode(500), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_issue_events_issue_id", "issue_events", ["issue_id"])


def downgrade():
    op.drop_table("issue_events")
    op.drop_table("issues")
    op.drop_table("accounts")
