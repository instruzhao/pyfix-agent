from pyfixagent.agent.prompts import PATCH_PROMPT, REPLACEMENT_PROMPT
from pyfixagent.core.contracts import ApplyResult, ContextBundle, RepairMode


class PromptBuilder:
    """Builds mode-specific prompts and feedback without executing edits."""

    def build(
        self,
        *,
        mode: RepairMode,
        task: str,
        iteration: int,
        max_iterations: int,
        file_tree: str,
        initial_test_output: str,
        current_test_output: str,
        feedback: str,
        context: ContextBundle,
    ) -> str:
        template = REPLACEMENT_PROMPT if mode == "replacement" else PATCH_PROMPT
        prompt = template.format(
            task=task,
            iteration=iteration,
            max_iterations=max_iterations,
            file_tree=file_tree,
            initial_test_output=initial_test_output,
            current_test_output=current_test_output,
            feedback=feedback,
            python_files=context.rendered,
        )
        context.metadata["prompt_chars"] = len(prompt)
        context.metadata.setdefault("stats", {})["prompt_chars"] = len(prompt)
        return prompt

    @staticmethod
    def patch_failure(patch: str, error: str) -> str:
        return (
            "The previous model response could not be applied by git apply.\n"
            "Return a valid unified diff patch only. Do not use SEARCH/REPLACE blocks.\n"
            f"git apply error:\n{error}\n\n"
            f"Previous invalid patch:\n{patch}"
        )

    @staticmethod
    def patch_test_failure(test_output: str) -> str:
        return (
            "The previous patch was applied, but pytest still failed.\n"
            "Generate a new incremental unified diff patch against the current Python files.\n"
            f"Pytest output after previous patch:\n{test_output}"
        )

    @staticmethod
    def replacement_failure(raw_output: str, error: str) -> str:
        return (
            "The previous replacement response could not be parsed or applied.\n"
            "Use the failure reason below to fix the next JSON replacement attempt.\n"
            "If old text appears multiple times, either make old longer with surrounding context or include start_line.\n"
            "Return only a JSON array of objects with path, old, and new string fields.\n"
            "Do not return a unified diff patch or Markdown code block.\n"
            f"Replacement failure reason:\n{error}\n\n"
            f"Previous replacement response:\n{raw_output}"
        )

    @staticmethod
    def replacement_test_failure(test_output: str) -> str:
        return (
            "The previous replacement was applied, but pytest still failed.\n"
            "Return a new JSON array of small, exact old/new replacements against the current Python files.\n"
            f"Pytest output after previous replacement:\n{test_output}"
        )

    def apply_failure(self, result: ApplyResult) -> str:
        if result.mode == "replacement":
            return self.replacement_failure(result.raw_output, result.error or "")
        return self.patch_failure(result.cleaned_patch, result.error or "")

    @staticmethod
    def mode_switch_failure(result: ApplyResult, next_mode: RepairMode) -> str:
        return (
            f"The previous {result.mode} edit could not be applied, so the repair backend "
            f"is switching to {next_mode} mode.\n"
            "Follow the output rules for the current mode and use the current source context as truth.\n"
            f"Previous failure reason:\n{result.error or 'unknown apply failure'}"
        )

    @staticmethod
    def failure_action(result: ApplyResult) -> str:
        actions = {
            ("replacement", "parse"): "replacement parsing failed",
            ("replacement", "apply"): "replacement apply failed",
            ("replacement", "diff"): "replacement applied but git diff failed",
            ("patch", "check"): "patch check failed",
            ("patch", "apply"): "patch failed",
            ("patch", "diff"): "patch applied but git diff failed",
        }
        return actions.get((result.mode, result.failure_stage), "edit apply failed")
