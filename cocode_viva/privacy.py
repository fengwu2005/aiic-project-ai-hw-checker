from __future__ import annotations

from cocode_viva.config import privacy_mode


def filtered_material_texts(material_texts: dict[str, str], analysis: dict) -> dict[str, str]:
    mode = privacy_mode()
    if mode == "full":
        return material_texts
    if mode == "balanced":
        return {
            "readme": _limit(material_texts.get("readme", ""), 1800),
            "final_code": _focused_code_excerpt(material_texts.get("final_code", "")),
            "student_report": _limit(material_texts.get("student_report", ""), 2200),
        }
    if mode == "strict":
        return {
            "readme": _strict_summary(analysis),
            "final_code": _strict_summary(analysis),
            "student_report": _strict_summary(analysis),
        }
    return {}


def privacy_summary() -> dict[str, str]:
    mode = privacy_mode()
    labels = {
        "full": "完整材料模式",
        "balanced": "摘要与片段模式",
        "strict": "严格摘要模式",
        "offline": "离线模式",
    }
    descriptions = {
        "full": "API 可接收完整 README、终版代码和报告，用于生成更贴近代码的答辩问题。",
        "balanced": "API 只接收截断报告、README 和关键代码片段，减少原始材料外发。",
        "strict": "API 只接收本地静态分析、隐藏验收和风险摘要，不发送原始代码正文。",
        "offline": "完全不调用外部 API，只使用本地隐藏验收、规则评分和教师审核。",
    }
    return {
        "mode": mode,
        "label": labels.get(mode, labels["full"]),
        "description": descriptions.get(mode, descriptions["full"]),
    }


def _limit(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[privacy truncated]"


def _focused_code_excerpt(source: str) -> str:
    lines = (source or "").splitlines()
    selected: list[str] = []
    interesting = ("def ", "import ", "Image.", ".resize", ".rotate", ".crop", "getpixel", "putpixel", "kernel", "median", "raise ")
    for index, line in enumerate(lines, start=1):
        if any(token in line for token in interesting):
            selected.append(f"{index}: {line[:180]}")
        if len(selected) >= 80:
            break
    return "\n".join(selected) if selected else _limit(source, 1800)


def _strict_summary(analysis: dict) -> str:
    code = analysis.get("code", {})
    execution = analysis.get("execution", {})
    interaction = analysis.get("interaction", {})
    similarity = analysis.get("similarity", {})
    return "\n".join([
        "隐私模式：strict，未发送原始代码或完整报告。",
        f"函数：{', '.join(code.get('functions', [])[:40])}",
        f"导入：{', '.join(code.get('imports', [])[:20])}",
        f"功能痕迹：{', '.join(name for name, ok in code.get('features', {}).items() if ok)}",
        f"隐藏验收：{execution.get('passed', 0)}/{execution.get('total', 0)}",
        f"报告长度：{interaction.get('student_report_chars', 0)} 字符",
        f"查重风险：{similarity.get('risk_label', '未计算')}",
    ])
