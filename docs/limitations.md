# Limitations

PyFixAgent is intentionally scoped as a local prototype for small Python projects. The following limits are current project boundaries, not hidden bugs.

## Not Production-grade Sandbox

The sandbox is a local command runner with command policy checks and subprocess timeouts. It does not provide container isolation, filesystem isolation, network isolation, CPU limits, memory limits, or hardening for untrusted code.

## Designed for Small Python Projects

The agent is meant for small local Python workspaces where pytest output and a few source files are enough to reason about the failure.

## pytest Is the Main Validation Signal

PyFixAgent treats pytest as the primary correctness signal. If tests are incomplete, flaky, slow, or misleading, the repair loop inherits those weaknesses.

## Context Selection Is Lightweight

The default traceback context strategy uses failing tests, traceback frames, and direct test imports. It is designed to be simple and inspectable.

## No Full Repository Indexing

PyFixAgent does not build or maintain a full repository index.

## No Vector Database / RAG

There is no vector database, embedding search, or retrieval-augmented generation system.

## No Complete Dependency Graph

Direct imports from failing tests may be included, but the project does not compute a complete import graph or dependency graph.

## No GitHub PR Integration

PyFixAgent does not create GitHub issues, branches, pull requests, comments, or review threads.

## LLM Output Reliability Is Not Guaranteed

Model responses can be malformed, incomplete, overbroad, or wrong. PyFixAgent adds parsing, validation, and pytest feedback, but it cannot guarantee reliable repairs.

## Trace Sensitivity

Traces may contain source code, pytest logs, model outputs, local paths, and environment details. Do not publish traces that contain secrets, private source code, API keys, credentials, or sensitive logs.
