#!/usr/bin/env python3
from flask import Flask, redirect, url_for, request, session, flash
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
import os

# Extensions
from config.mongo import init_mongo, load_db_config

# Blueprints
from service.users import bp as users_bp
from service.categories import bp as categories_bp
from service.settings import bp as settings_bp
from service.tokens import bp as tokens_bp
from service.files import bp as files_bp
from service.balances import bp as balances_bp
from service.auth import bp as auth_bp


def home():
    """Route untuk redirect ke halaman utama Admin Users"""
    return redirect(url_for("users.admin_users"))


def create_app():
    load_dotenv()
    app = Flask(__name__)

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=3600,  # 1 jam
        SESSION_REFRESH_EACH_REQUEST=True
    )

    app.secret_key = os.getenv("SECRET_KEY", "super-secret")
    
    # Initialize CSRF Protection
    csrf = CSRFProtect(app)
    
    # CSRF Error Handler
    @app.errorhandler(400)
    def handle_csrf_error(e):
        if e.description == "The CSRF token is missing." or "CSRF" in str(e.description):
            flash("Security token expired. Please try again.", "danger")
            return redirect(request.url or url_for("auth.login"))
        return e

    # Load config Mongo dari JSON
    cfg = load_db_config()
    app.config["MONGO_URI"] = cfg["MONGO_URI"]
    app.config["MONGO_DB"] = cfg["MONGO_DB"]
    app.config["USERS_COL"] = os.getenv("USERS_COL", "users")
    app.config["CATS_COL"] = os.getenv("CATS_COL", "agentcategories")

    # Init Mongo (dengan fallback error handling)
    try:
        init_mongo(app)
    except Exception as e:
        app.logger.error(f"[Mongo] Gagal inisialisasi: {e}")

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(tokens_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(balances_bp)

    # Proteksi semua route /admin/* wajib login
    @app.before_request
    def _protect_admin():
        path = request.path or ""
        # allowlist: static, login, dev hash (opsional), favicon
        allowed = (
            path.startswith("/login")
            or path.startswith("/_dev/hash")
            or path.startswith("/static/")
            or path == "/favicon.ico"
            or path == "/"
        )
        if allowed:
            return
        # jika akses /admin/* tapi belum login -> redirect ke /login?next=<path>
        if path.startswith("/admin-klg/admin/") and not session.get("logged_in"):
            return redirect(url_for("auth.login", next=path))
        
    
    @app.after_request
    def add_no_cache(resp):
        p = request.path or ""
        if p.startswith("/admin-klg/admin/"):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp

    # Route home
    app.add_url_rule("/", "home", home)

    


    return app


if __name__ == "__main__":
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 3000)),
        debug=os.getenv("DEBUG", "false").lower() == "true"
    )
