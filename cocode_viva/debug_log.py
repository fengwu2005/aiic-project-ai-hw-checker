from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cocode_viva.config import DATA_DIR


DEBUG_LOG_DIR = DATA_DIR / "debug_logs"
DEBUG_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> str:
    return str(value)


def session_log_dir(session_id: str) -> Path:
    target = DEBUG_LOG_DIR / session_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def log_event(session_id: str, event: str, payload: dict[str, Any] | None = None) -> None:
    target = session_log_dir(session_id) / "events.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "payload": payload or {},
    }
    with target.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False, default=_json_default) + "\n")


def write_snapshot(session_id: str, name: str, payload: dict[str, Any]) -> None:
    safe_name = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in name)
    target = session_log_dir(session_id) / f"{safe_name}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def read_events(session_id: str) -> list[dict[str, Any]]:
    target = session_log_dir(session_id) / "events.jsonl"
    if not target.exists():
        return []
    events = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def list_snapshots(session_id: str) -> list[str]:
    root = session_log_dir(session_id)
    return sorted(path.name for path in root.glob("*.json"))


def format_events_for_view(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    formatted = []
    for event in events:
        payload = event.get("payload", {})
        formatted.append({
            "ts": str(event.get("ts", "")),
            "event": str(event.get("event", "")),
            "summary": _event_summary(str(event.get("event", "")), payload),
            "payload_json": json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        })
    return formatted


def _event_summary(event: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return str(payload)[:180]
    if event == "submission_analyzed":
        return (
            f"文件 {len(payload.get('extracted_files', []))} 个，"
            f"代码 {payload.get('line_count', 0)} 行，"
            f"隐藏验收 {payload.get('hidden_tests', '-')}, "
            f"AI 交互 {payload.get('interaction_rounds', 0)} 轮。"
        )
    if event == "answer_submitted":
        return (
            f"{payload.get('question_id', '')}，"
            f"{payload.get('answer_chars', 0)} 字，"
            f"预览：{payload.get('answer_preview', '')}"
        )
    if event == "followup_inserted":
        return f"因回答证据不足，在 {payload.get('after_question_id', '')} 后插入追问。"
    if event in {"rule_report_generated", "final_report_saved"}:
        return (
            f"总分 {payload.get('total', '-')}, "
            f"答辩 {payload.get('defense_validity', '-')}, "
            f"贡献 {payload.get('contribution', '-')}%。"
        )
    return ", ".join(f"{key}={value}" for key, value in list(payload.items())[:4])[:220]
