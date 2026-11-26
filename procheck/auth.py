import secrets
from functools import wraps
from threading import Lock
from time import monotonic

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from .models import Account, db_session

auth = Blueprint("auth", __name__)
LOGIN_LOCK = Lock()
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(24))


@auth.before_app_request
def load_account():
    g.account = None
    account_id = session.get("account_id")
    if account_id is not None and request.endpoint != "static":
        with db_session() as db:
            g.account = db.get(Account, account_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.account is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@auth.route("/dang-nhap", methods=["GET", "POST"])
def login():
    if g.account:
        return redirect(url_for("issues.index"))

    error = None
    if request.method == "POST":
        # ProCheck binds to localhost by default. This window is per app process.
        now = monotonic()
        address = request.remote_addr
        with LOGIN_LOCK:
            attempts = current_app.extensions.setdefault("procheck_login_attempts", {})
            for expired in [address for address, (started, _) in attempts.items() if now - started >= 60]:
                del attempts[expired]
            started, count = attempts.get(address, (now, 0))
            if count >= 6:
                abort(429, "Đăng nhập sai nhiều lần. Hãy thử lại sau một phút.")
            attempts[address] = (started, count + 1)

        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        account = None
        if len(username) <= 40 and 1 <= len(password) <= 128:
            with db_session() as db:
                account = db.scalar(select(Account).where(Account.username == username))
                valid = check_password_hash(account.password_hash if account else DUMMY_HASH, password)
            if valid and account:
                with LOGIN_LOCK:
                    attempts.pop(address, None)
                session.clear()
                session.permanent = True
                session["account_id"] = account.id
                return redirect(url_for("issues.index"))

        error = "Tên đăng nhập hoặc mật khẩu chưa đúng."

    return render_template("login.html", error=error), (401 if error else 200)


@auth.post("/dang-xuat")
@login_required
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
