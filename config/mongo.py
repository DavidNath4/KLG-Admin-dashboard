from flask import current_app
from pymongo import MongoClient
import json, os

CONFIG_FILE = os.path.join("config", "db_config.json")


_client = None
_db = None

def load_db_config():
    """Load konfigurasi MongoDB dari file JSON, fallback ke default."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}

def _load_from_json():
    """Baca konfigurasi default dari JSON jika ada."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("MONGO_URI"), cfg.get("MONGO_DB")
    return "mongodb://localhost:27017/", "LibreChat"  # fallback default


def init_mongo(app):
    """Dipanggil sekali dari app.py untuk membuat 1 koneksi Mongo."""
    global _client, _db

    # Ambil config dari Flask config atau JSON fallback
    uri = app.config.get("MONGO_URI")
    dbname = app.config.get("MONGO_DB")

    if not uri or not dbname:
        uri, dbname = _load_from_json()
        app.config["MONGO_URI"] = uri
        app.config["MONGO_DB"] = dbname

    _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    _client.admin.command("ping")
    _db = _client[dbname]
    app.logger.info(f"[Mongo] Connected to {uri}, db={dbname}")


def get_db():
    """Ambil handle DB yang sama, tanpa buka koneksi baru."""
    if _db is None:
        uri, dbname = _load_from_json()
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return client[dbname]
    return _db


def get_col(name: str):
    """Helper ambil collection."""
    return get_db()[name]


def reload_mongo(app, new_uri: str, new_dbname: str):
    """Dipakai di halaman Settings saat user klik 'Apply'."""
    global _client, _db
    _client = MongoClient(new_uri, serverSelectionTimeoutMS=3000)
    _client.admin.command("ping")
    _db = _client[new_dbname]
    app.config["MONGO_URI"] = new_uri
    app.config["MONGO_DB"] = new_dbname
    app.logger.info(f"[Mongo] Reloaded to {new_uri}, db={new_dbname}")
