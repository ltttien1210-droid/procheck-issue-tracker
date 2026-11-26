import re

import click
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .models import Account, Base, Issue, IssueEvent, Verification, db_session


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create tables in the configured database."""
        Base.metadata.create_all(app.extensions["procheck_engine"])
        click.echo("Đã sẵn sàng cơ sở dữ liệu ProCheck.")

    @app.cli.command("create-user")
    @click.argument("username")
    @click.password_option(confirmation_prompt=True)
    def create_user(username, password):
        """Create a local workspace account."""
        username = username.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.-]{3,40}", username):
            raise click.ClickException("Tên đăng nhập từ 3–40 ký tự a-z, 0-9, dấu chấm, gạch nối hoặc gạch dưới.")
        if not 12 <= len(password) <= 128:
            raise click.ClickException("Mật khẩu phải có 12–128 ký tự.")
        with db_session() as db:
            db.add(Account(username=username, password_hash=generate_password_hash(password)))
            try:
                db.commit()
            except IntegrityError as error:
                raise click.ClickException("Tên đăng nhập đã được sử dụng.") from error
        click.echo(f"Đã tạo tài khoản {username}.")

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
