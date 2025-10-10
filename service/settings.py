from flask import Blueprint, render_template, request, flash, current_app, redirect, url_for
from time import perf_counter
from config.mongo import init_mongo, reload_mongo
from pymongo import MongoClient
import json
import os

CONFIG_FILE = os.path.join("config", "db_config.json")

def db_exists(uri, dbname):
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        dblist = client.list_database_names()
        return dbname in dblist
    except Exception:
        return False


def load_db_config():
    """Load konfigurasi MongoDB dari file JSON dengan fallback default."""
    if not os.path.exists(CONFIG_FILE):
        return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"MONGO_URI": "mongodb://localhost:27017/", "MONGO_DB": "LibreChat"}


def save_db_config(uri: str, dbname: str):
    """Simpan konfigurasi MongoDB ke file JSON."""
    cfg = {"MONGO_URI": uri, "MONGO_DB": dbname}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

bp = Blueprint("settings", __name__, url_prefix="/admin-klg/admin")

@bp.route("/settings", methods=["GET", "POST"])
def db_settings():
    # Load default config dari JSON
    cfg = load_db_config()
    uri = request.form.get("MONGO_URI", cfg["MONGO_URI"])
    dbname = request.form.get("MONGO_DB", cfg["MONGO_DB"])
    action = request.form.get("action")
    test_result = None

    if request.method == "POST":
        if action == "test":
            try:
                t0 = perf_counter()
                _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
                _client.admin.command("ping")

                if not db_exists(uri, dbname):
                    test_result = {"ok": False, "message": f"⚠️ DB '{dbname}' belum ada di server"}
                else:
                    _ = list(_client[dbname].list_collections())
                    dt = (perf_counter() - t0) * 1000
                    test_result = {"ok": True, "message": f"✅ Koneksi OK ke {dbname} ({dt:.0f} ms)"}
            except Exception as e:
                test_result = {"ok": False, "message": f"❌ Failled to connect: {e}"}

        elif action == "save":
            try:
                save_db_config(uri, dbname)
                flash("Konfigurasi disimpan ke db_config.json")
            except Exception as e:
                flash(f"Gagal menyimpan konfigurasi: {e}")
            return redirect(url_for("settings.db_settings"))

        elif action == "apply":
            try:
                save_db_config(uri, dbname)
                reload_mongo(current_app, uri, dbname)
                flash("Koneksi Mongo berhasil di-apply.")
            except Exception as e:
                flash(f"Gagal apply koneksi: {e}")
            return redirect(url_for("settings.db_settings"))

    
    return render_template(
        "settings.html",
        title="DB Settings",
        active="settings",
        MONGO_URI=uri,
        MONGO_DB=dbname,
        test_result=test_result,
    )
