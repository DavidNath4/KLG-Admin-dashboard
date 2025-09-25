from datetime import datetime
from bson.regex import Regex
from extensions.db import get_collection
from flask import current_app

def col_users():
    return get_collection(current_app.config['USERS_COL'])

def find_user_by_username(email_query: ste, limit: int = 20):
    regex = Regex(f".*{email_query}.*", "i")
    users = col_users().find({"email": regex}).limit(limit)
    return list(users)

def update_user_role(user_id, new_role: str):
    from bson import ObjectId
    res = col_users().update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role, "updated_at": datetime.utcnow()}}
    )
    return res.modified_count == 1