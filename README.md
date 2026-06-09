# CoCode Viva：编程作业掌握度答辩系统

CoCode Viva 是一个面向大学课程的作业答辩系统。当前固定作业为 **ImageLab：PIL 图像变换工具**，学生提交 zip 作业包并完成短答辩；教师在教师端查看系统评分参考、后台证据、风险排序，并审核最终分数。

系统重点不是查重，也不强制学生提交外部工具使用记录。它根据终版代码、报告、隐藏验收和答辩回答判断学生是否真正掌握实现方法。

## 系统角色

- 学生端：注册账号、用班级邀请码加入班级、查看作业、上传 zip、查看并下载自己的提交文件、删除不想展示的历史提交、完成逐题短答辩。答辩中如果没理解题意，可以直接在回答框里追问，系统会判断为澄清请求并改写当前问题，不计入正式答题轮次；也可以补交完整 zip 或单个代码/报告文件。教师审核前只展示提交状态；审核后展示教师确认的最终分数、评语和面向学习复盘的系统反馈，但不展示后台证据或隐藏验收明细。
- 教师端：按学生和作业查看最近一次提交，展开查看历史提交，打开学生提交文件、下载提交 zip、查看评分报告和后台证据、按风险优先复核、审核并保存教师最终分数。

默认演示班级为 `智能方向 2026 春`，学生邀请码为：

```text
AI2026
```

教师注册码为：

```text
TEACH2026
```

默认教师账号：

```text
teacher_demo / demo1234
```

## 运行方式

```bash
cd /root/project-1wk
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

如果环境缺少依赖：

```bash
pip3 install -r requirements.txt
```

## 可选大模型配置

系统默认可以离线运行，使用本地规则生成问题和报告。如果需要接入 OpenAI-compatible API，复制配置文件：

```bash
cp config/local_settings.example.json config/local_settings.json
```

然后编辑 `config/local_settings.json`：

```json
{
  "OPENAI_API_KEY": "你的 API Key",
  "OPENAI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
  "OPENAI_MODEL": "qwen3.5-122b-a10b",
  "PRIVACY_MODE": "full"
}
```

配置 API key 后，DefenseAgent 会通过受控 JSON 工具读取终版代码、README、报告和隐藏验收摘要，动态生成答辩问题与评分参考；没有 API key 时自动使用本地规则。

`PRIVACY_MODE` 可选：

- `full`：默认模式，API 可使用完整 README、终版代码和报告，答辩问题最贴近代码。
- `balanced`：只发送截断后的报告、README 和关键代码片段，减少原始材料外发。
- `strict`：只发送本地静态分析、隐藏验收、查重风险和报告长度等摘要，不发送原始代码正文。
- `offline`：完全不调用外部 API，只使用本地隐藏验收、规则问题和教师审核。

上传作业和提交答辩回答后，系统会先确认“已收到”，再在后台生成首问、追问或最终评分报告。学生页面会自动刷新处理状态；教师端后台证据页可以查看解压、材料读取、隐藏验收和 API 调用耗时日志。

服务启动后，本地运行 `python3 app.py` 的终端会每 10 秒打印最近 60 秒活跃访问终端数量，便于现场 demo 时观察当前有多少浏览器/设备正在访问网站。

## 固定提交格式

学生提交 zip 内必须包含：

```text
ImageLab_Submission/
  README.md
  final/
    image_ops.py
  report/
    report.md
```

`final/image_ops.py` 必须使用 Pillow/PIL 实现图像处理，并暴露固定函数接口：

```text
load_image
save_image
resize_image
rotate_image
crop_image
invert_image
blur_image
edge_detect
median_filter
transform_image
```

`report/report.md` 应说明实现方法、验证方式、关键贡献和已知不足。答辩评分会围绕 AI 助教提出的每一道问题，判断学生是否答中问题、理解是否正确、解释是否自洽，而不是机械检查固定关键词。

## 样例提交包

样例源码目录：

```text
examples/image_lab_sample_submission/
```

样例 zip：

```text
examples/image_lab_sample_submission.zip
```

真实 API demo 还额外生成了 4 个不同质量的提交包：

```text
examples/image_lab_excellent_submission.zip
examples/image_lab_partial_submission.zip
examples/image_lab_weak_submission.zip
examples/image_lab_broken_submission.zip
```

教师端默认账号：

```text
teacher_demo / demo1234
```

完整 demo 账号清单见 `accounts.md`。

当前 demo 会话均通过配置的 OpenAI-compatible API 生成答辩问题、模拟学生回答并生成 Agent 评分参考；教师端可以直接查看风险排序、逐题证据和审核状态。

## 本地 skills

- `ArchiveSkill`：安全解压 zip，限制路径穿越、文件数量和文件大小。
- `FileReaderSkill`：按固定命名读取 README、终版代码和学生报告。
- `CodeAnalysisSkill`：解析 Python AST，识别函数、类、导入和图像处理关键词。
- `HiddenTestSkill`：导入终版代码，执行教师隐藏验收，检查固定图像函数接口和真实像素行为。
- `InteractionSkill`：分析报告中的实现、验证、个人实现说明和限制说明。
- `SimilaritySkill`：基于本地历史提交做 AST 结构相似度和函数级相似度分析，只生成教师复核风险提示，不直接扣分。
- `AgentToolSkill`：为系统助教提供受控工具，支持读取材料、搜索材料和获取静态分析。
- `DefenseAgent`：配置 API key 后负责调度大模型，通过工具证据生成答辩问题和评分参考。
- `QuestionSkill`：提供本地候选问题池；系统每轮根据上一轮回答动态选择或生成下一问。
- `ScoringSkill`：根据终版代码、报告、隐藏验收和答辩回答生成评分参考。

## 交付物对应

- 作业题目与考核方法：系统作业页和 `docs/assignment.md`
- 可运行答辩系统：`app.py`
- 设计说明文档：`docs/design.md`
- 学生提交样例：`examples/image_lab_sample_submission.zip`
