# service/balances.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from bson import ObjectId
from datetime import datetime
from config.mongo import get_col

bp = Blueprint("balances", __name__, url_prefix="/admin")

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

    users_map = {
        str(u["_id"]): {"email": u.get("email", "-"), "name": u.get("name", "-")}
        for u in users_col.find({}, {"_id": 1, "email": 1, "name": 1})
    }
    data = []
    for b in balances_col.find().sort("tokenCredits", -1):
        user_id = str(b.get("user"))
        user_info = users_map.get(user_id, {"email": "-", "name": "-"})
        last_refill_dt = b.get("lastRefill")
        last_refill = last_refill_dt.strftime("%Y-%m-%d") if last_refill_dt else "-"
        data.append({
            "id": str(b["_id"]),
            "email": user_info["email"],
            "name": user_info["name"],
            "tokenCredits": b.get("tokenCredits", 0),
            "autoRefillEnabled": b.get("autoRefillEnabled", False),
            "refillAmount": b.get("refillAmount", 0),
            "refillIntervalUnit": b.get("refillIntervalUnit", "-"),
            "refillIntervalValue": b.get("refillIntervalValue", "-"),
            "lastRefill": last_refill
        })
    # --- untuk dropdown refillIntervalUnit, hardcode default ("days", "weeks", dst)
    refill_units = ["seconds", "minutes", "hours", "days", "weeks", "months"]  # referensi dari LibreChat docs
    return render_template(
        "balances.html",
        title="Balance Management",
        active="balances",
        rows=data,
        refill_units=refill_units,
    )

@bp.route("/balances/<balance_id>/edit", methods=["POST"])
def edit_balance(balance_id):
    balances_col = get_col("balances")

    if balances_col is None:
        flash("Database tidak tersedia. Tidak bisa update balance.", "danger")
        return redirect(url_for("balances.balance_list"))

    try:
        # Ambil doc sekarang untuk fallback default
        cur = balances_col.find_one({"_id": ObjectId(balance_id)}, {
            "refillAmount": 1,
            "refillIntervalUnit": 1,
            "refillIntervalValue": 1,
            "tokenCredits": 1,
            "autoRefillEnabled": 1
        }) or {}

        # --- Parse & sanitize input ---
        raw_tokens = (request.form.get("tokenCredits", "") or "").replace(",", "").strip()
        raw_tokens = raw_tokens.replace(" ", "")
        tokenCredits = float(raw_tokens) if raw_tokens not in ("", ".", "-") else float(cur.get("tokenCredits", 0))

        autoRefillEnabled = (request.form.get("autoRefillEnabled", "off") == "on")

        # gunakan get() agar tidak 400 jika field tidak terkirim (disabled)
        refillAmount = request.form.get("refillAmount", None)
        refillIntervalValue = request.form.get("refillIntervalValue", None)
        refillIntervalUnit = request.form.get("refillIntervalUnit", None)

        # fallback ke nilai existing bila None/empty
        try:
            refillAmount = int(refillAmount) if refillAmount not in (None, "") else int(cur.get("refillAmount", 0))
        except ValueError:
            refillAmount = int(cur.get("refillAmount", 0))

        try:
            refillIntervalValue = int(refillIntervalValue) if refillIntervalValue not in (None, "") else int(cur.get("refillIntervalValue", 0))
        except ValueError:
            refillIntervalValue = int(cur.get("refillIntervalValue", 0))

        refillIntervalUnit = (refillIntervalUnit or cur.get("refillIntervalUnit", "days"))

        # Jika OFF, paksa amount/value ke 0 (unit boleh dibiarkan)
        if not autoRefillEnabled:
            refillAmount = 0
            refillIntervalValue = 0

        # --- Update ---
        balances_col.update_one(
            {"_id": ObjectId(balance_id)},
            {"$set": {
                "tokenCredits": float(tokenCredits),
                "autoRefillEnabled": bool(autoRefillEnabled),
                "refillAmount": int(refillAmount),
                "refillIntervalUnit": str(refillIntervalUnit),
                "refillIntervalValue": int(refillIntervalValue),
                "lastRefill": datetime.utcnow()
            }}
        )
        flash("Balance updated!", "success")

    except Exception as e:
        # BadRequestKeyError, ValueError, dsb. tertangkap di sini
        flash(f"Update failed: {e}", "danger")

    return redirect(url_for("balances.balance_list"))
