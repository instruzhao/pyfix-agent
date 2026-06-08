# Benchmark

This document records a lightweight v0.2.2 comparison of PyFixAgent context strategies. It is meant to explain prompt/context behavior on the included demo workspaces, not to claim broad code repair ability.

## Benchmark Goal

The goal is to compare two context strategies on small Python workspaces:

- `full` context reads all Python files in the workspace.
- `traceback` context uses pytest failure output to select relevant failing tests, traceback source files, and direct test imports.

The core questions are:

- Does `traceback` reduce prompt size?
- Can `traceback` still complete the repair?
- Does structured trace explain each repair iteration?

This is not an academic benchmark, a large-scale evaluation, or a SWE-bench-style comparison.

## Benchmark Scope

The comparison uses the resettable demo workspaces committed in this repository:

- `workspaces/demo_project`
- `workspaces/sklearn_iris_tree_project`

Each run starts from the committed failing baseline using `scripts/reset_demo.py`. Temporary traces were generated under `outputs/traces/` and were used only to extract the metrics below.

## Compared Context Strategies

`traceback` is the default strategy. It selects a bounded set of snippets related to failing tests and traceback frames. It is lightweight and intentionally not RAG, not a vector search system, and not a complete dependency graph.

`full` includes every Python file in the workspace. In this document, `full` is the "all Python files" strategy.

Both strategies were run with:

- mode: `replacement`
- model: `openai/glm-5`
- temperature: `0.0`
- max tokens: `8192`
- traceback line window: `25`
- Python: `3.14.5`
- pytest: `9.0.3`

## Evaluation Metrics

Metrics come from structured trace JSON:

- `final_summary.initial_failed`
- `final_summary.final_failed`
- `final_summary.iterations_used`
- `final_summary.modified_files`
- `context.strategy`
- `context.stats.selected_file_count`
- `context.stats.selected_snippet_count`
- `context.stats.selected_context_chars`
- `context.stats.pytest_output_chars`
- `context.stats.prompt_chars`
- `failure_delta`
- `iteration_result.failure_type`
- `edit_summary`
- `model_call`

`total_prompt_chars` and `total_selected_context_chars` are summed from per-iteration trace fields.

## Results

| Workspace | Strategy | Mode | Initial Failed | Final Failed | Iterations | Success | Total Prompt Chars | Max Prompt Chars | Selected Files | Modified Files |
|---|---|---|---:|---:|---:|---|---:|---:|---:|---|
| demo_project | traceback | replacement | 3 | 0 | 2 | yes | 21298 | 12193 | 2, 2 | `src/billing.py` |
| demo_project | full | replacement | 3 | 0 | 1 | yes | 12396 | 12396 | 4 | `src/billing.py` |
| sklearn_iris_tree_project | traceback | replacement | 3 | 0 | 1 | yes | 21368 | 21368 | 6 | `ml_iris_tree/data.py`, `ml_iris_tree/model.py`, `ml_iris_tree/plot.py` |
| sklearn_iris_tree_project | full | replacement | 3 | 0 | 1 | yes | 22162 | 22162 | 9 | `ml_iris_tree/data.py`, `ml_iris_tree/model.py`, `ml_iris_tree/plot.py` |

## Per-iteration Results

| Workspace | Strategy | Iteration | Failed Before | Failed After | Failure Type | Prompt Chars | Selected Context Chars | Selected Files | Fixed | Remaining | New |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| demo_project | traceback | 1 | 3 | 1 | incomplete_fix | 12193 | 2980 | 2 | 2 | 1 | 0 |
| demo_project | traceback | 2 | 1 | 0 | success | 9105 | 2816 | 2 | 1 | 0 | 0 |
| demo_project | full | 1 | 3 | 0 | success | 12396 | 3362 | 4 | 3 | 0 | 0 |
| sklearn_iris_tree_project | traceback | 1 | 3 | 0 | success | 21368 | 4082 | 6 | 3 | 0 | 0 |
| sklearn_iris_tree_project | full | 1 | 3 | 0 | success | 22162 | 5315 | 9 | 3 | 0 | 0 |

## Per-case Notes

`demo_project` required two iterations with `traceback` in this run. The first iteration fixed two of three failing billing tests and left one money-rounding failure. The second iteration fixed the remaining failure. The structured trace captured this as `incomplete_fix` followed by `success`. The `full` strategy completed in one iteration in this run.

`sklearn_iris_tree_project` completed in one iteration for both strategies in this run. Both strategies modified the data, model, and plot modules and reduced the failure count from three to zero.

The local trace files used for this table were:

| Workspace | Strategy | Local Trace |
|---|---|---|
| demo_project | traceback | `outputs/traces/run_20260608_203936.json` |
| demo_project | full | `outputs/traces/run_20260608_204011.json` |
| sklearn_iris_tree_project | traceback | `outputs/traces/run_20260608_204106.json` |
| sklearn_iris_tree_project | full | `outputs/traces/run_20260608_204153.json` |

These trace files are generated artifacts and are not intended to be committed unless they are explicitly sanitized and moved under `docs/examples/traces/`.

## Observations

- `traceback` selected fewer files than `full` in both workspaces.
- `traceback` produced lower per-iteration prompt character counts in these runs.
- `full` included more complete workspace context, but also included files unrelated to the active failures.
- Both strategies reached passing tests for both demo workspaces in this run.
- Multi-round repair is not automatically a failure. In `demo_project`, the trace made partial progress visible through `failure_delta` and `iteration_result`.
- Structured trace made it possible to compare prompt size, selected files, failure deltas, modified files, and final test status without reading full pytest output.

## Limitations

- This is a two-workspace demo benchmark, not a statistically meaningful evaluation.
- The result depends on the configured model, prompt, provider behavior, and local environment.
- The benchmark does not compare models or repair algorithms.
- The benchmark does not test large repositories, flaky tests, hostile code, or production sandboxing.
- `traceback` was smaller in these runs, but this does not prove it is always better.
- `full` had more context in these runs, but this does not prove it is always more reliable.
