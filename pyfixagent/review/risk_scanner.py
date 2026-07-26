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
            if (has_split and has_composition and not has_boundary_normalization) or self._has_repeat_delimiter_risk(tree):
                self._add(
                    cues,
                    StructuralRiskCue(
                        "delimiter_composition",
                        "representation",
                        "The candidate splits structured text and later composes output from caller-provided "
                        "fragments. Check absent, repeated, and already-present delimiters at every join boundary. "
                        "In particular, a regex such as re.sub(\"[^a-z0-9-]+\", \"-\", text) excludes the \"-\" "
                        "replacement from the matched class, so pre-existing separators survive and can repeat "
                        "(\"a -- b\" -> \"a----b\"); confirm runs of the delimiter are collapsed to one.",
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

    @classmethod
    def _has_repeat_delimiter_risk(cls, tree: ast.AST) -> bool:
        """Detect a normalization that inserts a delimiter which can then repeat.

        Fires when a ``re.sub``/``re.subn`` uses a negated character class such as
        ``[^a-z0-9-]+`` whose excluded set contains the single-character replacement
        delimiter. Because the delimiter is excluded from the matched class, separators
        already present in the input survive the substitution and run together with the
        newly inserted ones (the classic slugify bug: ``"a -- b" -> "a----b"``). A later
        collapse step (``re.sub("-+", "-", ...)`` or ``str.replace("--", "-")``) clears
        the risk, as does a correct class that does not exclude the delimiter
        (``re.sub("[^a-z0-9]+", "-", ...)``).
        """
        inserted_delimiters: list[str] = []
        has_collapse = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            attr = node.func.attr
            if attr in {"sub", "subn", "split"} and cls._is_re_func(node.func):
                pattern = cls._const_str(node.args[0]) if node.args else None
                if pattern is None:
                    continue
                excluded = cls._negated_class_chars(pattern)
                if excluded is not None:
                    if attr in {"sub", "subn"} and len(node.args) > 1:
                        repl = cls._const_str(node.args[1])
                        if repl is not None and len(repl) == 1 and cls._char_in_excluded(repl, excluded):
                            inserted_delimiters.append(repl)
                elif cls._is_collapse_pattern(pattern):
                    has_collapse = True
            elif attr == "replace" and len(node.args) >= 2:
                old = cls._const_str(node.args[0])
                new = cls._const_str(node.args[1])
                if old and new and len(old) > len(new) and set(new) <= set(old):
                    has_collapse = True
        return bool(inserted_delimiters) and not has_collapse

    @staticmethod
    def _is_re_func(func: ast.Attribute) -> bool:
        return isinstance(func.value, ast.Name) and func.value.id == "re"

    @staticmethod
    def _const_str(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _negated_class_chars(pattern: str) -> str | None:
        match = re.match(r"^\s*\[\^([^\]]*)\]\s*[+*?]?\s*$", pattern)
        return match.group(1) if match else None

    @staticmethod
    def _is_collapse_pattern(pattern: str) -> bool:
        if pattern.lstrip().startswith("[^"):
            return False
        if re.match(r"^\s*(?:\\.|\.|\[[^\]]*\]|[^\\\s])[+*]\??\s*$", pattern):
            return True
        return bool(re.search(r"\{2,\}|\{2\}", pattern))

    @staticmethod
    def _char_in_excluded(ch: str, spec: str) -> bool:
        i = 0
        n = len(spec)
        while i < n:
            c = spec[i]
            if c == "\\" and i + 1 < n:
                nxt = spec[i + 1]
                if nxt == ch:
                    return True
                if nxt == "d" and ch.isdigit():
                    return True
                if nxt == "s" and ch.isspace():
                    return True
                if nxt == "w" and (ch.isalnum() or ch == "_"):
                    return True
                i += 2
                continue
            if i + 2 < n and spec[i + 1] == "-":
                if c <= ch <= spec[i + 2]:
                    return True
                i += 3
                continue
            if c == ch:
                return True
            i += 1
        return False

    @staticmethod
    def _add(cues: list[StructuralRiskCue], cue: StructuralRiskCue) -> None:
        if all(existing.cue_id != cue.cue_id for existing in cues):
            cues.append(cue)
