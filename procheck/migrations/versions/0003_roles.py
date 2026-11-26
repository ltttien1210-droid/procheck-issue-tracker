"""Add account roles and assignment."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.add_column(
        "accounts", sa.Column("role", sa.String(10), nullable=False, server_default="dev"),
    )
    # SQLite accepts a column with an inline REFERENCES clause without rebuilding issues.
    op.execute("ALTER TABLE issues ADD assignee_id INTEGER NULL REFERENCES accounts(id)")
    op.create_index("ix_issues_assignee_id", "issues", ["assignee_id"])


def downgrade():
    raise RuntimeError("Restore the pre-upgrade backup to preserve assignment and role data.")
