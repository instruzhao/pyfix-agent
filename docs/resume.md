# Resume Notes

## English

- Built PyFixAgent, a lightweight test-driven repair agent for local Python projects that runs pytest, collects failure traces, prompts an LLM through LiteLLM, applies structured code edits, and verifies fixes through iterative test execution.
- Designed dual repair backends: unified-diff patch mode with git-apply validation, and JSON replacement mode with workspace/path constraints and context-aware replacement for reliable small-scope edits.
- Implemented traceback-driven context selection and structured repair traces, recording selected files, test deltas, iteration results, model outputs, applied edits, and final repair summaries.
- Added CLI/config support, resettable demo workspaces, lightweight benchmark documentation, and 60+ unit tests covering agent loop, patch handling, replacement application, context selection, trace generation, and sandbox policy.

## 中文

- 实现 PyFixAgent，一个面向本地 Python 小项目的轻量级测试驱动代码修复 Agent：自动运行 pytest、收集失败信息、调用大模型生成修复、应用代码修改，并通过多轮测试反馈验证结果。
- 设计 patch 与 replacement 两种修复后端：patch 模式支持 unified diff 清理、校验和 git apply 检查；replacement 模式支持结构化 JSON 替换、路径约束和上下文匹配，提高小范围修复稳定性。
- 实现基于 pytest 失败信息的上下文选择和结构化 trace，记录每轮 selected files、failure delta、iteration result、model output、applied edits 和 final summary。
- 补充 CLI/config 支持、可重置示例 workspace、轻量 benchmark 文档和 60+ 单元测试，覆盖 Agent 主流程、patch 处理、replacement 应用、上下文选择、trace 生成和 sandbox 策略。
