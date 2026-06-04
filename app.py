from __future__ import annotations

import shutil
import uuid
import argparse
import socket

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

from cocode_viva.config import PROJECT_ROOT, STATIC_DIR, TEMPLATE_DIR, UPLOAD_DIR
from cocode_viva.debug_log import format_events_for_view, list_snapshots, read_events
from cocode_viva.engine import analyze_submission, finish_defense, load_session, submit_single_answer
from cocode_viva.skills.archive_skill import ArchiveError


env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render(template: str, **context) -> web.Response:
    page = env.get_template(template).render(**context)
    return web.Response(text=page, content_type="text/html")


async def assignment(request: web.Request) -> web.Response:
    return render("assignment.html", page="assignment")


async def defense(request: web.Request) -> web.Response:
    return render("defense.html", page="defense", session=None, error=None)


async def upload_submission(request: web.Request) -> web.Response:
    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "submission":
        return render("defense.html", page="defense", session=None, error="请上传 zip 格式作业包。")

    filename = field.filename or "submission.zip"
    if not filename.lower().endswith(".zip"):
        return render("defense.html", page="defense", session=None, error="文件格式必须是 .zip。")

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
        return render("defense.html", page="defense", session=session, error=None)
    except ArchiveError as exc:
        return render("defense.html", page="defense", session=None, error=str(exc))
    except Exception as exc:
        return render("defense.html", page="defense", session=None, error=f"分析失败：{exc}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


async def submit_defense(request: web.Request) -> web.Response:
    session_id = request.match_info["session_id"]
    data = await request.post()
    answers = {key: str(value) for key, value in data.items() if key.startswith("q")}
    await finish_defense(session_id, answers)
    raise web.HTTPFound(f"/report/{session_id}")


async def submit_answer(request: web.Request) -> web.Response:
    session_id = request.match_info["session_id"]
    data = await request.post()
    answer = str(data.get("answer", ""))
    session = await submit_single_answer(session_id, answer)
    if session.get("report"):
        raise web.HTTPFound(f"/report/{session_id}")
    return render("defense.html", page="defense", session=session, error=None)


async def report(request: web.Request) -> web.Response:
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="报告不存在")
    return render("report.html", page="report", session=session)


async def debug_session(request: web.Request) -> web.Response:
    session_id = request.match_info["session_id"]
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise web.HTTPNotFound(text="后台证据不存在")
    return render(
        "debug.html",
        page="debug",
        session=session,
        events=format_events_for_view(read_events(session_id)),
        snapshots=list_snapshots(session_id),
    )


async def download_sample(request: web.Request) -> web.FileResponse:
    sample = PROJECT_ROOT / "examples" / "taskflow_sample_submission.zip"
    return web.FileResponse(sample)


def create_app() -> web.Application:
    app = web.Application(client_max_size=10 * 1024**2)
    app.router.add_get("/", assignment)
    app.router.add_get("/assignment", assignment)
    app.router.add_get("/defense", defense)
    app.router.add_post("/defense/upload", upload_submission)
    app.router.add_post("/defense/{session_id}/answer", submit_answer)
    app.router.add_post("/defense/{session_id}/submit", submit_defense)
    app.router.add_get("/report/{session_id}", report)
    app.router.add_get("/debug/{session_id}", debug_session)
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
