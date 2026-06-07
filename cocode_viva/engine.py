from __future__ import annotations

import json
import uuid
from pathlib import Path

from cocode_viva.agent import DefenseAgent
from cocode_viva.config import SESSION_DIR, UPLOAD_DIR
from cocode_viva.debug_log import log_event, write_snapshot
from cocode_viva.skills.archive_skill import safe_extract_zip
from cocode_viva.skills.code_analysis_skill import analyze_code
from cocode_viva.skills.file_reader_skill import read_expected_materials
from cocode_viva.skills.hidden_test_skill import run_hidden_tests
from cocode_viva.skills.interaction_skill import analyze_report
from cocode_viva.skills.question_skill import generate_questions
from cocode_viva.skills.scoring_skill import build_report


MAX_DEFENSE_ROUNDS = 4


def _session_path(session_id: str) -> Path:
    return SESSION_DIR / f"{session_id}.json"


def save_session(session: dict) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    _session_path(session["id"]).write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(session_id: str) -> dict:
    return json.loads(_session_path(session_id).read_text(encoding="utf-8"))


async def analyze_submission(zip_path: Path) -> dict:
    session_id = uuid.uuid4().hex[:12]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    extract_dir = UPLOAD_DIR / session_id
    extracted = safe_extract_zip(zip_path, extract_dir)
    read_result = read_expected_materials(extract_dir)
    materials = read_result["materials"]
    material_texts = {
        key: value["text"]
        for key, value in materials.items()
    }

    code = analyze_code(materials["final_code"]["text"])
    execution = run_hidden_tests(extract_dir)
    interaction = analyze_report(
        materials["readme"]["text"],
        materials["final_code"]["text"],
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
        "execution": execution,
        "interaction": interaction,
    }

    question_pool = generate_questions(analysis)
    questions = question_pool[:1]
    agent = DefenseAgent()
    agent_tool_results = []
    if agent.enabled:
        llm_question, agent_tool_results = await agent.generate_first_question(analysis, material_texts)
        if llm_question:
            llm_question["source"] = "api_agent"
            questions = [llm_question]

    session = {
        "id": session_id,
        "analysis": analysis,
        "material_texts": material_texts,
        "questions": questions,
        "question_pool": question_pool,
        "agent_tool_results": agent_tool_results,
        "current_index": 0,
        "answers": {},
        "report": None,
        "agent_enabled": agent.enabled,
    }
    save_session(session)
    log_event(session_id, "submission_analyzed", {
        "extracted_files": extracted,
        "missing": analysis["missing"],
        "line_count": code["line_count"],
        "hidden_tests": f"{execution.get('passed', 0)}/{execution.get('total', 0)}",
        "report_chars": interaction["student_report_chars"],
        "agent_enabled": agent.enabled,
        "first_question_source": questions[0].get("source") if questions else "",
    })
    write_snapshot(session_id, "analysis", analysis)
    write_snapshot(session_id, "active_questions", {"questions": questions})
    write_snapshot(session_id, "local_fallback_question_pool", {
        "note": "仅用于 API 不可用或结构化返回失败时兜底，不会一次性展示给学生。",
        "count": len(question_pool),
    })
    if agent_tool_results:
        write_snapshot(session_id, "question_agent_tool_results", {"tool_results": agent_tool_results})
    return session


def _answer_is_weak(answer: str) -> bool:
    stripped = answer.strip()
    if len(stripped) < 40:
        return True
    useful_terms = ["函数", "验收", "代码", "原因", "验证", "修改", "报告", "图像", "像素", "滤波", "卷积", "异常"]
    return not any(term.lower() in stripped.lower() for term in useful_terms)


def _answer_is_no_knowledge(answer: str) -> bool:
    stripped = answer.strip().lower()
    if not stripped:
        return True
    no_knowledge_terms = [
        "我不会",
        "不知道",
        "不清楚",
        "不懂",
        "没看懂",
        "答不上来",
        "不会回答",
        "不太会",
        "不太清楚",
        "i don't know",
        "idk",
    ]
    if stripped in {"不会", "不知道", "不清楚", "不懂", "不会回答", "答不上来", "idk"}:
        return True
    return any(term in stripped for term in no_knowledge_terms)


def _build_followup_question(previous_question: dict, answer: str, question_id: str) -> dict:
    return {
        "id": question_id,
        "dimension": "深度追问",
        "is_followup": True,
        "source": "local_fallback",
        "text": (
            "请具体到一个函数：它处理了什么边界？你用什么输入验证？"
        ),
        "focus": "追问回答是否能落到函数实现、边界输入和验证证据。",
        "evidence": previous_question.get("evidence", ""),
    }


def _build_no_knowledge_followup(previous_question: dict, question_id: str) -> dict:
    return {
        "id": question_id,
        "dimension": "换向追问",
        "is_followup": True,
        "source": "local_fallback",
        "text": (
            "换个基础问题：说出一个固定函数，它做什么，你改过哪里？"
        ),
        "focus": "给学生换维度说明的机会，考察是否能提供任何可验证的个人理解证据。",
        "evidence": previous_question.get("evidence", ""),
    }


async def _build_next_question(session: dict, previous_question: dict, answer: str) -> tuple[dict | None, list[dict]]:
    questions = session.get("questions", [])
    answers = session.get("answers", {})
    next_id = f"q{len(questions) + 1}"
    agent = DefenseAgent()
    if agent.enabled:
        decision, tool_results = await agent.decide_next_step(
            session["analysis"],
            session.get("material_texts", {}),
            questions,
            answers,
            previous_question,
            answer,
            next_id,
            MAX_DEFENSE_ROUNDS,
        )
        if decision:
            session["last_agent_decision"] = {
                "action": decision.get("action"),
                "reason": decision.get("reason", ""),
                "after_question_id": previous_question.get("id"),
                "source": "api_agent",
            }
            if decision.get("action") == "end_defense":
                session["early_finish_reason"] = decision.get("reason") or "系统助教判断继续追问已无法有效验证学生理解，答辩提前结束。"
                return None, tool_results
            if decision.get("question"):
                decision["question"]["source"] = "api_agent"
                return decision["question"], tool_results
        session["last_agent_decision"] = {
            "action": "fallback",
            "reason": "API Agent 未返回可用结构化决策，系统使用本地兜底问题。",
            "after_question_id": previous_question.get("id"),
            "source": "local_fallback",
        }

    if _answer_is_no_knowledge(answer):
        if previous_question.get("is_followup") and len(questions) >= 3:
            session["early_finish_reason"] = "学生多轮仍未提供可验证说明，答辩提前结束。"
            return None, []
        next_question = _build_no_knowledge_followup(previous_question, next_id)
        return next_question, []

    if _answer_is_weak(answer) and not previous_question.get("is_followup"):
        next_question = _build_followup_question(previous_question, answer, next_id)
        return next_question, []

    asked_text = {question.get("text") for question in questions}

    for candidate in session.get("question_pool", []):
        if candidate.get("text") not in asked_text:
            candidate = dict(candidate)
            candidate["id"] = next_id
            candidate["source"] = "local_fallback"
            return candidate, []
    return None, []


async def submit_single_answer(session_id: str, answer: str) -> dict:
    session = load_session(session_id)
    if session.get("report"):
        return session

    current_index = int(session.get("current_index", 0))
    questions = session.get("questions", [])
    if current_index >= len(questions):
        return await finish_defense(session_id, session.get("answers", {}))

    question = questions[current_index]
    session.setdefault("answers", {})[question["id"]] = answer.strip()
    log_event(session_id, "answer_submitted", {
        "question_id": question["id"],
        "question_dimension": question.get("dimension"),
        "answer_chars": len(answer.strip()),
        "answer_preview": answer.strip()[:300],
        "current_index": current_index,
        "no_knowledge": _answer_is_no_knowledge(answer),
    })

    if len(questions) < MAX_DEFENSE_ROUNDS:
        next_question, next_tool_results = await _build_next_question(session, question, answer)
        if session.get("early_finish_reason"):
            session["questions"] = questions
            session["current_index"] = current_index + 1
            save_session(session)
            log_event(session_id, "defense_ended_early", {
                "reason": session["early_finish_reason"],
                "question_id": question["id"],
                "agent_decision": session.get("last_agent_decision"),
                "agent_tools": len(next_tool_results),
            })
            if next_tool_results:
                session.setdefault("next_question_tool_results", []).append({
                    "after_question_id": question["id"],
                    "tool_results": next_tool_results,
                })
            return await finish_defense(session_id, session["answers"])
        if next_question:
            questions.append(next_question)
            log_event(session_id, "next_question_generated", {
                "after_question_id": question["id"],
                "next_question_id": next_question["id"],
                "dimension": next_question.get("dimension"),
                "source": next_question.get("source"),
                "weak_answer": _answer_is_weak(answer),
                "agent_tools": len(next_tool_results),
                "agent_decision": session.get("last_agent_decision"),
            })
            if next_tool_results:
                session.setdefault("next_question_tool_results", []).append({
                    "after_question_id": question["id"],
                    "tool_results": next_tool_results,
                })

    session["questions"] = questions
    session["current_index"] = current_index + 1
    save_session(session)

    if session["current_index"] >= len(session["questions"]):
        return await finish_defense(session_id, session["answers"])
    return session


async def finish_defense(session_id: str, answers: dict[str, str]) -> dict:
    session = load_session(session_id)
    session["answers"] = answers
    report = build_report(session["analysis"], session["questions"], answers)
    if session.get("early_finish_reason"):
        report["early_finish_reason"] = session["early_finish_reason"]
        if session["early_finish_reason"] not in report.setdefault("risks", []):
            report["risks"].insert(0, session["early_finish_reason"])
    log_event(session_id, "rule_report_generated", {
        "total": report["total"],
        "raw_total": report.get("raw_total"),
        "defense_score": report["defense_score"],
        "defense_validity": report.get("defense_validity"),
        "contribution": report["contribution"],
    })
    agent = DefenseAgent()
    if agent.enabled:
        overlay, report_tool_results = await agent.generate_report(
            session["analysis"],
            session.get("material_texts", {}),
            session["questions"],
            answers,
            report,
        )
        session["report_agent_tool_results"] = report_tool_results
        if report_tool_results:
            write_snapshot(session_id, "report_agent_tool_results", {"tool_results": report_tool_results})
        if overlay:
            report["agent_overlay"] = overlay
            write_snapshot(session_id, "agent_report_overlay", overlay)
            if overlay.get("contribution") is not None and report.get("defense_validity") not in {"invalid", "weak"}:
                report["contribution"] = overlay["contribution"]
            if overlay.get("contribution_level") and report.get("defense_validity") not in {"invalid", "weak"}:
                report["contribution_level"] = overlay["contribution_level"]
            if overlay.get("strengths") and report.get("defense_validity") not in {"invalid", "weak"}:
                report["strengths"] = overlay["strengths"]
            if overlay.get("risks"):
                guard_risks = []
                if report.get("cap_note"):
                    guard_risks.append(report["cap_note"])
                report["risks"] = guard_risks + overlay["risks"]
            if overlay.get("basis"):
                report["basis"] = overlay["basis"]
    session["report"] = report
    save_session(session)
    write_snapshot(session_id, "final_questions", {
        "questions": session.get("questions", []),
        "answers": session.get("answers", {}),
    })
    write_snapshot(session_id, "final_report", report)
    log_event(session_id, "final_report_saved", {
        "total": report["total"],
        "defense_validity": report.get("defense_validity"),
        "contribution": report["contribution"],
    })
    return session
