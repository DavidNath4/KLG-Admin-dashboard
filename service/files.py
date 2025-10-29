from flask import Blueprint, render_template, request, send_file, current_app, url_for, flash
from datetime import datetime, time
from io import BytesIO
from openpyxl import Workbook
from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError

from config.mongo import get_col
from utils.helper import parse_date, human_bytes

bp = Blueprint("files", __name__, url_prefix="/admin-klg/admin")


def _build_query(start_str: str, end_str: str, user_str: str) -> dict:
    """Build MongoDB query from date & user filters with error handling"""
    query: dict = {}

    try:
        # Date range parsing
        start_dt = parse_date(start_str)
        end_dt = parse_date(end_str)
        if start_dt or end_dt:
            query["createdAt"] = {}
            if start_dt:
                query["createdAt"]["$gte"] = datetime.combine(start_dt, time.min)
            if end_dt:
                query["createdAt"]["$lte"] = datetime.combine(end_dt, time.max)

        # User ObjectId parsing
        if user_str:
            try:
                query["user"] = ObjectId(user_str)
            except InvalidId as e:
                current_app.logger.warning(f"[Files] Invalid user ObjectId: {user_str}")
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"[Files] Invalid user ID format: {e}")

    except (ValueError, TypeError) as e:
        current_app.logger.error(f"[Files] Query building error: {e}")
    except Exception as e:
        current_app.logger.error(f"[Files] Unexpected error building query: {e}")

    return query


@bp.get("/files")
def file_monitoring():
    """File monitoring with comprehensive error handling"""
    try:
        # Get database collections
        files_col = get_col("files")
        users_col = get_col(current_app.config["USERS_COL"])
        agents_col = get_col("agents")
        convos_col = get_col("conversations")

        # Parse and validate parameters
        try:
            start_str = request.args.get("start", "").strip()
            end_str = request.args.get("end", "").strip()
            user_str = request.args.get("user", "").strip()
            sort_key = request.args.get("s", "createdAt").strip()
            sort_ord = request.args.get("o", "desc").strip()
            
            # Validate and parse pagination
            page = max(int(request.args.get("page", 1) or 1), 1)
            per_page = int(request.args.get("per_page", 10) or 10)
            per_page = max(min(per_page, 200), 5)
            
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"[Files] Parameter validation error: {e}")
            page, per_page = 1, 10

        # Validate sort parameters
        allowed_sort_keys = {"createdAt", "filename", "type", "bytes", "user"}
        if sort_key not in allowed_sort_keys:
            sort_key = "createdAt"
        if sort_ord not in {"asc", "desc"}:
            sort_ord = "desc"

        # Build query with error handling
        query = _build_query(start_str, end_str, user_str)

        # Get user dropdown options
        user_options = []
        if files_col is not None and users_col is not None:
            try:
                distinct_ids = [u for u in files_col.distinct("user", query) if isinstance(u, ObjectId)]
                if distinct_ids:
                    name_map = {}
                    try:
                        for u in users_col.find({"_id": {"$in": distinct_ids}}, {"name": 1, "email": 1}):
                            name_map[str(u["_id"])] = (u.get("name") or u.get("email") or str(u["_id"]))
                    except PyMongoError as e:
                        current_app.logger.error(f"[Files] Error loading user names: {e}")
                        
                    for oid in distinct_ids:
                        key = str(oid)
                        user_options.append({"_id": key, "name": name_map.get(key, key)})
                    user_options.sort(key=lambda x: (x["name"] or "").lower())
                    
            except PyMongoError as e:
                current_app.logger.error(f"[Files] Error getting user options: {e}")
            except (KeyError, TypeError) as e:
                current_app.logger.warning(f"[Files] Data format error in user options: {e}")

        # Get totals with error handling
        total_files = 0
        total_size_bytes = 0
        total_users = 0
        
        if files_col is not None:
            try:
                total_files = files_col.count_documents(query)
                
                # Calculate total size
                pipe = [
                    {"$match": query},
                    {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$bytes", 0]}}}},
                ]
                agg = list(files_col.aggregate(pipe))
                total_size_bytes = agg[0]["total"] if agg else 0
                
                # Count distinct users
                distinct_users = files_col.distinct("user", query)
                total_users = len([u for u in distinct_users if u is not None])
                
            except PyMongoError as e:
                current_app.logger.error(f"[Files] Database error calculating totals: {e}")
                flash("Error calculating file statistics", "warning")
            except (KeyError, TypeError) as e:
                current_app.logger.warning(f"[Files] Data format error in totals: {e}")

        total_size_h = human_bytes(total_size_bytes)

        # Sorting and pagination
        sort_fields_map = {
            "createdAt": "createdAt",
            "filename": "filename",
            "type": "type",
            "bytes": "bytes",
        }
        mongo_sort = sort_fields_map.get(sort_key, "createdAt")
        sort_dir = -1 if sort_ord == "desc" else 1

        rows = []
        if files_col is not None:
            try:
                cursor = files_col.find(query).sort(mongo_sort, sort_dir).skip((page - 1) * per_page).limit(per_page)
                
                for doc in cursor:
                    try:
                        # Resolve user name
                        user_name = None
                        if users_col is not None and doc.get("user"):
                            try:
                                u = users_col.find_one({"_id": doc["user"]}, {"name": 1})
                                if u:
                                    user_name = u.get("name")
                            except PyMongoError as e:
                                current_app.logger.warning(f"[Files] Error resolving user name: {e}")

                        # Find related agent
                        related_agent = None
                        try:
                            if doc.get("context") == "agents":
                                target_file_id = doc.get("file_id")
                                if target_file_id and agents_col is not None:
                                    related_agent = agents_col.find_one({
                                        "tool_resources.file_search.file_ids": {"$in": [target_file_id]}
                                    })

                            # Check conversation files
                            file_id = doc.get("file_id")
                            if file_id and convos_col is not None:
                                conversation_with_file = convos_col.find_one({"files": {"$in": [file_id]}})
                                if conversation_with_file and agents_col is not None:
                                    related_agent = agents_col.find_one({
                                        "id": conversation_with_file.get("agent_id")
                                    })
                        except PyMongoError as e:
                            current_app.logger.warning(f"[Files] Error finding related agent: {e}")

                        rows.append({
                            "createdAt": doc.get("createdAt"),
                            "filename": doc.get("filename"),
                            "type": doc.get("type"),
                            "size_h": human_bytes(doc.get("bytes")),
                            "size": doc.get("bytes"),
                            "user": user_name or (str(doc.get("user")) if doc.get("user") else None),
                            "user_id": str(doc.get("user")) if doc.get("user") else "",
                            "_id": str(doc.get("_id")),
                            "file_id": doc.get("file_id"),
                            "agent": related_agent.get("name") if related_agent else '-',
                        })
                        
                    except (KeyError, TypeError, AttributeError) as e:
                        current_app.logger.warning(f"[Files] Error processing file record: {e}")
                        continue
                        
            except PyMongoError as e:
                current_app.logger.error(f"[Files] Database error fetching files: {e}")
                flash("Error fetching file data", "danger")

        # Sort by user name in-memory
        if sort_key == "user":
            try:
                rows.sort(key=lambda r: (r["user"] or "").lower(), reverse=(sort_ord == "desc"))
            except (KeyError, TypeError) as e:
                current_app.logger.warning(f"[Files] Error sorting by user: {e}")

        # Handle Excel export
        if request.args.get("export") == "1":
            try:
                return _export_excel(files_col, users_col, agents_col, convos_col, query, mongo_sort, sort_dir, 
                                   sort_key, sort_ord, start_str, end_str, user_str)
            except Exception as e:
                current_app.logger.error(f"[Files] Excel export error: {e}")
                flash("Error generating Excel export", "danger")

        total_pages = max((total_files + per_page - 1) // per_page, 1) if total_files > 0 else 1

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
        
    except Exception as e:
        current_app.logger.error(f"[Files] Route error: {e}")
        flash("System error. Please contact administrator.", "danger")
        return render_template(
            "files.html",
            title="File Monitoring",
            active="files",
            rows=[],
            start="",
            end="",
            user="",
            user_options=[],
            s="createdAt",
            o="desc",
            page=1,
            per_page=10,
            total=0,
            total_pages=1,
            total_size_bytes=0,
            total_size_h="0 B",
            total_users=0,
        )


def _export_excel(files_col, users_col, agents_col, convos_col, query, mongo_sort, sort_dir, 
                 sort_key, sort_ord, start_str, end_str, user_str):
    """Export files to Excel with error handling"""
    try:
        all_rows = []
        if files_col is not None:
            try:
                cur = files_col.find(query).sort(mongo_sort, sort_dir)
                for doc in cur:
                    try:
                        uname = None
                        if users_col is not None and doc.get("user"):
                            try:
                                u = users_col.find_one({"_id": doc["user"]}, {"name": 1})
                                if u:
                                    uname = u.get("name")
                            except PyMongoError as e:
                                current_app.logger.warning(f"[Files] Export user lookup error: {e}")

                        agent_name = "-"
                        related_agent = None
                        try:
                            if doc.get("context") == "agents":
                                target_file_id = doc.get("file_id")
                                if target_file_id and agents_col is not None:
                                    related_agent = agents_col.find_one({
                                        "tool_resources.file_search.file_ids": {"$in": [target_file_id]}
                                    })
                            
                            # Check conversation files
                            file_id = doc.get("file_id")
                            if file_id and convos_col is not None:
                                conversation_with_file = convos_col.find_one({"files": {"$in": [file_id]}})
                                if conversation_with_file and agents_col is not None:
                                    related_agent = agents_col.find_one({
                                        "id": conversation_with_file.get("agent_id")
                                    })
                            
                            agent_name = related_agent.get("name") if related_agent else "-"
                        except PyMongoError as e:
                            current_app.logger.warning(f"[Files] Export agent lookup error: {e}")

                        all_rows.append({
                            "createdAt": doc.get("createdAt"),
                            "filename": doc.get("filename"),
                            "type": doc.get("type"),
                            "size": doc.get("bytes"),
                            "user": uname or (str(doc.get("user")) if doc.get("user") else None),
                            "_id": str(doc.get("_id")),
                            "file_id": doc.get("file_id"),
                            "agent": agent_name,
                        })
                    except (KeyError, TypeError, AttributeError) as e:
                        current_app.logger.warning(f"[Files] Export record processing error: {e}")
                        continue
                        
            except PyMongoError as e:
                current_app.logger.error(f"[Files] Export database error: {e}")
                raise

        if sort_key == "user":
            try:
                all_rows.sort(key=lambda r: (r["user"] or "").lower(), reverse=(sort_ord == "desc"))
            except (KeyError, TypeError) as e:
                current_app.logger.warning(f"[Files] Export sorting error: {e}")

        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "files"
        headers = ["createdAt", "filename", "type", "size(bytes)", "uploadedBy", "agent"]
        ws.append(headers)
        
        for r in all_rows:
            try:
                ws.append([
                    r["createdAt"].isoformat() if r["createdAt"] else "",
                    r["filename"] or "",
                    r["type"] or "",
                    r["size"] or 0,
                    r["user"] or "",
                    r["agent"] or "",
                ])
            except (KeyError, AttributeError, ValueError) as e:
                current_app.logger.warning(f"[Files] Export row error: {e}")
                continue

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
        
    except (OSError, IOError) as e:
        current_app.logger.error(f"[Files] Excel file creation error: {e}")
        raise Exception("Failed to create Excel file")
    except Exception as e:
        current_app.logger.error(f"[Files] Excel export error: {e}")
        raise
