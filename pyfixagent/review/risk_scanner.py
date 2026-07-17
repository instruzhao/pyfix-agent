from __future__ import annotations

import ast
from dataclasses import dataclass


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
        return tuple(cues)

    @staticmethod
    def _add(cues: list[StructuralRiskCue], cue: StructuralRiskCue) -> None:
        if all(existing.cue_id != cue.cue_id for existing in cues):
            cues.append(cue)
