# Design

PyFixAgent is a lightweight test-driven repair agent for small local Python projects. Its design favors a readable repair loop, constrained edits, and structured traces over broad automation.

## Project Goal

The goal is to demonstrate a local coding-agent loop that can use pytest failures as feedback:

    run pytest
    collect failure output
    select relevant context
    prompt LLM
    parse model output
    apply repair
    rerun pytest
    record trace
    iterate until pass or max iterations

The project is built for inspectability. A user should be able to see what tests failed, what context was selected, what the model returned, what was applied, and whether the next pytest run improved the situation.

## Non-goals

PyFixAgent is not trying to be a production coding agent. The current scope excludes:

- Web UI
- VM or microVM isolation
- GitHub PR or issue integration
- RAG or vector database
- multi-model voting
- automatic test generation
- AST editor
- complex import graph
- large benchmark platform

## Agent Loop

The default agent starts by scanning the workspace and running pytest. If tests already pass, it exits without calling the model. If pytest fails, each iteration:

- parses the pytest output
- selects context
- builds a prompt
- calls the configured model through LiteLLM
- parses the model response
- validates and applies the edit
- reruns pytest
- records a structured iteration trace

The loop stops when pytest passes or `max_iterations` is reached.

## v0.4 Component Architecture

v0.4 keeps the public `DefaultAgent` API and trace schema stable while separating internal responsibilities. `DefaultAgent` is now an assembly facade; `RepairEngine` owns only the deterministic state machine and delegates focused work:

- `WorkspaceSession` inspects the Git baseline, applies the clean-workspace guard, scans files, and creates artifact paths.
- `TestRunner` is the only visible-test execution boundary.
- `ContextProvider` parses failures and selects prompt context.
- `PromptBuilder` renders mode-specific prompts and retry feedback.
- `ModelClient` owns provider calls, duration, and token metadata.
- `PatchBackend` and `ReplacementBackend` independently parse, validate, and apply their edit formats.
- `AttemptEvaluator` maps attempt facts into the stable structured trace schema.
- `RetryPolicy` owns retry and patch-to-replacement mode-switch decisions.

The repair sequence is explicit:

    PREPARE -> RUN_TESTS -> SELECT_CONTEXT -> BUILD_PROMPT -> GENERATE_EDIT
    -> VALIDATE_AND_APPLY -> VERIFY -> EVALUATE -> RETRY_OR_STOP

The benchmark follows the same boundary rule. Manifest parsing, isolated workspace lifecycle, holdout execution, metrics, report rendering, and CLI handling live in separate modules under `pyfixagent/benchmarking/`. `pyfixagent.benchmark` remains a compatibility facade.

## v0.5 Transactional Execution

The default CLI and benchmark paths repair a detached temporary Git worktree. `WorkspaceTransaction` exclusively owns worktree creation, Git checkpoints, rollback, final diff export, and cleanup. `WorkspaceSession` connects that lifecycle to file-tree discovery and patch artifact paths; `RepairEngine` only requests lifecycle actions based on normalized outcomes.

Accepted partial improvements become worktree-local checkpoint commits. An iteration that introduces new failing tests is rolled back to the last checkpoint before another model call. A successful run exports one aggregate patch from the original revision through the final checkpoint, then removes the temporary worktree. The selected checkout remains unchanged until a user explicitly applies the exported patch.

`TestCommandPolicy` accepts argv lists that invoke `pytest` directly or through `python -m pytest`. Shell strings and shell operators are rejected. `TestRunner` executes configured commands in order and stops at the first failure, keeping command validation separate from process execution.

## v0.5.1 Semantic Retry

`RetryPolicy` consumes the normalized iteration result rather than raw pytest text. Partial progress requests a checkpoint and incremental repair. No progress and regressions request rollback plus context expansion. Test timeouts request rollback without pretending that a semantic failure was diagnosed.

`ContextExpansionPolicy` does not select files. It emits a bounded plan consumed by `ContextProvider`: level 0 uses configured traceback context, level 1 doubles the line window and file limit, and level 2 can use full context when full fallback is enabled. The engine records the plan and policy reason but does not contain the classification rules.

`PromptBuilder` converts the decision into generic feedback containing fixed, remaining, and newly introduced test IDs plus the actual checkpoint/rollback state. It does not add project-specific business rules or expose benchmark holdouts.

The component boundaries use small data contracts (`RepairRequest`, `ContextBundle`, `EditProposal`, `ApplyResult`, and `RetryDecision`) instead of passing mutable agent internals between responsibilities. This makes an edit backend or retry policy independently testable without invoking a model or running the complete agent.

## v0.6.0 Semantic Acceptance

A visible pytest pass creates a candidate checkpoint rather than immediately proving final success. `ReviewContextProvider` builds changed-file and visible-test context, `SemanticReviewer` produces strict JSON, `ReviewParser` and evidence validation normalize it, and `ReviewPolicy` alone chooses accept, revise, or `needs_review`.

`StructuralRiskScanner` emits deterministic code-shape questions rather than hidden business rules. A delimiter composition cue disappears when the candidate normalizes an already-present boundary marker; a numeric tie-breaking cue disappears when quantization selects an explicit rounding policy. In v0.6.2, an explicit docstring positive-input cue disappears only when every declared parameter visibly rejects non-positive values. Evidence-based reviewer warnings matching a cue can trigger a bounded revision even when the model labels them non-blocking.

Reviewer output never edits the workspace and is not copied raw into the repair prompt. `ReviewFeedbackBuilder` renders only validated risks and counterexample properties. A revision that breaks visible tests is rolled back to the previous visible-pass checkpoint. The final result distinguishes `visible_success` from semantic acceptance and exports the last candidate even when strict review ends in `needs_review`.

## v0.6.2 Evaluation and Privacy Boundaries

Benchmark manifest schema 3 keeps evaluation knowledge outside the agent boundary. Tags, required/relevant context paths, and distractors are loaded into `BenchmarkCase` for runner-side scoring, but `agent_task` remains generated only from allowed edit roots. Repository-on/off variants use separate fixture copies and are keyed independently for Success@1 and Pass@k.

Benchmark report schema 4 treats repair, review, retrieval, and indexing as distinct measurements. It records repair/review tokens and model duration separately, aggregates repository cache/build timing, and scores selected paths only after the agent closes. Paired A/B results compare matching case, strategy, and repetition identities.

The CLI assembles a separate reviewer model instance from the same provider configuration with an independent output limit. A reviewer thinking budget is sent only when explicitly configured, so provider-specific repair parameters cannot leak into review calls. `SemanticReviewer` still depends only on `ModelClient`; the engine does not know provider limits. Direct library callers can omit the reviewer model and preserve shared-model behavior.

## Provider-Safe Model Defaults

The default configuration uses the Alibaba Cloud deployment of `deepseek-v4-flash` through the existing DashScope OpenAI-compatible endpoint. Thinking is enabled, temperature uses the configured thinking-mode value, and system instructions use the standard system role. The configuration omits `thinking_budget`, which is a Qwen-specific control on this endpoint.

`build_review_model_config` copies connection and general generation settings into a distinct reviewer configuration, then replaces its output limit and thinking flag. It removes any inherited thinking budget unless `semantic_review.thinking_budget` explicitly supplies one. This keeps provider capability decisions at the composition boundary instead of coupling them to `RepairEngine`, `SemanticReviewer`, or benchmark orchestration.

Trace privacy is an output concern owned by `TraceRedactor`, not by repair orchestration. `paths` replaces known absolute roots while retaining prompts and diffs. `safe` replaces source-bearing strings with length and SHA-256 markers while preserving normalized decisions, counts, timings, and token usage. Neither mode changes the in-memory result used by the runner or the external holdout boundary.

## Repair Modes

`replacement` is the default mode. It asks the model for a JSON array of old/new replacements. It is best suited to small, structured edits where exact matching can be validated before writing files.

`patch` is an optional mode. It asks the model for a unified diff and validates it with `git apply --check -` before applying it. Patch mode is useful for diff-style workflows, but model-generated hunk headers can be brittle. If patch validation repeatedly fails, the agent can fall back to replacement mode.

## Context Strategy

The default strategy is `traceback`. It is lightweight and based on pytest failure output. Selected context mainly comes from:

- failing test files
- traceback source files
- direct imports from failing tests

In v0.6.1, traceback selection is the seed stage. `RepositoryIndexer` parses Python files without importing them, `RepositoryIndexService` owns content fingerprints and cache lookup, and `RepositoryContextExpander` alone owns graph traversal, ranking, symbol selection, and source-context budgeting. `ContextProvider` still returns the same `ContextBundle`, so the repair engine does not depend on repository internals.

Import dependencies and reverse importers are traversed to a bounded depth. Seeds always retain priority; related files use stable scores and lexical tie-breaking. When query evidence references an indexed symbol, its source range is selected. Otherwise, a bounded file prefix is used. The aggregate selected source is clipped using a conservative character-to-token estimate.

The cache is content-addressed and stored outside the active repair workspace. If configuration points it inside that workspace, persistent caching is bypassed so cache files cannot enter the candidate patch. Any source edit changes the fingerprint and causes a new index to be built before the next repair or review context request.

This is not a complete semantic call graph or RAG system. It does not execute imports, resolve dynamic dispatch, index non-Python languages, or use embeddings.

The `full` strategy is available for small workspaces and includes all Python files in the workspace. It gives the model broader context, but it can include unrelated code and larger prompts.

The v0.2.2 benchmark compares these two context strategies on the resettable demo workspaces with `context.line_window` set to 25 for traceback snippets. It focuses on selected file counts, selected context characters, prompt characters, failure deltas, iteration results, and final pytest status.

## Structured Trace

Structured trace records each repair attempt as data instead of only text logs. It includes test summaries, failure deltas, selected context metadata, model output parsing, apply status, generated diffs, edit summaries, model call metadata, environment information, and final summary.

Trace schema 1.5 nests execution metadata under `environment.execution`. Local traces identify host-process execution. Container traces retain the effective resource/network policy, requested image, resolved image digest or ID when available, runtime, and runtime version. The standalone viewer is script-free, escapes embedded JSON, applies a restrictive content-security policy, and reports path/source-redaction findings before a trace is shared.

The trace is useful because it separates different failure modes:

- model output could not be parsed
- edit could not be applied
- pytest still failed after applying an edit
- a partial fix reduced the failure set
- a regression introduced new failures
- tests passed

## Sandbox Boundary

`Sandbox` is the stable test-execution protocol. It owns command execution, workspace rebinding, pytest temporary paths, and environment metadata. `TestRunner`, the main CLI, benchmark visible tests, and external holdouts depend on this protocol instead of constructing `LocalSandbox` internally.

`LocalSandbox` remains the compatibility default. It runs a policy-checked subprocess on the host, disables bytecode writes, and enforces a timeout; it is suitable only for trusted projects.

`ContainerSandbox` starts one ephemeral Docker or Podman container per test command. It requires the repair engine's temporary Git worktree and mounts only that disposable workspace at `/workspace`. Its default policy disables networking, makes the container root read-only, provides a bounded no-exec `/tmp`, drops all Linux capabilities, enables no-new-privileges, runs as a non-root UID, and limits CPU, memory, PIDs, and wall time. A timed-out container is force-removed by its generated name. The host repository, model credentials, and host environment are not passed into the container.

Dependencies follow an `image_only` policy: runtime installation commands are rejected and the runner image is built from `containers/requirements.lock`. Trace metadata captures the requested image and best-effort resolved digest/ID. Operators who need other dependencies must build a reviewed image and select it in configuration.

This is defense in depth, not a claim that a shared-kernel container is equivalent to a VM, microVM, or fully hardened hostile-code service. Docker/Podman daemon security, kernel vulnerabilities, image provenance, and platform-specific bind-mount behavior remain operator responsibilities.

## Patch Approval Boundary

An isolated repair exports a patch but never applies it to the selected checkout. The result points to `pyfixagent-apply`, not raw `git apply`. The apply CLI requires a clean Git workspace, reruns patch-format, path, suffix, forbidden-test, file-count, changed-line, and `git apply --check` validation, then prints the SHA-256 of the exact cleaned patch and exits without mutation. A second invocation must supply that exact digest through `--approve`; any patch or workspace change invalidates the approval. Applied changes remain uncommitted for normal human review.

## Workspace Safety Rules

The CLI inspects the selected Git workspace before running and refuses a dirty workspace by default. The starting revision and status are included in the trace. Direct library users may opt out for compatibility, but should do so only when they manage their own snapshot or worktree.

Patch and replacement modes share a tool-enforced edit policy:

- paths must be relative to the workspace
- paths must not escape the workspace
- only Python files are accepted
- tests are not modified
- optional allowed source roots are enforced
- file count and approximate changed-line budgets are enforced

Replacement mode additionally applies exact-content checks before modifying files:

- old text must match exactly once unless `start_line` disambiguates it

Patch mode validates patches with `git apply --check -` before applying them.

Generated patches and traces are stored under `outputs/`, which is ignored except for `.gitkeep` files.

## Failure Handling

PyFixAgent records failure type instead of flattening everything into a generic error. Iteration results can distinguish parse failures, apply failures, incomplete fixes, no progress, regressions, timeouts, and successful repairs.

When an edit applies but pytest still fails, `AttemptEvaluator` classifies the failure delta and `RetryPolicy` chooses the next workspace action. Partial progress is checkpointed for an incremental repair. No progress or a regression is rolled back in transactional mode before retrying with expanded context. In-place compatibility mode cannot provide rollback and records that the modified workspace was retained.

## Limitations

The current design is intentionally narrow. It depends on pytest as the validation signal, uses bounded static Python context, trusts a local workspace boundary, and does not attempt dynamic or cross-language repository understanding. These are prototype boundaries, not hidden production guarantees.
