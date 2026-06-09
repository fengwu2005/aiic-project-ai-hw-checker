from __future__ import annotations

import shutil
import uuid
import argparse
import socket
import io
import zipfile
import asyncio
import time
from datetime import datetime, timezone

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

from cocode_viva.config import PROJECT_ROOT, STATIC_DIR, TEMPLATE_DIR, UPLOAD_DIR
from cocode_viva.debug_log import format_events_for_view, list_snapshots, read_events
from cocode_viva.privacy import privacy_summary
from cocode_viva.skills.similarity_skill import analyze_similarity
from cocode_viva.engine import (
    analyze_submission,
    dialogue_timeline,
    finish_defense,
    load_session,
    prepare_first_question,
    process_pending_answer,
    process_pending_clarification,
    record_answer,
    save_session,
)
from cocode_viva.portal import (
    attach_submission_context,
    authenticate,
    create_login_token,
    delete_login_token,
    get_assignment,
    get_class,
    list_assignments_for_user,
    list_submission_groups,
    list_submissions,
    mark_submission_report_ready,
    repair_session_status,
    register_user,
    save_teacher_review,
    user_by_token,
)
from cocode_viva.skills.archive_skill import ArchiveError


env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)

AUTH_COOKIE = "cocode_viva_token"
SUBMISSION_LOCKS: set[str] = set()
ANSWER_LOCKS: set[str] = set()
BACKGROUND_SESSION_TASKS: set[str] = set()
ACTIVE_TERMINALS: dict[str, dict] = {}
ACTIVE_WINDOW_SECONDS = 60
ACTIVE_PRINT_INTERVAL_SECONDS = 10

SUBMISSION_FILE_LABELS = {
    "readme": "README.md",
    "final_code": "final/image_ops.py",
    "student_report": "report/report.md",
}


def render(template: str, **context) -> web.Response:
    context.setdefault("dialogue_timeline", dialogue_timeline)
    page = env.get_template(template).render(**context)
    return web.Response(text=page, content_type="text/html")


def current_user(request: web.Request) -> dict | None:
    return user_by_token(request.cookies.get(AUTH_COOKIE))


def redirect_for_user(user: dict | None) -> str:
    if not user:
        return "/login"
    return "/teacher" if user["role"] == "teacher" else "/student"


def require_role(request: web.Request, role: str | None = None) -> dict:
    user = current_user(request)
    if not user:
        raise web.HTTPFound("/login")
    if role and user["role"] != role:
        raise web.HTTPForbidden(text="当前账号无权访问该页面。")
    return user


def require_session_for_student(session: dict, user: dict) -> None:
    if user["role"] == "student" and session.get("portal", {}).get("student_id") != user["id"]:
        raise web.HTTPForbidden(text="不能访问其他学生的答辩会话。")


def _terminal_key(request: web.Request, user: dict | None) -> str:
    if user:
        return f"user:{user['id']}"
    remote = request.remote or "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")[:80]
    return f"guest:{remote}:{user_agent}"


def _terminal_label(request: web.Request, user: dict | None) -> str:
    remote = request.remote or "unknown"
    if user:
        return f"{user.get('display_name', user.get('username', '用户'))}({user.get('role', '-')})@{remote}"
    return f"未登录@{remote}"


def _active_terminal_rows() -> list[dict]:
    now = time.monotonic()
    stale_keys = [
        key for key, item in ACTIVE_TERMINALS.items()
        if now - float(item.get("last_seen", 0)) > ACTIVE_WINDOW_SECONDS
    ]
    for key in stale_keys:
        ACTIVE_TERMINALS.pop(key, None)
    return sorted(ACTIVE_TERMINALS.values(), key=lambda item: item.get("last_seen", 0), reverse=True)


@web.middleware
async def terminal_monitor_middleware(request: web.Request, handler):
    user = current_user(request)
    if not request.path.startswith("/static/"):
        ACTIVE_TERMINALS[_terminal_key(request, user)] = {
            "label": _terminal_label(request, user),
            "path": request.path,
            "method": request.method,
            "last_seen": time.monotonic(),
            "wall_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    return await handler(request)


async def _print_active_terminals(app: web.Application) -> None:
    try:
        while True:
            await asyncio.sleep(ACTIVE_PRINT_INTERVAL_SECONDS)
            rows = _active_terminal_rows()
            if not rows:
                print(f"[访问监控] 最近 {ACTIVE_WINDOW_SECONDS} 秒活跃终端：0")
                continue
            summary = " | ".join(
                f"{item['label']} {item['method']} {item['path']}"
                for item in rows[:6]
            )
            more = f" | 另 {len(rows) - 6} 个" if len(rows) > 6 else ""
            print(f"[访问监控] 最近 {ACTIVE_WINDOW_SECONDS} 秒活跃终端：{len(rows)} | {summary}{more}")
    except asyncio.CancelledError:
        pass


async def _start_terminal_monitor(app: web.Application) -> None:
    app["terminal_monitor_task"] = asyncio.create_task(_print_active_terminals(app))
    print(f"[访问监控] 已开启：每 {ACTIVE_PRINT_INTERVAL_SECONDS} 秒显示最近 {ACTIVE_WINDOW_SECONDS} 秒活跃终端数。")


async def _stop_terminal_monitor(app: web.Application) -> None:
    task = app.get("terminal_monitor_task")
    if task:
        task.cancel()
        await task


def _line_numbered(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return "1  "
    width = len(str(len(lines)))
    return "\n".join(f"{index:>{width}}  {line}" for index, line in enumerate(lines, start=1))


def _submission_files(session: dict) -> list[dict]:
    material_texts = session.get("material_texts") or {}
    materials = session.get("analysis", {}).get("materials", {})
    files = []
    for key, path in SUBMISSION_FILE_LABELS.items():
        text = material_texts.get(key, "")
        meta = materials.get(key, {})
        files.append({
            "key": key,
            "path": meta.get("found") or path,
            "expected": path,
            "text": text,
            "numbered_text": _line_numbered(text),
            "chars": len(text),
            "missing": not bool(text),
        })
    return files


def _submission_zip_bytes(session: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in _submission_files(session):
            archive.writestr(f"ImageLab_Submission/{item['expected']}", item["text"])
    return buffer.getvalue()


def _download_filename(session: dict) -> str:
    return f"imagelab_{session.get('id', 'submission')}.zip"


def _supplement_target(filename: str) -> str | None:
    lowered = filename.lower()
    if lowered.endswith(".py"):
        return "final_code"
    if lowered == "readme.md":
        return "readme"
    if lowered.endswith(".md") or lowered.endswith(".txt"):
        return "student_report"
    return None


def _merged_supplement_zip(session: dict, target_key: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in _submission_files(session):
            content = text if item["key"] == target_key else item["text"]
            archive.writestr(f"ImageLab_Submission/{item['expected']}", content)
    return buffer.getvalue()


def _start_background(coro, *, report_may_be_ready: bool = False, session_id: str | None = None) -> None:
    if session_id and session_id in BACKGROUND_SESSION_TASKS:
        return
    if session_id:
        BACKGROUND_SESSION_TASKS.add(session_id)
    task = asyncio.create_task(coro)

    def _done(done_task: asyncio.Task) -> None:
        try:
            session = done_task.result()
            if report_may_be_ready and session and session.get("report"):
                session = mark_submission_report_ready(session)
                save_session(session)
        except Exception as exc:
            if session_id:
                try:
                    session = load_session(session_id)
                    session["processing"] = None
                    session["question_update_pending"] = False
                    session["processing_error"] = f"后台处理失败：{exc}"
                    save_session(session)
                except Exception:
                    pass
            print(f"Background task failed: {exc}")
        finally:
            if session_id:
                BACKGROUND_SESSION_TASKS.discard(session_id)

    task.add_done_callback(_done)


def _redirect_defense(session_id: str) -> web.HTTPFound:
    return web.HTTPFound(f"/student/defense/{session_id}")


def _repair_stale_first_question_processing(session: dict) -> dict:
    processing = session.get("processing") or {}
    if processing.get("kind") == "first_question":
        session["processing"] = None
        session["question_update_pending"] = True
        session["question_update_message"] = processing.get("message") or "AI 助教正在阅读你的代码和报告，生成第一道答辩问题。"
        save_session(session)
    return session


def _repair_session_for_view(session: dict) -> dict:
    changed = repair_session_status(session)
    if changed:
        save_session(session)
    return session


def _refresh_similarity_for_session(session: dict) -> dict:
    source = (session.get("material_texts") or {}).get("final_code", "")
    if not source:
        return session
    student_id = (session.get("portal") or {}).get("student_id", "")
    session.setdefault("analysis", {})["similarity"] = analyze_similarity(session.get("id", ""), source, student_id)
    session["analysis"]["privacy"] = privacy_summary()
    if session.get("report"):
        session["report"]["similarity"] = session["analysis"]["similarity"]
        session["report"]["privacy"] = session["analysis"]["privacy"]
    return session


def _needs_final_report(session: dict) -> bool:
    if session.get("report"):
        return False
    answers = session.get("answers") if isinstance(session.get("answers"), dict) else {}
    questions = session.get("questions") if isinstance(session.get("questions"), list) else []
    max_rounds = int(session.get("max_rounds") or 6)
    current_index = int(session.get("current_index") or 0)
    return bool(answers) and (
        len(answers) >= max_rounds
        or current_index >= len(questions) and len(answers) >= len(questions)
    )


def _ensure_final_report_background(session: dict) -> dict:
    session_id = session.get("id", "")
    if not session_id or not _needs_final_report(session):
        return session
    processing = session.get("processing") or {}
    if processing.get("kind") != "final_report":
        session["processing"] = {
            "kind": "final_report",
            "message": "答辩已完成，系统正在生成评分报告。",
        }
        save_session(session)
    if session_id not in BACKGROUND_SESSION_TASKS:
        _start_background(finish_defense(session_id, session.get("answers", {})), report_may_be_ready=True, session_id=session_id)
    return session


def _resume_pending_background_work(session: dict) -> None:
    processing = session.get("processing") or {}
    session_id = session.get("id", "")
    if not session_id or session_id in BACKGROUND_SESSION_TASKS:
        return
    if _needs_final_report(session):
        _start_background(finish_defense(session_id, session.get("answers", {})), report_may_be_ready=True, session_id=session_id)
        return
    if processing.get("kind") in {"answer", "final_report"} and session.get("pending_answer"):
        _start_background(process_pending_answer(session_id), report_may_be_ready=True, session_id=session_id)
    elif processing.get("kind") == "clarification" and session.get("pending_clarification"):
        _start_background(process_pending_clarification(session_id), session_id=session_id)


async def index(request: web.Request) -> web.Response:
    user = current_user(request)
    raise web.HTTPFound(redirect_for_user(user))


async def login_page(request: web.Request) -> web.Response:
    return render("portal.html", page="login", mode="login", user=current_user(request), error=None)


async def register_page(request: web.Request) -> web.Response:
    return render("portal.html", page="login", mode="register", user=current_user(request), error=None)


async def login_submit(request: web.Request) -> web.Response:
    data = await request.post()
    user, error = authenticate(str(data.get("username", "")), str(data.get("password", "")))
    if not user:
        return render("portal.html", page="login", mode="login", user=None, error=error)
    response = web.HTTPFound(redirect_for_user(user))
    response.set_cookie(AUTH_COOKIE, create_login_token(user["id"]), httponly=True, samesite="Lax")
    raise response


async def register_submit(request: web.Request) -> web.Response:
    data = await request.post()
    user, error = register_user(
        str(data.get("role", "")),
        str(data.get("username", "")),
        str(data.get("password", "")),
        str(data.get("display_name", "")),
        str(data.get("class_code", "")),
    )
    if not user:
        return render("portal.html", page="login", mode="register", user=None, error=error)
    response = web.HTTPFound(redirect_for_user(user))
    response.set_cookie(AUTH_COOKIE, create_login_token(user["id"]), httponly=True, samesite="Lax")
    raise response


async def logout(request: web.Request) -> web.Response:
    delete_login_token(request.cookies.get(AUTH_COOKIE, ""))
    response = web.HTTPFound("/login")
    response.del_cookie(AUTH_COOKIE)
    raise response


async def assignment(request: web.Request) -> web.Response:
    return render("assignment.html", page="assignment", user=current_user(request))


async def student_dashboard(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    klass = get_class(user.get("class_id", ""))
    for item in list_submissions(user):
        try:
            _ensure_final_report_background(load_session(item["id"]))
        except Exception:
            pass
    return render(
        "student_dashboard.html",
        page="student",
        user=user,
        klass=klass,
        assignments=list_assignments_for_user(user),
        submissions=list_submissions(user),
    )


async def student_assignment(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    assignment_id = request.match_info["assignment_id"]
    assignment_obj = get_assignment(assignment_id)
    if not assignment_obj or assignment_obj.get("class_id") != user.get("class_id"):
        raise web.HTTPNotFound(text="作业不存在或不属于你的班级。")
    return render("assignment.html", page="assignment", user=user, assignment=assignment_obj)


async def defense_session(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="答辩会话不存在")
    session = _repair_stale_first_question_processing(session)
    session = _repair_session_for_view(session)
    session = _ensure_final_report_background(session)
    if session.get("report"):
        raise web.HTTPFound(f"/student/submissions/{session_id}/done")
    _resume_pending_background_work(session)
    require_session_for_student(session, user)
    return render("student_defense.html", page="student", user=user, session=session, error=None)


async def defense_status(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="答辩会话不存在")
    session = _repair_stale_first_question_processing(session)
    session = _repair_session_for_view(session)
    session = _ensure_final_report_background(session)
    _resume_pending_background_work(session)
    require_session_for_student(session, user)
    current_index = int(session.get("current_index", 0))
    questions = session.get("questions", [])
    current_question = questions[current_index] if current_index < len(questions) else None
    return web.json_response({
        "id": session_id,
        "processing": bool(session.get("processing")),
        "processing_kind": (session.get("processing") or {}).get("kind"),
        "processing_message": (session.get("processing") or {}).get("message", ""),
        "question_update_pending": bool(session.get("question_update_pending")),
        "current_index": current_index,
        "question_count": len(questions),
        "answer_count": len(session.get("answers", {})),
        "has_report": bool(session.get("report")),
        "first_question_fallback_ready": bool(session.get("first_question_fallback_ready")),
        "current_question_id": current_question.get("id") if current_question else "",
        "current_question_text": current_question.get("text") if current_question else "",
        "current_question_source": current_question.get("source") if current_question else "",
    })


async def upload_submission(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    assignment_id = request.match_info.get("assignment_id", "image-lab")
    assignment_obj = get_assignment(assignment_id)
    if not assignment_obj or assignment_obj.get("class_id") != user.get("class_id"):
        raise web.HTTPNotFound(text="作业不存在或不属于你的班级。")

    lock_key = f"upload:{user['id']}:{assignment_id}"
    if lock_key in SUBMISSION_LOCKS:
        return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error="上一次提交仍在处理中，请不要重复点击。")
    SUBMISSION_LOCKS.add(lock_key)
    temp_path = None
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != "submission":
            return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error="请上传 zip 格式作业包。")

        filename = field.filename or "submission.zip"
        if not filename.lower().endswith(".zip"):
            return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error="文件格式必须是 .zip。")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.zip"
        with temp_path.open("wb") as output:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                output.write(chunk)
        session = await analyze_submission(temp_path, use_agent=False)
        session = attach_submission_context(session, user, assignment_id)
        session = _refresh_similarity_for_session(session)
        if session.get("agent_enabled"):
            session["question_update_pending"] = True
            session["question_update_message"] = "AI 助教正在阅读你的代码和报告，生成第一道答辩问题。"
        save_session(session)
        if session.get("agent_enabled"):
            _start_background(prepare_first_question(session["id"]), session_id=session["id"])
        raise _redirect_defense(session["id"])
    except ArchiveError as exc:
        return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error=str(exc))
    except web.HTTPException:
        raise
    except Exception as exc:
        return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error=f"分析失败：{exc}")
    finally:
        SUBMISSION_LOCKS.discard(lock_key)
        if temp_path and temp_path.exists():
            temp_path.unlink()


async def submit_answer(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    session = load_session(session_id)
    session = _repair_stale_first_question_processing(session)
    require_session_for_student(session, user)
    lock_key = f"answer:{session_id}"
    if lock_key in ANSWER_LOCKS or session.get("processing"):
        return render("student_defense.html", page="student", user=user, session=session, error="上一条回答正在处理中，请不要重复提交。")
    ANSWER_LOCKS.add(lock_key)
    try:
        data = await request.post()
        answer = str(data.get("answer", ""))
        if not answer.strip():
            return render("student_defense.html", page="student", user=user, session=session, error="请先填写本题回答，空回答不会提交。")
        session = await record_answer(session_id, answer)
        if session.get("pending_answer"):
            _start_background(process_pending_answer(session_id), report_may_be_ready=True, session_id=session_id)
        if session.get("report"):
            session = mark_submission_report_ready(session)
            save_session(session)
            raise web.HTTPFound(f"/student/submissions/{session_id}/done")
        raise _redirect_defense(session_id)
    finally:
        ANSWER_LOCKS.discard(lock_key)


async def supplement_submission(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    old_session = load_session(session_id)
    require_session_for_student(old_session, user)
    if old_session.get("report"):
        return render("student_defense.html", page="student", user=user, session=old_session, error="答辩已完成，不能再补交文件。")

    lock_key = f"supplement:{session_id}"
    if lock_key in SUBMISSION_LOCKS or old_session.get("processing"):
        return render("student_defense.html", page="student", user=user, session=old_session, error="补交正在处理中，请不要重复提交。")
    SUBMISSION_LOCKS.add(lock_key)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != "supplement":
            return render("student_defense.html", page="student", user=user, session=old_session, error="请上传补交文件。")

        filename = field.filename or "supplement.zip"
        lowered_filename = filename.lower()
        target_key = _supplement_target(filename)
        if not lowered_filename.endswith(".zip") and not target_key:
            return render("student_defense.html", page="student", user=user, session=old_session, error="补交文件必须是 .zip、.py、.md 或 .txt。")

        temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.zip"
        uploaded = bytearray()
        with temp_path.open("wb") as output:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                if lowered_filename.endswith(".zip"):
                    output.write(chunk)
                else:
                    uploaded.extend(chunk)
        if not lowered_filename.endswith(".zip"):
            text = uploaded.decode("utf-8", errors="replace")
            temp_path.write_bytes(_merged_supplement_zip(old_session, target_key or "final_code", text))
        new_session = await analyze_submission(temp_path, use_agent=False, session_id=session_id)
        new_session["portal"] = old_session.get("portal", {})
        new_session = _refresh_similarity_for_session(new_session)
        new_session["resubmission_history"] = old_session.get("resubmission_history", []) + [{
            "previous_missing": old_session.get("analysis", {}).get("missing", []),
            "previous_answer_count": len(old_session.get("answers", {})),
        }]
        new_session["answers"] = {}
        new_session["current_index"] = 0
        new_session["report"] = None
        new_session.pop("teacher_review", None)
        new_session.setdefault("portal", {})["status"] = "defending"
        if new_session.get("agent_enabled"):
            new_session["question_update_pending"] = True
            new_session["question_update_message"] = "AI 助教正在基于补交文件重新生成第一道答辩问题。"
        save_session(new_session)
        if new_session.get("agent_enabled"):
            _start_background(prepare_first_question(new_session["id"]), session_id=new_session["id"])
        raise _redirect_defense(new_session["id"])
    except ArchiveError as exc:
        return render("student_defense.html", page="student", user=user, session=old_session, error=str(exc))
    except web.HTTPException:
        raise
    except Exception as exc:
        return render("student_defense.html", page="student", user=user, session=old_session, error=f"补交分析失败：{exc}")
    finally:
        SUBMISSION_LOCKS.discard(lock_key)
        if temp_path and temp_path.exists():
            temp_path.unlink()


async def student_done(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="提交记录不存在")
    session = _repair_session_for_view(session)
    session = _ensure_final_report_background(session)
    require_session_for_student(session, user)
    return render("student_done.html", page="student", user=user, session=session)


async def student_submission_files(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="提交记录不存在")
    session = _repair_session_for_view(session)
    require_session_for_student(session, user)
    return render("submission_files.html", page="student", user=user, session=session, files=_submission_files(session))


async def student_download_submission(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="提交记录不存在")
    session = _repair_session_for_view(session)
    require_session_for_student(session, user)
    data = _submission_zip_bytes(session)
    return web.Response(
        body=data,
        content_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_download_filename(session)}"'},
    )


async def student_delete_submission(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="提交记录不存在")
    require_session_for_student(session, user)
    session.setdefault("portal", {})["deleted_by_student"] = True
    session["portal"]["deleted_at"] = datetime.now(timezone.utc).isoformat()
    save_session(session)
    raise web.HTTPFound("/student")


async def report(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="报告不存在")
    session = _repair_session_for_view(session)
    session = _ensure_final_report_background(session)
    return render("report.html", page="teacher", user=user, session=session, can_review=True)


async def teacher_dashboard(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    for item in list_submissions():
        try:
            _ensure_final_report_background(load_session(item["id"]))
        except Exception:
            pass
    submissions = list_submissions()
    return render(
        "teacher_dashboard.html",
        page="teacher",
        user=user,
        assignments=list_assignments_for_user(user),
        submissions=submissions,
        submission_groups=list_submission_groups(),
    )


async def review_report(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="报告不存在")
    session = _repair_session_for_view(session)
    data = await request.post()
    try:
        final_score = int(str(data.get("final_score", "0")))
    except ValueError:
        final_score = int((session.get("report") or {}).get("total", 0))
    session = save_teacher_review(session, user, final_score, str(data.get("comment", "")))
    save_session(session)
    raise web.HTTPFound(f"/teacher/report/{session_id}")


async def debug_session(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="后台证据不存在")
    session = _repair_session_for_view(session)
    return render(
        "debug.html",
        page="debug",
        user=user,
        session=session,
        events=format_events_for_view(read_events(session_id)),
        snapshots=list_snapshots(session_id),
    )


async def teacher_submission_files(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="提交记录不存在")
    session = _repair_session_for_view(session)
    return render("submission_files.html", page="teacher", user=user, session=session, files=_submission_files(session))


async def teacher_download_submission(request: web.Request) -> web.Response:
    require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="提交记录不存在")
    session = _repair_session_for_view(session)
    data = _submission_zip_bytes(session)
    return web.Response(
        body=data,
        content_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{_download_filename(session)}"'},
    )


async def download_sample(request: web.Request) -> web.FileResponse:
    sample = PROJECT_ROOT / "examples" / "image_lab_sample_submission.zip"
    return web.FileResponse(sample)


def create_app() -> web.Application:
    app = web.Application(client_max_size=10 * 1024**2, middlewares=[terminal_monitor_middleware])
    app.on_startup.append(_start_terminal_monitor)
    app.on_cleanup.append(_stop_terminal_monitor)
    app.router.add_get("/", index)
    app.router.add_get("/login", login_page)
    app.router.add_get("/register", register_page)
    app.router.add_post("/login", login_submit)
    app.router.add_post("/register", register_submit)
    app.router.add_post("/logout", logout)
    app.router.add_get("/assignment", assignment)
    app.router.add_get("/student", student_dashboard)
    app.router.add_get("/student/assignments/{assignment_id}", student_assignment)
    app.router.add_post("/student/assignments/{assignment_id}/upload", upload_submission)
    app.router.add_get("/student/defense/{session_id}", defense_session)
    app.router.add_get("/student/defense/{session_id}/status", defense_status)
    app.router.add_post("/student/defense/{session_id}/answer", submit_answer)
    app.router.add_post("/student/defense/{session_id}/supplement", supplement_submission)
    app.router.add_get("/student/submissions/{session_id}/done", student_done)
    app.router.add_get("/student/submissions/{session_id}/files", student_submission_files)
    app.router.add_get("/student/submissions/{session_id}/download", student_download_submission)
    app.router.add_post("/student/submissions/{session_id}/delete", student_delete_submission)
    app.router.add_get("/teacher", teacher_dashboard)
    app.router.add_get("/teacher/report/{session_id}", report)
    app.router.add_post("/teacher/report/{session_id}/review", review_report)
    app.router.add_get("/teacher/debug/{session_id}", debug_session)
    app.router.add_get("/teacher/submissions/{session_id}/files", teacher_submission_files)
    app.router.add_get("/teacher/submissions/{session_id}/download", teacher_download_submission)
    app.router.add_get("/examples/image_lab_sample_submission.zip", download_sample)
    app.router.add_static("/static", STATIC_DIR)
    return app


def _first_available_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise OSError(f"No available port found from {preferred} to {preferred + 19}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run CoCode Viva")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    port = _first_available_port(args.host, args.port)
    if port != args.port:
        print(f"Port {args.port} is already in use. CoCode Viva will use {port} instead.")
    print(f"Open http://{args.host}:{port}")
    web.run_app(create_app(), host=args.host, port=port)
