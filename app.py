#!/usr/bin/env python3
# app.py — Flask Admin (Simple Dark, Mongo) + Settings (Test/Apply)
from flask import Flask, render_template, send_file,request, redirect, url_for, flash, send_file
from datetime import datetime, timedelta, date, time
from bson import ObjectId
from dotenv import load_dotenv
from time import perf_counter
import os, uuid, re
import pandas as pd
from io import BytesIO
from openpyxl import Workbook

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

def _files_col():
    return client[MONGO_DB]['files'] if client else None

def _human_bytes(n):
    if n is None: return "-"
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:.0f} {unit}" if unit=='B' else f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"

def _parse_date(dstr):
    if not dstr: return None
    try:
        return datetime.strptime(dstr, "%Y-%m-%d")
    except Exception:
        return None

@app.get("/admin/files")
def file_monitoring():
    files_col = _files_col()
    users_col = users  # handle collection users dari koneksi global

    start_str = request.args.get("start", "").strip()
    end_str   = request.args.get("end", "").strip()
    export    = request.args.get("export")

    # Filter by createdAt range
    query = {}
    start_dt = _parse_date(start_str)
    end_dt = _parse_date(end_str)
    if start_dt or end_dt:
        query["createdAt"] = {}
        if start_dt:
            query["createdAt"]["$gte"] = datetime.combine(start_dt, time.min)
        if end_dt:
            query["createdAt"]["$lte"] = datetime.combine(end_dt, time.max)

    rows = []
    if files_col is not None:
        cursor = files_col.find(query).sort("createdAt", -1).limit(1000)
        for doc in cursor:
            # resolve nama user dari users._id
            user_name = None
            if users_col is not None and doc.get("user"):
                u = users_col.find_one({"_id": doc["user"]}, {"name": 1})
                if u:
                    user_name = u.get("name")

            rows.append({
                "createdAt": doc.get("createdAt"),
                "filename":  doc.get("filename"),
                "type":      doc.get("type"),
                "size_h":    _human_bytes(doc.get("bytes")),
                "size":      doc.get("bytes"),
                "user":      user_name or (str(doc.get("user")) if doc.get("user") else None),
                "_id":       str(doc.get("_id")),
                "file_id":   doc.get("file_id"),
            })

    # Export Excel jika diminta
    if export == "1":
        wb = Workbook()
        ws = wb.active
        ws.title = "files"
        headers = ["createdAt","filename","type","size(bytes)","user","_id","file_id"]
        ws.append(headers)
        for r in rows:
            ws.append([
                r["createdAt"].isoformat() if r["createdAt"] else "",
                r["filename"] or "",
                r["type"] or "",
                r["size"] or 0,
                r["user"] or "",
                r["_id"] or "",
                r["file_id"] or "",
            ])
        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)
        fname = f"files_{start_str or 'all'}_{end_str or 'all'}.xlsx"
        return send_file(
            stream,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return render_template(
        "files.html",
        title="File Monitoring",
        active="files",
        rows=rows,
        start=start_str,
        end=end_str
    )

# --- Routes ---
@app.get("/")
def home():
    return redirect(url_for("admin_users"))

# ========== Admin Role Management ==========
@app.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    q = request.args.get("q", "").strip()
    sort_field = request.args.get("sort", "email")  # default sort email
    sort_dir   = request.args.get("dir", "asc")

    # validasi field agar aman
    allowed_fields = {"email", "name", "role"}
    if sort_field not in allowed_fields:
        sort_field = "email"

    direction = 1 if sort_dir == "asc" else -1

    data = []
    if users is not None:
        query = {"email": {"$regex": q, "$options": "i"}} if q else {}
        data = list(
            users.find(query)
                 .sort(sort_field, direction)
                 .limit(50 if q else 10)
        )

    return render_template(
        "users.html",
        title="Set Up Admin",
        active="users",
        users=data,
        q=q,
        users_col=USERS_COL,
        sort=sort_field,
        dir=sort_dir,
    )

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

@app.route("/admin/tokens")
def admin_tokens():
    
    rows = []
    selected_agent = request.args.get("agent", "general")  # default: all
    date_from = request.args.get("date_from", "")          # 'YYYY-MM-DD' atau ''
    date_to   = request.args.get("date_to", "")            # 'YYYY-MM-DD' atau ''
    agents_list = []
    print(selected_agent, date_from, date_to)

    if client is None:
        return render_template(
            "tokens.html",
            title="Token Usage",
            active="tokens",
            rows=rows,
            agents_list=agents_list,
            selected_agent=selected_agent,
            date_from=date_from,
            date_to=date_to,
        )

    # Ambil handle collection dari koneksi yang sama (bukan koneksi baru)
    db = client[MONGO_DB]
    users_col = db[USERS_COL]
    messages_col = db["messages"]
    convos_col = db["conversations"]
    agents_col = db["agents"]

    
    # ---- 1) Prefetch referensi yang dibutuhkan ----
    agents_list = list(agents_col.find({}, {"id": 1, "name": 1}).sort("name", 1))

    agents_map = {
        a["id"]: a.get("model")
        for a in agents_col.find({}, {"id": 1, "model": 1})
    }

    users_cache = {
        str(u["_id"]): {"name": u.get("name", "Unknown"), "email": u.get("email")}
        for u in users_col.find({}, {"name": 1, "email": 1})
    }

    # ---- 2) Ambil BALASAN AGENT (output) saja ----
    assistants_query = {"isCreatedByUser": {"$in": [False, "false", "False", 0]}}

    # Filter agent (jika bukan General)
    if selected_agent != "general":
        assistants_query["model"] = selected_agent

    # Filter tanggal (berbasis createdAt balasan agent)
    # - date_from -> createdAt >= YYYY-MM-DD 00:00:00
    # - date_to   -> createdAt <  (YYYY-MM-DD + 1 hari) 00:00:00  (exclusive)
    created_range = {}
    if date_from:
        try:
            start_dt = datetime.strptime(date_from, "%Y-%m-%d")
            created_range["$gte"] = start_dt
        except ValueError as e:
            print("[WARN] date_from invalid:", date_from, e)

    if date_to:
        try:
            end_dt_exclusive = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            created_range["$lt"] = end_dt_exclusive
        except ValueError as e:
            print("[WARN] date_to invalid:", date_to, e)

    if created_range:
        assistants_query["createdAt"] = created_range


    assistants = list(
        messages_col.find(
            assistants_query,
            {
                "user": 1,
                "model": 1,
                "createdAt": 1,
                "conversationId": 1,
                "tokenCount": 1,
                "parentMessageId": 1,
            },
        )
    )

    # Kumpulkan conversationId & parentMessageId untuk prefetch
    conv_ids = {str(m.get("conversationId")) for m in assistants if m.get("conversationId")}
    parent_ids = [m.get("parentMessageId") for m in assistants if m.get("parentMessageId")]

    # Prefetch conversations.createdAt (fallback saja)
    convos_map = {}
    if conv_ids:
        for c in convos_col.find({"_id": {"$in": list(conv_ids)}}, {"createdAt": 1}):
            convos_map[str(c["_id"])] = c.get("createdAt")

    # Prefetch parent messages
    parents_map = {}
    if parent_ids:
        for p in messages_col.find(
            {"messageId": {"$in": parent_ids}},
            {"messageId": 1, "isCreatedByUser": 1, "tokenCount": 1},
        ):
            parents_map[p.get("messageId")] = p

    # ---- 3) Build data per turn (input dari parent + output dari agent reply) ----
    data = []
    for m in assistants:
        user_id = str(m.get("user"))
        user_info = users_cache.get(user_id, {"name": "Unknown", "email": None})

        model_id_or_name = m.get("model")
        model_name = agents_map.get(model_id_or_name, model_id_or_name or "Unknown Model")

        created_at = m.get("createdAt") or convos_map.get(str(m.get("conversationId")))
        if not created_at:
            continue
        date_str = created_at.date()

        out_tokens = int(m.get("tokenCount", 0) or 0)

        in_tokens = 0
        parent = parents_map.get(m.get("parentMessageId"))
        if parent:
            raw_flag = parent.get("isCreatedByUser", False)
            if isinstance(raw_flag, bool):
                is_user_parent = raw_flag
            else:
                is_user_parent = (str(raw_flag).lower() == "true") or (raw_flag == 1)
            if is_user_parent:
                in_tokens = int(parent.get("tokenCount", 0) or 0)

        data.append({
            "date": str(date_str),
            "name": user_info.get("name", "Unknown"),
            "email": user_info.get("email"),
            "model": model_name,
            "tokens": in_tokens + out_tokens,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "messages_in_turn": 1 + (1 if parent else 0),
        })

    # ---- 4) Agregasi per (date, email, model) ----
    df = pd.DataFrame(data)
    if not df.empty:
        daily_usage = (
            df.groupby(["date", "email", "model"])
              .agg(
                  name=("name", "first"),
                  total_tokens=("tokens", "sum"),
                  input_tokens=("input_tokens", "sum"),
                  output_tokens=("output_tokens", "sum"),
                  total_messages=("messages_in_turn", "sum"),
              )
              .reset_index()
        )
        rows = daily_usage.to_dict(orient="records")
        rows.sort(key=lambda r: (r["date"], r["email"] or "", r["model"] or ""))
    
    now_date = date.today().isoformat()

    # === Export ke Excel (.xlsx) via pandas + openpyxl
    if request.args.get("export") == "xlsx":
        # Pastikan openpyxl ada
        try:
            import openpyxl  # noqa: F401
        except Exception:
            # Bisa juga pakai flash+redirect jika mau, tapi paling simpel: error jelas
            return "openpyxl belum terpasang. Jalankan: pip install openpyxl", 500

        from io import BytesIO
        from flask import send_file

        # Siapkan DataFrame dari rows; meski kosong kita tetap kasih header yang rapi
        df_x = pd.DataFrame(rows)
        if df_x.empty:
            df_x = pd.DataFrame(
                columns=[
                    "date", "name", "email", "model",
                    "total_tokens", "input_tokens", "output_tokens", "total_messages"
                ]
            )

        # Urutkan kolom biar konsisten
        wanted = [
            "date", "name", "email", "model",
            "total_tokens", "input_tokens", "output_tokens", "total_messages"
        ]
        cols = [c for c in wanted if c in df_x.columns]
        df_x = df_x[cols] if cols else df_x

        # Tulis ke buffer Excel
        output = BytesIO()
        filename = f"token-usage_{date_from or 'all'}_{date_to or 'all'}.xlsx"

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_x.to_excel(writer, index=False, sheet_name="Token Usage")
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return render_template(
        "tokens.html",
        title="Token Usage",
        active="tokens",
        rows=rows,
        agents_list=agents_list,
        selected_agent=selected_agent,
        date_from=date_from,
        date_to=date_to,
        now_date=now_date
    )


if __name__ == "__main__":
    app.run(debug=True, port=3000)
