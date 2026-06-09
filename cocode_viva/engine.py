from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path

from cocode_viva.agent import DefenseAgent
from cocode_viva.config import SESSION_DIR, UPLOAD_DIR, privacy_mode
from cocode_viva.debug_log import log_event, write_snapshot
from cocode_viva.privacy import filtered_material_texts, privacy_summary
from cocode_viva.skills.archive_skill import safe_extract_zip
from cocode_viva.skills.code_analysis_skill import analyze_code
from cocode_viva.skills.file_reader_skill import read_expected_materials
from cocode_viva.skills.hidden_test_skill import run_hidden_tests
from cocode_viva.skills.interaction_skill import analyze_report
from cocode_viva.skills.question_skill import generate_questions
from cocode_viva.skills.scoring_skill import apply_answer_evaluation, build_report
from cocode_viva.skills.similarity_skill import analyze_similarity


MAX_DEFENSE_ROUNDS = 6


def _session_path(session_id: str) -> Path:
    return SESSION_DIR / f"{session_id}.json"


def save_session(session: dict) -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    _session_path(session["id"]).write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(session_id: str) -> dict:
    return json.loads(_session_path(session_id).read_text(encoding="utf-8"))


def _agent_materials(session: dict) -> dict[str, str]:
    return filtered_material_texts(session.get("material_texts", {}), session.get("analysis", {}))


def dialogue_timeline(session: dict) -> list[dict]:
    stored_events: list[dict] = []
    if isinstance(session.get("dialogue"), list) and session["dialogue"]:
        stored_events = [
            _normalize_dialogue_event(item, index + 1)
            for index, item in enumerate(session["dialogue"])
            if isinstance(item, dict)
        ]

    events: list[dict] = []
    existing: set[tuple[str, str, str, str]] = set()
    order = 1
    clarifications_by_question: dict[str, list[dict]] = {}
    for clarification in session.get("clarifications", []):
        question_id = str(clarification.get("question_id", ""))
        clarifications_by_question.setdefault(question_id, []).append(clarification)
    for item in stored_events:
        if item["type"] == "clarification":
            clarifications_by_question.setdefault(item["question_id"], []).append({
                "question_id": item["question_id"],
                "original_question": item["question"],
                "student_message": item["student"],
                "assistant_response": item["assistant"],
            })

    for question in session.get("questions", []):
        question_id = str(question.get("id", ""))
        for clarification in clarifications_by_question.get(question_id, []):
            event = {
                "order": order,
                "type": "clarification",
                "question_id": question_id,
                "dimension": "题意澄清",
                "question": clarification.get("original_question") or question.get("original_text") or question.get("text", ""),
                "student": clarification.get("student_message", ""),
                "assistant": clarification.get("assistant_response", ""),
                "counts_for_score": False,
            }
            key = (event["type"], event["question_id"], event["student"], event["assistant"])
            if key not in existing:
                events.append(event)
                existing.add(key)
                order += 1
        answer = session.get("answers", {}).get(question_id)
        if not answer:
            answer = next(
                (item["student"] for item in stored_events if item["type"] == "answer" and item["question_id"] == question_id),
                "",
            )
        if answer:
            event = {
                "order": order,
                "type": "answer",
                "question_id": question_id,
                "dimension": question.get("dimension", "现场答辩"),
                "question": question.get("text", ""),
                "student": answer,
                "assistant": "",
                "counts_for_score": True,
            }
            key = (event["type"], event["question_id"], event["student"], event["assistant"])
            if key not in existing:
                events.append(event)
                existing.add(key)
                order += 1
    known_question_ids = {str(question.get("id", "")) for question in session.get("questions", [])}
    for item in stored_events:
        key = (item["type"], item["question_id"], item["student"], item["assistant"])
        if item["question_id"] not in known_question_ids and key not in existing:
            item["order"] = order
            events.append(item)
            existing.add(key)
            order += 1
    return sorted(events, key=lambda item: int(item.get("order", 0)))


def _normalize_dialogue_event(item: dict, fallback_order: int) -> dict:
    try:
        order = int(item.get("order", fallback_order))
    except (TypeError, ValueError):
        order = fallback_order
    return {
        "order": order,
        "type": str(item.get("type", "")),
        "question_id": str(item.get("question_id", "")),
        "dimension": str(item.get("dimension", "现场答辩") or "现场答辩"),
        "question": str(item.get("question", "")),
        "student": str(item.get("student", "")),
        "assistant": str(item.get("assistant", "")),
        "source": str(item.get("source", "")),
        "counts_for_score": bool(item.get("counts_for_score")),
    }


def _append_dialogue_event(session: dict, event: dict) -> None:
    if not isinstance(session.get("dialogue"), list):
        session["dialogue"] = []
    dialogue = session["dialogue"]
    event = {
        "order": len(dialogue) + 1,
        **event,
    }
    dialogue.append(event)


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def analyze_submission(zip_path: Path, use_agent: bool = True, session_id: str | None = None) -> dict:
    started = time.perf_counter()
    timings: dict[str, int] = {}
    session_id = session_id or uuid.uuid4().hex[:12]
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    extract_dir = UPLOAD_DIR / session_id
    shutil.rmtree(extract_dir, ignore_errors=True)
    step = time.perf_counter()
    extracted = safe_extract_zip(zip_path, extract_dir)
    timings["extract_zip_ms"] = _duration_ms(step)
    step = time.perf_counter()
    read_result = read_expected_materials(extract_dir)
    timings["read_materials_ms"] = _duration_ms(step)
    materials = read_result["materials"]
    material_texts = {
        key: value["text"]
        for key, value in materials.items()
    }

    step = time.perf_counter()
    code = analyze_code(materials["final_code"]["text"])
    timings["analyze_code_ms"] = _duration_ms(step)
    step = time.perf_counter()
    execution = run_hidden_tests(extract_dir)
    timings["hidden_tests_ms"] = _duration_ms(step)
    step = time.perf_counter()
    interaction = analyze_report(
        materials["readme"]["text"],
        materials["final_code"]["text"],
        materials["student_report"]["text"],
    )
    timings["analyze_report_ms"] = _duration_ms(step)
    step = time.perf_counter()
    similarity = analyze_similarity(session_id, materials["final_code"]["text"])
    timings["similarity_ms"] = _duration_ms(step)

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
        "similarity": similarity,
        "privacy": privacy_summary(),
    }

    step = time.perf_counter()
    question_pool = generate_questions(analysis)
    timings["local_questions_ms"] = _duration_ms(step)
    questions = question_pool[:1]
    agent = DefenseAgent()
    agent_tool_results = []
    if use_agent and agent.enabled:
        step = time.perf_counter()
        llm_question, agent_tool_results = await agent.generate_first_question(analysis, filtered_material_texts(material_texts, analysis))
        timings["api_first_question_ms"] = _duration_ms(step)
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
        "privacy_mode": privacy_mode(),
        "max_rounds": MAX_DEFENSE_ROUNDS,
        "processing": None,
    }
    timings["total_ms"] = _duration_ms(started)
    save_session(session)
    log_event(session_id, "submission_analyzed", {
        "extracted_files": extracted,
        "missing": analysis["missing"],
        "line_count": code["line_count"],
        "hidden_tests": f"{execution.get('passed', 0)}/{execution.get('total', 0)}",
        "report_chars": interaction["student_report_chars"],
        "agent_enabled": agent.enabled,
        "privacy_mode": privacy_mode(),
        "similarity": similarity.get("risk_label"),
        "first_question_source": questions[0].get("source") if questions else "",
    })
    log_event(session_id, "submission_timing", timings)
    write_snapshot(session_id, "analysis", analysis)
    write_snapshot(session_id, "active_questions", {"questions": questions})
    write_snapshot(session_id, "local_fallback_question_pool", {
        "note": "仅用于 API 不可用或结构化返回失败时兜底，不会一次性展示给学生。",
        "count": len(question_pool),
    })
    if agent_tool_results:
        write_snapshot(session_id, "question_agent_tool_results", {"tool_results": agent_tool_results})
    return session


async def prepare_first_question(session_id: str) -> dict:
    session = load_session(session_id)
    agent = DefenseAgent()
    if not agent.enabled:
        session["question_update_pending"] = False
        save_session(session)
        return session

    started = time.perf_counter()
    try:
        question, tool_results = await agent.generate_first_question(session["analysis"], _agent_materials(session))
        if question and int(session.get("current_index", 0)) == 0 and not session.get("answers"):
            question["source"] = "api_agent"
            session["questions"] = [question]
            session["first_question_fallback_ready"] = False
            session["agent_tool_results"] = tool_results
            write_snapshot(session_id, "question_agent_tool_results", {"tool_results": tool_results})
            write_snapshot(session_id, "active_questions", {"questions": session.get("questions", [])})
            log_event(session_id, "first_question_ready", {
                "source": "api_agent",
                "duration_ms": _duration_ms(started),
                "agent_tools": len(tool_results),
            })
        else:
            session["first_question_fallback_ready"] = True
            log_event(session_id, "first_question_fallback_ready", {
                "duration_ms": _duration_ms(started),
                "agent_tools": len(tool_results),
                "reason": "API Agent 未返回可用首问，显示本地兜底问题。",
            })
    except Exception as exc:
        session["processing_error"] = f"首问生成失败，已使用本地问题：{exc}"
        session["first_question_fallback_ready"] = True
        log_event(session_id, "first_question_failed", {
            "duration_ms": _duration_ms(started),
            "error": str(exc),
        })
    finally:
        session["question_update_pending"] = False
        save_session(session)
    return session


def _answer_is_weak(answer: str) -> bool:
    stripped = answer.strip()
    if len(stripped) < 40:
        return True
    useful_terms = ["原理", "过程", "因为", "原因", "验证", "图像", "像素", "通道", "滤波", "卷积", "输入", "输出", "结果", "边界", "代码"]
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


def _looks_like_clarification_request(answer: str) -> bool:
    stripped = answer.strip().lower()
    if not stripped:
        return False
    clarification_terms = [
        "没理解",
        "没看懂题",
        "看不懂题",
        "没懂题",
        "题目什么意思",
        "问题什么意思",
        "什么意思",
        "不明白你问",
        "不明白这个问题",
        "不理解这个问题",
        "没明白这个问题",
        "你是问",
        "是让我",
        "要我解释",
        "应该回答什么",
        "从哪个角度",
        "能不能解释",
        "能解释一下",
        "请解释",
        "clarify",
        "what do you mean",
        "what does this mean",
    ]
    return any(term in stripped for term in clarification_terms)


async def _classify_answer_intent(current_question: dict, answer: str) -> str:
    agent = DefenseAgent()
    if agent.enabled:
        try:
            intent = await agent.classify_answer_intent(current_question, answer)
            if intent:
                return intent
        except Exception:
            pass
    return "clarification_request" if _looks_like_clarification_request(answer) else "formal_answer"


def _build_followup_question(previous_question: dict, answer: str, question_id: str) -> dict:
    return {
        "id": question_id,
        "dimension": "深度追问",
        "is_followup": True,
        "source": "local_fallback",
        "text": (
            "请说清这个处理的原理、步骤，以及你怎么验证结果。"
        ),
        "focus": "追问学生是否理解处理原理、执行过程和结果验证方式。",
        "evidence": previous_question.get("evidence", ""),
    }


def _build_no_knowledge_followup(previous_question: dict, question_id: str) -> dict:
    return {
        "id": question_id,
        "dimension": "换向追问",
        "is_followup": True,
        "source": "local_fallback",
        "text": (
            "换个基础问题：选一个图像操作，说明输入怎样变成输出。"
        ),
        "focus": "给学生换维度说明的机会，考察是否能说清图像处理过程。",
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
            _agent_materials(session),
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


def _clear_processing(session: dict) -> None:
    session["processing"] = None
    session.pop("pending_answer", None)
    session.pop("pending_clarification", None)


def _clear_processing_for_empty_answer(session_id: str, session: dict, question: dict, current_index: int) -> dict:
    session.setdefault("answers", {}).pop(question["id"], None)
    _clear_processing(session)
    save_session(session)
    log_event(session_id, "empty_answer_ignored", {
        "question_id": question["id"],
        "current_index": current_index,
    })
    return session


async def record_answer(session_id: str, answer: str) -> dict:
    session = load_session(session_id)
    if session.get("report") or session.get("processing"):
        return session

    current_index = int(session.get("current_index", 0))
    questions = session.get("questions", [])
    if current_index >= len(questions):
        session["processing"] = {
            "kind": "final_report",
            "message": "答辩回答已收到，系统正在生成评分报告。",
        }
        save_session(session)
        return session

    question = questions[current_index]
    clean_answer = answer.strip()
    if not clean_answer:
        return _clear_processing_for_empty_answer(session_id, session, question, current_index)
    session["pending_answer"] = {
        "question_id": question["id"],
        "current_index": current_index,
        "answer": clean_answer,
    }
    session["processing"] = {
        "kind": "answer",
        "message": "本轮输入已提交，系统正在判断是正式回答还是问题澄清。",
    }
    save_session(session)
    log_event(session_id, "answer_received", {
        "question_id": question["id"],
        "question_dimension": question.get("dimension"),
        "message_chars": len(clean_answer),
        "message_preview": clean_answer[:300],
        "current_index": current_index,
        "no_knowledge": _answer_is_no_knowledge(clean_answer),
    })
    return session


async def process_pending_answer(session_id: str) -> dict:
    session = load_session(session_id)
    if session.get("report"):
        _clear_processing(session)
        save_session(session)
        return session

    pending = session.get("pending_answer") or {}
    current_index = int(pending.get("current_index", session.get("current_index", 0)))
    questions = session.get("questions", [])
    if current_index >= len(questions):
        return await finish_defense(session_id, session.get("answers", {}))

    question = questions[current_index]
    answer = str(pending.get("answer", "")).strip()
    if not answer.strip():
        return _clear_processing_for_empty_answer(session_id, session, question, current_index)
    started = time.perf_counter()
    log_event(session_id, "answer_processing_started", {
        "question_id": question["id"],
        "current_index": current_index,
    })

    intent = await _classify_answer_intent(question, answer)
    if intent == "clarification_request":
        session = await clarify_question(session_id, answer)
        _clear_processing(session)
        save_session(session)
        log_event(session_id, "answer_treated_as_clarification", {
            "question_id": question["id"],
            "duration_ms": _duration_ms(started),
            "message_chars": len(answer),
        })
        return session

    session.setdefault("answers", {})[question["id"]] = answer
    _append_dialogue_event(session, {
        "type": "answer",
        "question_id": question["id"],
        "dimension": question.get("dimension", "现场答辩"),
        "question": question.get("text", ""),
        "student": answer,
        "assistant": "",
        "counts_for_score": True,
    })
    save_session(session)

    if len(questions) < MAX_DEFENSE_ROUNDS:
        step = time.perf_counter()
        next_question, next_tool_results = await _build_next_question(session, question, answer)
        log_event(session_id, "next_question_timing", {
            "after_question_id": question["id"],
            "duration_ms": _duration_ms(step),
            "agent_tools": len(next_tool_results),
        })
        if session.get("early_finish_reason"):
            session["questions"] = questions
            session["current_index"] = current_index + 1
            _clear_processing(session)
            if next_tool_results:
                session.setdefault("next_question_tool_results", []).append({
                    "after_question_id": question["id"],
                    "tool_results": next_tool_results,
                })
            save_session(session)
            log_event(session_id, "defense_ended_early", {
                "reason": session["early_finish_reason"],
                "question_id": question["id"],
                "agent_decision": session.get("last_agent_decision"),
                "agent_tools": len(next_tool_results),
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
    _clear_processing(session)
    save_session(session)
    log_event(session_id, "answer_processing_finished", {
        "question_id": question["id"],
        "duration_ms": _duration_ms(started),
        "current_index": session["current_index"],
        "question_count": len(session["questions"]),
    })

    if session["current_index"] >= len(session["questions"]):
        return await finish_defense(session_id, session["answers"])
    return session


def _question_base_text(current_question: dict) -> str:
    return str(current_question.get("original_text") or current_question.get("text") or "").strip()


def _clarification_is_too_vague(response: str, original_question: str) -> bool:
    text = response.strip()
    if len(text) < 70:
        return True
    vague_phrases = [
        "一个具体实现点",
        "某个实现点",
        "这题想看",
        "请围绕",
        "相关函数",
        "完整说明它要解决什么问题",
        "核心处理步骤是什么",
        "用什么输入图片",
    ]
    if any(phrase in text for phrase in vague_phrases):
        return True
    if not any(marker in text for marker in ["题干", "这里", "函数", "变量", "表示", "负责", "作用"]):
        return True
    return False


def _question_reference_tokens(original_question: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.findall(r"`([^`]+)`|([A-Za-z_][A-Za-z0-9_]{2,})|第\s*\d+\s*行", original_question):
        token = next((part for part in raw if part), "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def _function_context(source: str, function_name: str, window: int = 36) -> str:
    if not source or not function_name:
        return ""
    lines = source.splitlines()
    pattern = re.compile(rf"^\s*def\s+{re.escape(function_name)}\s*\(")
    start = next((idx for idx, line in enumerate(lines) if pattern.search(line)), None)
    if start is None:
        return ""
    selected = lines[start:start + window]
    return "\n".join(selected)


def _describe_question_objects(original_question: str, material_texts: dict | None = None) -> str:
    tokens = _question_reference_tokens(original_question)
    source = ""
    if material_texts:
        source = str(material_texts.get("final_code", ""))
    function_names = [
        token for token in tokens
        if re.search(rf"^\s*def\s+{re.escape(token)}\s*\(", source, re.MULTILINE)
    ]
    function_name = function_names[0] if function_names else ""
    context = _function_context(source, function_name)
    explanations: list[str] = []

    if function_name == "edge_detect":
        explanations.append("`edge_detect` 是边缘检测函数，它用 3x3 卷积核比较中心像素和周围像素，差异越大输出越亮。")
    elif function_name:
        explanations.append(f"`{function_name}` 是这道题定位到的函数，需要看它在终版代码里怎样处理输入图像并生成输出。")

    if "total" in tokens or "total" in original_question:
        explanations.append("`total` 是某个颜色通道经过卷积核加权后的累加值，可能为负，也可能超过 0-255。")
    if "abs(total)" in original_question or "abs" in tokens:
        explanations.append("`abs(total)` 把边缘强度取成非负值，避免方向相反的边缘因为负数被直接压成黑色。")
    if "_clamp(abs(total))" in original_question or "_clamp" in tokens:
        explanations.append("`_clamp(...)` 把计算结果限制到图像像素允许的 0-255 范围，保证能写回 RGB 图像。")
    elif "_clamp" in context:
        explanations.append("代码里出现的 `_clamp` 通常是在防止像素值越界。")

    if not explanations and context:
        first_line = context.splitlines()[0].strip()
        explanations.append(f"题干定位到 `{first_line}` 附近的实现，重点是理解这段代码如何把输入像素变成输出像素。")
    if not explanations:
        target = original_question.rstrip("。？！!?；;，, ") or "当前题目"
        explanations.append(f"题干问的是：{target}。")
    return " ".join(explanations)


def _local_clarification(current_question: dict, student_message: str, material_texts: dict | None = None) -> str:
    original_question = _question_base_text(current_question)
    explanation = _describe_question_objects(original_question, material_texts)
    question = _focused_clarification_question(original_question)
    return (
        f"题干解释：{explanation} "
        f"请你回答：{question}"
    )


def _focused_clarification_question(original_question: str) -> str:
    if "edge_detect" in original_question and "_clamp(abs(total))" in original_question:
        return "为什么边缘检测这里要先取绝对值再限制到 0-255，而不是直接把卷积累加值写进输出图像？"
    if "edge_detect" in original_question and ("正负" in original_question or "范围" in original_question):
        return "卷积结果为什么会出现负数或超过 255，这段代码怎样把它变成可显示的边缘强度？"
    target = original_question.rstrip("。？！!?；;，, ") or "这段实现"
    return f"{target} 的核心原因是什么？请只围绕这个原因回答。"


async def clarify_question(session_id: str, student_message: str) -> dict:
    session = load_session(session_id)
    current_index = int(session.get("current_index", 0))
    questions = session.get("questions", [])
    if current_index >= len(questions):
        return session

    current_question = questions[current_index]
    clean_message = student_message.strip()
    agent = DefenseAgent()
    tool_results = []
    started = time.perf_counter()
    if agent.enabled:
        try:
            response, tool_results = await agent.clarify_question(
                session["analysis"],
                _agent_materials(session),
                questions,
                session.get("answers", {}),
                current_question,
                clean_message,
            )
        except Exception as exc:
            response = _local_clarification(current_question, clean_message, session.get("material_texts", {}))
            session["processing_error"] = f"澄清生成失败，已使用本地解释：{exc}"
            log_event(session_id, "clarification_failed", {
                "question_id": current_question["id"],
                "error": str(exc),
            })
    else:
        response = _local_clarification(current_question, clean_message, session.get("material_texts", {}))

    entry = {
        "question_id": current_question["id"],
        "original_question": _question_base_text(current_question),
        "student_message": clean_message,
        "assistant_response": response,
        "source": "api_agent" if agent.enabled and tool_results else "local_fallback",
    }
    original_text = _question_base_text(current_question)
    if not response or _clarification_is_too_vague(response, original_text):
        response = _local_clarification(current_question, clean_message, session.get("material_texts", {}))
        if entry["source"] == "api_agent":
            entry["source"] = "api_agent_repaired"
            entry["assistant_response"] = response
    session.setdefault("clarifications", []).append(entry)
    _append_dialogue_event(session, {
        "type": "clarification",
        "question_id": current_question["id"],
        "dimension": "题意澄清",
        "question": entry["original_question"],
        "student": clean_message,
        "assistant": response,
        "source": entry["source"],
        "counts_for_score": False,
    })

    if response:
        current_question.setdefault("original_text", current_question.get("text", ""))
        current_question["text"] = response
        current_question["dimension"] = "澄清后的问题"
        current_question["source"] = entry["source"]
        current_question["focus"] = "学生上一轮表示未理解题意，本轮不计入正式答辩；请基于澄清后的问题继续回答。"
        questions[current_index] = current_question
        session["questions"] = questions
    if tool_results:
        session.setdefault("clarification_tool_results", []).append({
            "question_id": current_question["id"],
            "tool_results": tool_results,
        })
    save_session(session)
    log_event(session_id, "clarification_created", {
        "question_id": current_question["id"],
        "message_chars": len(clean_message),
        "duration_ms": _duration_ms(started),
        "source": entry["source"],
        "agent_tools": len(tool_results),
    })
    return session


async def process_pending_clarification(session_id: str) -> dict:
    session = load_session(session_id)
    if session.get("report"):
        _clear_processing(session)
        save_session(session)
        return session

    pending = session.get("pending_clarification") or {}
    clean_message = str(pending.get("student_message", "")).strip()
    current_index = int(pending.get("current_index", session.get("current_index", 0)))
    questions = session.get("questions", [])
    if not clean_message or current_index >= len(questions):
        _clear_processing(session)
        save_session(session)
        return session

    current_question = questions[current_index]
    if pending.get("question_id") and pending.get("question_id") != current_question.get("id"):
        _clear_processing(session)
        save_session(session)
        log_event(session_id, "clarification_skipped", {
            "reason": "question_changed",
            "pending_question_id": pending.get("question_id"),
            "current_question_id": current_question.get("id"),
        })
        return session

    session = await clarify_question(session_id, clean_message)
    _clear_processing(session)
    save_session(session)
    return session


async def finish_defense(session_id: str, answers: dict[str, str]) -> dict:
    session = load_session(session_id)
    started = time.perf_counter()
    session["answers"] = answers
    _clear_processing(session)
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
        step = time.perf_counter()
        evaluation, evaluation_tool_results = await agent.evaluate_answers(
            session["analysis"],
            _agent_materials(session),
            session["questions"],
            answers,
        )
        log_event(session_id, "answer_evaluation_timing", {
            "duration_ms": _duration_ms(step),
            "agent_tools": len(evaluation_tool_results),
            "applied": bool(evaluation),
        })
        if evaluation_tool_results:
            session["answer_evaluation_tool_results"] = evaluation_tool_results
            write_snapshot(session_id, "answer_evaluation_tool_results", {"tool_results": evaluation_tool_results})
        if evaluation:
            report = apply_answer_evaluation(report, evaluation)
            session["answer_evaluation"] = evaluation
            write_snapshot(session_id, "answer_evaluation", evaluation)

        step = time.perf_counter()
        overlay, report_tool_results = await agent.generate_report(
            session["analysis"],
            _agent_materials(session),
            session["questions"],
            answers,
            report,
        )
        log_event(session_id, "report_agent_timing", {
            "duration_ms": _duration_ms(step),
            "agent_tools": len(report_tool_results),
        })
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
    if not session.get("teacher_review"):
        session.setdefault("portal", {})["status"] = "pending_review"
        session["portal"]["report_ready_at"] = session["portal"].get("report_ready_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
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
        "duration_ms": _duration_ms(started),
    })
    return session
