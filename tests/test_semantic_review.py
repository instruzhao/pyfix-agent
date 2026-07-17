import json
from pathlib import Path
import subprocess

import pytest

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.models.mock_model import MockModel
from pyfixagent.review.parser import ReviewParseError, ReviewParser
from pyfixagent.review.policy import ReviewPolicy
from pyfixagent.review.risk_scanner import StructuralRiskScanner
from pyfixagent.sandbox.local_sandbox import LocalSandbox


def init_workspace(tmp_path, source: str, test_source: str) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "paths.py").write_text(source, encoding="utf-8")
    (workspace / "test_paths.py").write_text(test_source, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True)
    return workspace


def accept_review() -> str:
    return json.dumps(
        {
            "verdict": "accept",
            "summary": "The candidate satisfies the supported contract.",
            "contracts": [
                {
                    "id": "C1",
                    "statement": "Replace only the final extension.",
                    "evidence": [{"path": "paths.py", "line": 1}],
                    "confidence": 0.9,
                }
            ],
            "risks": [],
            "repair_feedback": "",
        }
    )


def revise_review() -> str:
    return json.dumps(
        {
            "verdict": "revise",
            "summary": "The extension parameter is joined without normalization.",
            "contracts": [],
            "risks": [
                {
                    "id": "R1",
                    "category": "representation",
                    "severity": "blocking",
                    "reason": "A caller-provided leading separator is duplicated.",
                    "evidence": [{"path": "paths.py", "line": 3}],
                    "counterexamples": [
                        {
                            "input_shape": "extension already begins with a dot",
                            "expected_property": "the output contains one extension separator",
                        }
                    ],
                }
            ],
            "repair_feedback": "Normalize the extension parameter.",
        }
    )


def make_agent(workspace: Path, tmp_path: Path, outputs: list[str], **kwargs) -> DefaultAgent:
    return DefaultAgent(
        model=MockModel(outputs),
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        initial_mode="replacement",
        require_clean_workspace=True,
        isolate_workspace=True,
        semantic_review_enabled=True,
        **kwargs,
    )


def test_review_parser_requires_evidence_for_blocking_risk():
    data = json.loads(revise_review())
    data["risks"][0]["evidence"] = []

    with pytest.raises(ReviewParseError, match="requires evidence"):
        ReviewParser().parse(json.dumps(data))


def test_review_parser_enforces_compact_contract_budget():
    data = json.loads(accept_review())
    data["contracts"] = [
        {"id": f"C{index}", "statement": "contract", "evidence": [], "confidence": 0.5}
        for index in range(1, 5)
    ]

    with pytest.raises(ReviewParseError, match="contracts exceeds"):
        ReviewParser(max_contracts=3).parse(json.dumps(data))


def test_review_policy_only_revises_validated_blockers_within_budget():
    outcome = ReviewParser().parse(revise_review())
    policy = ReviewPolicy(max_semantic_revisions=1)

    assert policy.decide(outcome, revisions_used=0).action == "revise"
    exhausted = policy.decide(outcome, revisions_used=1)
    assert exhausted.action == "needs_review"
    assert exhausted.blocking_risk_ids == ("R1",)


def test_review_policy_promotes_evidence_based_warning_matching_structural_cue():
    data = json.loads(revise_review())
    data["verdict"] = "accept"
    data["risks"][0]["severity"] = "warning"
    outcome = ReviewParser().parse(json.dumps(data))

    decision = ReviewPolicy(max_semantic_revisions=1).decide(
        outcome,
        revisions_used=0,
        structural_cue_categories=("representation",),
    )

    assert decision.action == "revise"
    assert decision.blocking_risk_ids == ("R1",)
    assert "structural risk cue" in decision.reason


def test_review_policy_revises_unmitigated_deterministic_cue():
    outcome = ReviewParser().parse(accept_review())

    decision = ReviewPolicy(max_semantic_revisions=1).decide(
        outcome,
        revisions_used=0,
        structural_cue_ids=("delimiter_composition",),
    )

    assert decision.action == "revise"
    assert decision.blocking_risk_ids == ("cue:delimiter_composition",)


def test_structural_risk_scanner_emits_code_derived_generic_cues():
    scanner = StructuralRiskScanner()
    cues = scanner.scan(
        [
            'def replace(name, suffix):\n    stem = name.rsplit(".", 1)[0]\n    return f"{stem}.{suffix}"\n',
            'from decimal import Decimal\ndef money(value):\n    return value.quantize(Decimal("0.01"))\n',
        ]
    )

    assert [cue.cue_id for cue in cues] == ["delimiter_composition", "numeric_tie_breaking"]

    mitigated = scanner.scan(
        [
            'def replace(name, suffix):\n    stem = name.rsplit(".", 1)[0]\n'
            '    return f"{stem}.{suffix.lstrip(chr(46))}"\n',
            'from decimal import ROUND_HALF_UP, Decimal\n'
            'def money(value):\n    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)\n',
        ]
    )
    assert mitigated == ()


def test_structural_risk_scanner_requires_declared_positive_guards():
    scanner = StructuralRiskScanner()

    cues = scanner.scan(
        [
            "def schedule(attempt, base_seconds, max_seconds):\n"
            '    """Use a one-based attempt and positive delay bounds."""\n'
            "    if attempt < 1:\n"
            '        raise ValueError("attempt")\n'
            "    return min(base_seconds * attempt, max_seconds)\n"
        ]
    )

    assert [cue.cue_id for cue in cues] == ["declared_positive_precondition"]

    zero_still_allowed = scanner.scan(
        [
            "def schedule(attempt, base_seconds, max_seconds):\n"
            '    """Use a one-based attempt and positive delay bounds."""\n'
            "    if attempt < 1 or base_seconds < 0 or max_seconds < 0:\n"
            '        raise ValueError("inputs")\n'
            "    return min(base_seconds * attempt, max_seconds)\n"
        ]
    )

    assert [cue.cue_id for cue in zero_still_allowed] == ["declared_positive_precondition"]

    mitigated = scanner.scan(
        [
            "def schedule(attempt, base_seconds, max_seconds):\n"
            '    """Use a one-based attempt and positive delay bounds."""\n'
            "    if attempt < 1 or base_seconds <= 0 or max_seconds <= 0:\n"
            '        raise ValueError("positive inputs required")\n'
            "    return min(base_seconds * attempt, max_seconds)\n"
        ]
    )

    assert mitigated == ()


def test_visible_candidate_is_accepted_by_independent_reviewer(tmp_path):
    workspace = init_workspace(
        tmp_path,
        'def replace_extension(filename, extension):\n    return "broken"\n',
        'from paths import replace_extension\n\ndef test_replace():\n    assert replace_extension("a.txt", "csv") == "a.csv"\n',
    )
    repair = json.dumps(
        [
            {
                "path": "paths.py",
                "old": '    return "broken"',
                "new": (
                    '    return filename.rsplit(".", 1)[0] + "." + extension.lstrip(chr(46))'
                ),
            }
        ]
    )
    agent = make_agent(workspace, tmp_path, [repair, accept_review()], max_iterations=1)

    result = agent.run("Fix tests.")

    assert result.visible_success is True
    assert result.success is True
    assert result.acceptance_status == "accepted"
    assert len(result.reviews or []) == 1
    assert result.reviews[0].policy_action == "accept"
    assert result.iterations[0].workspace_action == "checkpointed_visible_candidate"
    assert result.candidate_patch == result.patch
    assert (workspace / "paths.py").read_text(encoding="utf-8").endswith('return "broken"\n')


def test_blocking_review_reenters_repair_then_accepts(tmp_path):
    workspace = init_workspace(
        tmp_path,
        'def replace_extension(filename, extension):\n    stem = filename.split(".")[0]\n    return f"{stem}.{extension}"\n',
        'from paths import replace_extension\n\ndef test_replace():\n    assert replace_extension("archive.tar.gz", "zip") == "archive.tar.zip"\n',
    )
    first = json.dumps(
        [{"path": "paths.py", "old": 'filename.split(".")[0]', "new": 'filename.rsplit(".", 1)[0]'}]
    )
    revision = json.dumps(
        [
            {
                "path": "paths.py",
                "old": 'return f"{stem}.{extension}"',
                "new": 'return f"{stem}.{extension.lstrip(chr(46))}"',
            }
        ]
    )
    agent = make_agent(
        workspace,
        tmp_path,
        [first, revise_review(), revision, accept_review()],
        max_iterations=2,
    )

    result = agent.run("Fix tests.")

    assert result.success is True
    assert result.acceptance_status == "accepted"
    assert result.semantic_revisions_used == 1
    assert len(result.reviews or []) == 2
    assert [review.policy_action for review in result.reviews] == ["revise", "accept"]
    assert result.iterations[1].trigger == "semantic_revision"
    assert result.iterations[1].review_feedback_ids == ["R1"]
    assert "lstrip" in result.patch


def test_invalid_review_fails_closed_but_exports_candidate(tmp_path):
    workspace = init_workspace(
        tmp_path,
        'def replace_extension(filename, extension):\n    return "broken"\n',
        'from paths import replace_extension\n\ndef test_replace():\n    assert replace_extension("a.txt", "csv") == "a.csv"\n',
    )
    repair = json.dumps(
        [
            {
                "path": "paths.py",
                "old": '    return "broken"',
                "new": '    return filename.rsplit(".", 1)[0] + "." + extension',
            }
        ]
    )
    agent = make_agent(
        workspace,
        tmp_path,
        [repair, "not json"],
        max_iterations=1,
        semantic_review_parse_retries=0,
    )

    result = agent.run("Fix tests.")

    assert result.visible_success is True
    assert result.success is False
    assert result.acceptance_status == "review_error"
    assert result.candidate_patch
    assert result.candidate_patch_path
    assert result.final_summary["status"] == "needs_review"
