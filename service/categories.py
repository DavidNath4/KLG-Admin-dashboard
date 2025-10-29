from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime, timezone
from config.mongo import get_col
from utils.helper import kebab
from pymongo.errors import PyMongoError
import uuid

bp = Blueprint("categories", __name__, url_prefix="/admin-klg/admin")

def next_order(cats_col):
    """Get next order number with specific error handling"""
    try:
        last = list(cats_col.find().sort("order", -1).limit(1))
        return (last[0]["order"] + 1) if last else 1
    except PyMongoError as e:
        current_app.logger.error(f"[Categories] Database error getting next order: {e}")
        return 1
    except (KeyError, TypeError) as e:
        current_app.logger.error(f"[Categories] Data format error getting next order: {e}")
        return 1
    except Exception as e:
        current_app.logger.error(f"[Categories] Unexpected error getting next order: {e}")
        return 1

def ensure_unique_value(cats_col, base: str) -> str:
    """Ensure unique category value with specific error handling"""
    try:
        v = base
        i = 0
        while cats_col.count_documents({"value": v}, limit=1) > 0:
            i += 1
            v = f"{base}-{i}"
            if i > 100:  # Prevent infinite loop
                v = f"{base}-{uuid.uuid4().hex[:8]}"
                break
        return v
    except PyMongoError as e:
        current_app.logger.error(f"[Categories] Database error ensuring unique value: {e}")
        return f"{base}-{uuid.uuid4().hex[:8]}"
    except (ValueError, TypeError) as e:
        current_app.logger.error(f"[Categories] Data validation error ensuring unique value: {e}")
        return f"{base}-{uuid.uuid4().hex[:8]}"
    except Exception as e:
        current_app.logger.error(f"[Categories] Unexpected error ensuring unique value: {e}")
        return f"{base}-{uuid.uuid4().hex[:8]}"

@bp.route("/categories", methods=["GET", "POST"])
def categories():
    """Categories management with comprehensive error handling"""
    try:
        cats_col = get_col(current_app.config["CATS_COL"])
        
        if cats_col is None:
            flash("Database connection unavailable. Cannot access categories.", "warning")
            current_app.logger.error("[Categories] Database collection unavailable")
            return render_template("categories.html", title="Categories", active="categories", cats=[])
            
        if request.method == "POST":
            try:
                name = request.form.get("name", "").strip()
                
                # Validate input
                if not name:
                    flash("Category name is required", "danger")
                    return redirect(url_for("categories.categories"))
                    
                if len(name) > 100:
                    flash("Category name too long (max 100 characters)", "danger")
                    return redirect(url_for("categories.categories"))

                # Generate category data
                slug = kebab(name)
                if not slug:
                    flash("Invalid category name format", "danger")
                    return redirect(url_for("categories.categories"))
                    
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
                    "createdAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc),
                    "__v": 0,
                }
                
                # Insert category
                result = cats_col.insert_one(doc)
                if result.inserted_id:
                    flash(f"Category '{name}' added successfully", "success")
                    current_app.logger.info(f"[Categories] Category added: {name}")
                else:
                    flash("Failed to add category", "danger")
                    
            except PyMongoError as e:
                current_app.logger.error(f"[Categories] Database error adding category: {e}")
                flash("Database error. Category not added.", "danger")
            except (ValueError, TypeError) as e:
                current_app.logger.error(f"[Categories] Data validation error adding category: {e}")
                flash("Invalid category data. Category not added.", "danger")
            except Exception as e:
                current_app.logger.error(f"[Categories] Unexpected error adding category: {e}")
                flash("Unexpected error. Category not added.", "danger")
                
            return redirect(url_for("categories.categories"))

        # Get categories list
        try:
            data = list(cats_col.find().sort("order", 1))
            current_app.logger.info(f"[Categories] Retrieved {len(data)} categories")
        except PyMongoError as e:
            current_app.logger.error(f"[Categories] Database error retrieving categories: {e}")
            flash("Database error retrieving categories", "danger")
            data = []
        except Exception as e:
            current_app.logger.error(f"[Categories] Error retrieving categories: {e}")
            flash("Error retrieving categories", "danger")
            data = []
            
        return render_template(
            "categories.html", 
            title="Categories", 
            active="categories", 
            cats=data, 
            cats_col=current_app.config["CATS_COL"]
        )
        
    except Exception as e:
        current_app.logger.error(f"[Categories] Route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return render_template("categories.html", title="Categories", active="categories", cats=[])

@bp.post("/categories/<id>/move/<direction>")
def move_category(id, direction):
    """Move category with comprehensive error handling"""
    try:
        # Validate ObjectId
        try:
            category_id = ObjectId(id)
        except InvalidId:
            flash("Invalid category ID", "danger")
            return redirect(url_for("categories.categories"))
            
        # Validate direction
        if direction not in ["up", "down"]:
            flash("Invalid move direction", "danger")
            return redirect(url_for("categories.categories"))
        
        cats_col = get_col(current_app.config["CATS_COL"])
        if cats_col is None:
            flash("Database connection unavailable. Cannot move category.", "danger")
            return redirect(url_for("categories.categories"))
        
        try:
            # Get all categories
            arr = list(cats_col.find().sort("order", 1))
            idx = next((i for i, c in enumerate(arr) if c["_id"] == category_id), None)
            
            if idx is None:
                flash("Category not found", "danger")
                return redirect(url_for("categories.categories"))

            moved = False
            if direction == "up" and idx > 0:
                # Swap orders
                arr[idx]["order"], arr[idx-1]["order"] = arr[idx-1]["order"], arr[idx]["order"]
                a, b = arr[idx], arr[idx-1]
                
                # Update database
                cats_col.update_one(
                    {"_id": a["_id"]}, 
                    {"$set": {"order": a["order"], "updatedAt": datetime.now(timezone.utc)}}
                )
                cats_col.update_one(
                    {"_id": b["_id"]}, 
                    {"$set": {"order": b["order"], "updatedAt": datetime.now(timezone.utc)}}
                )
                moved = True
                
            elif direction == "down" and idx < len(arr) - 1:
                # Swap orders
                arr[idx]["order"], arr[idx+1]["order"] = arr[idx+1]["order"], arr[idx]["order"]
                a, b = arr[idx], arr[idx+1]
                
                # Update database
                cats_col.update_one(
                    {"_id": a["_id"]}, 
                    {"$set": {"order": a["order"], "updatedAt": datetime.now(timezone.utc)}}
                )
                cats_col.update_one(
                    {"_id": b["_id"]}, 
                    {"$set": {"order": b["order"], "updatedAt": datetime.now(timezone.utc)}}
                )
                moved = True

            if not moved:
                flash("Cannot move category in that direction", "info")
                return redirect(url_for("categories.categories"))

            # Normalize order numbers
            arr = list(cats_col.find().sort("order", 1))
            for i, c in enumerate(arr, start=1):
                if c.get("order") != i:
                    cats_col.update_one(
                        {"_id": c["_id"]}, 
                        {"$set": {"order": i, "updatedAt": datetime.now(timezone.utc)}}
                    )
                    
            flash("Category order updated successfully", "success")
            current_app.logger.info(f"[Categories] Category moved {direction}: {id}")
            
        except PyMongoError as e:
            current_app.logger.error(f"[Categories] Database error moving category: {e}")
            flash("Database error. Category not moved.", "danger")
        except Exception as e:
            current_app.logger.error(f"[Categories] Error moving category: {e}")
            flash("Unexpected error. Category not moved.", "danger")
            
        return redirect(url_for("categories.categories"))
        
    except Exception as e:
        current_app.logger.error(f"[Categories] Move route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return redirect(url_for("categories.categories"))

@bp.post("/categories/<id>/delete")
def delete_category(id):
    """Delete category with comprehensive error handling"""
    try:
        # Validate ObjectId
        try:
            category_id = ObjectId(id)
        except InvalidId:
            flash("Invalid category ID", "danger")
            return redirect(url_for("categories.categories"))
        
        cats_col = get_col(current_app.config["CATS_COL"])
        if cats_col is None:
            flash("Database connection unavailable. Cannot delete category.", "danger")
            return redirect(url_for("categories.categories"))
        
        try:
            # Check if category exists and is custom
            category = cats_col.find_one({"_id": category_id})
            if not category:
                flash("Category not found", "danger")
                return redirect(url_for("categories.categories"))
                
            if not category.get("custom", False):
                flash("Cannot delete system categories", "danger")
                return redirect(url_for("categories.categories"))
            
            # Delete category
            result = cats_col.delete_one({"_id": category_id})
            
            if result.deleted_count > 0:
                # Normalize remaining categories
                arr = list(cats_col.find().sort("order", 1))
                for i, c in enumerate(arr, start=1):
                    if c.get("order") != i:
                        cats_col.update_one(
                            {"_id": c["_id"]}, 
                            {"$set": {"order": i, "updatedAt": datetime.now(timezone.utc)}}
                        )
                        
                flash(f"Category '{category.get('name', 'Unknown')}' deleted successfully", "success")
                current_app.logger.info(f"[Categories] Category deleted: {category.get('name')}")
            else:
                flash("Category not found or already deleted", "info")
                
        except PyMongoError as e:
            current_app.logger.error(f"[Categories] Database error deleting category: {e}")
            flash("Database error. Category not deleted.", "danger")
        except Exception as e:
            current_app.logger.error(f"[Categories] Error deleting category: {e}")
            flash("Unexpected error. Category not deleted.", "danger")
            
        return redirect(url_for("categories.categories"))
        
    except Exception as e:
        current_app.logger.error(f"[Categories] Delete route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return redirect(url_for("categories.categories"))
