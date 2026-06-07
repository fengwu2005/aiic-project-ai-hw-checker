from __future__ import annotations

import re


THINKING_TERMS = [
    "我发现",
    "我认为",
    "我决定",
    "我验证",
    "验证",
    "边界",
    "取舍",
    "修改",
    "测试",
    "验收",
    "函数",
    "像素",
    "卷积",
    "滤波",
    "原因",
]


def analyze_report(readme: str, final_code: str, student_report: str) -> dict:
    section_matches = re.findall(r"(?:^|\n)\s*#{1,3}\s+", student_report)
    validation_terms = ["测试", "验证", "验收", "断言", "边界", "异常", "非法", "通过", "失败"]
    implementation_terms = ["函数", "接口", "PIL", "Pillow", "像素", "RGB", "裁剪", "卷积", "滤波", "中值", "均值", "反色", "旋转"]
    contribution_terms = ["我实现", "我修改", "我加入", "我重构", "我选择", "我设计", "我处理", "自己", "个人实现", "关键实现"]
    limitation_terms = ["限制", "不足", "问题", "失败", "未完成", "边界", "风险"]

    report_lower = student_report.lower()
    thinking_hits = [term for term in THINKING_TERMS if term.lower() in report_lower]

    report_specificity = 0
    if len(student_report) >= 700:
        report_specificity += 1
    if any(term.lower() in report_lower for term in implementation_terms):
        report_specificity += 1
    if any(term in student_report for term in validation_terms):
        report_specificity += 1

    return {
        "sections": len(section_matches),
        "readme_chars": len(readme),
        "final_code_chars": len(final_code),
        "student_report_chars": len(student_report),
        "thinking_terms": thinking_hits,
        "report_specificity": report_specificity,
        "mentions_implementation": any(term.lower() in report_lower for term in implementation_terms),
        "mentions_validation": any(term in student_report for term in validation_terms),
        "mentions_personal_changes": any(term in student_report for term in contribution_terms),
        "mentions_limitations": any(term in student_report for term in limitation_terms),
    }
