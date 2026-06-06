# CoCode Viva：AI 协作编程作业答辩系统

CoCode Viva 是一个面向“允许学生使用 AI 完成编程作业”的答辩系统。系统固定作业为 **TaskFlow Pro 智能任务管理器**，学生在班级中提交 zip 作业包并完成短答辩；教师在教师端查看 AI 评分参考、后台证据，并审核最终分数。

## 系统角色

系统分为学生端和教师端：

- 学生端：注册账号、用班级邀请码加入班级、查看作业、上传 zip、完成逐题短答辩。学生端不展示评分报告、隐藏验收细节或后台证据。
- 教师端：查看班级作业提交、打开评分报告和后台证据、审核并保存教师最终分数。

默认演示班级为 `智能方向 2026 春`，学生注册时可使用班级邀请码：

```text
AI2026
```

默认作业为 `TaskFlow Pro：AI 协作编程作业`。

答辩采用逐题推进方式。上传后只生成第 1 问，学生每次只看到当前问题；每次回答后，系统会结合上一问、学生回答、材料证据和已问历史动态生成下一问。问题被限制为短小具体，最多 4 轮，目标是在约 10 分钟内完成。工具调用、逐题记录和 Agent 证据链只在教师端后台证据页展示。

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

也可以指定端口：

```bash
python3 app.py --port 8765
```

如果指定端口已被占用，程序会自动尝试后续端口，并在终端打印实际访问地址。

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

当前实现会先调用本地 skills 结构化读取提交材料，并执行教师隐藏验收。配置 API key 后，DefenseAgent 会通过受控 JSON 工具请求读取、搜索、比较学生提交材料，并结合隐藏验收结果动态生成答辩问题和评分参考；没有 API key 时自动使用本地 QuestionSkill 和 ScoringSkill 离线运行。后台证据页会显示 API 状态、工具调用记录和隐藏验收明细。

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
  ai/
    initial_prompt.md
    initial_response.md
    initial_code.py
    full_conversation.md
  report/
    report.md
```

文件名是系统读取材料和生成答辩问题的重要依据。

`final/taskflow.py` 还必须暴露固定函数接口，供教师隐藏验收调用：`add_task`、`list_tasks`、`update_status`、`complete_task`、`delete_task`、`batch_update_status`、`archive_tasks`、`export_tasks`、`import_tasks`、`task_statistics`。所有读写数据的函数都应支持 `path` 参数，用于验收隔离。

## 本地 skills

- `ArchiveSkill`：安全解压 zip，限制路径穿越、文件数量和文件大小。
- `FileReaderSkill`：按固定命名读取 README、最终代码、AI 初版材料、完整对话和学生报告。
- `CodeAnalysisSkill`：解析 Python AST，识别函数、类、导入和功能关键词。
- `HiddenTestSkill`：在临时目录导入最终代码，执行教师隐藏验收，检查固定函数接口和真实行为。
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
