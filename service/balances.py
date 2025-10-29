# service/balances.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from config.mongo import get_col
from pymongo.errors import PyMongoError
from math import ceil
import re

bp = Blueprint("balances", __name__, url_prefix="/admin-klg/admin")

def safe_template_render(template_name, **kwargs):
    """Safe template rendering with default values"""
    defaults = {
        "title": "Balance Management",
        "active": "balances",
        "rows": [],
        "refill_units": ["seconds", "minutes", "hours", "days", "weeks", "months"],
        "q": "",
        "page": 1,
        "per_page": 10,
        "total": 0,
        "total_pages": 1,
        "sort": "tokenCredits",
        "dir": "desc"
    }
    defaults.update(kwargs)
    return render_template(template_name, **defaults)

@bp.route("/balances")
def balance_list():
    """Balance list with comprehensive error handling"""
    try:
        # Get database collections
        balances_col = get_col("balances")
        users_col = get_col("users")

        if balances_col is None or users_col is None:
            flash("Database connection unavailable. Cannot load balances.", "warning")
            current_app.logger.error("[Balances] Database collections unavailable")
            return safe_template_render("balances.html", error="Database unavailable")

        # Parse and validate parameters
        q = (request.args.get("q", "") or "").strip()
        if len(q) > 100:  # Prevent extremely long queries
            q = q[:100]
            flash("Search query truncated to 100 characters", "info")

        # Validate pagination parameters
        try:
            page = max(request.args.get("page", 1, type=int), 1)
            per_page = request.args.get("per_page", 10, type=int)
            allowed_per_page = [5, 10, 20, 50, 100]
            if per_page not in allowed_per_page:
                per_page = 10
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"[Balances] Invalid pagination params: {e}")
            page, per_page = 1, 10

        # Validate sorting parameters
        sort_field = request.args.get("sort", "tokenCredits")
        sort_dir = request.args.get("dir", "desc")
        allowed_sorts = ["tokenCredits", "email", "lastRefill"]
        if sort_field not in allowed_sorts:
            sort_field = "tokenCredits"
        reverse = (sort_dir != "asc")

        try:
            # Preload user map with error handling
            users_map = {}
            try:
                users_cursor = users_col.find({}, {"_id": 1, "email": 1, "name": 1})
                users_map = {
                    str(u["_id"]): {
                        "email": u.get("email", "Unknown"), 
                        "name": u.get("name", "Unknown")
                    }
                    for u in users_cursor
                }
                current_app.logger.info(f"[Balances] Loaded {len(users_map)} users")
            except PyMongoError as e:
                current_app.logger.error(f"[Balances] Error loading users: {e}")
                flash("Error loading user data", "warning")

            # Build filter for balances based on email search
            bal_filter = {}
            if q:
                try:
                    # Find users with matching email
                    email_regex = {"$regex": re.escape(q), "$options": "i"}
                    matched_users = list(users_col.find({"email": email_regex}, {"_id": 1}))
                    
                    if not matched_users:
                        # No matching users
                        return safe_template_render(
                            "balances.html",
                            q=q, page=page, per_page=per_page,
                            sort=sort_field, dir=sort_dir
                        )

                    oid_list = [u["_id"] for u in matched_users]
                    str_list = [str(u["_id"]) for u in matched_users]
                    
                    # Support both ObjectId and string user references
                    bal_filter = {"$or": [
                        {"user": {"$in": oid_list}},
                        {"user": {"$in": str_list}},
                    ]}
                except PyMongoError as e:
                    current_app.logger.error(f"[Balances] Error building search filter: {e}")
                    flash("Search error occurred", "danger")
                    return safe_template_render("balances.html")

            # Count total documents
            try:
                total = balances_col.count_documents(bal_filter)
                total_pages = max(ceil(total / per_page), 1)
                if page > total_pages:
                    page = total_pages
                start = (page - 1) * per_page
            except PyMongoError as e:
                current_app.logger.error(f"[Balances] Error counting documents: {e}")
                flash("Error counting balances", "danger")
                return safe_template_render("balances.html")

            # Fetch balance data
            try:
                cursor = balances_col.find(
                    bal_filter,
                    {
                        "user": 1,
                        "tokenCredits": 1,
                        "autoRefillEnabled": 1,
                        "refillAmount": 1,
                        "refillIntervalUnit": 1,
                        "refillIntervalValue": 1,
                        "lastRefill": 1
                    }
                ).skip(start).limit(per_page)

                data = []
                for b in cursor:
                    try:
                        user_id_raw = b.get("user")
                        user_id_str = str(user_id_raw) if user_id_raw else "unknown"
                        user_info = users_map.get(user_id_str, {"email": "Unknown", "name": "Unknown"})
                        last_refill_dt = b.get("lastRefill")

                        data.append({
                            "id": str(b["_id"]),
                            "email": user_info["email"],
                            "tokenCredits": float(b.get("tokenCredits", 0)),
                            "autoRefillEnabled": bool(b.get("autoRefillEnabled", False)),
                            "refillAmount": b.get("refillAmount", 0),
                            "refillIntervalUnit": b.get("refillIntervalUnit", "-"),
                            "refillIntervalValue": b.get("refillIntervalValue", "-"),
                            "lastRefill": last_refill_dt or datetime.min
                        })
                    except (KeyError, TypeError, ValueError) as e:
                        current_app.logger.warning(f"[Balances] Data format error processing balance record: {e}")
                        continue
                    except Exception as e:
                        current_app.logger.warning(f"[Balances] Unexpected error processing balance record: {e}")
                        continue

                current_app.logger.info(f"[Balances] Retrieved {len(data)} balance records")

            except PyMongoError as e:
                current_app.logger.error(f"[Balances] Error fetching balances: {e}")
                flash("Error fetching balance data", "danger")
                return safe_template_render("balances.html")

            # Sort data in memory
            try:
                if sort_field == "email":
                    data.sort(key=lambda x: (x.get("email") or "").lower(), reverse=reverse)
                elif sort_field == "lastRefill":
                    data.sort(key=lambda x: x.get("lastRefill") or datetime.min, reverse=reverse)
                else:
                    data.sort(key=lambda x: float(x.get("tokenCredits", 0)), reverse=reverse)
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"[Balances] Data type error sorting data: {e}")
            except Exception as e:
                current_app.logger.warning(f"[Balances] Unexpected error sorting data: {e}")

            # Format lastRefill for display
            for d in data:
                try:
                    d["lastRefill"] = d["lastRefill"].strftime("%Y-%m-%d") if d["lastRefill"] != datetime.min else "-"
                except (AttributeError, ValueError) as e:
                    current_app.logger.warning(f"[Balances] Date format error: {e}")
                    d["lastRefill"] = "-"
                except Exception as e:
                    current_app.logger.warning(f"[Balances] Unexpected error formatting date: {e}")
                    d["lastRefill"] = "-"

            return safe_template_render(
                "balances.html",
                rows=data,
                q=q,
                page=page,
                per_page=per_page,
                total=total,
                total_pages=total_pages,
                sort=sort_field,
                dir=sort_dir
            )

        except Exception as e:
            current_app.logger.error(f"[Balances] Unexpected error in data processing: {e}")
            flash("Unexpected error occurred. Please try again.", "danger")
            return safe_template_render("balances.html")

    except Exception as e:
        current_app.logger.error(f"[Balances] Route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return safe_template_render("balances.html", error="System error")

@bp.route("/balances/<balance_id>/edit", methods=["POST"])
def edit_balance(balance_id):
    """Edit balance with comprehensive error handling"""
    try:
        # Validate balance ID
        try:
            balance_obj_id = ObjectId(balance_id)
        except InvalidId:
            flash("Invalid balance ID format", "danger")
            current_app.logger.warning(f"[Balances] Invalid balance ID: {balance_id}")
            return redirect(url_for("balances.balance_list"))

        # Get database collection
        balances_col = get_col("balances")
        if balances_col is None:
            flash("Database connection unavailable. Cannot update balance.", "danger")
            current_app.logger.error("[Balances] Database unavailable for balance edit")
            return redirect(url_for("balances.balance_list"))

        try:
            # Check if balance exists
            cur = balances_col.find_one({"_id": balance_obj_id}, {"tokenCredits": 1})
            if not cur:
                flash("Balance record not found", "danger")
                current_app.logger.warning(f"[Balances] Balance not found: {balance_id}")
                return redirect(url_for("balances.balance_list"))

            # Parse and validate token credits
            raw_tokens = (request.form.get("tokenCredits", "") or "").replace(",", "").strip()
            
            try:
                if not raw_tokens:
                    tokenCredits = float(cur.get("tokenCredits", 0))
                else:
                    tokenCredits = float(raw_tokens)
            except ValueError as e:
                current_app.logger.warning(f"[Balances] Invalid token value: {raw_tokens}")
                flash("Invalid token amount format", "danger")
                return redirect(url_for("balances.balance_list"))

            # Validate token amount
            if tokenCredits < 0:
                flash("Token balance cannot be negative", "danger")
                return redirect(url_for("balances.balance_list"))
                
            if tokenCredits > 1000000:  # Reasonable upper limit
                flash("Token balance too large (max 1,000,000)", "danger")
                return redirect(url_for("balances.balance_list"))

            # Update balance
            result = balances_col.update_one(
                {"_id": balance_obj_id},
                {"$set": {
                    "tokenCredits": float(tokenCredits),
                    "lastRefill": datetime.utcnow()
                }}
            )

            if result.modified_count > 0:
                flash(f"Token balance updated to {tokenCredits:,.2f}", "success")
                current_app.logger.info(f"[Balances] Balance updated: {balance_id} -> {tokenCredits}")
            else:
                flash("No changes made to balance", "info")

        except PyMongoError as e:
            current_app.logger.error(f"[Balances] Database error updating balance: {e}")
            flash("Database error. Balance not updated.", "danger")
        except (ValueError, TypeError) as e:
            current_app.logger.error(f"[Balances] Data validation error updating balance: {e}")
            flash("Invalid balance data. Balance not updated.", "danger")
        except Exception as e:
            current_app.logger.error(f"[Balances] Unexpected error updating balance: {e}")
            flash("Unexpected error. Balance not updated.", "danger")

        return redirect(url_for("balances.balance_list"))

    except Exception as e:
        current_app.logger.error(f"[Balances] Edit route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return redirect(url_for("balances.balance_list"))
