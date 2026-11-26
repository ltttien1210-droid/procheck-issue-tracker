from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm.exc import StaleDataError

from .auth import login_required
from .models import (
    SEVERITIES, STATUSES, TRANSITIONS, Account, Issue, IssueEvent, Verification, db_session,
)

issues = Blueprint("issues", __name__)
PAGE_SIZE = 12


@issues.app_context_processor
def issue_labels():
    return {
        "severities": SEVERITIES,
        "statuses": STATUSES,
        "transition_labels": {
            "in_progress": "Bắt đầu xử lý",
            "testing": "Gửi kiểm thử",
            "closed": "Xác nhận và đóng lỗi",
        },
    }


@issues.get("/")
@login_required
def index():
    severity = request.args.get("severity", "")
    status = request.args.get("status", "")
    search = request.args.get("q", "").strip()[:120]
    if (severity and severity not in SEVERITIES) or (status and status not in STATUSES):
        abort(400, "Bộ lọc không hợp lệ.")

    conditions = []
    if severity:
        conditions.append(Issue.severity == severity)
    if status:
        conditions.append(Issue.status == status)
    if "\x00" in search:
        abort(400, "Từ khóa tìm kiếm chứa ký tự không hợp lệ.")
    if search:
        escaped = search.replace("/", "//").replace("%", "/%").replace("_", "/_").replace("[", "/[")
        pattern = f"%{escaped}%"
        conditions.append(or_(Issue.title.ilike(pattern, escape="/"), Issue.assignee.ilike(pattern, escape="/")))

    with db_session() as db:
        counts = dict(db.execute(select(Issue.status, func.count()).group_by(Issue.status)).all())
        total = db.scalar(select(func.count()).select_from(Issue).where(*conditions))
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(max(1, request.args.get("page", 1, type=int)), pages)
        rows = db.scalars(
            select(Issue).where(*conditions)
            .order_by(Issue.updated_at.desc(), Issue.id.desc())
            .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
        ).all()

    return render_template(
        "index.html", rows=rows, counts=counts, total=total, page=page,
        pages=pages, severity=severity, status=status, search=search,
    )


@issues.get("/bao-cao")
@login_required
def dashboard():
    with db_session() as db:
        severity_counts = dict(db.execute(
            select(Issue.severity, func.count())
            .where(Issue.status != "closed")
            .group_by(Issue.severity)
        ).all())
        outcomes = dict(db.execute(
            select(IssueEvent.next_status, func.count())
            .where(IssueEvent.action == "status", IssueEvent.previous_status == "testing")
            .group_by(IssueEvent.next_status)
        ).all())
        blockers = db.scalars(
            select(Issue)
            .where(Issue.status != "closed", Issue.severity.in_(("critical", "high")))
            .order_by(
                case((Issue.severity == "critical", 0), else_=1),
                Issue.updated_at.desc(), Issue.id.desc(),
            )
            .limit(8)
        ).all()
        recent = db.execute(
            select(IssueEvent, Issue.title, Account.username, Verification)
            .select_from(IssueEvent)
            .join(Verification, Verification.event_id == IssueEvent.id)
            .join(Issue, Issue.id == IssueEvent.issue_id)
            .join(Account, Account.id == IssueEvent.actor_id)
            .order_by(IssueEvent.created_at.desc(), IssueEvent.id.desc())
            .limit(6)
        ).all()
    passed = outcomes.get("closed", 0)
    returned = outcomes.get("in_progress", 0)
    total = passed + returned
    return render_template(
        "dashboard.html", severity_counts=severity_counts, open_total=sum(severity_counts.values()),
        blockers=blockers, recent=recent, passed=passed, returned=returned,
        pass_rate=(round(100 * passed / total) if total else None),
    )


@issues.get("/loi/<int:issue_id>")
@login_required
def detail(issue_id):
    with db_session() as db:
        issue = get_issue(db, issue_id)
        return render_detail(db, issue)


def render_detail(db, issue, values=None, errors=None):
    events = db.execute(
        select(IssueEvent, Account.username, Verification)
        .select_from(IssueEvent)
        .join(Account, Account.id == IssueEvent.actor_id)
        .outerjoin(Verification, Verification.event_id == IssueEvent.id)
        .where(IssueEvent.issue_id == issue.id)
        .order_by(IssueEvent.id.desc())
    ).all()
    return render_template(
        "detail.html", issue=issue, events=events, transitions=TRANSITIONS[issue.status],
        values=values or {}, errors=errors or {},
    ), (422 if errors else 200)


@issues.route("/loi/moi", methods=["GET", "POST"])
@issues.route("/loi/<int:issue_id>/sua", methods=["GET", "POST"])
@login_required
def issue_form(issue_id=None):
    errors = {}
    with db_session() as db:
        issue = get_issue(db, issue_id) if issue_id is not None else None
        if issue and issue.status == "closed":
            abort(409, "Báo cáo đã đóng. Thông tin được giữ lại để tra cứu.")

        values = {
            "title": issue.title if issue else "",
            "description": issue.description if issue else "",
            "severity": issue.severity if issue else "medium",
            "assignee": issue.assignee if issue else "",
        }
        if request.method == "POST":
            if issue:
                check_version(issue)
            values = {field: request.form.get(field, "").strip() for field in values}
            errors = validate_issue(values)
            if not errors:
                if issue is None:
                    issue = Issue(**values)
                    db.add(issue)
                    db.flush()
                    record_event(db, issue, "created", next_status="new")
                    message = "Đã tạo báo cáo lỗi."
                else:
                    fields = {
                        "title": "tiêu đề", "description": "mô tả",
                        "severity": "mức độ", "assignee": "người xử lý",
                    }
                    changed = [field for field in values if getattr(issue, field) != values[field]]
                    for field in changed:
                        setattr(issue, field, values[field])
                    if changed:
                        record_event(db, issue, "edited", note="Đã sửa " + ", ".join(fields[field] for field in changed) + ".")
                    message = "Đã lưu báo cáo." if changed else "Chưa có thay đổi."
                saved_id = issue.id
                commit(db)
                flash(message)
                return redirect(url_for("issues.detail", issue_id=saved_id), code=303)

    return render_template("form.html", issue=issue, values=values, errors=errors), (422 if errors else 200)


@issues.post("/loi/<int:issue_id>/trang-thai")
@login_required
def change_status(issue_id):
    with db_session() as db:
        issue = get_issue(db, issue_id)
        check_version(issue)
        target = request.form.get("status")
        if target not in TRANSITIONS[issue.status]:
            abort(409, "Không thể chuyển sang trạng thái này từ trạng thái hiện tại.")

        values = {field: request.form.get(field, "").strip() for field in ("note", "environment", "build")}
        values["status"] = target
        previous = issue.status
        is_verification = previous == "testing"
        errors = validate_transition(values, is_verification)
        if errors:
            return render_detail(db, issue, values, errors)

        # Both the transition and its evidence belong to the same transaction.
        issue.status = target
        event = record_event(db, issue, "status", previous, target, values["note"])
        if is_verification:
            db.add(Verification(
                event=event, environment=values["environment"], build=values["build"],
            ))
        commit(db)

    flash(f"Đã chuyển sang trạng thái {STATUSES[target]}.")
    return redirect(url_for("issues.detail", issue_id=issue_id), code=303)


def validate_transition(values, is_verification):
    errors = {}
    limits = {"note": 500}
    if is_verification:
        limits.update(environment=120, build=80)
    for field, limit in limits.items():
        value = values[field]
        if "\x00" in value or utf16_length(value) > limit:
            errors[field] = f"Nhập văn bản hợp lệ, tối đa {limit} ký tự."
        elif is_verification and not value:
            errors[field] = "Hãy nhập thông tin này để lưu kết quả kiểm thử."
    return errors


def utf16_length(value):
    # SQL Server NVARCHAR(n) counts UTF-16 code units. An emoji can take two.
    return len(value.encode("utf-16-le")) // 2


def validate_issue(values):
    errors = {}
    for field, minimum, maximum, label in (
        ("title", 5, 120, "Tiêu đề"),
        ("description", 10, 4000, "Mô tả"),
        ("assignee", 0, 80, "Người xử lý"),
    ):
        value = values[field]
        if len(value) < minimum or utf16_length(value) > maximum or "\x00" in value:
            limit = f"từ {minimum} đến {maximum} ký tự" if minimum else f"tối đa {maximum} ký tự"
            errors[field] = f"{label} cần có độ dài {limit} và chứa văn bản hợp lệ."
    if values["severity"] not in SEVERITIES:
        errors["severity"] = "Hãy chọn một mức độ hợp lệ."
    return errors


def get_issue(db, issue_id):
    issue = db.get(Issue, issue_id)
    if issue is None:
        abort(404, "Không tìm thấy báo cáo lỗi.")
    return issue


def check_version(issue):
    if request.form.get("version", type=int) != issue.version:
        abort(409, "Báo cáo đã thay đổi. Hãy mở lại trang chi tiết trước khi tiếp tục.")


def record_event(db, issue, action, previous_status=None, next_status=None, note=""):
    event = IssueEvent(
        issue_id=issue.id,
        actor_id=g.account.id,
        action=action,
        previous_status=previous_status,
        next_status=next_status,
        note=note,
    )
    db.add(event)
    return event


def commit(db):
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        abort(409, "Báo cáo vừa được cập nhật. Hãy tải lại trang để xem dữ liệu mới.")
