from __future__ import annotations


def generate_questions(analysis: dict) -> list[dict]:
    code = analysis["code"]
    interaction = analysis["interaction"]
    features = code["features"]
    execution = analysis.get("execution", {})

    questions = [
        {
            "id": "q1",
            "dimension": "代码理解",
            "is_followup": False,
            "text": "请说明 TaskFlow 的任务数据模型如何支持优先级、截止日期、标签、归档状态和统计功能。哪些字段是你后来从 AI 初版中调整或新增的？",
            "focus": "能否解释高级字段和最终代码相对 AI 初版的演进。",
        },
        {
            "id": "q2",
            "dimension": "AI 协作",
            "is_followup": False,
            "text": "请比较 `ai/initial_code.py` 和 `final/taskflow.py`：你认为最关键的三处变化是什么？每一处变化解决了 AI 初版的什么问题？",
            "focus": "是否能把个人贡献落到初版代码和最终代码的具体差异上。",
        },
        {
            "id": "q3",
            "dimension": "系统验收",
            "is_followup": False,
            "text": "系统隐藏验收会检查组合查询、排序、非法输入、导入导出和归档等行为。请说明你的代码中哪些函数负责这些能力，以及你如何确认它们能被外部验收调用。",
            "focus": "是否理解系统验收关注真实行为和固定函数接口，而不是只跑通 CLI。",
        },
        {
            "id": "q4",
            "dimension": "过程反思",
            "is_followup": False,
            "text": "请选 `ai/full_conversation.md` 中最能体现你个人思考的一轮，说明那轮提示词的目标、AI 建议的价值或问题，以及你最终如何取舍。",
            "focus": "是否有明确的提示策略、验证动作和工程取舍。",
        },
    ]

    if not features["date_validation"]:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "is_followup": False,
            "text": "如果用户输入非法截止日期、非法优先级或不存在的标签筛选条件，你的程序应该如何处理？当前实现是否覆盖？",
            "focus": "追问未明显体现的日期校验能力。",
        })
    else:
        questions.append({
            "id": "q5",
            "dimension": "边界情况",
            "is_followup": False,
            "text": "你是如何校验截止日期格式的？当日期校验与排序、统计或导入功能结合时，最容易出现什么边界错误？",
            "focus": "确认学生理解日期校验实现。",
        })

    if not features["import_export"]:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "is_followup": False,
            "text": "作业要求包含导入导出能力。请说明你为什么没有实现，或者如果要补充，你会如何设计文件格式、冲突处理和校验流程？",
            "focus": "追问缺失的必做工程功能和设计补救能力。",
        })
    else:
        questions.append({
            "id": "q6",
            "dimension": "工程扩展",
            "is_followup": False,
            "text": "导入导出功能如何处理重复 id、字段缺失或损坏 JSON？你是否保留了数据校验的一致入口？",
            "focus": "考察数据迁移和持久化的健壮性。",
        })

    if interaction["rounds"] < 5:
        questions.append({
            "id": "q7",
            "dimension": "原创性",
            "is_followup": False,
            "text": "你的 AI 交互记录少于要求的 5 轮有效迭代。请说明最终代码中哪些关键修改来自你的独立判断，而不是直接复制 AI 输出。",
            "focus": "交互证据不足时追问个人贡献。",
        })
    elif execution and execution.get("passed", 0) < execution.get("total", 0):
        questions.append({
            "id": "q7",
            "dimension": "系统验收",
            "is_followup": False,
            "text": "系统隐藏验收发现部分行为没有通过。请结合你的函数接口说明最可能失败的位置，以及你会如何定位和修复。",
            "focus": "考察对验收失败的定位能力。",
        })
    else:
        questions.append({
            "id": "q7",
            "dimension": "原创性",
            "is_followup": False,
            "text": "最终报告中你声称的关键贡献，哪一项最能体现你的工程能力？请结合具体函数、系统验收要求和 AI 对话记录说明。",
            "focus": "要求把贡献落到具体证据上。",
        })

    return questions[:5]
