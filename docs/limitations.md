# Limitations

PyFixAgent is intentionally scoped as a local prototype for small Python projects. The following limits are current project boundaries, not hidden bugs.

## Not Production-grade Sandbox

The sandbox is a local command runner with command policy checks and subprocess timeouts. It does not provide container isolation, filesystem isolation, network isolation, CPU limits, memory limits, or hardening for untrusted code.

## Designed for Small Python Projects

The agent is meant for small local Python workspaces where pytest output and a few source files are enough to reason about the failure.

## Git Workspace Model

The CLI requires a Git repository with a HEAD commit and requires a clean selected workspace by default. v0.5 repairs a detached temporary worktree, checkpoints accepted iterations, rolls back regressions, exports a patch, and removes the worktree. This protects the selected checkout from repair mutations, but it does not isolate executed code from the host. `--in-place` and `--allow-dirty` are explicit compatibility escape hatches with weaker guarantees.

## pytest Is the Main Validation Signal

PyFixAgent treats pytest as the primary correctness signal. If tests are incomplete, flaky, slow, or misleading, the repair loop inherits those weaknesses.

## Repository Understanding Is Static and Bounded

The default traceback context strategy uses failing tests, traceback frames, and direct test imports as seeds. v0.6.1 adds an execution-free Python AST index and bounded direct import/importer traversal. It does not resolve runtime imports, dynamic dispatch, monkeypatching, generated modules, or non-Python dependencies.

## No Vector Database / RAG

There is no vector database, embedding search, or retrieval-augmented generation system.

## No Dynamic or Cross-language Dependency Graph

The static graph is evidence for context selection, not a claim of complete program understanding.

## No GitHub PR Integration

PyFixAgent does not create GitHub issues, branches, pull requests, comments, or review threads.

## LLM Output Reliability Is Not Guaranteed

Model responses can be malformed, incomplete, overbroad, or wrong. PyFixAgent adds parsing, validation, and pytest feedback, but it cannot guarantee reliable repairs.

## Trace Sensitivity

Traces may contain source code, pytest logs, model outputs, local paths, and environment details. Do not publish traces that contain secrets, private source code, API keys, credentials, or sensitive logs.
