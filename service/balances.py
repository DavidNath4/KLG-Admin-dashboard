# service/balances.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from bson import ObjectId
from datetime import datetime
from config.mongo import get_col
from math import ceil

bp = Blueprint("balances", __name__, url_prefix="/admin-klg/admin")


@bp.route("/balances")
def balance_list():
    balances_col = get_col("balances")
    users_col = get_col("users")

    if balances_col is None or users_col is None:
        flash("Database tidak tersedia. Tidak bisa memuat balances.", "danger")
        return render_template(
            "balances.html",
            title="Balance Management",
            active="balances",
            rows=[],
            refill_units=["seconds", "minutes", "hours", "days", "weeks", "months"],
            error="Database tidak tersedia."
        )

    # --- Preload user map ---
    users_map = {
        str(u["_id"]): {"email": u.get("email", "-"), "name": u.get("name", "-")}
        for u in users_col.find({}, {"_id": 1, "email": 1, "name": 1})
    }

    # === Pagination params ===
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = request.args.get("per_page", 10, type=int)
    allowed_per_page = [5, 10, 20, 50, 100]
    if per_page not in allowed_per_page:
        per_page = 10

    total = balances_col.count_documents({})
    total_pages = max(ceil(total / per_page), 1)
    if page > total_pages:
        page = total_pages
    start = (page - 1) * per_page

    # === Sorting params ===
    sort_field = request.args.get("sort", "tokenCredits")
    sort_dir = request.args.get("dir", "desc")
    allowed_sorts = ["tokenCredits", "email", "lastRefill"]
    if sort_field not in allowed_sorts:
        sort_field = "tokenCredits"
    reverse = (sort_dir != "asc")

    # --- Ambil data balances---
    cursor = balances_col.find({}, {
        "user": 1,
        "tokenCredits": 1,
        "autoRefillEnabled": 1,
        "refillAmount": 1,
        "refillIntervalUnit": 1,
        "refillIntervalValue": 1,
        "lastRefill": 1
    }).skip(start).limit(per_page)

    data = []
    for b in cursor:
        user_id = str(b.get("user"))
        user_info = users_map.get(user_id, {"email": "-", "name": "-"})
        last_refill_dt = b.get("lastRefill")
        data.append({
            "id": str(b["_id"]),
            "email": user_info["email"],
            "tokenCredits": b.get("tokenCredits", 0),
            "autoRefillEnabled": b.get("autoRefillEnabled", False),
            "refillAmount": b.get("refillAmount", 0),
            "refillIntervalUnit": b.get("refillIntervalUnit", "-"),
            "refillIntervalValue": b.get("refillIntervalValue", "-"),
            "lastRefill": last_refill_dt or datetime.min
        })

    # === Sorting===
    if sort_field == "email":
        data.sort(key=lambda x: (x.get("email") or "").lower(), reverse=reverse)
    elif sort_field == "lastRefill":
        data.sort(key=lambda x: x.get("lastRefill") or datetime.min, reverse=reverse)
    else:
        data.sort(key=lambda x: float(x.get("tokenCredits", 0)), reverse=reverse)

    # Format lastRefill jadi string untuk ditampilkan
    for d in data:
        d["lastRefill"] = d["lastRefill"].strftime("%Y-%m-%d") if d["lastRefill"] != datetime.min else "-"

    refill_units = ["seconds", "minutes", "hours", "days", "weeks", "months"]

    return render_template(
        "balances.html",
        title="Balance Management",
        active="balances",
        rows=data,
        refill_units=refill_units,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        sort=sort_field,
        dir=sort_dir
    )


@bp.route("/balances/<balance_id>/edit", methods=["POST"])
def edit_balance(balance_id):
    balances_col = get_col("balances")

    if balances_col is None:
        flash("Database tidak tersedia. Tidak bisa update balance.", "danger")
        return redirect(url_for("balances.balance_list"))

    try:
        cur = balances_col.find_one({"_id": ObjectId(balance_id)}, {"tokenCredits": 1})
        if not cur:
            flash("Data balance tidak ditemukan.", "danger")
            return redirect(url_for("balances.balance_list"))

        raw_tokens = (request.form.get("tokenCredits", "") or "").replace(",", "").strip()
        try:
            tokenCredits = float(raw_tokens)
        except ValueError:
            tokenCredits = float(cur.get("tokenCredits", 0))

        if tokenCredits < 0:
            flash("Token balance tidak boleh negatif.", "danger")
            return redirect(url_for("balances.balance_list"))

        balances_col.update_one(
            {"_id": ObjectId(balance_id)},
            {"$set": {
                "tokenCredits": float(tokenCredits),
                "lastRefill": datetime.utcnow()
            }}
        )
        flash("Token balance updated successfully.", "success")

    except Exception as e:
        flash(f"Update failed: {e}", "danger")

    return redirect(url_for("balances.balance_list"))
