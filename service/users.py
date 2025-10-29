from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from bson import ObjectId
from bson.errors import InvalidId
from config.mongo import get_col
from datetime import datetime
from pymongo.errors import PyMongoError

bp = Blueprint("users", __name__, url_prefix="/admin-klg/admin")

@bp.route("/users", methods=["GET", "POST"])
def admin_users():
    """Admin users management with comprehensive error handling"""
    try:
        # Parse and validate parameters
        q = request.args.get("q", "").strip()
        sort_field = request.args.get("sort", "email")
        sort_dir = request.args.get("dir", "asc")
        
        # Validate sort parameters
        allowed_fields = {"email", "name", "role"}
        if sort_field not in allowed_fields:
            sort_field = "email"
        direction = 1 if sort_dir == "asc" else -1

        # Parse and validate pagination
        try:
            page = max(int(request.args.get("page", 1) or 1), 1)
            per_page = int(request.args.get("per_page", 10) or 10)
            per_page = max(min(per_page, 200), 5)
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"[Users] Invalid pagination params: {e}")
            page, per_page = 1, 10

        users_col = get_col(current_app.config["USERS_COL"])
        total = 0
        users_list = []

        if users_col is None:
            flash("Database connection unavailable. Please try again later.", "warning")
            current_app.logger.error("[Users] Database collection unavailable")
        else:
            try:
                # Build query
                query = {}
                if q:
                    # Validate search query
                    if len(q) > 100:  # Prevent extremely long queries
                        q = q[:100]
                        flash("Search query truncated to 100 characters", "info")
                    query = {"email": {"$regex": q, "$options": "i"}}

                # Execute database operations
                total = users_col.count_documents(query)
                cursor = (
                    users_col.find(query)
                    .sort(sort_field, direction)
                    .skip((page - 1) * per_page)
                    .limit(per_page)
                )
                users_list = list(cursor)
                
                current_app.logger.info(f"[Users] Retrieved {len(users_list)} users (total: {total})")
                
            except PyMongoError as e:
                current_app.logger.error(f"[Users] Database error: {e}")
                flash("Database error occurred. Please try again.", "danger")
            except (ValueError, TypeError) as e:
                current_app.logger.error(f"[Users] Data validation error: {e}")
                flash("Invalid data format. Please try again.", "danger")
            except Exception as e:
                current_app.logger.error(f"[Users] Unexpected error: {e}")
                flash("An unexpected error occurred. Please try again.", "danger")

        # Calculate pagination
        total_pages = max((total + per_page - 1) // per_page, 1) if total > 0 else 1

        return render_template(
            "users.html",
            title="User Management",
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
        
    except Exception as e:
        current_app.logger.error(f"[Users] Route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return render_template(
            "users.html",
            title="User Management",
            active="users",
            users=[],
            q="",
            sort="email",
            dir="asc",
            page=1,
            per_page=10,
            total=0,
            total_pages=1,
        )

@bp.post("/users/<id>/role")
def change_role(id):
    """Change user role with comprehensive error handling"""
    try:
        # Validate ObjectId
        try:
            user_id = ObjectId(id)
        except InvalidId as e:
            current_app.logger.warning(f"[Users] Invalid user ID: {id}")
            flash("Invalid user ID format", "danger")
            return redirect(url_for("users.admin_users"))

        # Get and validate new role
        new_role = request.form.get("role", "").strip()
        if not new_role:
            flash("Role cannot be empty", "danger")
            return redirect(url_for("users.admin_users"))
            
        # Validate role value
        allowed_roles = {"USER", "ADMIN"}  
        if new_role.upper() not in allowed_roles:
            current_app.logger.warning(f"[Users] Invalid role attempted: {new_role}")
            flash(f"Invalid role. Allowed roles: {', '.join(allowed_roles)}", "danger")
            return redirect(url_for("users.admin_users"))

        # Get database collection
        users_col = get_col("users")
        if users_col is None:
            flash("Database connection unavailable. Role cannot be changed.", "danger")
            current_app.logger.error("[Users] Database unavailable for role change")
            return redirect(url_for("users.admin_users"))

        try:
            # Check if user exists
            existing_user = users_col.find_one({"_id": user_id})
            if not existing_user:
                flash("User not found", "danger")
                current_app.logger.warning(f"[Users] User not found for role change: {id}")
                return redirect(url_for("users.admin_users"))

            # Update user role
            result = users_col.update_one(
                {"_id": user_id},
                {
                    "$set": {
                        "role": new_role.upper(),
                        "updatedAt": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                flash(f"Role successfully changed to {new_role}", "success")
                current_app.logger.info(f"[Users] Role changed for user {id}: {new_role}")
            else:
                flash("No changes made to user role", "info")
                current_app.logger.info(f"[Users] No role change needed for user {id}")
                
        except PyMongoError as e:
            current_app.logger.error(f"[Users] Database error changing role: {e}")
            flash("Database error. Role change failed.", "danger")
        except (ValueError, TypeError) as e:
            current_app.logger.error(f"[Users] Data validation error changing role: {e}")
            flash("Invalid role data. Role change failed.", "danger")
        except Exception as e:
            current_app.logger.error(f"[Users] Unexpected error changing role: {e}")
            flash("Unexpected error. Role change failed.", "danger")

        return redirect(url_for("users.admin_users", q=request.args.get("q", "")))
        
    except Exception as e:
        current_app.logger.error(f"[Users] Role change route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return redirect(url_for("users.admin_users"))
