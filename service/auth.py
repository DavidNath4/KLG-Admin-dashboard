# service/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app, flash
from pathlib import Path
import json, hashlib, re

bp = Blueprint("auth", __name__, url_prefix="")

_SHA1_HEX_RE = re.compile(r"^[0-9a-fA-F]{40}$")

def verify_password(plain: str, stored: str) -> bool:
    """Verifikasi password:
    - Jika stored = SHA1 hex (40 char), cek sha1(plain) == stored
    - (Opsional) jika nanti kamu isi format werkzeug (pbkdf2:...), tetap bisa dipakai di masa depan.
    """
    if not stored:
        return False
    if _SHA1_HEX_RE.match(stored):
        return hashlib.sha1(plain.encode("utf-8")).hexdigest().lower() == stored.lower()
    # fallback: dukung hash werkzeug kalau suatu saat diganti
    try:
        from werkzeug.security import check_password_hash
        return check_password_hash(stored, plain)
    except Exception:
        return False

def _load_creds():
    """Baca hanya credentials.json sejajar app.py."""
    try:
        project_root = Path(current_app.root_path)
    except RuntimeError:
        project_root = Path(__file__).resolve().parents[1]
    json_path = (project_root / "credentials.json").resolve()
    current_app.logger.info(f"[Auth] Loading creds from: {json_path}")
    if not json_path.exists():
        current_app.logger.error(f"[Auth] credentials.json tidak ditemukan: {json_path}")
        return None, None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("username"), data.get("password_hash")
    except Exception as e:
        current_app.logger.error(f"[Auth] Gagal baca {json_path}: {e}")
        return None, None

@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("users.admin_users"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        cfg_user, cfg_pw_hash = _load_creds()
        if not cfg_user or not cfg_pw_hash:
            flash("Kredensial belum dikonfigurasi di credentials.json.", "danger")
            return redirect(url_for("auth.login", next=request.args.get("next")))
        if username == cfg_user and verify_password(password, cfg_pw_hash):
            session["logged_in"] = True
            session["admin_username"] = username
            flash("Berhasil masuk.", "success")
            next_url = request.args.get("next") or url_for("users.admin_users")
            return redirect(next_url)
        flash("Username atau password salah.", "danger")
        return redirect(url_for("auth.login", next=request.args.get("next")))
    return render_template("login.html", hide_sidebar=True)

@bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    flash("Anda telah keluar.", "info")
    return redirect(url_for("auth.login"))

@bp.route("/_dev/hash", methods=["GET"])
def dev_hash():
    pwd = request.args.get("p")
    if not pwd:
        return "masukkan ?p=password", 400
    import hashlib
    return hashlib.sha1(pwd.encode()).hexdigest(), 200, {"Content-Type": "text/plain; charset=utf-8"}

