import argparse
import json
from pathlib import Path


DATA_FILE = Path("tasks.json")


def load_tasks():
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception:
        return []


def save_tasks(tasks):
    DATA_FILE.write_text(json.dumps(tasks, indent=2))


def add_task(title, priority, deadline, tags=""):
    tasks = load_tasks()
    task = {
        "id": len(tasks) + 1,
        "title": title,
        "priority": priority,
        "deadline": deadline,
        "tags": tags,
        "status": "pending",
    }
    tasks.append(task)
    save_tasks(tasks)
    return task


def list_tasks(status=None, priority=None, tag=None):
    tasks = load_tasks()
    if status:
        tasks = [task for task in tasks if task["status"] == status]
    if priority:
        tasks = [task for task in tasks if task["priority"] == priority]
    if tag:
        tasks = [task for task in tasks if tag in task.get("tags", "")]
    return tasks


def complete_task(task_id):
    tasks = load_tasks()
    for task in tasks:
        if task["id"] == int(task_id):
            task["status"] = "completed"
            save_tasks(tasks)
            return task
    return None


def delete_task(task_id):
    tasks = load_tasks()
    tasks = [task for task in tasks if task["id"] != int(task_id)]
    save_tasks(tasks)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    add = subparsers.add_parser("add")
    add.add_argument("title")
    add.add_argument("--priority", default="medium")
    add.add_argument("--deadline")
    add.add_argument("--tags", default="")
    args = parser.parse_args()
    if args.command == "add":
        print(add_task(args.title, args.priority, args.deadline, args.tags))


if __name__ == "__main__":
    main()

