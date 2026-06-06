from __future__ import annotations

import shutil
import uuid
import argparse
import socket

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

from cocode_viva.config import PROJECT_ROOT, STATIC_DIR, TEMPLATE_DIR, UPLOAD_DIR
from cocode_viva.debug_log import format_events_for_view, list_snapshots, read_events
from cocode_viva.engine import analyze_submission, finish_defense, load_session, save_session, submit_single_answer
from cocode_viva.portal import (
    attach_submission_context,
    authenticate,
    create_login_token,
    delete_login_token,
    get_assignment,
    get_class,
    list_assignments_for_user,
    list_submissions,
    mark_submission_report_ready,
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


def render(template: str, **context) -> web.Response:
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


async def index(request: web.Request) -> web.Response:
    user = current_user(request)
    raise web.HTTPFound(redirect_for_user(user))


async def login_page(request: web.Request) -> web.Response:
    return render("portal.html", page="login", user=current_user(request), error=None)


async def login_submit(request: web.Request) -> web.Response:
    data = await request.post()
    user, error = authenticate(str(data.get("username", "")), str(data.get("password", "")))
    if not user:
        return render("portal.html", page="login", user=None, error=error)
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
        return render("portal.html", page="login", user=None, error=error)
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


async def defense(request: web.Request) -> web.Response:
    raise web.HTTPFound(redirect_for_user(current_user(request)))


async def defense_session(request: web.Request) -> web.Response:
    user = require_role(request)
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="答辩会话不存在")
    if user["role"] == "student":
        require_session_for_student(session, user)
        return render("student_defense.html", page="student", user=user, session=session, error=None)
    return render("defense.html", page="teacher", user=user, session=session, error=None)


async def upload_submission(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    assignment_id = request.match_info.get("assignment_id", "image-lab")
    assignment_obj = get_assignment(assignment_id)
    if not assignment_obj or assignment_obj.get("class_id") != user.get("class_id"):
        raise web.HTTPNotFound(text="作业不存在或不属于你的班级。")

    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "submission":
        return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error="请上传 zip 格式作业包。")

    filename = field.filename or "submission.zip"
    if not filename.lower().endswith(".zip"):
        return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error="文件格式必须是 .zip。")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.zip"
    try:
        with temp_path.open("wb") as output:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                output.write(chunk)
        session = await analyze_submission(temp_path)
        session = attach_submission_context(session, user, assignment_id)
        save_session(session)
        return render("student_defense.html", page="student", user=user, session=session, error=None)
    except ArchiveError as exc:
        return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error=str(exc))
    except Exception as exc:
        return render("student_dashboard.html", page="student", user=user, klass=get_class(user.get("class_id", "")), assignments=list_assignments_for_user(user), submissions=list_submissions(user), error=f"分析失败：{exc}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


async def submit_defense(request: web.Request) -> web.Response:
    require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    data = await request.post()
    answers = {key: str(value) for key, value in data.items() if key.startswith("q")}
    await finish_defense(session_id, answers)
    raise web.HTTPFound(f"/report/{session_id}")


async def submit_answer(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    session = load_session(session_id)
    require_session_for_student(session, user)
    data = await request.post()
    answer = str(data.get("answer", ""))
    session = await submit_single_answer(session_id, answer)
    if session.get("report"):
        session = mark_submission_report_ready(session)
        save_session(session)
        raise web.HTTPFound(f"/student/submissions/{session_id}/done")
    return render("student_defense.html", page="student", user=user, session=session, error=None)


async def student_done(request: web.Request) -> web.Response:
    user = require_role(request, "student")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="提交记录不存在")
    require_session_for_student(session, user)
    return render("student_done.html", page="student", user=user, session=session)


async def report(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="报告不存在")
    return render("report.html", page="teacher", user=user, session=session, can_review=True)


async def teacher_dashboard(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    return render(
        "teacher_dashboard.html",
        page="teacher",
        user=user,
        assignments=list_assignments_for_user(user),
        submissions=list_submissions(),
    )


async def review_report(request: web.Request) -> web.Response:
    user = require_role(request, "teacher")
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="报告不存在")
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
    return render(
        "debug.html",
        page="debug",
        user=user,
        session=session,
        events=format_events_for_view(read_events(session_id)),
        snapshots=list_snapshots(session_id),
    )


async def download_sample(request: web.Request) -> web.FileResponse:
    sample = PROJECT_ROOT / "examples" / "image_lab_sample_submission.zip"
    return web.FileResponse(sample)


def create_app() -> web.Application:
    app = web.Application(client_max_size=10 * 1024**2)
    app.router.add_get("/", index)
    app.router.add_get("/login", login_page)
    app.router.add_post("/login", login_submit)
    app.router.add_post("/register", register_submit)
    app.router.add_post("/logout", logout)
    app.router.add_get("/assignment", assignment)
    app.router.add_get("/student", student_dashboard)
    app.router.add_get("/student/assignments/{assignment_id}", student_assignment)
    app.router.add_post("/student/assignments/{assignment_id}/upload", upload_submission)
    app.router.add_get("/student/defense/{session_id}", defense_session)
    app.router.add_post("/student/defense/{session_id}/answer", submit_answer)
    app.router.add_get("/student/submissions/{session_id}/done", student_done)
    app.router.add_get("/teacher", teacher_dashboard)
    app.router.add_get("/teacher/report/{session_id}", report)
    app.router.add_post("/teacher/report/{session_id}/review", review_report)
    app.router.add_get("/teacher/debug/{session_id}", debug_session)
    app.router.add_get("/defense", defense)
    app.router.add_get("/defense/{session_id}", defense_session)
    app.router.add_post("/defense/upload", upload_submission)
    app.router.add_post("/defense/{session_id}/answer", submit_answer)
    app.router.add_post("/defense/{session_id}/submit", submit_defense)
    app.router.add_get("/report/{session_id}", report)
    app.router.add_get("/debug/{session_id}", debug_session)
    app.router.add_get("/examples/image_lab_sample_submission.zip", download_sample)
    app.router.add_get("/examples/taskflow_sample_submission.zip", download_sample)
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
