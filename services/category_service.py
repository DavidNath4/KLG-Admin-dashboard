import re
import uuid
from datetime import datetime
import typing import List, Dict, Any
from extensions
from flask import current_app

def col_cats():
    return get_collection(current_app.config['CATS_COL'])

def kebab(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')

def next_order() -> int:
    last_cat = col_cats().find_one(sort=[("order", -1)])
    return (last_cat["order"] + 1) if last_cat and "order" in last_cat else 1

def list_categories() -> List[Dict[str, Any]]:
    cats = col_cats().find().sort("order", 1)
    return list(cats)

def create_category(name: str, created_from_ui: bool = True) -> Dict[str, Any]:
    """Generate unique guid for id/value/label/description as requested.
    Keep human-readable name and slug; ensure unique order.
    """
    slug = kebab(name)
    guid = uuid.uuid4().hex # 32 hex chars
    short = guid[:8]


    payload = {
        # Mongo _id is ObjectId; we also keep our own GUID string id
        "id": guid,
        "name": name,
        "slug": slug,
        "value": f"{slug}-{short}",
        "label": f"com_agents_category_{slug}_{short}",
        "description": f"com_agents_category_{slug}_{short}_description",
        "order": next_order(),
        "isActive": True,
        "custom": bool(created_from_ui),
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
        "__v": 0,
    }
    col_cats().insert_one(payload)
    return payload

def delete_category(cat_id: str) -> bool:
    from bson import ObjectId
    res = col_cats().delete_one({"_id": ObjectId(cat_id)})
    if res.deleted_count:
        reorder_categories()
        return True
    return False

def reorder_categories():
    cats = list_categories()
    for index, cat in enumerate(cats):
        new_order = index + 1
        if cat.get("order") != new_order:
            col_cats().update_one(
                {"_id": cat["_id"]},
                {"$set": {"order": new_order, "updatedAt": datetime.utcnow()}}
            )
        if ops:
            for op in ops:
                col_cats().update_one(op["filter"], op["update"])

def move_category(doc_id: str, direction: str) -> bool:
    cats = list_categories()
    idx = next((i for i, c in enumerate(cats) if str(c["_id"]) == doc_id), None)
    if idx is None:
        return False
    if direction == "up" and idx > 0:
        cats[idx]["order"], cats[idx-1]["order"] = cats[idx-1]["order"], cats[idx]["order"]
    elif direction == "down" and idx < len(cats)-1:
        cats[idx]["order"], cats[idx+1]["order"] = cats[idx+1]["order"], cats[idx]["order"]
    else:
        return False
    # Persist swapped orders
    col_cats().update_one({"_id": cats[idx]["_id"]}, {"$set": {"order": cats[idx]["order"], "updatedAt": datetime.utcnow()}})
    neighbor = cats[idx-1] if direction == "up" else cats[idx+1]
    col_cats().update_one({"_id": neighbor["_id"]}, {"$set": {"order": neighbor["order"], "updatedAt": datetime.utcnow()}})
    # Normalize
    reorder_categories()
    return True