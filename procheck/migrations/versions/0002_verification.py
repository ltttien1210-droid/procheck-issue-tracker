"""Add verification details."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table(
        "issue_verifications",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("issue_events.id"), primary_key=True, autoincrement=False),
        sa.Column("environment", sa.Unicode(120), nullable=False),
        sa.Column("build", sa.Unicode(80), nullable=False),
    )


def downgrade():
    op.drop_table("issue_verifications")
