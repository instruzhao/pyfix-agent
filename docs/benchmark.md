# Benchmark

This document records a lightweight demo benchmark for PyFixAgent v0.2.2. It is meant to make the project easier to inspect, not to claim broad repair ability.

## Benchmark Scope

The benchmark covers small local Python workspaces committed in this repository:

- `workspaces/demo_project`
- `workspaces/sklearn_iris_tree_project`

The goal is to show that PyFixAgent can run a pytest-driven repair loop, select traceback-related context, apply small edits, rerun tests, and record structured trace data. This is not an academic benchmark, a large-scale evaluation, or a SWE-bench-style comparison.

## Cases

`demo_project` is a small billing/calculator example. The failing tests focus on money rounding, discount-before-tax behavior, shipping threshold logic, and line item validation.

`sklearn_iris_tree_project` is a small scikit-learn iris classifier example. The failing tests focus on data loading metadata, label prediction shape, and saving a confusion matrix image.

## Metrics

The table uses lightweight, locally reproducible metrics:

- case and workspace
- repair mode
- context strategy
- initial pytest result
- final pytest result
- observed repair iterations in local demo runs
- selected files from first traceback-context pass
- first prompt size in characters
- modified files
- final status

The first prompt metrics were computed with the existing context builder and replacement prompt. The final results were verified by running `python -m pytest -p no:cacheprovider -q` from each workspace after the representative repairs were applied.

## Results

| Case | Workspace | Mode | Context Strategy | Initial Result | Final Result | Iterations | Selected Files | First Prompt Chars | Modified Files | Final Status |
|---|---|---|---|---|---|---:|---:|---:|---|---|
| demo_project | `workspaces/demo_project` | replacement | traceback | 3 failed, 3 passed | 6 passed | 2 | 2 | 12029 | `src/billing.py` | passed |
| sklearn_iris_tree_project | `workspaces/sklearn_iris_tree_project` | replacement | traceback | 3 failed, 3 passed | 6 passed | 2 | 6 | 21426 | `ml_iris_tree/data.py`, `ml_iris_tree/model.py`, `ml_iris_tree/plot.py` | passed |

Selected files in the first context pass:

| Case | Selected Files |
|---|---|
| demo_project | `tests/test_billing.py`, `src/billing.py` |
| sklearn_iris_tree_project | `tests/test_data.py`, `tests/test_model.py`, `tests/test_plot.py`, `ml_iris_tree/plot.py`, `ml_iris_tree/data.py`, `ml_iris_tree/model.py` |

## Observations

- Both cases start from a failing committed baseline and can be repaired to a passing pytest state.
- Traceback context selects the failing tests and the most relevant source files instead of sending every Python file.
- The selected context is small enough for the demo projects while still exposing the code needed for the repair.
- Structured trace fields make it possible to inspect each iteration through summaries, deltas, apply status, generated diffs, and final status.
- Multi-round repair can converge from failed to passed without adding a larger benchmark system.

## Limitations

- This benchmark has only two small local demo projects.
- The results are intended for project demonstration, not statistical claims.
- The benchmark does not measure general coding ability.
- The benchmark does not compare against other agents or models.
- The benchmark does not include hostile code, flaky tests, large repositories, or production sandboxing.
- LLM behavior may vary by model, prompt, and provider settings.
