from __future__ import annotations

from statistics import mean


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _answer_is_no_knowledge(answer: str) -> bool:
    lowered = answer.strip().lower()
    terms = ["我不会", "不会", "不知道", "不清楚", "不懂", "没看懂", "答不上来", "不会回答", "仍然不会", "i don't know", "idk"]
    return not lowered or any(term in lowered for term in terms)


def score_materials(analysis: dict) -> dict:
    code = analysis["code"]
    interaction = analysis["interaction"]
    missing = analysis["missing"]
    execution = analysis.get("execution", {})

    feature_score = sum(1 for enabled in code["features"].values() if enabled)
    hidden_total = int(execution.get("total") or 0)
    hidden_passed = int(execution.get("passed") or 0)
    hidden_rate = hidden_passed / hidden_total if hidden_total else 0

    functionality = _clamp(round(feature_score * 0.7 + hidden_rate * 12 + (0 if missing else 3)), 0, 25)
    code_quality = _clamp(4 + min(len(code["functions"]), 6) + (3 if code["syntax_ok"] else 0) + (2 if code["classes"] else 0), 0, 15)
    validation = _clamp(round(hidden_rate * 15), 0, 15)
    process = _clamp(interaction["rounds"] * 2 + interaction["prompt_specificity"] * 2 + len(interaction["thinking_terms"]), 0, 15)
    report_score = _clamp(
        (4 if interaction["student_report_chars"] >= 400 else 2)
        + (3 if interaction["mentions_ai_limits"] else 0)
        + (3 if interaction["mentions_personal_changes"] else 0),
        0,
        10,
    )

    return {
        "functionality": functionality,
        "code_quality": code_quality,
        "validation": validation,
        "process": process,
        "report": report_score,
    }


def score_defense(questions: list[dict], answers: dict[str, str]) -> dict:
    per_question = []
    non_empty_answers = []
    for question in questions:
        answer = answers.get(question["id"], "").strip()
        if answer:
            non_empty_answers.append(answer)
        lowered = answer.lower()
        score = 0
        if not _answer_is_no_knowledge(answer):
            if len(answer) >= 80:
                score += 1
            if any(term in answer for term in ["函数", "文件", "验收", "边界", "异常", "原因", "修改", "验证"]):
                score += 1
            if any(term in lowered for term in ["json", "argparse", "id", "priority", "deadline", "ai", "验收"]):
                score += 1
            if len(answer) >= 180:
                score += 1
        per_question.append({
            "id": question["id"],
            "dimension": question["dimension"],
            "question": question["text"],
            "answer": answer,
            "score": score,
            "max_score": 4,
        })

    raw = sum(item["score"] for item in per_question)
    max_raw = max(1, len(per_question) * 4)
    defense_score = round(raw / max_raw * 20)
    avg_answer_len = round(mean([len(item["answer"]) for item in per_question]) if per_question else 0)
    unique_answers = len({answer.strip() for answer in non_empty_answers})
    weak_answers = sum(1 for answer in non_empty_answers if len(answer.strip()) < 40)
    no_knowledge_answers = sum(1 for answer in non_empty_answers if _answer_is_no_knowledge(answer))
    answered_count = len(non_empty_answers)
    validity = "valid"
    if answered_count == 0 or no_knowledge_answers >= 1 and answered_count <= 2 or no_knowledge_answers >= 2 or defense_score <= 2 or weak_answers >= max(1, answered_count - 1) or unique_answers <= 1 and answered_count >= 3:
        validity = "invalid"
    elif defense_score <= 7 or weak_answers >= answered_count // 2:
        validity = "weak"
    elif defense_score <= 12:
        validity = "partial"
    return {
        "score": defense_score,
        "per_question": per_question,
        "avg_answer_len": avg_answer_len,
        "answered_count": answered_count,
        "weak_answers": weak_answers,
        "no_knowledge_answers": no_knowledge_answers,
        "unique_answers": unique_answers,
        "validity": validity,
    }


def build_report(analysis: dict, questions: list[dict], answers: dict[str, str]) -> dict:
    material_scores = score_materials(analysis)
    defense = score_defense(questions, answers)
    raw_total = sum(material_scores.values()) + defense["score"]

    process = material_scores["process"]
    defense_score = defense["score"]
    report_score = material_scores["report"]
    code_quality = material_scores["code_quality"]

    contribution = _clamp(round(35 + process * 1.8 + defense_score * 1.2 + report_score * 2 + code_quality * 0.7), 20, 95)

    cap_note = ""
    total_cap = 100
    contribution_cap = 95
    if defense["validity"] == "invalid":
        total_cap = 45
        contribution_cap = 35
        cap_note = "现场答辩回答无效，无法验证学生本人掌握程度，因此总分和个人贡献比例被封顶。"
    elif defense["validity"] == "weak":
        total_cap = 60
        contribution_cap = 50
        cap_note = "现场答辩回答明显不足，材料证据不能完全转化为本人掌握证据，因此总分和个人贡献比例被限制。"
    elif defense["validity"] == "partial":
        total_cap = 75
        contribution_cap = 70
        cap_note = "现场答辩只部分证明理解，最终分数受到答辩有效性限制。"

    total = min(raw_total, total_cap)
    contribution = min(contribution, contribution_cap)

    if defense["validity"] == "invalid":
        level = "较低"
    elif defense["validity"] == "weak":
        level = "偏低"
    elif defense_score < 8 and process < 7:
        level = "较低"
    elif contribution >= 75:
        level = "较高"
    elif contribution >= 55:
        level = "中等"
    else:
        level = "偏低"

    strengths = []
    risks = []
    code = analysis["code"]
    interaction = analysis["interaction"]
    execution = analysis.get("execution", {})

    if code["features"]["json_persistence"]:
        strengths.append("最终代码体现了 JSON 持久化能力。")
    else:
        risks.append("未明显识别到 JSON 持久化实现，可能影响作业核心功能。")
    if interaction["rounds"] >= 5:
        strengths.append("AI 协作记录达到至少 5 轮有效迭代的过程要求。")
    else:
        risks.append("AI 协作轮次不足 5 轮，难以证明完整迭代过程。")
    if defense_score >= 14:
        strengths.append("答辩回答能较好连接代码、系统验收和修改原因。")
    elif defense_score < 9:
        risks.append("答辩回答较短或泛化，和最终代码的对应关系不足。")
    if cap_note:
        risks.insert(0, cap_note)
    if execution:
        passed = execution.get("passed", 0)
        hidden_total = execution.get("total", 0)
        if hidden_total and passed == hidden_total:
            strengths.append(f"教师隐藏验收通过 {passed}/{hidden_total}，最终代码行为与作业接口要求一致。")
        else:
            risks.append(f"教师隐藏验收通过 {passed}/{hidden_total}，说明最终代码存在接口或行为缺口。")

    return {
        "total": total,
        "raw_total": raw_total,
        "total_cap": total_cap,
        "cap_note": cap_note,
        "material_scores": material_scores,
        "defense_score": defense["score"],
        "defense_validity": defense["validity"],
        "per_question": defense["per_question"],
        "contribution": contribution,
        "contribution_level": level,
        "strengths": strengths,
        "risks": risks,
        "basis": [
            "最终代码功能、结构和系统验收表现作为作业结果证据。",
            "教师隐藏验收结果作为代码真实行为证据。",
            "第一次 AI 回复、AI 初版代码、完整对话记录和学生报告作为协作过程证据。",
            "现场答辩回答与提交材料的一致性作为理解程度证据。",
            "系统不判断是否使用 AI，而判断学生是否能负责任地使用、验证和修正 AI。",
            "若学生自主实现 AI 共创扩展功能，教师可结合 README、隐藏验收、报告和答辩证据额外给出最多 5 分 bonus。",
        ],
    }
