from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from bson import ObjectId
from datetime import datetime
from config.mongo import get_col
from utils.helper import kebab
import uuid

bp = Blueprint("categories", __name__, url_prefix="/admin")

def next_order(cats_col):
    last = list(cats_col.find().sort("order", -1).limit(1))
    return (last[0]["order"] + 1) if last else 1

def ensure_unique_value(cats_col, base: str) -> str:
    v = base
    i = 0
    while cats_col.count_documents({"value": v}, limit=1) > 0:
        i += 1
        v = f"{base}-{i}"
    return v

@bp.route("/categories", methods=["GET", "POST"])
def categories():
    cats_col = get_col(current_app.config["CATS_COL"])
    if cats_col is None:
        flash("Database tidak tersedia. Tidak bisa mengakses kategori.")
        return render_template("categories.html", title="Categories", active="categories", cats=[])
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Nama kategori wajib diisi.")
            return redirect(url_for("categories.categories"))

        slug = kebab(name)
        value = ensure_unique_value(cats_col, slug)

        doc = {
            "id": uuid.uuid4().hex,
            "name": name,
            "slug": slug,
            "value": value,
            "label": value,
            "description": f"com_agents_category_{value}_description",
            "order": next_order(cats_col),
            "isActive": True,
            "custom": True,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
            "__v": 0,
        }
        cats_col.insert_one(doc)
        flash("Kategori ditambahkan.")
        return redirect(url_for("categories.categories"))

    data = list(cats_col.find().sort("order", 1))
    return render_template("categories.html", title="Categories", active="categories", cats=data, cats_col=current_app.config["CATS_COL"])

@bp.post("/categories/<id>/move/<direction>")
def move_category(id, direction):
    cats_col = get_col(current_app.config["CATS_COL"])
    
    if cats_col is None:
        flash("Database tidak tersedia. Tidak bisa memindahkan kategori.")
        return redirect(url_for("categories.categories"))
    
    arr = list(cats_col.find().sort("order", 1))
    idx = next((i for i, c in enumerate(arr) if str(c["_id"]) == id), None)
    if idx is None:
        flash("Item tidak ditemukan.")
        return redirect(url_for("categories.categories"))

    if direction == "up" and idx > 0:
        arr[idx]["order"], arr[idx-1]["order"] = arr[idx-1]["order"], arr[idx]["order"]
        a, b = arr[idx], arr[idx-1]
        cats_col.update_one({"_id": a["_id"]}, {"$set": {"order": a["order"], "updatedAt": datetime.utcnow()}})
        cats_col.update_one({"_id": b["_id"]}, {"$set": {"order": b["order"], "updatedAt": datetime.utcnow()}})
    elif direction == "down" and idx < len(arr) - 1:
        arr[idx]["order"], arr[idx+1]["order"] = arr[idx+1]["order"], arr[idx]["order"]
        a, b = arr[idx], arr[idx+1]
        cats_col.update_one({"_id": a["_id"]}, {"$set": {"order": a["order"], "updatedAt": datetime.utcnow()}})
        cats_col.update_one({"_id": b["_id"]}, {"$set": {"order": b["order"], "updatedAt": datetime.utcnow()}})
    else:
        flash("Tidak bisa dipindah.")
        return redirect(url_for("categories.categories"))

    # Normalisasi
    arr = list(cats_col.find().sort("order", 1))
    for i, c in enumerate(arr, start=1):
        if c.get("order") != i:
            cats_col.update_one({"_id": c["_id"]}, {"$set": {"order": i, "updatedAt": datetime.utcnow()}})
    flash("Urutan diperbarui.")
    return redirect(url_for("categories.categories"))

@bp.post("/categories/<id>/delete")
def delete_category(id):
    cats_col = get_col(current_app.config["CATS_COL"])
    if cats_col is None:
        flash("Database tidak tersedia. Tidak bisa menghapus kategori.")
        return redirect(url_for("categories.categories"))
    cats_col.delete_one({"_id": ObjectId(id)})
    arr = list(cats_col.find().sort("order", 1))
    for i, c in enumerate(arr, start=1):
        if c.get("order") != i:
            cats_col.update_one({"_id": c["_id"]}, {"$set": {"order": i, "updatedAt": datetime.utcnow()}})
    flash("Kategori dihapus.")
    return redirect(url_for("categories.categories"))
