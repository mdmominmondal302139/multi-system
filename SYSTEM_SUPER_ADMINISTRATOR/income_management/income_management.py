from flask import Blueprint, render_template, request, session, redirect, url_for, Response, jsonify
import csv
import io
from datetime import datetime
from pathlib import Path
import importlib.util

ROLE = "SYSTEM_SUPER_ADMINISTRATOR"
PAGE = "income_management"
BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(f"{ROLE}_{PAGE}_services", BASE / "services.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
bp = Blueprint("system_super_administrator_income_management_bp", __name__, url_prefix="/system_super_administrator/income-management")

def _context():
    return {"role": session.get("role"), "user_id": session.get("user_id"), "username": session.get("username"), "branch_id": session.get("branch_id"), "branch_name": session.get("branch_name")}

def _format_date(value):
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return value

def _format_time(value):
    value = str(value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(value.upper(), fmt).strftime("%I:%M %p")
        except ValueError:
            pass
    return value

def _form_options():
    from DATABASE.mongodb import get_database
    db = get_database()
    branch_names = set()
    for collection_name in ("branches", "branch_management"):
        for x in db[collection_name].find({}):
            value = str(x.get("branch_name") or x.get("name") or x.get("branch") or "").strip()
            if value:
                branch_names.add(value)
    branches = sorted(branch_names, key=str.casefold)
    return {'branches': branches}

@bp.route("/export.csv", methods=["GET"])
def export_csv():
    if session.get("authenticated") is not True or session.get("role") != ROLE:
        return redirect(url_for("login"))
    records = service.list_records(_context(), request.args.to_dict())
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["SL", "Date", "Time", "Amount", "Income Type", "Method", "Note"])
    for i, record in enumerate(records, 1):
        writer.writerow([i, _format_date(record.get("date", "")), _format_time(record.get("time", "")), record.get("amount", ""), record.get("type", record.get("source", "")), record.get("method", ""), record.get("note", "")])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=income_records.csv"})


def _api_authorized():
    return session.get("authenticated") is True and session.get("role") == ROLE

def _member_is_active(doc):
    """Handle common active flags used by member/account collections."""
    inactive_values = {"inactive", "disabled", "suspended", "blocked", "deleted", "deactivated", "pending", "false", "0", "no"}
    for key in ("is_active", "active", "isActive", "enabled", "is_enabled"):
        if key in doc and doc.get(key) is not None:
            value = doc.get(key)
            if isinstance(value, bool):
                if not value:
                    return False
            elif str(value).strip().lower() in inactive_values:
                return False
    for key in ("status", "account_status", "member_status", "user_status"):
        if key in doc and doc.get(key) is not None:
            value = str(doc.get(key)).strip().lower()
            if value in inactive_values:
                return False
    return True


def _active_member_options():
    from DATABASE.mongodb import get_database
    from bson import ObjectId
    db = get_database()
    current_id = str(session.get("user_id") or "")
    current_username = str(session.get("username") or session.get("user_name") or "")
    current_name = str(session.get("full_name") or session.get("name") or "").strip()
    docs_by_key = {}
    current_doc = None
    for collection_name in ("users", "user", "members", "accounts"):
        try:
            collection = db[collection_name]
            queries = []
            if current_id:
                queries.extend([{"_id": ObjectId(current_id)}] if ObjectId.is_valid(current_id) else [{"_id": current_id}])
                queries.extend([{"user_id": current_id}, {"id": current_id}])
            if current_username:
                queries.extend([{"username": current_username}, {"user_name": current_username}])
            for query in queries:
                found = collection.find_one(query)
                if found and (current_doc is None):
                    current_doc = found
            for doc in collection.find({}).limit(2000):
                if not _member_is_active(doc):
                    continue
                role_text = str(doc.get("role") or doc.get("user_role") or "").strip().upper()
                doc_id = str(doc.get("_id") or doc.get("user_id") or doc.get("id") or "")
                username = str(doc.get("username") or doc.get("user_name") or doc.get("email") or "").strip()
                is_current = (current_id and doc_id == current_id) or (current_username and username.casefold() == current_username.casefold())
                # Show active member accounts; always keep the currently logged-in account available.
                if role_text and "SUPER_ADMIN" in role_text and not is_current:
                    continue
                name = ""
                for field in ("full_name", "fullname", "fullName", "name", "member_name", "display_name", "displayName"):
                    name = str(doc.get(field) or "").strip()
                    if name:
                        break
                label = name or username
                if not label:
                    continue
                mobile = ""
                for field in ("mobile_no", "mobile_number", "mobile", "phone_number", "phone", "contact_number", "contact", "telephone"):
                    value = doc.get(field)
                    if value is not None and str(value).strip():
                        mobile = str(value).strip()
                        break
                key = label.casefold()
                if key not in docs_by_key:
                    docs_by_key[key] = {"label": label, "value": label, "mobileNo": mobile, "isCurrent": bool(is_current)}
                elif is_current:
                    docs_by_key[key]["isCurrent"] = True
                    if mobile:
                        docs_by_key[key]["mobileNo"] = mobile
        except Exception:
            continue
    if current_doc:
        for field in ("full_name", "fullname", "fullName", "name", "member_name", "display_name", "displayName"):
            current_name = str(current_doc.get(field) or "").strip()
            if current_name:
                break
        if not current_name:
            current_name = current_username or "My Account"
    if not current_name:
        current_name = current_username or "My Account"
    current_key = current_name.casefold()
    if current_key not in docs_by_key:
        docs_by_key[current_key] = {"label": current_name, "value": current_name, "isCurrent": True}
    else:
        docs_by_key[current_key]["isCurrent"] = True
    options = sorted(docs_by_key.values(), key=lambda x: (not x["isCurrent"], x["label"].casefold()))
    return {"members": options, "currentUser": current_name}


@bp.route("/api/active-members", methods=["GET"])
def api_active_members():
    if not _api_authorized():
        return jsonify({"ok": False, "error": "Please log in again."}), 401
    try:
        return jsonify({"ok": True, **_active_member_options()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/api/records", methods=["GET"])
def api_list_records():
    if not _api_authorized():
        return jsonify({"ok": False, "error": "Please log in again."}), 401
    try:
        return jsonify({"ok": True, "records": service.list_records(_context())})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

@bp.route("/api/records", methods=["POST"])
def api_create_record():
    if not _api_authorized():
        return jsonify({"ok": False, "error": "Please log in again."}), 401
    try:
        data = request.get_json(silent=True) or {}
        record_id = service.create_record(_context(), data)
        return jsonify({"ok": True, "id": record_id, "message": "Income saved successfully."}), 201
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

@bp.route("/api/records/<record_id>", methods=["PUT", "DELETE"])
def api_change_record(record_id):
    if not _api_authorized():
        return jsonify({"ok": False, "error": "Please log in again."}), 401
    try:
        if request.method == "DELETE":
            deleted = service.delete_record(_context(), record_id)
            if not deleted:
                return jsonify({"ok": False, "error": "Record not found."}), 404
            return jsonify({"ok": True, "message": "Income deleted successfully."})
        data = request.get_json(silent=True) or {}
        updated = service.update_record(_context(), record_id, data)
        if not updated:
            return jsonify({"ok": False, "error": "Record not found."}), 404
        return jsonify({"ok": True, "message": "Income updated successfully."})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

@bp.route("/", methods=["GET", "POST"])
def page():
    if session.get("authenticated") is not True or session.get("role") != ROLE:
        return redirect(url_for("login"))
    message = session.pop("income_management_message", None)
    error = None
    records = []
    try:
        options = _form_options()
    except Exception as exc:
        options = {'branches': []}
        error = f"Option loading error: {exc}"
    try:
        if request.method == "POST":
            action = request.form.get("action", "save")
            data = dict(request.form)
            if action == "delete":
                service.delete_record(_context(), request.form.get("record_id", ""))
                session["income_management_message"] = "Income deleted successfully."
            elif action == "update":
                service.update_record(_context(), request.form.get("record_id", ""), data)
                session["income_management_message"] = "Income updated successfully."
            else:
                service.create_record(_context(), data)
                session["income_management_message"] = "Income saved successfully."
            # Post/Redirect/Get prevents duplicate records when the page is refreshed.
            return redirect(url_for("system_super_administrator_income_management_bp.page"))
        records = service.list_records(_context(), request.args.to_dict())
    except Exception as exc:
        error = str(exc)
    return render_template("SYSTEM_SUPER_ADMINISTRATOR/income_management/income_management.html", records=records, message=message, error=error, session=session, options=options, format_date=_format_date, format_time=_format_time)
