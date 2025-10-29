from flask import Blueprint, render_template, request, send_file, current_app, flash
from datetime import datetime, timedelta, date
from io import BytesIO
import pandas as pd
from config.mongo import get_col
from pymongo.errors import PyMongoError
from math import ceil
import re

bp = Blueprint("tokens", __name__, url_prefix="/admin-klg/admin")

def safe_template_render(**kwargs):
    """Safe template rendering with default values"""
    defaults = {
        "title": "Token Usage",
        "active": "tokens",
        "rows": [],
        "agents_list": [],
        "selected_agent": "general",
        "date_from": "",
        "date_to": "",
        "now_date": date.today().isoformat(),
        "page": 1,
        "per_page": 10,
        "total": 0,
        "total_pages": 1,
        "q": ""
    }
    defaults.update(kwargs)
    return render_template("tokens.html", **defaults)

@bp.route("/tokens")
def admin_tokens():
    """Token usage analysis with comprehensive error handling"""
    try:
        # Parse and validate parameters
        try:
            selected_agent = request.args.get("agent", "general").strip()
            date_from = request.args.get("date_from", "").strip()
            date_to = request.args.get("date_to", "").strip()
            q = (request.args.get("q", "") or "").strip()
            
            # Validate pagination
            page = max(int(request.args.get("page", 1) or 1), 1)
            per_page = max(min(int(request.args.get("per_page", 10) or 10), 100), 5)
            
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"[Tokens] Parameter validation error: {e}")
            page, per_page = 1, 10

        # Get database collections
        try:
            users_col = get_col(current_app.config["USERS_COL"])
            messages_col = get_col("messages")
            convos_col = get_col("conversations")
            agents_col = get_col("agents")
        except (KeyError, AttributeError) as e:
            current_app.logger.error(f"[Tokens] Configuration error: {e}")
            flash("Configuration error. Please contact administrator.", "danger")
            return safe_template_render(error="Configuration error")

        if any(col is None for col in [users_col, messages_col, convos_col, agents_col]):
            flash("Database connection unavailable. Please try again later.", "warning")
            current_app.logger.error("[Tokens] Database collections unavailable")
            return safe_template_render(error="Database unavailable")

        # Get agents list with error handling
        agents_list = []
        agents_map = {}
        agent_name_by_id = {}
        
        try:
            agents_list = list(agents_col.find({}, {"id": 1, "name": 1}).sort("name", 1))
            
            # Build agent mappings
            for a in agents_col.find({}, {"id": 1, "model": 1, "name": 1}):
                agent_id = a.get("id")
                if agent_id:
                    agents_map[agent_id] = a.get("model")
                    agent_name_by_id[agent_id] = a.get("name")
                    
        except PyMongoError as e:
            current_app.logger.error(f"[Tokens] Error loading agents: {e}")
            flash("Error loading agent data", "warning")

        # Build users cache with error handling
        users_cache = {}
        try:
            for u in users_col.find({}, {"name": 1, "email": 1}):
                user_id = str(u["_id"])
                users_cache[user_id] = {
                    "name": u.get("name", "Unknown"), 
                    "email": u.get("email")
                }
        except PyMongoError as e:
            current_app.logger.error(f"[Tokens] Error loading users cache: {e}")
            flash("Error loading user data", "warning")

        # Build messages query with error handling
        try:
            assistants_query = {"isCreatedByUser": {"$in": [False, "false", "False", 0]}}
            
            # Agent filter
            if selected_agent != "general":
                assistants_query["model"] = selected_agent

            # Date range filter
            created_range = {}
            if date_from:
                try:
                    start_dt = datetime.strptime(date_from, "%Y-%m-%d")
                    created_range["$gte"] = start_dt
                except ValueError as e:
                    current_app.logger.warning(f"[Tokens] Invalid date_from format: {date_from}")
                    flash("Invalid start date format", "warning")
                    
            if date_to:
                try:
                    end_dt_exclusive = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
                    created_range["$lt"] = end_dt_exclusive
                except ValueError as e:
                    current_app.logger.warning(f"[Tokens] Invalid date_to format: {date_to}")
                    flash("Invalid end date format", "warning")
                    
            if created_range:
                assistants_query["createdAt"] = created_range

            # Email filter
            if q:
                try:
                    email_regex = {"$regex": re.escape(q), "$options": "i"}
                    matched_users = list(users_col.find({"email": email_regex}, {"_id": 1}))
                    
                    if not matched_users:
                        return safe_template_render(
                            agents_list=agents_list,
                            selected_agent=selected_agent,
                            date_from=date_from,
                            date_to=date_to,
                            q=q
                        )
                        
                    oid_list = [u["_id"] for u in matched_users]
                    str_list = [str(u["_id"]) for u in matched_users]
                    assistants_query["user"] = {"$in": oid_list + str_list}
                    
                except PyMongoError as e:
                    current_app.logger.error(f"[Tokens] Error filtering by email: {e}")
                    flash("Error filtering by email", "danger")

        except (ValueError, TypeError) as e:
            current_app.logger.error(f"[Tokens] Query building error: {e}")
            flash("Error building search query", "danger")
            return safe_template_render()

        # Fetch messages data
        assistants = []
        try:
            assistants = list(
                messages_col.find(
                    assistants_query,
                    {"user":1,"model":1,"createdAt":1,"conversationId":1,"tokenCount":1,"parentMessageId":1}
                )
            )
            current_app.logger.info(f"[Tokens] Retrieved {len(assistants)} assistant messages")
            
        except PyMongoError as e:
            current_app.logger.error(f"[Tokens] Error fetching messages: {e}")
            flash("Error fetching token data", "danger")
            return safe_template_render()

        # Prefetch conversations and parent messages
        convos_map = {}
        parents_map = {}
        
        try:
            # Get conversation data
            conv_ids = {str(m.get("conversationId")) for m in assistants if m.get("conversationId")}
            if conv_ids:
                for c in convos_col.find({"_id": {"$in": list(conv_ids)}}, {"createdAt": 1}):
                    convos_map[str(c["_id"])] = c.get("createdAt")

            # Get parent message data
            parent_ids = [m.get("parentMessageId") for m in assistants if m.get("parentMessageId")]
            if parent_ids:
                for p in messages_col.find({"messageId": {"$in": parent_ids}},
                                         {"messageId":1,"isCreatedByUser":1,"tokenCount":1}):
                    parents_map[p.get("messageId")] = p
                    
        except PyMongoError as e:
            current_app.logger.error(f"[Tokens] Error fetching related data: {e}")
            flash("Error fetching conversation data", "warning")

        # Process token data
        data = []
        for m in assistants:
            try:
                user_id = str(m.get("user", ""))
                uinfo = users_cache.get(user_id, {"name":"Unknown","email":None})

                mid_or_name = m.get("model")
                model_name = agents_map.get(mid_or_name, mid_or_name or "Unknown Model")

                agent_name = agent_name_by_id.get(mid_or_name)
                is_agent = bool(agent_name)

                agent_label = agent_name if is_agent else "General"
                model_label = model_name

                created_at = m.get("createdAt") or convos_map.get(str(m.get("conversationId")))
                if not created_at:
                    continue

                try:
                    out_tokens = int(m.get("tokenCount", 0) or 0)
                except (ValueError, TypeError):
                    out_tokens = 0

                in_tokens = 0
                parent = parents_map.get(m.get("parentMessageId"))
                if parent:
                    try:
                        raw_flag = parent.get("isCreatedByUser", False)
                        is_user_parent = raw_flag if isinstance(raw_flag, bool) else (str(raw_flag).lower() == "true" or raw_flag == 1)
                        if is_user_parent:
                            in_tokens = int(parent.get("tokenCount", 0) or 0)
                    except (ValueError, TypeError):
                        in_tokens = 0

                data.append({
                    "date": str(created_at.date()),
                    "email": uinfo.get("email"),
                    "model": model_name,
                    "agent_name": agent_name,
                    "agent_label": agent_label,
                    "model_label": model_label,
                    "tokens": in_tokens + out_tokens,
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                    "messages_in_turn": 1 + (1 if parent else 0),
                })
                
            except (KeyError, TypeError, AttributeError) as e:
                current_app.logger.warning(f"[Tokens] Error processing message record: {e}")
                continue

        # Aggregate data using pandas
        rows = []
        try:
            df = pd.DataFrame(data)
            if not df.empty:
                daily_usage = (
                    df.groupby(["date","email","agent_label","model_label"])
                    .agg(
                        agent_name=("agent_name","first"),
                        total_tokens=("tokens","sum"),
                        input_tokens=("input_tokens","sum"),
                        output_tokens=("output_tokens","sum"),
                        total_messages=("messages_in_turn","sum"),
                    )
                    .reset_index()
                )

                rows = daily_usage.to_dict(orient="records")
                rows.sort(
                    key=lambda r: (
                        r["date"],
                        r["email"] or "",
                        r["agent_label"] or "",
                        r["model_label"] or "",
                    ),
                    reverse=True
                )
                
        except (ValueError, KeyError) as e:
            current_app.logger.error(f"[Tokens] Data aggregation error: {e}")
            flash("Error processing token data", "danger")
        except Exception as e:
            current_app.logger.error(f"[Tokens] Unexpected aggregation error: {e}")
            flash("Unexpected error processing data", "danger")

        # Handle Excel export
        if request.args.get("export") == "xlsx":
            try:
                return _export_excel(rows, date_from, date_to)
            except Exception as e:
                current_app.logger.error(f"[Tokens] Excel export error: {e}")
                flash("Error generating Excel export", "danger")

        # Pagination
        total = len(rows)
        total_pages = ceil(total / per_page) if total > 0 else 1
        start = (page - 1) * per_page
        end = start + per_page
        paginated_rows = rows[start:end]

        return safe_template_render(
            rows=paginated_rows,
            agents_list=agents_list,
            selected_agent=selected_agent,
            date_from=date_from,
            date_to=date_to,
            page=page,
            per_page=per_page,
            total=total,
            total_pages=total_pages,
            q=q
        )

    except Exception as e:
        current_app.logger.error(f"[Tokens] Route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return safe_template_render(error="System error")


def _export_excel(rows, date_from, date_to):
    """Export tokens data to Excel with error handling"""
    try:
        df_x = pd.DataFrame(rows)
        if df_x.empty:
            df_x = pd.DataFrame(columns=[
                "date","email","model","total_tokens","input_tokens","output_tokens","total_messages"
            ])

        order = ["date","email","agent_label","model_label","total_tokens","input_tokens","output_tokens","total_messages"]
        df_x = df_x[[c for c in order if c in df_x.columns]]

        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df_x.to_excel(writer, index=False, sheet_name="Token Usage")
        bio.seek(0)

        fname = f"token-usage_{date_from or 'all'}_{date_to or 'all'}.xlsx"
        return send_file(
            bio,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except (OSError, IOError) as e:
        current_app.logger.error(f"[Tokens] Excel file creation error: {e}")
        raise Exception("Failed to create Excel file")
    except (ValueError, KeyError) as e:
        current_app.logger.error(f"[Tokens] Excel data processing error: {e}")
        raise Exception("Failed to process data for Excel export")
    except Exception as e:
        current_app.logger.error(f"[Tokens] Excel export error: {e}")
        raise
