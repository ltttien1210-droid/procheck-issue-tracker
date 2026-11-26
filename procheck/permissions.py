from flask import current_app, g


def can_write():
    return not current_app.config["DEMO_READ_ONLY"]


def can_assign():
    return can_write() and g.account.role == "admin"


def can_edit(issue):
    return can_write() and issue.status not in ("testing", "closed") and (
        g.account.role == "admin"
        or (g.account.role == "dev" and issue.assignee_id in (None, g.account.id))
    )


def can_transition(issue):
    if issue.status in ("testing", "closed"):
        return can_write() and g.account.role in ("admin", "tester")
    return can_edit(issue)
