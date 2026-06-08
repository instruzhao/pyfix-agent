import json

from pyfixagent.agent.prompts import REPLACEMENT_PROMPT
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

    assert data[0]["old"] == 'target_names = ["iris"]'
    assert "Current Python source files / selected context:" in prompt
    assert "selected relevant snippets" in prompt


def test_patch_eval_prompt_constrains_agent_output_format():
    assert "valid JSON object" in PATCH_OUTPUT_PROMPT
    assert '"patch"' in PATCH_OUTPUT_PROMPT
    assert "diff --git a/<path> b/<path>" in PATCH_OUTPUT_PROMPT
    assert "git apply --check" in PATCH_OUTPUT_PROMPT
    assert "old_count/new_count must match" in PATCH_OUTPUT_PROMPT
