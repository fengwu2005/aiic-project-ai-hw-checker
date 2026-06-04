# 后续完整 AI 对话记录

## 第 1 轮

我的提示词：
请审查第一次代码，不要重写全部代码。重点指出数据模型、状态设计、标签、日期校验和 JSON 读写的风险。

AI 回应摘要：
AI 指出需要校验优先级和日期，建议增加 description 字段，建议状态从 pending/completed 改成 todo/doing/done。

我发现的问题：
AI 没有提到归档状态，也没有指出 `except Exception: return []` 会隐藏 JSON 损坏。

验证方式：
我设计了非法日期、损坏 JSON、非法优先级三个自查场景。

我的处理：
我加入 `validate_priority`、`validate_status`、`parse_date`，并让损坏 JSON 抛出 ValueError。

## 第 2 轮

我的提示词：
请帮我设计 TaskFlow Pro 的必做工程功能接口，包括组合筛选、关键词搜索、排序、批量归档、导入导出和统计。只给接口建议，不要直接写完整代码。

AI 回应摘要：
AI 建议 `list_tasks` 接收 status、priority、tag、keyword 参数，建议 `archive_tasks(ids)` 和 `task_statistics()`。

我发现的问题：
AI 没有考虑截止日期范围，也没有考虑导入重复 id。

验证方式：
我用临时 JSON 文件检查 deadline_from/deadline_to，并构造导入重复 id 的数据。

我的处理：
我扩展 `list_tasks` 支持日期范围和 sort_by，导入时遇到重复 id 会重新分配。

## 第 3 轮

我的提示词：
请检查我的函数接口是否足够支持课程系统隐藏验收。重点看组合筛选、搜索、排序、批量归档、导入导出和统计是否能被外部直接调用。

AI 回应摘要：
AI 建议保留 `list_tasks`、`archive_tasks`、`import_tasks`、`export_tasks` 和 `task_statistics` 等函数。

我发现的问题：
AI 仍然让部分函数使用默认 tasks.json，容易让系统验收互相污染。

验证方式：
我用两个临时 JSON 文件分别调用函数，确认不同数据文件之间互不影响。

我的处理：
我给核心函数保留 `path` 参数，支持系统隐藏验收隔离数据文件。

## 第 4 轮

我的提示词：
导入功能遇到重复 id、字段缺失、非法日期时应该如何处理？请给出设计取舍。

AI 回应摘要：
AI 建议重复 id 直接跳过，字段缺失时填默认值，非法日期时忽略。

我发现的问题：
这些建议虽然能让程序不报错，但会让数据悄悄丢失或变脏。

验证方式：
我构造字段缺失和非法 JSON 的导入文件，看程序是否明确报错。

我的处理：
我采用更严格策略：字段缺失和非法日期抛出错误，重复 id 重新分配并保留任务。

## 第 5 轮

我的提示词：
请从代码质量角度审查最终版本，重点看命令行解析和业务逻辑是否分离。

AI 回应摘要：
AI 建议把 parser 构建放到 `build_parser`，把 CLI 的错误转换放在 `main`，业务函数不直接 print。

我发现的问题：
这个建议合理，但 AI 又建议把统计函数直接打印字符串，不利于系统验收复用。

验证方式：
我检查 `task_statistics` 是否能直接返回结构化字典。

我的处理：
我让 `task_statistics` 返回字典，CLI 层再统一输出 JSON。
