import argparse
import json
from datetime import datetime
from pathlib import Path


DATA_FILE = Path("tasks.json")
VALID_PRIORITIES = {"high", "medium", "low"}
VALID_STATUS = {"pending", "completed"}


def load_tasks(path=DATA_FILE):
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_tasks(tasks, path=DATA_FILE):
    path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_priority(priority):
    if priority not in VALID_PRIORITIES:
        raise ValueError("priority must be high, medium, or low")
    return priority


def validate_deadline(deadline):
    try:
        datetime.strptime(deadline, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("deadline must use YYYY-MM-DD") from exc
    return deadline


def next_id(tasks):
    if not tasks:
        return 1
    return max(int(task["id"]) for task in tasks) + 1


def add_task(title, priority, deadline, path=DATA_FILE):
    tasks = load_tasks(path)
    task = {
        "id": next_id(tasks),
        "title": title,
        "priority": validate_priority(priority),
        "deadline": validate_deadline(deadline),
        "status": "pending",
    }
    tasks.append(task)
    save_tasks(tasks, path)
    return task


def complete_task(task_id, path=DATA_FILE):
    tasks = load_tasks(path)
    for task in tasks:
        if int(task["id"]) == int(task_id):
            task["status"] = "completed"
            save_tasks(tasks, path)
            return task
    raise ValueError("task not found")


def delete_task(task_id, path=DATA_FILE):
    tasks = load_tasks(path)
    filtered = [task for task in tasks if int(task["id"]) != int(task_id)]
    if len(filtered) == len(tasks):
        raise ValueError("task not found")
    save_tasks(filtered, path)
    return True


def list_tasks(status=None, priority=None, deadline=None, path=DATA_FILE):
    tasks = load_tasks(path)
    if status:
        if status not in VALID_STATUS:
            raise ValueError("status must be pending or completed")
        tasks = [task for task in tasks if task["status"] == status]
    if priority:
        validate_priority(priority)
        tasks = [task for task in tasks if task["priority"] == priority]
    if deadline:
        validate_deadline(deadline)
        tasks = [task for task in tasks if task["deadline"] == deadline]
    return tasks


def build_parser():
    parser = argparse.ArgumentParser(description="TaskFlow command line task manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("title")
    add_parser.add_argument("--priority", default="medium")
    add_parser.add_argument("--deadline", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--priority")
    list_parser.add_argument("--deadline")

    done_parser = subparsers.add_parser("done")
    done_parser.add_argument("task_id")

    delete_parser = subparsers.add_parser("delete")
    delete_parser.add_argument("task_id")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "add":
            task = add_task(args.title, args.priority, args.deadline)
            print(json.dumps(task, ensure_ascii=False))
        elif args.command == "list":
            print(json.dumps(list_tasks(args.status, args.priority, args.deadline), ensure_ascii=False))
        elif args.command == "done":
            print(json.dumps(complete_task(args.task_id), ensure_ascii=False))
        elif args.command == "delete":
            delete_task(args.task_id)
            print("deleted")
    except ValueError as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    main()

