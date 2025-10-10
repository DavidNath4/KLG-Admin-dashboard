from flask import Blueprint, render_template, request, send_file
from datetime import datetime, timedelta, date
from io import BytesIO
import pandas as pd
from config.mongo import get_col
from flask import current_app
from math import ceil

bp = Blueprint("tokens", __name__, url_prefix="/admin-klg/admin")

@bp.route("/tokens")
def admin_tokens():
    rows = []
    selected_agent = request.args.get("agent", "general")
    date_from = request.args.get("date_from", "")
    date_to   = request.args.get("date_to", "")

    # Collections
    users_col    = get_col(current_app.config["USERS_COL"])
    messages_col = get_col("messages")
    convos_col   = get_col("conversations")
    agents_col   = get_col("agents")

    if any(col is None for col in [users_col, messages_col, convos_col, agents_col]):
        return render_template(
            "tokens.html",
            title="Token Usage",
            active="tokens",
            rows=[],
            agents_list=[],
            selected_agent=selected_agent,
            date_from=date_from,
            date_to=date_to,
            now_date=date.today().isoformat(),
            error="Database tidak tersedia. Silakan coba lagi nanti."
        )


    # Dropdown agents
    agents_list = list(agents_col.find({}, {"id": 1, "name": 1}).sort("name", 1))

    # Map agent.id -> model name (mis. "us.amazon.nova-pro-v1:0")
    agents_map = {
        a["id"]: a.get("model")
        for a in agents_col.find({}, {"id": 1, "model": 1})
    }

    # Cache user { userId(str): {name, email} }
    users_cache = {
        str(u["_id"]): {"name": u.get("name", "Unknown"), "email": u.get("email")}
        for u in users_col.find({}, {"name": 1, "email": 1})
    }

    # -- Query messages: hanya balasan agent (output)
    assistants_query = {"isCreatedByUser": {"$in": [False, "false", "False", 0]}}
    if selected_agent != "general":
        assistants_query["model"] = selected_agent

    # Range tanggal optional (createdAt)
    created_range = {}
    if date_from:
        try:
            start_dt = datetime.strptime(date_from, "%Y-%m-%d")
            created_range["$gte"] = start_dt
        except ValueError:
            pass
    if date_to:
        try:
            end_dt_exclusive = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            created_range["$lt"] = end_dt_exclusive
        except ValueError:
            pass
    if created_range:
        assistants_query["createdAt"] = created_range

    assistants = list(
        messages_col.find(
            assistants_query,
            {"user":1,"model":1,"createdAt":1,"conversationId":1,"tokenCount":1,"parentMessageId":1}
        )
    )

    # Prefetch convos & parents
    conv_ids = {str(m.get("conversationId")) for m in assistants if m.get("conversationId")}
    parent_ids = [m.get("parentMessageId") for m in assistants if m.get("parentMessageId")]

    convos_map = {}
    if conv_ids:
        for c in convos_col.find({"_id": {"$in": list(conv_ids)}}, {"createdAt": 1}):
            convos_map[str(c["_id"])] = c.get("createdAt")

    parents_map = {}
    if parent_ids:
        for p in messages_col.find({"messageId": {"$in": parent_ids}},
                                   {"messageId":1,"isCreatedByUser":1,"tokenCount":1}):
            parents_map[p.get("messageId")] = p

    # Build per-turn
    data = []
    for m in assistants:
        user_id = str(m.get("user"))
        uinfo = users_cache.get(user_id, {"name":"Unknown","email":None})

        mid_or_name = m.get("model")
        model_name = agents_map.get(mid_or_name, mid_or_name or "Unknown Model")

        created_at = m.get("createdAt") or convos_map.get(str(m.get("conversationId")))
        if not created_at:
            continue

        out_tokens = int(m.get("tokenCount", 0) or 0)

        in_tokens = 0
        parent = parents_map.get(m.get("parentMessageId"))
        if parent:
            raw_flag = parent.get("isCreatedByUser", False)
            is_user_parent = raw_flag if isinstance(raw_flag, bool) else (str(raw_flag).lower() == "true" or raw_flag == 1)
            if is_user_parent:
                in_tokens = int(parent.get("tokenCount", 0) or 0)

        data.append({
            "date": str(created_at.date()),
            "email": uinfo.get("email"),
            "model": model_name,
            "tokens": in_tokens + out_tokens,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "messages_in_turn": 1 + (1 if parent else 0),
        })

    # Aggregasi
    df = pd.DataFrame(data)
    if not df.empty:
        daily_usage = (
            df.groupby(["date","email","model"])
              .agg(
                  total_tokens=("tokens","sum"),
                  input_tokens=("input_tokens","sum"),
                  output_tokens=("output_tokens","sum"),
                  total_messages=("messages_in_turn","sum"),
              )
              .reset_index()
        )
        rows = daily_usage.to_dict(orient="records")
        rows.sort(key=lambda r: (r["date"], r["email"] or "", r["model"] or ""), reverse=True)
    else:
        rows = []

    # Export XLSX
    if request.args.get("export") == "xlsx":

        df_x = pd.DataFrame(rows)
        if df_x.empty:
            df_x = pd.DataFrame(columns=[
                "date","email","model","total_tokens","input_tokens","output_tokens","total_messages"
            ])

        order = ["date","email","model","total_tokens","input_tokens","output_tokens","total_messages"]
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
    
    # --- Pagination setup ---
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    total = len(rows)
    total_pages = ceil(total / per_page) if total > 0 else 1

    start = (page - 1) * per_page
    end = start + per_page
    paginated_rows = rows[start:end]

    now_date = date.today().isoformat()

    return render_template(
        "tokens.html",
        title="Token Usage",
        active="tokens",
        rows=paginated_rows,
        agents_list=agents_list,
        selected_agent=selected_agent,
        date_from=date_from,
        date_to=date_to,
        now_date=now_date,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages
    )
