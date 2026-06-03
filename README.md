# CoCode Viva：AI 协作编程作业答辩系统

CoCode Viva 是一个面向“允许学生使用 AI 完成编程作业”的答辩系统。系统固定作业为 **TaskFlow Pro 智能任务管理器**，学生提交 zip 作业包后，系统会读取最终代码、测试、第一次 AI prompt、第一次 AI 回复、AI 初版代码、完整对话记录和学生报告，动态生成答辩问题，并输出评分参考与个人贡献比例判断。

## 页面结构

系统只有三个页面：

1. 题目要求：展示 TaskFlow 作业背景、功能要求、固定提交格式和评分标准。
2. 提交与答辩：上传 zip，系统分析材料并生成现场答辩问题。
3. 评分报告：展示总分、分项得分、原创性判断、证据和风险提示。

答辩采用逐题推进方式。上传后只生成第 1 问，学生每次只看到当前问题；每次回答后，系统会结合上一问、学生回答、材料证据和已问历史动态生成下一问。工具调用、逐题记录和 Agent 证据链默认隐藏在后台证据页。

每次运行都会写入本地 debug 日志，位置为 `data/debug_logs/<session_id>/`。其中 `events.jsonl` 记录上传、回答、追问、报告生成等事件，其他 JSON 文件保存分析结果、问题列表、工具调用结果和最终报告快照。

## 运行方式

```bash
cd /home/ubuntu/fengwu/aiic-project0/project-1wk
python3 app.py
```

浏览器访问：

```text
http://127.0.0.1:8000
```

如果环境缺少依赖：

```bash
pip3 install -r requirements.txt
```

## 可选大模型配置

系统默认可以离线运行，使用本地规则生成问题和报告。如果需要接入 OpenAI-compatible API，推荐复制本地配置文件：

```bash
cp config/local_settings.example.json config/local_settings.json
```

然后编辑 `config/local_settings.json`：

```json
{
  "OPENAI_API_KEY": "你的 API Key",
  "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
  "OPENAI_MODEL": "qwen3.5-122b-a10b"
}
```

再启动：

```bash
python3 app.py
```

也可以临时使用环境变量覆盖本地配置：

```bash
export OPENAI_API_KEY="你的 API Key"
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
export OPENAI_MODEL="qwen3.5-122b-a10b"
python3 app.py
```

当前实现会先调用本地 skills 结构化读取提交材料。配置 API key 后，DefenseAgent 会通过受控 JSON 工具请求读取、搜索、比较学生提交材料，再动态生成答辩问题和评分参考；没有 API key 时自动使用本地 QuestionSkill 和 ScoringSkill 离线运行。

## 样例提交包

样例源码目录：

```text
examples/taskflow_sample_submission/
```

样例 zip：

```text
examples/taskflow_sample_submission.zip
```

系统第二页也提供“下载样例提交包”入口。

## 固定提交格式

学生提交 zip 内必须包含：

```text
TaskFlow_Submission/
  README.md
  final/
    taskflow.py
  tests/
    test_taskflow.py
  ai/
    initial_prompt.md
    initial_response.md
    initial_code.py
    full_conversation.md
  report/
    report.md
```

文件名是系统读取材料和生成答辩问题的重要依据。

## 本地 skills

- `ArchiveSkill`：安全解压 zip，限制路径穿越、文件数量和文件大小。
- `FileReaderSkill`：按固定命名读取 README、最终代码、测试、AI 初版材料、完整对话和学生报告。
- `CodeAnalysisSkill`：解析 Python AST，识别函数、类、导入、功能关键词和测试覆盖。
- `InteractionSkill`：分析 AI 交互轮次、提示具体度、报告中的个人判断证据。
- `AgentToolSkill`：为 AI 助教提供受控工具，支持读取材料、搜索材料、比较 AI 初版和最终代码、获取静态分析。
- `DefenseAgent`：配置 API key 后负责调度大模型，通过工具证据生成答辩问题和评分参考。
- `QuestionSkill`：提供本地候选问题池；系统每轮根据上一轮回答动态选择或生成下一问。
- `ScoringSkill`：根据材料证据和答辩回答生成评分参考。

## 交付物对应

- 作业题目与考核方法：见系统第一页和 `docs/assignment.md`
- 可运行答辩系统：`app.py`
- 设计说明文档：`docs/design.md`
- 学生提交样例：`examples/taskflow_sample_submission.zip`
