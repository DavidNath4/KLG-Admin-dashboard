from flask import Blueprint, render_template, request, redirect, url_for, flash
from bson import ObjectId
from config.mongo import get_col
from datetime import datetime

bp = Blueprint("users", __name__, url_prefix="/admin")

@bp.route("/users", methods=["GET", "POST"])
def admin_users():
    q = request.args.get("q", "").strip()
    sort_field = request.args.get("sort", "email")
    sort_dir   = request.args.get("dir", "asc")
    allowed_fields = {"email", "name", "role"}
    if sort_field not in allowed_fields:
        sort_field = "email"
    direction = 1 if sort_dir == "asc" else -1

    users_col = get_col(request.app.config["USERS_COL"]) if hasattr(request, "app") else get_col("users")
    data = []
    if users_col is not None:
        query = {"email": {"$regex": q, "$options": "i"}} if q else {}
        data = list(
            users_col.find(query)
                     .sort(sort_field, direction)
                     .limit(50 if q else 10)
        )

    return render_template(
        "users.html",
        title="Set Up Admin",
        active="users",
        users=data,
        q=q,
        users_col=(request.app.config["USERS_COL"] if hasattr(request, "app") else "users"),
        sort=sort_field,
        dir=sort_dir,
    )

@bp.post("/users/<id>/role")
def change_role(id):
    users_col = get_col("users")
    new_role = request.form.get("role", "").strip()
    if users_col is None or not new_role:
        flash("Role tidak boleh kosong atau DB tidak terhubung.")
        return redirect(url_for("users.admin_users", q=request.args.get("q", "")))

    users_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}}
    )
    flash("Role berhasil diubah.")
    return redirect(url_for("users.admin_users", q=request.args.get("q", "")))
