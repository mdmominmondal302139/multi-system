from datetime import datetime, timezone
from bson import ObjectId
from DATABASE.mongodb import get_database, clean

ROLE = "SYSTEM_SUPER_ADMINISTRATOR"
COLLECTION = "income_management"

def _guard(context):
    if not isinstance(context, dict) or context.get("role") != ROLE:
        raise PermissionError("Access denied.")

def _to_id(value):
    value = str(value or "")
    return ObjectId(value) if ObjectId.is_valid(value) else value

def _serialize(doc):
    record_id = doc.get("_id") or doc.get("id") or ""
    def _date_text(value):
        return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
    entries = doc.get("items") if isinstance(doc.get("items"), list) else []
    normalized_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            amount = float(entry.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        normalized_entries.append({
            "id": str(entry.get("id") or ""),
            "type": str(entry.get("type") or ""),
            "amount": amount,
            "description": str(entry.get("description") or ""),
            "receipt": str(entry.get("receipt") or ""),
        })
    try:
        total = float(doc.get("total") or sum(entry["amount"] for entry in normalized_entries))
    except (TypeError, ValueError):
        total = sum(entry["amount"] for entry in normalized_entries)
    return {
        "id": str(record_id),
        "date": str(doc.get("date") or ""),
        "source": str(doc.get("source") or doc.get("project") or ""),
        "project": str(doc.get("source") or doc.get("project") or ""),
        "submittedBy": str(doc.get("submittedBy") or ""),
        "mobileNo": str(doc.get("mobileNo") or ""),
        "paymentMethod": str(doc.get("paymentMethod") or ""),
        "remarks": str(doc.get("remarks") or ""),
        "items": normalized_entries,
        "total": total,
        "createdAt": _date_text(doc.get("created_at")),
        "updatedAt": _date_text(doc.get("updated_at")),
    }

def list_records(context, filters=None):
    _guard(context)
    docs = get_database()[COLLECTION].find({}).sort("_id", -1)
    return [_serialize(doc) for doc in docs]

def create_record(context, data):
    _guard(context)
    data = dict(data or {})
    item = {
        "date": str(data.get("date") or ""),
        "source": str(data.get("source") or data.get("project") or "").strip(),
        "project": str(data.get("source") or data.get("project") or "").strip(),
        "submittedBy": str(data.get("submittedBy") or "").strip(),
        "mobileNo": str(data.get("mobileNo") or "").strip(),
        "paymentMethod": str(data.get("paymentMethod") or "").strip(),
        "remarks": str(data.get("remarks") or "").strip(),
        "items": [],
        "total": 0.0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "created_by": context.get("user_id"),
        "created_by_role": ROLE,
    }
    for entry in data.get("items", []):
        if not isinstance(entry, dict):
            continue
        item["items"].append({
            "id": str(entry.get("id") or ""),
            "type": str(entry.get("type") or "").strip(),
            "amount": float(entry.get("amount") or 0),
            "description": str(entry.get("description") or "").strip(),
            "receipt": str(entry.get("receipt") or "").strip(),
        })
    item["total"] = sum(entry["amount"] for entry in item["items"])
    result = get_database()[COLLECTION].insert_one(item)
    return str(result.inserted_id)

def update_record(context, record_id, data):
    _guard(context)
    data = dict(data or {})
    entries = []
    for entry in data.get("items", []):
        if not isinstance(entry, dict):
            continue
        entries.append({
            "id": str(entry.get("id") or ""),
            "type": str(entry.get("type") or "").strip(),
            "amount": float(entry.get("amount") or 0),
            "description": str(entry.get("description") or "").strip(),
            "receipt": str(entry.get("receipt") or "").strip(),
        })
    item = {
        "date": str(data.get("date") or ""),
        "source": str(data.get("source") or data.get("project") or "").strip(),
        "project": str(data.get("source") or data.get("project") or "").strip(),
        "submittedBy": str(data.get("submittedBy") or "").strip(),
        "mobileNo": str(data.get("mobileNo") or "").strip(),
        "paymentMethod": str(data.get("paymentMethod") or "").strip(),
        "remarks": str(data.get("remarks") or "").strip(),
        "items": entries,
        "total": sum(entry["amount"] for entry in entries),
        "updated_at": datetime.now(timezone.utc),
    }
    result = get_database()[COLLECTION].update_one({"_id": _to_id(record_id)}, {"$set": item})
    return result.modified_count or result.matched_count

def delete_record(context, record_id):
    _guard(context)
    result = get_database()[COLLECTION].delete_one({"_id": _to_id(record_id)})
    return result.deleted_count
