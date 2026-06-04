from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


TIMEOUT_SECONDS = 6


def run_hidden_tests(extract_dir: Path) -> dict:
    """Run deterministic instructor checks against final/taskflow.py in a subprocess."""
    source_path = _find_final_code(extract_dir)
    if not source_path.exists():
        return {
            "enabled": True,
            "passed": 0,
            "total": 1,
            "pass_rate": 0,
            "status": "failed",
            "cases": [{"name": "final/taskflow.py exists", "ok": False, "detail": "file not found"}],
            "error": "final/taskflow.py not found",
        }

    with tempfile.TemporaryDirectory(prefix="taskflow_hidden_") as temp_dir:
        runner = Path(temp_dir) / "hidden_runner.py"
        runner.write_text(_runner_script(source_path), encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, str(runner)],
                cwd=temp_dir,
                text=True,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "enabled": True,
                "passed": 0,
                "total": 1,
                "pass_rate": 0,
                "status": "timeout",
                "cases": [{"name": "hidden test timeout", "ok": False, "detail": f">{TIMEOUT_SECONDS}s"}],
                "error": "student code timed out during hidden tests",
            }

    output = completed.stdout.strip().splitlines()
    marker_lines = [line for line in output if line.startswith("__HIDDEN_TEST_RESULT__")]
    if not marker_lines:
        return {
            "enabled": True,
            "passed": 0,
            "total": 1,
            "pass_rate": 0,
            "status": "failed",
            "cases": [{"name": "hidden runner output", "ok": False, "detail": completed.stderr[-800:] or completed.stdout[-800:]}],
            "error": "hidden runner did not return structured result",
        }

    try:
        result = json.loads(marker_lines[-1].replace("__HIDDEN_TEST_RESULT__", "", 1))
    except json.JSONDecodeError as exc:
        return {
            "enabled": True,
            "passed": 0,
            "total": 1,
            "pass_rate": 0,
            "status": "failed",
            "cases": [{"name": "hidden runner json", "ok": False, "detail": str(exc)}],
            "error": "hidden runner returned invalid JSON",
        }

    result["enabled"] = True
    result["returncode"] = completed.returncode
    if completed.stderr:
        result["stderr_tail"] = completed.stderr[-1200:]
    return result


def _runner_script(source_path: Path) -> str:
    source = json.dumps(str(source_path))
    return textwrap.dedent(f"""
        import importlib.util
        import json
        from pathlib import Path

        RESULT = {{"cases": []}}

        def record(name, ok, detail=""):
            RESULT["cases"].append({{"name": name, "ok": bool(ok), "detail": str(detail)[:500]}})

        def require(condition, message="assertion failed"):
            if not condition:
                raise AssertionError(message)

        def expect_raises(func, *args, **kwargs):
            try:
                func(*args, **kwargs)
            except Exception:
                return True
            raise AssertionError("expected an exception")

        try:
            spec = importlib.util.spec_from_file_location("student_taskflow", {source})
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            record("import final/taskflow.py", True)
        except Exception as exc:
            record("import final/taskflow.py", False, repr(exc))
            module = None

        required_functions = [
            "add_task", "list_tasks", "update_status", "complete_task", "delete_task",
            "batch_update_status", "archive_tasks", "export_tasks", "import_tasks", "task_statistics",
        ]

        if module is not None:
            try:
                missing = [name for name in required_functions if not callable(getattr(module, name, None))]
                require(not missing, "missing functions: " + ", ".join(missing))
                record("required function API", True)
            except Exception as exc:
                record("required function API", False, repr(exc))

            data_path = Path("tasks.json")
            export_path = Path("export.json")
            import_path = Path("import.json")

            try:
                first = module.add_task(
                    "Finish AI report",
                    description="write the reflection",
                    priority="high",
                    deadline="2026-06-10",
                    tags=["course", "ai"],
                    path=data_path,
                )
                second = module.add_task(
                    "Read paper",
                    description="rag retrieval notes",
                    priority="low",
                    deadline="2026-06-12",
                    tags="reading,ai",
                    path=data_path,
                )
                require(first["id"] != second["id"], "ids must be unique")
                require(first["status"] == "todo", "new task should be todo")
                require("created_at" in first and "updated_at" in first, "timestamps required")
                record("add_task and persistence", True)
            except Exception as exc:
                record("add_task and persistence", False, repr(exc))

            try:
                expect_raises(module.add_task, "Bad priority", priority="urgent", deadline="2026-06-11", path=data_path)
                expect_raises(module.add_task, "Bad date", priority="high", deadline="2026-02-31", path=data_path)
                record("input validation", True)
            except Exception as exc:
                record("input validation", False, repr(exc))

            try:
                updated = module.update_status(1, "doing", path=data_path)
                require(updated["status"] == "doing", "status should become doing")
                done = module.complete_task(1, path=data_path)
                require(done["status"] == "done", "complete_task should mark done")
                expect_raises(module.update_status, 999, "done", path=data_path)
                record("status update and missing id errors", True)
            except Exception as exc:
                record("status update and missing id errors", False, repr(exc))

            try:
                filtered = module.list_tasks(priority="low", tag="reading", keyword="paper", sort_by="deadline", path=data_path)
                require(len(filtered) == 1 and filtered[0]["title"] == "Read paper", "filter/search should find Read paper")
                deadline_filtered = module.list_tasks(deadline_from="2026-06-11", deadline_to="2026-06-13", path=data_path)
                require(len(deadline_filtered) == 1, "deadline range should filter correctly")
                record("filter search and sort", True)
            except Exception as exc:
                record("filter search and sort", False, repr(exc))

            try:
                module.batch_update_status([1, 2], "done", path=data_path)
                listed = module.list_tasks(status="done", path=data_path)
                require(len(listed) == 2, "batch_update_status should update both tasks")
                module.archive_tasks([2], path=data_path)
                visible = module.list_tasks(path=data_path)
                require(all(task["status"] != "archived" for task in visible), "archived tasks hidden by default")
                archived = module.list_tasks(status="archived", include_archived=True, path=data_path)
                require(len(archived) == 1, "archived task should be visible with include_archived")
                record("batch and archive operations", True)
            except Exception as exc:
                record("batch and archive operations", False, repr(exc))

            try:
                count = module.export_tasks(export_path, path=data_path)
                require(count >= 2 and export_path.exists(), "export should write JSON file")
                import_path.write_text(json.dumps([{{
                    "id": 1,
                    "title": "Imported task",
                    "description": "duplicate id should be handled",
                    "priority": "medium",
                    "deadline": "2026-06-20",
                    "status": "todo",
                    "tags": ["imported"],
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "updated_at": "2026-06-01T00:00:00+00:00",
                }}]), encoding="utf-8")
                imported = module.import_tasks(import_path, path=data_path)
                require(imported == 1, "import_tasks should report one imported task")
                tasks = module.list_tasks(include_archived=True, path=data_path)
                require(len({{int(task["id"]) for task in tasks}}) == len(tasks), "duplicate ids must be resolved")
                record("import export and duplicate id handling", True)
            except Exception as exc:
                record("import export and duplicate id handling", False, repr(exc))

            try:
                stats = module.task_statistics(today="2026-06-15", path=data_path)
                require(stats["total"] >= 3, "stats total should include imported task")
                require("by_status" in stats and "by_tag" in stats, "stats should include status and tag summaries")
                require(stats.get("high_priority_open", 0) >= 0 and stats.get("overdue", 0) >= 0, "stats counters required")
                record("task_statistics", True)
            except Exception as exc:
                record("task_statistics", False, repr(exc))

            try:
                module.delete_task(1, path=data_path)
                expect_raises(module.delete_task, 404, path=data_path)
                record("delete_task and missing id errors", True)
            except Exception as exc:
                record("delete_task and missing id errors", False, repr(exc))

        passed = sum(1 for case in RESULT["cases"] if case["ok"])
        total = len(RESULT["cases"]) or 1
        RESULT.update({{
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / total, 3),
            "status": "passed" if passed == total else "partial" if passed else "failed",
        }})
        print("__HIDDEN_TEST_RESULT__" + json.dumps(RESULT, ensure_ascii=False))
    """)


def _find_final_code(extract_dir: Path) -> Path:
    direct = (extract_dir / "final" / "taskflow.py").resolve()
    if direct.exists():
        return direct
    matches = sorted(extract_dir.glob("*/final/taskflow.py"))
    if matches:
        return matches[0].resolve()
    return direct
