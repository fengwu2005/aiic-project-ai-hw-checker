from __future__ import annotations

from statistics import mean


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def score_materials(analysis: dict) -> dict:
    code = analysis["code"]
    interaction = analysis["interaction"]
    missing = analysis["missing"]

    feature_score = sum(1 for enabled in code["features"].values() if enabled)
    test_feature_score = sum(1 for enabled in code["test_features"].values() if enabled)

    functionality = _clamp(feature_score * 3 + (0 if missing else 4), 0, 25)
    code_quality = _clamp(4 + min(len(code["functions"]), 6) + (3 if code["syntax_ok"] else 0) + (2 if code["classes"] else 0), 0, 15)
    tests = _clamp(code["test_count"] * 2 + code["assert_count"] + test_feature_score, 0, 15)
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
        "tests": tests,
        "process": process,
        "report": report_score,
    }


def score_defense(questions: list[dict], answers: dict[str, str]) -> dict:
    per_question = []
    for question in questions:
        answer = answers.get(question["id"], "").strip()
        lowered = answer.lower()
        score = 0
        if len(answer) >= 80:
            score += 1
        if any(term in answer for term in ["函数", "文件", "测试", "边界", "异常", "原因", "修改", "验证"]):
            score += 1
        if any(term in lowered for term in ["json", "pytest", "argparse", "id", "priority", "deadline", "ai"]):
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
    return {
        "score": defense_score,
        "per_question": per_question,
        "avg_answer_len": avg_answer_len,
    }


def build_report(analysis: dict, questions: list[dict], answers: dict[str, str]) -> dict:
    material_scores = score_materials(analysis)
    defense = score_defense(questions, answers)
    total = sum(material_scores.values()) + defense["score"]

    process = material_scores["process"]
    defense_score = defense["score"]
    report_score = material_scores["report"]
    code_quality = material_scores["code_quality"]

    contribution = _clamp(round(35 + process * 1.8 + defense_score * 1.2 + report_score * 2 + code_quality * 0.7), 20, 95)
    if defense_score < 8 and process < 7:
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

    if code["features"]["json_persistence"]:
        strengths.append("最终代码体现了 JSON 持久化能力。")
    else:
        risks.append("未明显识别到 JSON 持久化实现，可能影响作业核心功能。")
    if code["test_count"] >= 12:
        strengths.append("测试数量达到作业要求。")
    else:
        risks.append("测试数量不足 12 个，验证 AI 代码和必做功能组合的证据偏弱。")
    if interaction["rounds"] >= 5:
        strengths.append("AI 协作记录达到至少 5 轮有效迭代的过程要求。")
    else:
        risks.append("AI 协作轮次不足 5 轮，难以证明完整迭代过程。")
    if defense_score >= 14:
        strengths.append("答辩回答能较好连接代码、测试和修改原因。")
    elif defense_score < 9:
        risks.append("答辩回答较短或泛化，和最终代码的对应关系不足。")

    return {
        "total": total,
        "material_scores": material_scores,
        "defense_score": defense["score"],
        "per_question": defense["per_question"],
        "contribution": contribution,
        "contribution_level": level,
        "strengths": strengths,
        "risks": risks,
        "basis": [
            "最终代码功能、结构和测试覆盖作为作业结果证据。",
            "AI 初始输出、交互日志和反思报告作为协作过程证据。",
            "现场答辩回答与提交材料的一致性作为理解程度证据。",
            "系统不判断是否使用 AI，而判断学生是否能负责任地使用、验证和修正 AI。",
            "若学生自主实现 AI 共创扩展功能，教师可结合 README、测试、报告和答辩证据额外给出最多 5 分 bonus。",
        ],
    }
