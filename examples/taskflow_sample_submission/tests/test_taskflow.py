import json

import pytest

from final.taskflow import (
    add_task,
    complete_task,
    delete_task,
    list_tasks,
    load_tasks,
    validate_deadline,
    validate_priority,
)


def test_add_task_creates_expected_fields(tmp_path):
    path = tmp_path / "tasks.json"
    task = add_task("write report", "high", "2026-06-10", path)
    assert task["id"] == 1
    assert task["status"] == "pending"


def test_add_task_persists_json(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("demo", "medium", "2026-06-10", path)
    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "demo"


def test_complete_task_changes_status(tmp_path):
    path = tmp_path / "tasks.json"
    task = add_task("demo", "low", "2026-06-10", path)
    completed = complete_task(task["id"], path)
    assert completed["status"] == "completed"


def test_delete_task_removes_item(tmp_path):
    path = tmp_path / "tasks.json"
    task = add_task("demo", "low", "2026-06-10", path)
    delete_task(task["id"], path)
    assert load_tasks(path) == []


def test_filter_by_priority(tmp_path):
    path = tmp_path / "tasks.json"
    add_task("a", "high", "2026-06-10", path)
    add_task("b", "low", "2026-06-11", path)
    assert len(list_tasks(priority="high", path=path)) == 1


def test_filter_by_status(tmp_path):
    path = tmp_path / "tasks.json"
    task = add_task("a", "high", "2026-06-10", path)
    complete_task(task["id"], path)
    assert len(list_tasks(status="completed", path=path)) == 1


def test_invalid_priority_raises():
    with pytest.raises(ValueError):
        validate_priority("urgent")


def test_invalid_deadline_raises():
    with pytest.raises(ValueError):
        validate_deadline("2026-02-31")

