import json

from pyfixagent.agent.prompts import REPLACEMENT_PROMPT
from pyfixagent.repair.prompting import PromptBuilder
from patch_eval.prompts import PATCH_OUTPUT_PROMPT


def test_replacement_prompt_example_is_valid_json():
    prompt = REPLACEMENT_PROMPT.format(
        task="Fix tests.",
        iteration=1,
        max_iterations=3,
        file_tree="app.py",
        initial_test_output="initial",
        current_test_output="current",
        feedback="No previous attempt.",
        python_files="--- app.py ---\nVALUE = 1\n",
    )
    example = prompt.split("Example JSON array:", 1)[1].strip()

    data = json.loads(example)

    assert data[0]["path"] == "package/module.py"
    assert data[0]["old"] == "return incorrect_value"
    assert data[0]["new"] == "return correct_value"
    assert "Current Python source files / selected context:" in prompt
    assert "selected relevant snippets" in prompt
    assert "canonical output representation" in prompt
    assert "emit the marker exactly once" in prompt
    assert "f(f(x)) == f(x)" in prompt


def test_patch_eval_prompt_constrains_agent_output_format():
    assert "valid JSON object" in PATCH_OUTPUT_PROMPT
    assert '"patch"' in PATCH_OUTPUT_PROMPT
    assert "diff --git a/<path> b/<path>" in PATCH_OUTPUT_PROMPT
    assert "git apply --check" in PATCH_OUTPUT_PROMPT
    assert "old_count/new_count must match" in PATCH_OUTPUT_PROMPT


def test_semantic_retry_feedback_distinguishes_rollback_and_failure_delta():
    feedback = PromptBuilder.semantic_test_failure(
        mode="replacement",
        failure_type="regression",
        delta={"fixed": ["test_old"], "remaining": [], "new": ["test_new"]},
        test_output="1 failed",
        rolled_back=True,
        context_expansion_level=1,
    )

    assert "rolled back" in feedback
    assert "test_old" in feedback
    assert "test_new" in feedback
    assert "Context expansion level for the next attempt: 1" in feedback
    assert "JSON array" in feedback
