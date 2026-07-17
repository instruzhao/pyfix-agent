from __future__ import annotations

import ast
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class StructuralRiskCue:
    cue_id: str
    category: str
    description: str


class StructuralRiskScanner:
    """Finds generic semantic risk shapes without inferring business outcomes."""

    def scan(self, sources: list[str]) -> tuple[StructuralRiskCue, ...]:
        cues: list[StructuralRiskCue] = []
        for source in sources:
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
            has_split = any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr in {"split", "rsplit", "partition", "rpartition"}
                for call in calls
            )
            has_boundary_normalization = any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr in {"lstrip", "strip", "removeprefix"}
                for call in calls
            )
            has_composition = any(
                isinstance(node, (ast.JoinedStr, ast.BinOp, ast.Call))
                and (
                    isinstance(node, ast.JoinedStr)
                    or isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                    or isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"format", "join"}
                )
                for node in ast.walk(tree)
            )
            if has_split and has_composition and not has_boundary_normalization:
                self._add(
                    cues,
                    StructuralRiskCue(
                        "delimiter_composition",
                        "representation",
                        "The candidate splits structured text and later composes output from caller-provided "
                        "fragments. Check absent, repeated, and already-present delimiters at every join boundary.",
                    ),
                )
            implicit_quantization = any(
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "quantize"
                and len(call.args) < 2
                and all(keyword.arg != "rounding" for keyword in call.keywords)
                for call in calls
            )
            has_round = any(isinstance(call.func, ast.Name) and call.func.id == "round" for call in calls)
            if implicit_quantization or has_round:
                self._add(
                    cues,
                    StructuralRiskCue(
                        "numeric_tie_breaking",
                        "numeric_precision",
                        "The candidate rounds or quantizes numeric values. Check aggregation order, rounding "
                        "stage, and whether the implicit halfway rule is supported by domain evidence.",
                    ),
                )
            if self._has_unenforced_positive_precondition(tree):
                self._add(
                    cues,
                    StructuralRiskCue(
                        "declared_positive_precondition",
                        "boundary",
                        "A changed public function explicitly declares positive input bounds, but not every "
                        "parameter has a visible non-positive-value guard. Check zero and negative values "
                        "for each declared input before accepting the candidate.",
                    ),
                )
        return tuple(cues)

    @classmethod
    def _has_unenforced_positive_precondition(cls, tree: ast.AST) -> bool:
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            docstring = ast.get_docstring(node, clean=True) or ""
            if not re.search(
                r"\bpositive(?:\s+[a-z_]+){0,2}\s+"
                r"(?:inputs?|arguments?|parameters?|bounds?|durations?|timeouts?|limits?|counts?|sizes?)\b",
                docstring.lower(),
            ):
                continue
            parameters = [
                argument.arg
                for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
                if argument.arg not in {"self", "cls"}
            ]
            if parameters and any(
                not cls._has_non_positive_guard(node, parameter)
                for parameter in parameters
            ):
                return True
        return False

    @staticmethod
    def _has_non_positive_guard(
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        parameter: str,
    ) -> bool:
        for branch in ast.walk(function):
            if not isinstance(branch, ast.If):
                continue
            if not any(isinstance(item, ast.Raise) for item in ast.walk(branch)):
                continue
            for comparison in ast.walk(branch.test):
                if not isinstance(comparison, ast.Compare) or len(comparison.ops) != 1:
                    continue
                left = comparison.left
                right = comparison.comparators[0]
                operator = comparison.ops[0]
                if (
                    isinstance(left, ast.Name)
                    and left.id == parameter
                    and isinstance(right, ast.Constant)
                    and isinstance(right.value, (int, float))
                    and (
                        isinstance(operator, ast.LtE) and right.value >= 0
                        or isinstance(operator, ast.Lt) and right.value > 0
                    )
                ):
                    return True
                if (
                    isinstance(right, ast.Name)
                    and right.id == parameter
                    and isinstance(left, ast.Constant)
                    and isinstance(left.value, (int, float))
                    and (
                        isinstance(operator, ast.GtE) and left.value >= 0
                        or isinstance(operator, ast.Gt) and left.value > 0
                    )
                ):
                    return True
        return False

    @staticmethod
    def _add(cues: list[StructuralRiskCue], cue: StructuralRiskCue) -> None:
        if all(existing.cue_id != cue.cue_id for existing in cues):
            cues.append(cue)
