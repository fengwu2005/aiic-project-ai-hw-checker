from __future__ import annotations

import re


THINKING_TERMS = [
    "我发现",
    "我认为",
    "我决定",
    "我验证",
    "测试",
    "边界",
    "取舍",
    "修改",
    "拒绝",
    "保留",
    "原因",
]


def analyze_interaction(initial_prompt: str, initial_response: str, conversation: str, student_report: str) -> dict:
    round_matches = re.findall(r"(?:^|\n)\s*#{1,3}\s*(?:第\s*)?(\d+)\s*(?:轮|round)", conversation, flags=re.I)
    fallback_rounds = len(re.findall(r"(?:我的提示词|prompt|ai 输出|我发现的问题|我的处理)", conversation, flags=re.I)) // 3
    rounds = len(round_matches) if round_matches else fallback_rounds

    combined = "\n".join([initial_prompt, conversation, student_report]).lower()
    thinking_hits = [term for term in THINKING_TERMS if term.lower() in combined]

    prompt_specificity = 0
    if len(initial_prompt) >= 80:
        prompt_specificity += 1
    if any(term in initial_prompt.lower() for term in ["json", "test", "pytest", "argparse", "deadline", "priority"]):
        prompt_specificity += 1
    if any(term in initial_prompt for term in ["不要", "必须", "边界", "异常", "测试"]):
        prompt_specificity += 1

    return {
        "rounds": rounds,
        "initial_prompt_chars": len(initial_prompt),
        "initial_response_chars": len(initial_response),
        "student_report_chars": len(student_report),
        "thinking_terms": thinking_hits,
        "prompt_specificity": prompt_specificity,
        "mentions_ai_limits": any(term in student_report for term in ["AI", "错误", "冗长", "幻觉", "不严谨", "问题"]),
        "mentions_personal_changes": any(term in student_report for term in ["我修改", "我加入", "我删除", "我重构", "自己", "人工"]),
    }
