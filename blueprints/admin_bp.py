from flask import Blueprint, render_template, request, redirect, url_for, flash
from services.user_service import find_users_by_email, update_user_role


admin_bp = Blueprint("admin", __name__, template_folder="../templates")

@admin_bp.route("/users", methods=["GET", "POST"])
def users():
    users = []
    q = request.args.get("q", "").strip()
    if q:
        users = find_users_by_email(q)
    return render_template("admin/users.html", users=users, q=q)

@admin_bp.route("/users/<user_id>/role")
def change_user_role(user_id):
    new_role = request.form.get("role", "").strip()
    if not new_role:
        flash("Role tidak boleh kosong.")
        return redirect(url_for("admin.users", q=request.args.get("q", "")))
    ok = update_user_role(user_id, new_role)
    flash("Role berhasil diubah." if ok else "Gagal mengubah role.")
    return redirect(url_for("admin.users", q=request.args.get("q", "")))