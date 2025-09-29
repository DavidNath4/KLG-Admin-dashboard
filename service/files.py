from flask import Blueprint, render_template, request, send_file, current_app
from datetime import datetime, time
from io import BytesIO
from openpyxl import Workbook
from config.mongo import get_col
from utils.helper import parse_date, human_bytes

bp = Blueprint("files", __name__, url_prefix="/admin")

@bp.get("/files")
def file_monitoring():
    files_col = get_col("files")
    users_col = get_col(current_app.config["USERS_COL"])

    start_str = request.args.get("start", "").strip()
    end_str   = request.args.get("end", "").strip()
    export    = request.args.get("export")

    query = {}
    start_dt = parse_date(start_str)
    end_dt = parse_date(end_str)
    if start_dt or end_dt:
        query["createdAt"] = {}
        if start_dt:
            query["createdAt"]["$gte"] = datetime.combine(start_dt, time.min)
        if end_dt:
            query["createdAt"]["$lte"] = datetime.combine(end_dt, time.max)

    rows = []
    if files_col is not None:
        cursor = files_col.find(query).sort("createdAt", -1).limit(1000)
        for doc in cursor:
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
                "_id":       str(doc.get("_id")),
                "file_id":   doc.get("file_id"),
            })

    if export == "1":
        wb = Workbook()
        ws = wb.active
        ws.title = "files"
        headers = ["createdAt","filename","type","size(bytes)","user","_id","file_id"]
        ws.append(headers)
        for r in rows:
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
        fname = f"files_{start_str or 'all'}_{end_str or 'all'}.xlsx"
        return send_file(
            stream,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return render_template(
        "files.html",
        title="File Monitoring",
        active="files",
        rows=rows,
        start=start_str,
        end=end_str
    )
