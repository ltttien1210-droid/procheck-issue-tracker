import re

import click
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .migration import upgrade_database
from .models import ROLES, Account, Issue, IssueEvent, Verification, db_session


def register_commands(app):
    @app.cli.command("db-upgrade")
    def db_upgrade():
        """Apply database migrations."""
        upgrade_database(app.extensions["procheck_engine"])
        click.echo("Đã sẵn sàng cơ sở dữ liệu ProCheck.")

    app.cli.add_command(db_upgrade, "init-db")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.option("--role", type=click.Choice(list(ROLES)), default="dev", show_default=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, envvar="PROCHECK_USER_PASSWORD")
    def create_user(username, role, password):
        """Create a workspace account."""
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
            raise click.ClickException("Tên đăng nhập từ 3–40 ký tự a-z, 0-9, dấu chấm, gạch nối hoặc gạch dưới.")
        if not 12 <= len(password) <= 128:
            raise click.ClickException("Mật khẩu phải có 12–128 ký tự.")
        with db_session() as db:
            db.add(Account(username=username, role=role, password_hash=generate_password_hash(password)))
            try:
                db.commit()
            except IntegrityError as error:
                raise click.ClickException("Tên đăng nhập đã được sử dụng.") from error
        click.echo(f"Đã tạo tài khoản {username} ({role}).")

    @app.cli.command("set-role")
    @click.argument("username")
    @click.argument("role", type=click.Choice(list(ROLES)))
    def set_role(username, role):
        """Change a workspace account's role."""
        with db_session() as db:
            account = db.scalar(select(Account).where(Account.username == username.lower()))
            if account is None:
                raise click.ClickException("Không tìm thấy tài khoản.")
            if role == "tester" and db.scalar(select(Issue.id).where(Issue.assignee_id == account.id).limit(1)):
                raise click.ClickException("Hãy chuyển các báo cáo đang giao cho tài khoản này trước.")
            account.role = role
            db.commit()
        click.echo(f"Đã cập nhật vai trò của {username} thành {role}.")

    @app.cli.command("prepare-public-demo")
    @click.pass_context
    def prepare_public_demo(ctx):
        """Prepare the read-only public dataset and account."""
        if not app.config["DEMO_READ_ONLY"] or app.config["DATABASE_BACKEND"] != "sqlite":
            raise click.ClickException("Chỉ dùng cho demo SQLite ở chế độ chỉ xem.")
        with db_session() as db:
            exists = db.scalar(select(Account.id).where(Account.username == "demo"))
        if exists is None:
            ctx.invoke(create_user, username="demo", role="tester", password="ProCheck-Demo-2026!")
        ctx.invoke(seed_demo, username="demo")

    @app.cli.command("seed-demo")
    @click.argument("username")
    def seed_demo(username):
        """Populate an empty workspace with sample reports."""
        rows = [
            ("Không đăng nhập được sau khi đổi mật khẩu", "Đăng nhập bằng mật khẩu mới. Hệ thống báo thông tin không hợp lệ.", "critical", "new", ""),
            ("Bộ lọc tìm kiếm bị mất khi chuyển trang", "Lọc theo mức độ Cao rồi bấm trang tiếp theo. Danh sách bị bỏ lọc.", "high", "in_progress", "Minh"),
            ("Sai định dạng ngày trên màn hình lịch sử", "Ngày hiển thị theo dạng tháng/ngày. Kỳ vọng ngày/tháng/năm.", "medium", "testing", "Hà"),
            ("Nút lưu xuống dòng trên điện thoại", "Mở biểu mẫu tại chiều rộng 390px. Kiểm tra hàng nút ở cuối form.", "low", "closed", "An"),
        ]
        with db_session() as db:
            account = db.scalar(select(Account).where(Account.username == username.lower()))
            if account is None:
                raise click.ClickException("Hãy tạo tài khoản trước khi nạp dữ liệu mẫu.")
            if db.scalar(select(Issue.id).limit(1)) is not None:
                click.echo("Danh sách đã có dữ liệu. Bỏ qua dữ liệu mẫu.")
                return
            sample_reviews = {
                "in_progress": "Lỗi vẫn xuất hiện khi sang trang thứ hai sau khi lọc theo mức độ Cao.",
                "closed": "Nút lưu hiển thị đúng trên chiều rộng 390px và gửi biểu mẫu thành công.",
            }
            for title, description, severity, status, assignee in rows:
                issue = Issue(title=title, description=description, severity=severity, status=status, assignee=assignee)
                db.add(issue)
                db.flush()
                note = sample_reviews.get(status)
                db.add(IssueEvent(
                    issue_id=issue.id, actor_id=account.id, action="seed",
                    next_status="testing" if note else status,
                ))
                if note:
                    db.flush()
                    review_event = IssueEvent(
                        issue_id=issue.id, actor_id=account.id, action="status",
                        previous_status="testing", next_status=status, note=note,
                    )
                    db.add(Verification(event=review_event, environment="Staging · Chrome", build="v1.0.1"))
            db.commit()
        click.echo("Đã tạo 4 báo cáo mẫu.")
