import re
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.security import check_password_hash

from procheck import create_app
from procheck.models import Account, Issue, IssueEvent, Verification, db_session


class ProCheckTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-000000000000000000000",
            "DATABASE_BACKEND": "sqlite",
            "SQLITE_PATH": Path(folder.name) / "test.sqlite",
            "SESSION_COOKIE_SECURE": False,
        })
        self.addCleanup(self.app.extensions["procheck_engine"].dispose)
        self.client = self.app.test_client()
        cli = self.app.test_cli_runner()
        result = cli.invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)
        result = cli.invoke(
            args=["create-user", "tester"],
            input="Only-for-tests!77\nOnly-for-tests!77\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)

    def login(self, password="Only-for-tests!77"):
        page = self.client.get("/dang-nhap")
        token = re.search(r'name="_csrf" value="([^"]+)"', page.text).group(1)
        return self.client.post("/dang-nhap", data={
            "_csrf": token, "username": "tester", "password": password,
        })

    def csrf(self):
        self.client.get("/")
        with self.client.session_transaction() as session:
            return session["_csrf"]

    def create_issue(self, **overrides):
        data = {
            "_csrf": self.csrf(),
            "title": "Lỗi kiểm thử 100%",
            "description": "Mô tả lỗi khi sử dụng chức năng đăng nhập.",
            "severity": "high",
            "assignee": "Tiên",
        }
        return self.client.post("/loi/moi", data=data | overrides)

    def version(self, path):
        page = self.client.get(path)
        return re.search(r'name="version" value="(\d+)"', page.text).group(1)

    def move(self, path, status, note="", version=None, **verification):
        return self.client.post(path + "/trang-thai", data={
            "_csrf": self.csrf(), "status": status, "note": note,
            "version": self.version(path) if version is None else version,
        } | verification)

    def test_auth_csrf_and_cookie(self):
        self.assertEqual(self.client.get("/").location, "/dang-nhap")
        self.assertEqual(self.login(password="invalid").status_code, 401)
        login = self.login()
        self.assertEqual(login.status_code, 302)
        self.assertIn("HttpOnly", login.headers["Set-Cookie"])
        self.assertIn("SameSite=Lax", login.headers["Set-Cookie"])
        self.assertEqual(self.client.post("/loi/moi").status_code, 400)
        self.assertEqual(self.create_issue(_csrf="ấ").status_code, 400)
        self.assertEqual(self.client.get("/dang-xuat").status_code, 405)
        self.assertEqual(self.client.post("/dang-xuat", data={"_csrf": self.csrf()}).status_code, 302)
        self.assertEqual(self.client.get("/loi/moi").location, "/dang-nhap")
        with self.app.app_context(), db_session() as db:
            account = db.scalar(select(Account))
            self.assertNotIn("Only-for-tests", account.password_hash)
            self.assertTrue(check_password_hash(account.password_hash, "Only-for-tests!77"))

    def test_login_throttle(self):
        for _ in range(6):
            self.assertEqual(self.login(password="invalid").status_code, 401)
        self.assertEqual(self.login().status_code, 429)

    def test_workflow_and_history(self):
        self.login()
        created = self.create_issue()
        self.assertEqual(created.status_code, 303)
        path = created.location
        original = self.version(path)
        self.assertEqual(self.move(path, "closed").status_code, 409)
        self.assertEqual(self.move(path, "in_progress").status_code, 303)
        self.assertEqual(self.move(path, "testing", version=original).status_code, 409)
        self.assertEqual(self.move(path, "testing").status_code, 303)
        self.assertEqual(self.move(path, "in_progress").status_code, 422)
        self.assertEqual(self.move(
            path, "in_progress", "Vẫn tái hiện lỗi trên máy QA.", environment="Chrome", build="v1.0",
        ).status_code, 303)
        self.assertEqual(self.move(path, "testing").status_code, 303)
        rejected = self.move(path, "closed", "Đã kiểm thử lại.", environment="Chrome")
        self.assertEqual(rejected.status_code, 422)
        self.assertIn("Đã kiểm thử lại.", rejected.text)
        self.assertEqual(self.move(
            path, "closed", "Đã kiểm thử lại.", environment="Safari <b>", build="v1.1",
        ).status_code, 303)
        self.assertEqual(self.client.get(path + "/sua").status_code, 409)
        detail = self.client.get(path).text
        self.assertIn("Đã kiểm thử lại.", detail)
        self.assertIn("Safari &lt;b&gt; · v1.1", detail)
        self.assertIn("Chrome · v1.0", detail)
        dashboard = self.client.get("/bao-cao").text
        self.assertIn("50%", dashboard)
        self.assertIn("Phiếu kiểm thử gần đây", dashboard)
        self.assertIn("Safari &lt;b&gt; · v1.1", dashboard)
        with self.app.app_context(), db_session() as db:
            issue = db.scalar(select(Issue))
            self.assertEqual(issue.status, "closed")
            self.assertEqual(len(db.scalars(select(IssueEvent)).all()), 6)
            self.assertEqual(len(db.scalars(select(Verification)).all()), 2)

    def test_validation_search_and_escaping(self):
        self.login()
        self.assertEqual(self.create_issue(title="x", severity="bad").status_code, 422)
        self.assertEqual(self.create_issue(title="\x00Invalid title").status_code, 422)
        large_title = "🔧" * 61
        self.assertEqual(self.create_issue(title=large_title).status_code, 422)
        created = self.create_issue(title='<b>Kiểm thử 100%</b>', description="ệ" * 4000)
        page = self.client.get(created.location)
        self.assertIn("&lt;b&gt;Kiểm thử 100%&lt;/b&gt;", page.text)
        self.assertIn("frame-ancestors 'none'", page.headers["Content-Security-Policy"])
        self.assertIn("no-store", page.headers["Cache-Control"])
        self.create_issue(title="Lỗi khác", severity="low")
        matched = self.client.get("/", query_string={"severity": "high", "q": "%"}).text
        self.assertIn("1 kết quả", matched)
        self.assertNotIn("Lỗi khác", matched)
        self.assertIn("0 kết quả", self.client.get("/?q=%27%20OR%201%3D1").text)
        self.assertEqual(self.client.get("/?severity=invalid").status_code, 400)

    def test_edit_and_stale_form(self):
        self.login()
        path = self.create_issue().location
        stale_version = self.version(path)
        data = {
            "_csrf": self.csrf(), "version": stale_version, "title": "Nội dung đã cập nhật",
            "description": "Các bước tái hiện đầy đủ.", "severity": "medium", "assignee": "An",
        }
        self.assertEqual(self.client.post(path + "/sua", data=data).status_code, 303)
        self.assertEqual(self.client.post(path + "/sua", data=data).status_code, 409)
        detail = self.client.get(path).text
        self.assertIn("Nội dung đã cập nhật", detail)
        self.assertIn("Đã sửa tiêu đề, mô tả, mức độ, người xử lý.", detail)

    def test_concurrent_database_update_rolls_back_history(self):
        self.login()
        self.create_issue()
        with self.app.app_context(), db_session() as first, db_session() as second:
            first_copy = first.scalar(select(Issue))
            second_copy = second.scalar(select(Issue))
            first_copy.title = "Thay đổi đã được lưu"
            first.commit()
            second_copy.title = "Thay đổi cạnh tranh"
            second.add(IssueEvent(
                issue_id=second_copy.id, actor_id=1, action="edited", note="Không được lưu.",
            ))
            with self.assertRaises(StaleDataError):
                second.commit()
            second.rollback()
            self.assertEqual(second.get(Issue, second_copy.id).title, "Thay đổi đã được lưu")
            self.assertEqual(len(second.scalars(select(IssueEvent)).all()), 1)

    def test_upgrade_preserves_existing_issues_and_events(self):
        self.login()
        path = self.create_issue(title="Lỗi dữ liệu từ V1").location
        engine = self.app.extensions["procheck_engine"]
        Verification.__table__.drop(engine)
        self.assertEqual(self.app.test_cli_runner().invoke(args=["init-db"]).exit_code, 0)
        self.assertIn("Lỗi dữ liệu từ V1", self.client.get(path).text)
        self.assertIn("Tạo báo cáo", self.client.get(path).text)
        dashboard = self.client.get("/bao-cao")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Lỗi dữ liệu từ V1", dashboard.text)
        self.assertIn("Chưa có phiếu kiểm thử.", dashboard.text)

    def test_seed_and_pagination(self):
        cli = self.app.test_cli_runner()
        for _ in range(2):
            result = cli.invoke(args=["seed-demo", "tester"])
            self.assertEqual(result.exit_code, 0, result.output)
        self.login()
        self.assertIn("4 kết quả", self.client.get("/").text)
        self.assertIn("50%", self.client.get("/bao-cao").text)
        self.assertIn("Staging · Chrome", self.client.get("/bao-cao").text)
        for index in range(13):
            self.assertEqual(self.create_issue(title=f"Lỗi lọc trang {index}").status_code, 303)
        view = self.client.get("/?severity=high&q=L%E1%BB%97i+l%E1%BB%8Dc+trang&page=999").text
        self.assertIn("Trang 2 / 2", view)
        self.assertIn("Lỗi lọc trang 0", view)
        self.assertNotIn("Lỗi lọc trang 12", view)


if __name__ == "__main__":
    unittest.main()
