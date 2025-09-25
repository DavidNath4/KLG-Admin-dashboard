from flask import Blueprint, render_template, request, redirect, url_for, flash
from services.category_service import list_categories, create_category, delete_category, move_category

categories_bp = Blueprint("categories", __name__, template_folder="../templates")

@categories_bp.route("/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Nama kategori tidak boleh kosong.", "error")
        else:
            create_category(name)
            flash(f"Kategori '{name}' berhasil dibuat.", "success")
        return redirect(url_for("categories.categories"))

    cats = list_categories()
    return render_template("categories.html", title="Category Configuration", active="categories", cats=cats)


@categories_bp.post("/categories/<doc_id>/move/<direction>")
def move(doc_id, direction):
    if move_category(doc_id, direction):
        flash("Urutan diperbarui.")
    else:
        flash("Gagal memperbarui urutan.")
    return redirect(url_for("categories.categories"))

@categories_bp.post("/categories/<doc_id>/delete")
def delete(doc_id):
    if delete_category(doc_id):
        flash("Kategori dihapus & order dinormalisasi.")
    else:
        flash("Gagal menghapus kategori.")
    return redirect(url_for("categories.categories"))