# TaskFlow 作业提交说明

这是一个 AI 辅助完成的命令行任务管理器。程序入口是 `final/taskflow.py`，数据默认保存到 `tasks.json`。

## 支持功能

- 添加任务：标题、优先级、截止日期
- 查看任务：可按状态、优先级和截止日期筛选
- 完成任务：根据任务 id 标记为 completed
- 删除任务：根据任务 id 删除
- JSON 持久化：程序启动后读取本地任务文件

## 运行示例

```bash
python final/taskflow.py add "finish report" --priority high --deadline 2026-06-10
python final/taskflow.py list --status pending
python final/taskflow.py done 1
python final/taskflow.py delete 1
```

## 测试

```bash
python -m pytest tests/test_taskflow.py
```

我使用 AI 生成了第一版代码，随后重点修改了日期校验、文件不存在处理、任务 id 生成和测试用例。

