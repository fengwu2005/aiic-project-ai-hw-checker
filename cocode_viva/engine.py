from __future__ import annotations

import json
import uuid
from pathlib import Path

from cocode_viva.config import SESSION_DIR, UPLOAD_DIR
from cocode_viva.llm_client import LLMClient
from cocode_viva.skills.archive_skill import safe_extract_zip
from cocode_viva.skills.code_analysis_skill import analyze_code
from cocode_viva.skills.file_reader_skill import read_expected_materials
from cocode_viva.skills.interaction_skill import analyze_interaction
from cocode_viva.skills.question_skill import generate_questions
from cocode_viva.skills.scoring_skill import build_report


def _session_path(session_id: str) -> Path:
    return SESSION_DIR / f"{session_id}.json"


def save_session(session: dict) -> None:
    _session_path(session["id"]).write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(session_id: str) -> dict:
    return json.loads(_session_path(session_id).read_text(encoding="utf-8"))


async def analyze_submission(zip_path: Path) -> dict:
    session_id = uuid.uuid4().hex[:12]
    extract_dir = UPLOAD_DIR / session_id
    extracted = safe_extract_zip(zip_path, extract_dir)
    read_result = read_expected_materials(extract_dir)
    materials = read_result["materials"]

    code = analyze_code(materials["final_code"]["text"], materials["tests"]["text"])
    interaction = analyze_interaction(
        materials["initial_prompt"]["text"],
        materials["initial_response"]["text"],
        materials["full_conversation"]["text"],
        materials["student_report"]["text"],
    )

    analysis = {
        "id": session_id,
        "extracted_files": extracted,
        "materials": {
            key: {
                "expected": value["expected"],
                "found": value["found"],
                "chars": value["chars"],
                "preview": value["text"][:1200],
            }
            for key, value in materials.items()
        },
        "missing": read_result["missing"],
        "code": code,
        "interaction": interaction,
    }

    questions = generate_questions(analysis)
    llm_questions = await _maybe_generate_llm_questions(analysis)
    if llm_questions:
        questions = llm_questions

    session = {
        "id": session_id,
        "analysis": analysis,
        "questions": questions,
        "answers": {},
        "report": None,
    }
    save_session(session)
    return session


async def _maybe_generate_llm_questions(analysis: dict) -> list[dict] | None:
    client = LLMClient()
    if not client.enabled:
        return None

    system = "你是计算机专业课程助教，请基于提交材料分析生成可解释的现场答辩问题。只输出 JSON。"
    user = json.dumps({
        "task": "生成 7 个答辩问题，覆盖代码理解、AI 协作、测试验证、边界情况和原创性。输出格式：{\"questions\":[{\"id\":\"q1\",\"dimension\":\"...\",\"text\":\"...\",\"focus\":\"...\"}]}",
        "analysis": analysis,
    }, ensure_ascii=False)
    result = await client.chat_json(system, user)
    questions = (result or {}).get("questions")
    if isinstance(questions, list) and len(questions) >= 5:
        normalized = []
        for index, item in enumerate(questions[:7], start=1):
            normalized.append({
                "id": f"q{index}",
                "dimension": str(item.get("dimension", "综合能力")),
                "text": str(item.get("text", "")).strip(),
                "focus": str(item.get("focus", "考察学生对提交材料的真实理解。")),
            })
        if all(item["text"] for item in normalized):
            return normalized
    return None


async def finish_defense(session_id: str, answers: dict[str, str]) -> dict:
    session = load_session(session_id)
    session["answers"] = answers
    report = build_report(session["analysis"], session["questions"], answers)
    session["report"] = report
    save_session(session)
    return session
