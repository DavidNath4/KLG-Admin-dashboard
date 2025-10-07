from flask import Blueprint, render_template, request, send_file, current_app, url_for
from datetime import datetime, time
from io import BytesIO
from openpyxl import Workbook
from bson import ObjectId

from config.mongo import get_col
from utils.helper import parse_date, human_bytes

bp = Blueprint("files", __name__, url_prefix="/admin")


def _build_query(start_str: str, end_str: str, user_str: str) -> dict:
    """Bangun query Mongo dari filter date & user (ObjectId)."""
    query: dict = {}

    # Date range
    start_dt = parse_date(start_str)
    end_dt = parse_date(end_str)
    if start_dt or end_dt:
        query["createdAt"] = {}
        if start_dt:
            query["createdAt"]["$gte"] = datetime.combine(start_dt, time.min)
        if end_dt:
            query["createdAt"]["$lte"] = datetime.combine(end_dt, time.max)

    # User
    if user_str:
        try:
            query["user"] = ObjectId(user_str)
        except Exception:
            pass

    return query


@bp.get("/files")
def file_monitoring():
    files_col = get_col("files")
    users_col = get_col(current_app.config["USERS_COL"])

    # ---- filters & params
    start_str = request.args.get("start", "").strip()
    end_str   = request.args.get("end", "").strip()
    user_str  = request.args.get("user", "").strip()
    sort_key  = request.args.get("s", "createdAt").strip()     # createdAt|filename|type|bytes|user
    sort_ord  = request.args.get("o", "desc").strip()          # asc|desc
    page      = max(int(request.args.get("page", 1) or 1), 1)
    per_page  = int(request.args.get("per_page", 20) or 20)
    per_page  = max(min(per_page, 200), 5)

    # ---- build query
    query = _build_query(start_str, end_str, user_str)

    # ---- user dropdown options (distinct dari files -> resolve name)
    user_options = []
    if files_col is not None and users_col is not None:
        distinct_ids = [u for u in files_col.distinct("user", query) if isinstance(u, ObjectId)]
        if distinct_ids:
            name_map = {}
            for u in users_col.find({"_id": {"$in": distinct_ids}}, {"name": 1, "email": 1}):
                name_map[str(u["_id"])] = (u.get("name") or u.get("email") or str(u["_id"]))
            for oid in distinct_ids:
                key = str(oid)
                user_options.append({"_id": key, "name": name_map.get(key, key)})
        user_options.sort(key=lambda x: (x["name"] or "").lower())

    # ---- totals (filtered, no pagination)
    total_files = files_col.count_documents(query) if files_col is not None else 0

    total_size_bytes = 0
    if files_col is not None:
        pipe = [
            {"$match": query},
            {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$bytes", 0]}}}},
        ]
        agg = list(files_col.aggregate(pipe))
        total_size_bytes = agg[0]["total"] if agg else 0
    total_size_h = human_bytes(total_size_bytes)

    total_users = 0
    if files_col is not None:
        distinct_users = files_col.distinct("user", query)
        total_users = len([u for u in distinct_users if u is not None])

    # ---- sorting & pagination
    sort_fields_map = {
        "createdAt": "createdAt",
        "filename":  "filename",
        "type":      "type",
        "bytes":     "bytes",
    }
    mongo_sort = sort_fields_map.get(sort_key, "createdAt")
    sort_dir = -1 if sort_ord == "desc" else 1

    rows = []
    if files_col is not None:
        cursor = files_col.find(query).sort(mongo_sort, sort_dir).skip((page - 1) * per_page).limit(per_page)
        for doc in cursor:
            # resolve nama user
            user_name = None
            if users_col is not None and doc.get("user"):
                u = users_col.find_one({"_id": doc["user"]}, {"name": 1})
                if u:
                    user_name = u.get("name")

            rows.append({
                "createdAt": doc.get("createdAt"),
                "filename":  doc.get("filename"),
                "type":      doc.get("type"),
                "size_h":    human_bytes(doc.get("bytes")),
                "size":      doc.get("bytes"),
                "user":      user_name or (str(doc.get("user")) if doc.get("user") else None),
                "user_id":   str(doc.get("user")) if doc.get("user") else "",
                "_id":       str(doc.get("_id")),
                "file_id":   doc.get("file_id"),
            })

    # Sort by user name in-memory (karena bukan field di dokumen files)
    if sort_key == "user":
        rows.sort(key=lambda r: (r["user"] or "").lower(), reverse=(sort_ord == "desc"))

    # ---- export excel (full filtered result, tanpa pagination)
    if request.args.get("export") == "1":
        all_rows = []
        if files_col is not None:
            cur = files_col.find(query).sort(mongo_sort, sort_dir)
            for doc in cur:
                uname = None
                if users_col is not None and doc.get("user"):
                    u = users_col.find_one({"_id": doc["user"]}, {"name": 1})
                    if u:
                        uname = u.get("name")
                all_rows.append({
                    "createdAt": doc.get("createdAt"),
                    "filename":  doc.get("filename"),
                    "type":      doc.get("type"),
                    "size":      doc.get("bytes"),
                    "user":      uname or (str(doc.get("user")) if doc.get("user") else None),
                    "_id":       str(doc.get("_id")),
                    "file_id":   doc.get("file_id"),
                })
        if sort_key == "user":
            all_rows.sort(key=lambda r: (r["user"] or "").lower(), reverse=(sort_ord == "desc"))

        wb = Workbook()
        ws = wb.active
        ws.title = "files"
        headers = ["createdAt", "filename", "type", "size(bytes)", "user", "_id", "file_id"]
        ws.append(headers)
        for r in all_rows:
            ws.append([
                r["createdAt"].isoformat() if r["createdAt"] else "",
                r["filename"] or "",
                r["type"] or "",
                r["size"] or 0,
                r["user"] or "",
                r["_id"] or "",
                r["file_id"] or "",
            ])
        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)
        fname = f"files_{start_str or 'all'}_{end_str or 'all'}_{user_str or 'all'}_{sort_key}_{sort_ord}.xlsx"
        return send_file(
            stream,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    total_pages = max((total_files + per_page - 1) // per_page, 1)

    return render_template(
        "files.html",
        title="File Monitoring",
        active="files",
        rows=rows,
        start=start_str,
        end=end_str,
        user=user_str,
        user_options=user_options,
        s=sort_key,
        o=sort_ord,
        page=page,
        per_page=per_page,
        total=total_files,
        total_pages=total_pages,
        total_size_bytes=total_size_bytes,
        total_size_h=total_size_h,
        total_users=total_users,
    )
