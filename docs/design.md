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
- Docker sandbox
- GitHub PR or issue integration
- RAG or vector database
- multi-model voting
- automatic test generation
- AST editor
- complex import graph
- large benchmark platform
- broad refactoring of the repair loop

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

## Repair Modes

`replacement` is the default mode. It asks the model for a JSON array of old/new replacements. It is best suited to small, structured edits where exact matching can be validated before writing files.

`patch` is an optional mode. It asks the model for a unified diff and validates it with `git apply --check -` before applying it. Patch mode is useful for diff-style workflows, but model-generated hunk headers can be brittle. If patch validation repeatedly fails, the agent can fall back to replacement mode.

## Context Strategy

The default strategy is `traceback`. It is lightweight and based on pytest failure output. Selected context mainly comes from:

- failing test files
- traceback source files
- direct imports from failing tests

This is not a complete import graph, repository index, or RAG system. The strategy is meant to keep small demo prompts focused on files likely to explain the current failure.

The `full` strategy is available for small workspaces and includes all Python files in the workspace. It gives the model broader context, but it can include unrelated code and larger prompts.

The v0.2.2 benchmark compares these two context strategies on the resettable demo workspaces with `context.line_window` set to 25 for traceback snippets. It focuses on selected file counts, selected context characters, prompt characters, failure deltas, iteration results, and final pytest status.

## Structured Trace

Structured trace records each repair attempt as data instead of only text logs. It includes test summaries, failure deltas, selected context metadata, model output parsing, apply status, generated diffs, edit summaries, model call metadata, environment information, and final summary.

The trace is useful because it separates different failure modes:

- model output could not be parsed
- edit could not be applied
- pytest still failed after applying an edit
- a partial fix reduced the failure set
- a regression introduced new failures
- tests passed

## Sandbox Boundary

The local sandbox is a command runner with a command policy and subprocess timeout. It is not a production security sandbox.

It does not provide container isolation, filesystem isolation, network isolation, CPU limits, memory limits, or untrusted-code hardening. It is intended for local demos and trusted small workspaces.

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

When an edit applies but pytest still fails, the agent keeps the workspace in its current modified state and asks for an incremental repair against the new failure output. This behavior is recorded as an incremental repair strategy.

## Limitations

The current design is intentionally narrow. It depends on pytest as the validation signal, uses lightweight context selection, trusts a local workspace boundary, and does not attempt full repository understanding. These are prototype boundaries, not hidden production guarantees.
