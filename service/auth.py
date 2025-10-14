# service/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from pathlib import Path
import json
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint("auth", __name__, url_prefix="/admin-klg")

def verify_password(plain: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        return check_password_hash(stored, plain)
    except Exception:
        return False

def _load_creds(username: str):
    try:
        project_root = Path(current_app.root_path)
    except RuntimeError:
        project_root = Path(__file__).resolve().parents[1]
    json_path = (project_root / "credentials.json").resolve()
    current_app.logger.info(f"[Auth] Loading creds")
    if not json_path.exists():
        current_app.logger.error(f"[Auth] credentials file not found")
        return None, None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for cred in data:
                if username == cred.get("username"):
                    return cred.get("username"), cred.get("password_hash")
            return None, None  
    except Exception as e:
        current_app.logger.error(f"[Auth] failed to read creds: {e}")
        return None, None

@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("users.admin_users"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        cfg_user, cfg_pw_hash = _load_creds(username)
        if not cfg_user or not cfg_pw_hash:
            flash("Kredensial belum dikonfigurasi", "danger")
            return redirect(url_for("auth.login", next=request.args.get("next")))
        if username == cfg_user and verify_password(password, cfg_pw_hash):
            session.permanent = True
            session["logged_in"] = True
            session["admin_username"] = username
            flash("Login success.", "success")
            next_url = request.args.get("next") or url_for("users.admin_users")
            return redirect(next_url)
        flash("Wrong username or password.", "danger")
        return redirect(url_for("auth.login", next=request.args.get("next")))
    return render_template("login.html", hide_sidebar=True)

@bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    flash("Logout Success.", "info")
    return redirect(url_for("auth.login"))

@bp.route("/_dev/hash", methods=["GET"])
def dev_hash():
    pwd = request.args.get("p")
    if not pwd:
        return "masukkan ?p=password", 400
    return generate_password_hash(pwd), 200, {"Content-Type": "text/plain; charset=utf-8"}
