from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from bson import ObjectId
from config.mongo import get_col
from datetime import datetime

bp = Blueprint("users", __name__, url_prefix="/admin")

@bp.route("/users", methods=["GET", "POST"])
def admin_users():
    # filter / sort params
    q = request.args.get("q", "").strip()
    sort_field = request.args.get("sort", "email")
    sort_dir   = request.args.get("dir", "asc")
    allowed_fields = {"email", "name", "role"}
    if sort_field not in allowed_fields:
        sort_field = "email"
    direction = 1 if sort_dir == "asc" else -1

    # pagination params
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = int(request.args.get("per_page", 10) or 10)
    per_page = max(min(per_page, 200), 5)

    users_col = get_col(current_app.config["USERS_COL"])

    total = 0
    users_list = []

    if users_col is None:
        # DB tidak tersedia → tampilkan halaman kosong dengan warning
        flash("Database tidak tersedia. Silakan coba lagi nanti.", "error")
    else:
        query = {}
        if q:
            query = {"email": {"$regex": q, "$options": "i"}}
        try:
            total = users_col.count_documents(query)
            cursor = (
                users_col.find(query)
                .sort(sort_field, direction)
                .skip((page - 1) * per_page)
                .limit(per_page)
            )
            users_list = list(cursor)
        except Exception as e:
            flash(f"Terjadi error saat membaca database: {e}", "error")

    total_pages = max((total + per_page - 1) // per_page, 1)

    return render_template(
        "users.html",
        title="Set Up Admin",
        active="users",
        users=users_list,
        q=q,
        sort=sort_field,
        dir=sort_dir,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )

@bp.post("/users/<id>/role")
def change_role(id):
    users_col = get_col("users")
    new_role = request.form.get("role", "").strip()

    if users_col is None:
        flash("Database tidak tersedia. Role tidak dapat diubah.", "error")
        return redirect(url_for("users.admin_users", q=request.args.get("q", "")))

    if not new_role:
        flash("Role tidak boleh kosong.", "error")
        return redirect(url_for("users.admin_users", q=request.args.get("q", "")))

    try:
        users_col.update_one(
            {"_id": ObjectId(id)},
            {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}},
        )
        flash("Role berhasil diubah.", "success")
    except Exception as e:
        flash(f"Gagal mengubah role: {e}", "error")

    return redirect(url_for("users.admin_users", q=request.args.get("q", "")))
