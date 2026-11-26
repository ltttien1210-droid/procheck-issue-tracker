"""Integration test against the disposable SQL Server database in CI."""

import os
import unittest
from uuid import uuid4

from sqlalchemy import select

from procheck import create_app
from procheck.models import Account, Issue, Verification, db_session


@unittest.skipUnless(os.getenv("MSSQL_ODBC_CONNECTION"), "Requires a SQL Server connection")
class SQLServerSmokeTest(unittest.TestCase):
    def test_migration_and_unicode_issue_workflow(self):
        app = create_app({"TESTING": True, "SESSION_COOKIE_SECURE": False})
        self.addCleanup(app.extensions["procheck_engine"].dispose)
        self.assertEqual(app.extensions["procheck_engine"].dialect.name, "mssql")
        cli = app.test_cli_runner()
        for _ in range(2):
            result = cli.invoke(args=["db-upgrade"])
            self.assertEqual(result.exit_code, 0, result.output)
        username = f"ci-{uuid4().hex[:8]}"
        result = cli.invoke(args=["create-user", username, "--role", "admin", "--password", "Test-sql-only-987!"])
        self.assertEqual(result.exit_code, 0, result.output)
        with app.app_context(), db_session() as db:
            account_id = db.scalar(select(Account.id).where(Account.username == username))

        client = app.test_client()
        with client.session_transaction() as session:
            session["account_id"] = account_id
            session["_csrf"] = "test-token"

        created = client.post("/loi/moi", data={
            "_csrf": "test-token", "title": "Kiểm thử tiếng Việt 🔧",
            "description": "Mô tả kiểm thử với chuỗi Unicode.", "severity": "critical",
            "assignee_id": str(account_id),
        })
        self.assertEqual(created.status_code, 303)
        path = created.location
        self.assertIn("Kiểm thử tiếng Việt", client.get("/?mine=1&q=ti%E1%BA%BFng").text)
        for version, target in enumerate(("in_progress", "testing", "closed"), 1):
            saved = client.post(path + "/trang-thai", data={
                "_csrf": "test-token", "version": version, "status": target,
                "environment": "Chrome", "build": "v2.1", "note": "Đã kiểm thử lại.",
            })
            self.assertEqual(saved.status_code, 303)
        self.assertIn("Chrome · v2.1", client.get("/bao-cao").text)
        with app.app_context(), db_session() as db:
            issue = db.get(Issue, int(path.rsplit("/", 1)[-1]))
            self.assertEqual(issue.status, "closed")
            self.assertEqual(issue.assignee_id, account_id)
            self.assertIn("🔧", issue.title)
            self.assertIsNotNone(db.scalar(select(Verification.event_id).where(Verification.build == "v2.1")))
