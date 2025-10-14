from flask import current_app
from pymongo import MongoClient, errors
import json, os

CONFIG_FILE = os.path.join("config", "db_config.json")

_client = None
_db = None

def load_db_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}

def _load_from_json():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("MONGO_URI"), cfg.get("MONGO_DB")
    return "mongodb://localhost:27017/", "LibreChat"  # fallback default

def init_mongo(app):
    global _client, _db

    uri = app.config.get("MONGO_URI")
    dbname = app.config.get("MONGO_DB")

    if not uri or not dbname:
        uri, dbname = _load_from_json()
        app.config["MONGO_URI"] = uri
        app.config["MONGO_DB"] = dbname

    try:
        _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        _client.admin.command("ping")
        _db = _client[dbname]
        app.logger.info(f"[Mongo] Connected to {uri}, db={dbname}")
    except errors.ServerSelectionTimeoutError as e:
        app.logger.warning(f"[Mongo] Could not connect to {uri}, db={dbname}: {e}")
        _client, _db = None, None

def get_db():
    global _client, _db
    if _db is None:
        try:
            uri, dbname = _load_from_json()
            client = MongoClient(uri, serverSelectionTimeoutMS=3000)
            client.admin.command("ping")
            return client[dbname]
        except errors.ServerSelectionTimeoutError:
            return None
    return _db

def get_col(name: str):
    db = get_db()
    if db is None:
        return None
    return db[name]

def reload_mongo(app, new_uri: str, new_dbname: str):
    global _client, _db
    try:
        _client = MongoClient(new_uri, serverSelectionTimeoutMS=3000)
        _client.admin.command("ping")
        _db = _client[new_dbname]
        app.config["MONGO_URI"] = new_uri
        app.config["MONGO_DB"] = new_dbname
        app.logger.info(f"[Mongo] Reloaded to {new_uri}, db={new_dbname}")
    except errors.ServerSelectionTimeoutError as e:
        app.logger.warning(f"[Mongo] Reload failed for {new_uri}, db={new_dbname}: {e}")
        _client, _db = None, None
