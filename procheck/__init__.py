import os
import secrets
from datetime import timedelta
from hmac import compare_digest
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, abort, render_template, request, session
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import sessionmaker
from werkzeug.exceptions import HTTPException

from .auth import auth
from .commands import register_commands
from .issues import issues


def create_app(test_config=None):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", interpolate=False)
    app = Flask(__name__, instance_relative_config=True)
    trusted_hosts = ["localhost", "127.0.0.1", "[::1]"]
    trusted_hosts.extend(filter(None, (host.strip() for host in os.getenv("PROCHECK_HOSTS", "").split(","))))
    if render_host := os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        trusted_hosts.append(render_host)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        DATABASE_BACKEND=os.getenv("DATABASE_BACKEND", "mssql"),
        MSSQL_ODBC_CONNECTION=os.getenv("MSSQL_ODBC_CONNECTION"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        MAX_CONTENT_LENGTH=64 * 1024,
        TRUSTED_HOSTS=trusted_hosts,
        DEMO_READ_ONLY=os.getenv("PROCHECK_DEMO_READ_ONLY") == "1",
    )
    app.config.update(test_config or {})

    if len(app.config["SECRET_KEY"] or "") < 32:
        raise RuntimeError("Hãy đặt SECRET_KEY ngẫu nhiên (ít nhất 32 ký tự) trong .env.")

    backend = app.config["DATABASE_BACKEND"]
    if backend == "mssql":
        connection = app.config["MSSQL_ODBC_CONNECTION"]
        if not connection:
            raise RuntimeError("Thiếu MSSQL_ODBC_CONNECTION trong .env.")
        url = URL.create("mssql+pyodbc", query={"odbc_connect": connection})
    elif backend == "sqlite":
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        path = app.config.get("SQLITE_PATH", Path(app.instance_path) / "procheck.sqlite")
        url = URL.create("sqlite", database=str(path))
    else:
        raise RuntimeError("DATABASE_BACKEND phải là mssql hoặc sqlite.")

    engine = create_engine(url, pool_pre_ping=True)
    if backend == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    app.extensions["procheck_engine"] = engine
    app.extensions["procheck_session"] = sessionmaker(engine)

    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.before_request
    def protect_post():
        if request.method == "POST":
            if request.blueprint == "issues" and app.config["DEMO_READ_ONLY"]:
                abort(403, "Bản demo trực tuyến chỉ cho phép xem.")
            expected = session.get("_csrf", "").encode("utf-8")
            supplied = request.form.get("_csrf", "").encode("utf-8")
            if not expected or not compare_digest(expected, supplied):
                abort(400, "Phiên biểu mẫu đã hết hạn. Hãy tải lại trang và thử lại.")

    @app.after_request
    def set_response_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.template_filter("local_time")
    def local_time(value):
        utc = ZoneInfo("UTC")
        return value.replace(tzinfo=utc).astimezone(
            ZoneInfo("Asia/Ho_Chi_Minh")
        ).strftime("%H:%M · %d/%m/%Y")

    @app.errorhandler(HTTPException)
    def http_error(error):
        return render_template("error.html", error=error), error.code

    app.register_blueprint(auth)
    app.register_blueprint(issues)
    register_commands(app)
    return app
