#!/usr/bin/env python3
from flask import Flask, redirect, url_for
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


def home():
    """Route untuk redirect ke halaman utama Admin Users"""
    return redirect(url_for("users.admin_users"))


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "super-secret")

    # Load config Mongo dari JSON
    cfg = load_db_config()
    app.config["MONGO_URI"] = cfg["MONGO_URI"]
    app.config["MONGO_DB"] = cfg["MONGO_DB"]
    app.config["USERS_COL"] = os.getenv("USERS_COL", "users")
    app.config["CATS_COL"] = os.getenv("CATS_COL", "agentcategories")

    # Init Mongo
    init_mongo(app)

    # Register Blueprints
    app.register_blueprint(users_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(tokens_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(balances_bp)

    # Daftarkan route home (tanpa def dalam def)
    app.add_url_rule("/", "home", home)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=3000)
