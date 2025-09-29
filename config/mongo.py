from flask import current_app
from pymongo import MongoClient

_client = None  # singleton
_db = None      # singleton DB handle

def init_mongo(app):
    """Dipanggil sekali dari app.py untuk membuat 1 koneksi Mongo."""
    global _client, _db
    uri = app.config["MONGO_URI"]
    dbname = app.config["MONGO_DB"]

    _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    _client.admin.command("ping")
    _db = _client[dbname]
    app.logger.info(f"[Mongo] Connected to {uri}, db={dbname}")

def get_db():
    """Ambil handle DB yang sama, tanpa buka koneksi baru."""
    if _db is None:
        # Pada kasus import salah urut, fallback pakai config
        uri = current_app.config["MONGO_URI"]
        dbname = current_app.config["MONGO_DB"]
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
