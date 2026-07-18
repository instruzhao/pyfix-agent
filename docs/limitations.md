# Limitations

PyFixAgent is intentionally scoped as a local prototype for small Python projects. The following limits are current project boundaries, not hidden bugs.

## Container Isolation Is Not VM Isolation

The default v0.7.1 container backend disables network access, mounts only the disposable repair worktree, uses a read-only root and bounded tmpfs, drops capabilities, disables privilege escalation, runs as a non-root UID, and enforces CPU, memory, PID, open-file, single-file, output, sampled worktree-growth, and time limits. The local host-process backend must be selected explicitly and is intended only for trusted projects. These controls reduce exposure but do not provide a separate kernel, VM-grade isolation, or a guarantee against container/runtime vulnerabilities.

Container execution requires a running Docker or Podman daemon and a reviewed runner image. Platform bind-mount semantics and daemon configuration remain operator responsibilities. The distributed image recipe pins its base digest and Linux/amd64 wheel hashes, while the resolved image digest/ID is captured at runtime when available. The sampled worktree monitor is defense in depth rather than a filesystem quota: a very fast create/delete burst can occur between samples, though the per-file kernel limit remains active. Current reviewed base-image CVE exceptions are explicit, expiring, and checked by `pyfixagent-verify-container`.

The distributed scientific runner is not a universal dependency environment. Projects needing other system or Python packages must build a reviewed image ahead of execution and select it with `--container-image`; runtime dependency installation remains blocked.

## Designed for Small Python Projects

The agent is meant for small local Python workspaces where pytest output and a few source files are enough to reason about the failure.

## Git Workspace Model

The CLI requires a Git repository with a HEAD commit and requires a clean selected workspace by default. It repairs a detached temporary worktree, checkpoints accepted iterations, rolls back regressions, exports a patch, and removes the worktree. Container execution requires that isolated worktree and cannot be combined with `--in-place`. Local `--in-place` and `--allow-dirty` remain compatibility escape hatches with weaker guarantees.

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

Generation parameters are provider-specific. The default configuration avoids sending a Qwen-only thinking budget, but custom model configurations remain the operator's responsibility and should be checked against the selected provider documentation.

## Trace Sensitivity

Path-redacted traces may still contain source code, pytest logs, model outputs, credentials embedded in source, and other sensitive text. Safe mode hashes known source-bearing fields but is not a general secret detector and cannot guarantee that every sensitive value is removed from normalized errors or metadata. Review traces before publishing them.

The static trace viewer embeds the selected trace data into a standalone HTML file. It escapes content and uses a restrictive content-security policy, but the resulting file retains whatever sensitive data remains in the input. Generate viewers with `--redaction safe` and review the privacy audit before sharing.
