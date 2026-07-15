# Resume Notes

## English

- Built PyFixAgent, a test-driven repair agent for local Python projects that runs pytest, selects failure-driven context, applies constrained LLM-generated edits, and verifies fixes through iterative test execution.
- Designed unified edit policies for replacement and patch modes, enforcing workspace-relative paths, allowed source roots, test-file protection, and file/change budgets.
- Implemented structured, versioned repair traces and a repeatable benchmark runner with YAML case manifests, repeated runs, Success@1, Pass@k, prompt/token metrics, and JSON/Markdown reports.
- Added clean Git workspace checks, CLI exit status, provider-independent LiteLLM integration, resettable fixtures, CI across supported Python versions, and 100+ unit tests.

## 中文

- 实现 PyFixAgent：面向本地 Python 项目的测试驱动代码修复 Agent，自动运行 pytest、选择失败相关上下文、应用受约束的模型编辑，并通过多轮测试反馈验证修复结果。
- 为 replacement 与 patch 模式设计统一编辑策略，在工具层强制执行工作区相对路径、允许源码目录、测试文件保护以及文件数和改动行数预算。
- 实现带版本的结构化修复 Trace 和可重复 Benchmark Runner，支持 YAML 案例清单、重复运行、Success@1、Pass@k、Prompt/Token 指标及 JSON/Markdown 报告。
- 加入 Git 干净工作区检查、可靠 CLI 退出码、LiteLLM 多模型接入、可重置测试样例、多 Python 版本 CI 和 100+ 单元测试。
