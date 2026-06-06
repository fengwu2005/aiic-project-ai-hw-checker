from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cocode_viva.config import DATA_DIR, SESSION_DIR


PORTAL_PATH = DATA_DIR / "portal.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_portal() -> dict[str, Any]:
    if not PORTAL_PATH.exists():
        store = _default_store()
        save_portal(store)
        return store
    try:
        data = json.loads(PORTAL_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = _default_store()
    changed = _ensure_defaults(data)
    if changed:
        save_portal(data)
    return data


def save_portal(store: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PORTAL_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def register_user(role: str, username: str, password: str, display_name: str, class_code: str = "") -> tuple[dict[str, Any] | None, str]:
    role = role.strip()
    username = username.strip()
    display_name = display_name.strip() or username
    if role not in {"student", "teacher"}:
        return None, "请选择学生或教师身份。"
    if len(username) < 2 or len(password) < 4:
        return None, "账号至少 2 位，密码至少 4 位。"

    store = load_portal()
    if any(user["username"] == username for user in store["users"].values()):
        return None, "该账号已存在。"

    class_id = ""
    if role == "student":
        klass = class_by_code(store, class_code)
        if not klass:
            return None, "班级邀请码不存在，请向教师确认。"
        class_id = klass["id"]

    user_id = secrets.token_hex(8)
    user = {
        "id": user_id,
        "role": role,
        "username": username,
        "display_name": display_name,
        "password_hash": _hash_password(password),
        "class_id": class_id,
        "created_at": now_iso(),
    }
    store["users"][user_id] = user
    save_portal(store)
    return _public_user(user), ""


def authenticate(username: str, password: str) -> tuple[dict[str, Any] | None, str]:
    store = load_portal()
    for user in store["users"].values():
        if user["username"] == username.strip() and _verify_password(password, user["password_hash"]):
            return _public_user(user), ""
    return None, "账号或密码错误。"


def create_login_token(user_id: str) -> str:
    store = load_portal()
    token = secrets.token_urlsafe(24)
    store.setdefault("tokens", {})[token] = {
        "user_id": user_id,
        "created_at": now_iso(),
    }
    save_portal(store)
    return token


def delete_login_token(token: str) -> None:
    store = load_portal()
    store.setdefault("tokens", {}).pop(token, None)
    save_portal(store)


def user_by_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    store = load_portal()
    entry = store.get("tokens", {}).get(token)
    if not entry:
        return None
    user = store.get("users", {}).get(entry.get("user_id", ""))
    return _public_user(user) if user else None


def get_class(class_id: str) -> dict[str, Any] | None:
    return load_portal().get("classes", {}).get(class_id)


def class_by_code(store: dict[str, Any], class_code: str) -> dict[str, Any] | None:
    normalized = class_code.strip().upper()
    for klass in store.get("classes", {}).values():
        if klass.get("code", "").upper() == normalized:
            return klass
    return None


def list_assignments_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    store = load_portal()
    assignments = list(store.get("assignments", {}).values())
    if user["role"] == "student":
        assignments = [item for item in assignments if item.get("class_id") == user.get("class_id")]
    return sorted(assignments, key=lambda item: item.get("created_at", ""))


def get_assignment(assignment_id: str) -> dict[str, Any] | None:
    return load_portal().get("assignments", {}).get(assignment_id)


def list_submissions(user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    submissions = []
    for path in sorted(SESSION_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meta = session.get("portal", {})
        if not meta:
            continue
        if user:
            if user["role"] == "student" and meta.get("student_id") != user["id"]:
                continue
            if user["role"] == "teacher":
                pass
        submissions.append(_submission_summary(session))
    return submissions


def attach_submission_context(session: dict[str, Any], user: dict[str, Any], assignment_id: str) -> dict[str, Any]:
    assignment = get_assignment(assignment_id) or {}
    klass = get_class(assignment.get("class_id", "")) or {}
    session["portal"] = {
        "student_id": user["id"],
        "student_name": user["display_name"],
        "class_id": klass.get("id", ""),
        "class_name": klass.get("name", ""),
        "assignment_id": assignment.get("id", assignment_id),
        "assignment_title": assignment.get("title", "TaskFlow Pro"),
        "submitted_at": now_iso(),
        "status": "defending",
    }
    return session


def mark_submission_report_ready(session: dict[str, Any]) -> dict[str, Any]:
    session.setdefault("portal", {})["status"] = "pending_review"
    session["portal"]["report_ready_at"] = now_iso()
    return session


def save_teacher_review(session: dict[str, Any], teacher: dict[str, Any], final_score: int, comment: str) -> dict[str, Any]:
    final_score = max(0, min(100, int(final_score)))
    session["teacher_review"] = {
        "teacher_id": teacher["id"],
        "teacher_name": teacher["display_name"],
        "final_score": final_score,
        "comment": comment.strip(),
        "reviewed_at": now_iso(),
    }
    session.setdefault("portal", {})["status"] = "reviewed"
    return session


def _submission_summary(session: dict[str, Any]) -> dict[str, Any]:
    meta = session.get("portal", {})
    report = session.get("report") or {}
    review = session.get("teacher_review") or {}
    return {
        "id": session.get("id", ""),
        "student_name": meta.get("student_name", "未知学生"),
        "class_name": meta.get("class_name", "未分班"),
        "assignment_title": meta.get("assignment_title", "未关联作业"),
        "status": meta.get("status", "defending"),
        "submitted_at": meta.get("submitted_at", ""),
        "has_report": bool(report),
        "ai_score": report.get("total"),
        "final_score": review.get("final_score"),
        "reviewed": bool(review),
    }


def _default_store() -> dict[str, Any]:
    now = now_iso()
    return {
        "users": {},
        "tokens": {},
        "classes": {
            "class-ai-2026": {
                "id": "class-ai-2026",
                "name": "智能方向 2026 春",
                "code": "AI2026",
                "created_at": now,
            }
        },
        "assignments": {
            "image-lab": {
                "id": "image-lab",
                "class_id": "class-ai-2026",
                "title": "ImageLab：AI 协作图像变换作业",
                "description": "实现图片读取与多种图像变换，并通过 AI 助教短答辩。",
                "created_at": now,
            }
        },
    }


def _ensure_defaults(store: dict[str, Any]) -> bool:
    changed = False
    defaults = _default_store()
    for key in ("users", "tokens", "classes", "assignments"):
        if key not in store or not isinstance(store[key], dict):
            store[key] = defaults[key]
            changed = True
    for key, value in defaults["classes"].items():
        if key not in store["classes"]:
            store["classes"][key] = value
            changed = True
    for key, value in defaults["assignments"].items():
        if key not in store["assignments"]:
            store["assignments"][key] = value
            changed = True
    return changed


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(12)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"{salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    current = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return secrets.compare_digest(current, digest)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key != "password_hash"}
