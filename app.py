#!/usr/bin/env python3
# app.py — Flask Admin (Simple Dark, Mongo) + Settings (Test/Apply)
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime
from bson import ObjectId
from dotenv import load_dotenv
from time import perf_counter
import os, uuid, re

# --- Load ENV ---
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB  = os.getenv("MONGO_DB", "LibreChat")
USERS_COL = os.getenv("USERS_COL", "users")
CATS_COL  = os.getenv("CATS_COL", "agentcategories")
SECRET    = os.getenv("SECRET_KEY", "super-secret")

# --- App setup ---
app = Flask(__name__)
app.secret_key = SECRET

client = None
users = None
cats  = None

def connect_mongo(uri: str, dbname: str):
    """Return (client, db, users_col, cats_col); raises on error."""
    from pymongo import MongoClient
    _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    _client.admin.command("ping")  # will raise if cannot connect
    _db = _client[dbname]
    return _client, _db, _db[USERS_COL], _db[CATS_COL]

# Initial connect (best effort)
try:
    client, _db, users, cats = connect_mongo(MONGO_URI, MONGO_DB)
    print("[INFO] Mongo connected at", MONGO_URI, "db:", MONGO_DB)
except Exception as e:
    print("[WARN] Mongo initial connect failed:", e)

# --- Helpers ---
def kebab(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")

def next_order() -> int:
    if cats is None:
        return 1
    last = list(cats.find().sort("order", -1).limit(1))
    return (last[0]["order"] + 1) if last else 1

def ensure_unique_value(base: str) -> str:
    """
    Pastikan 'value' unik di collection categories.
    Jika sudah ada 'base', tambahkan -1, -2, ... hingga unik.
    """
    if cats is None:
        return base
    v = base
    i = 0
    while cats.count_documents({"value": v}, limit=1) > 0:
        i += 1
        v = f"{base}-{i}"
    return v

def reload_mongo(uri: str, dbname: str):
    global client, users, cats, MONGO_URI, MONGO_DB
    client, _db, users, cats = connect_mongo(uri, dbname)
    MONGO_URI = uri
    MONGO_DB  = dbname

def upsert_env(path: str, key: str, value: str):
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

# --- Routes ---
@app.get("/")
def home():
    return redirect(url_for("admin_users"))

# ========== Admin Role Management ==========
@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    q = request.args.get("q", "").strip()
    data = []
    if users is not None:
        if q:
            # hasil pencarian
            data = list(users.find({"email": {"$regex": q, "$options": "i"}}).limit(50))
        else:
            # default: 10 user random
            data = list(users.aggregate([{"$sample": {"size": 10}}]))
    return render_template("users.html", title="Set Up Admin", active="users", users=data, q=q, users_col=USERS_COL)

@app.post("/admin/users/<id>/role")
def change_role(id):
    new_role = request.form.get("role", "").strip()
    if users is None or not new_role:
        flash("Role tidak boleh kosong atau DB tidak terhubung.")
        return redirect(url_for("admin_users", q=request.args.get("q", "")))
    users.update_one({"_id": ObjectId(id)}, {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}})
    flash("Role berhasil diubah.")
    return redirect(url_for("admin_users", q=request.args.get("q", "")))

# ========== Category Configuration ==========
@app.route("/admin/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Nama kategori wajib diisi.")
            return redirect(url_for("categories"))

        # value & label harus sama (unik). Basisnya pakai slug dari name.
        slug = kebab(name)
        unique_val = ensure_unique_value(slug)
        # value == label
        value = unique_val
        label = unique_val

        guid = uuid.uuid4().hex  # masih simpan id unik internal jika dibutuhkan
        doc = {
            "id": guid,
            "name": name,
            "slug": slug,
            "value": value,
            "label": label,
            "description": f"com_agents_category_{value}_description",
            "order": next_order(),
            "isActive": True,
            "custom": True,  # dibuat dari UI
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "__v": 0,
        }
        if cats is not None:
            cats.insert_one(doc)
            flash("Kategori ditambahkan.")
        else:
            flash("DB tidak terhubung, penyimpanan dibatalkan.")
        return redirect(url_for("categories"))

    data = list(cats.find().sort("order", 1)) if cats is not None else []
    return render_template("categories.html", title="Categories", active="categories", cats=data, cats_col=CATS_COL)

@app.post("/admin/categories/<id>/move/<direction>")
def move_category(id, direction):
    if cats is None:
        flash("DB tidak terhubung.")
        return redirect(url_for("categories"))
    arr = list(cats.find().sort("order", 1))
    idx = next((i for i, c in enumerate(arr) if str(c["_id"]) == id), None)
    if idx is None:
        flash("Item tidak ditemukan.")
        return redirect(url_for("categories"))

    if direction == "up" and idx > 0:
        arr[idx]["order"], arr[idx-1]["order"] = arr[idx-1]["order"], arr[idx]["order"]
        a, b = arr[idx], arr[idx-1]
        cats.update_one({"_id": a["_id"]}, {"$set": {"order": a["order"], "updatedAt": datetime.utcnow()}})
        cats.update_one({"_id": b["_id"]}, {"$set": {"order": b["order"], "updatedAt": datetime.utcnow()}})
    elif direction == "down" and idx < len(arr) - 1:
        arr[idx]["order"], arr[idx+1]["order"] = arr[idx+1]["order"], arr[idx]["order"]
        a, b = arr[idx], arr[idx+1]
        cats.update_one({"_id": a["_id"]}, {"$set": {"order": a["order"], "updatedAt": datetime.utcnow()}})
        cats.update_one({"_id": b["_id"]}, {"$set": {"order": b["order"], "updatedAt": datetime.utcnow()}})
    else:
        flash("Tidak bisa dipindah.")
        return redirect(url_for("categories"))

    # normalisasi 1..n
    arr = list(cats.find().sort("order", 1))
    for i, c in enumerate(arr, start=1):
        if c.get("order") != i:
            cats.update_one({"_id": c["_id"]}, {"$set": {"order": i, "updatedAt": datetime.utcnow()}})
    flash("Urutan diperbarui.")
    return redirect(url_for("categories"))

@app.post("/admin/categories/<id>/delete")
def delete_category(id):
    if cats is None:
        flash("DB tidak terhubung.")
        return redirect(url_for("categories"))
    cats.delete_one({"_id": ObjectId(id)})
    arr = list(cats.find().sort("order", 1))
    for i, c in enumerate(arr, start=1):
        if c.get("order") != i:
            cats.update_one({"_id": c["_id"]}, {"$set": {"order": i, "updatedAt": datetime.utcnow()}})
    flash("Kategori dihapus.")
    return redirect(url_for("categories"))

# ========== DB Settings (test / save / apply) ==========
@app.route("/admin/settings", methods=["GET", "POST"])
def db_settings():
    global MONGO_URI, MONGO_DB
    uri = request.form.get("MONGO_URI", MONGO_URI)
    dbname = request.form.get("MONGO_DB", MONGO_DB)
    action = request.form.get("action")

    test_result = None
    if request.method == "POST":
        if action == "test":
            try:
                t0 = perf_counter()
                _client, _db, _users, _cats = connect_mongo(uri, dbname)
                _ = list(_db.list_collections())
                dt = (perf_counter() - t0) * 1000
                test_result = {"ok": True, "message": f"✅ Koneksi OK ({dt:.0f} ms)"}
            except Exception as e:
                test_result = {"ok": False, "message": f"❌ Gagal konek: {e}"}
        elif action == "save":
            try:
                env_path = os.path.join(os.getcwd(), ".env")
                upsert_env(env_path, "MONGO_URI", uri)
                upsert_env(env_path, "MONGO_DB", dbname)
                flash("Konfigurasi disimpan ke .env")
            except Exception as e:
                flash(f"Gagal menyimpan .env: {e}")
        elif action == "apply":
            try:
                reload_mongo(uri, dbname)
                flash("Koneksi Mongo berhasil di-apply.")
            except Exception as e:
                flash(f"Gagal apply koneksi: {e}")

    return render_template(
        "settings.html",
        title="DB Settings",
        active="settings",
        MONGO_URI=uri,
        MONGO_DB=dbname,
        test_result=test_result,
    )

if __name__ == "__main__":
    app.run(debug=True, port=3000)
