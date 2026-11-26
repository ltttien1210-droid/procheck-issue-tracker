from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Unicode,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ROLES = {"admin": "Admin", "dev": "Developer", "tester": "Tester"}

STATUSES = {
    "new": "Mới",
    "in_progress": "Đang xử lý",
    "testing": "Chờ kiểm thử",
    "closed": "Đã đóng",
}
SEVERITIES = {"low": "Thấp", "medium": "Trung bình", "high": "Cao", "critical": "Nghiêm trọng"}
TRANSITIONS = {
    "new": ("in_progress",),
    "in_progress": ("testing",),
    "testing": ("closed", "in_progress"),
    "closed": ("in_progress",),
}


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def db_session():
    return current_app.extensions["procheck_session"]()


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="dev", server_default="dev")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_issue_severity"),
        CheckConstraint("status IN ('new','in_progress','testing','closed')", name="ck_issue_status"),
        Index("ix_issue_status_severity", "status", "severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Unicode(120))
    description: Mapped[str] = mapped_column(Unicode(4000))
    severity: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(16), default="new")
    assignee: Mapped[str] = mapped_column(Unicode(80), default="")
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), index=True)
    assignee_account: Mapped[Account | None] = relationship()

    @property
    def assignee_name(self):
        if self.assignee_account:
            return self.assignee_account.username
        return self.assignee

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    __mapper_args__ = {"version_id_col": version}


class IssueEvent(Base):
    __tablename__ = "issue_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    action: Mapped[str] = mapped_column(String(12))
    previous_status: Mapped[str | None] = mapped_column(String(16))
    next_status: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Unicode(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Verification(Base):
    """Store the extra QA information for one status event."""

    __tablename__ = "issue_verifications"

    event_id: Mapped[int] = mapped_column(
        ForeignKey("issue_events.id"), primary_key=True, autoincrement=False
    )
    event: Mapped[IssueEvent] = relationship()
    environment: Mapped[str] = mapped_column(Unicode(120))
    build: Mapped[str] = mapped_column(Unicode(80))
