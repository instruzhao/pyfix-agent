REVIEW_SYSTEM_PROMPT = """You are an independent semantic reviewer for a Python repair candidate.
Return exactly one JSON object matching the requested schema.
Do not return Markdown, code edits, patches, replacement blocks, or text outside JSON.
Do not invent requirements. A missing test alone is not a blocking defect.
Only report a blocking risk when it is supported by supplied code evidence and a concrete behavioral counterexample."""


REVIEW_PROMPT = """Review this candidate after all visible tests passed.

Task:
{task}

Review cycle:
{review_index}

Visible pytest output:
{visible_test_output}

Aggregate candidate diff:
{candidate_diff}

Changed source and visible-test context:
{context}

Infer the narrowest behavioral contract supported by names, signatures, types, docstrings, callers,
visible tests, current code, and the aggregate diff. Check whether the candidate generalizes beyond
the exact visible examples. Consider boundary values, equivalent input representations, numeric
precision, ordering, state transitions, errors, and compatibility only when relevant to supplied evidence.
Treat explicit docstring preconditions as contracts: enumerate them and verify that the implementation
enforces each one. Do not silently narrow or omit a documented input constraint.

Apply these common domain conventions as things to verify against the task wording and supplied code.
Each is only a question to investigate; report a blocking risk only when the task/domain actually
requires the convention and the candidate visibly violates it:
- Rounding and tie-breaking: when the task involves proration, allocation, distribution, or splitting
  a quantity that must preserve a fixed total, a naive ROUND_HALF_UP can misallocate exact halves;
  check whether banker's rounding (decimal.ROUND_HALF_EVEN) or a largest-remainder scheme is required.
  For currency, tax, or invoice display, ROUND_HALF_UP is normally correct. Decide from the task, not
  from assumption.
- Normalized identifiers and slugs: runs of separators or whitespace normally collapse to a single
  delimiter, with leading and trailing delimiters trimmed. A regex class that excludes the delimiter
  (for example "[^a-z0-9-]" replaced by "-") leaves pre-existing delimiters to repeat, producing runs
  such as "----". Check whether repeated separators survive.
- Configuration-style numeric parameters (delays, timeouts, retries, sizes, counts, rates): such values
  normally must be positive or otherwise valid; check whether non-positive or malformed inputs are
  rejected with an explicit error instead of being silently coerced or accepted.
- Chain, linked-list, graph, or rotation traversal: check whether cycles are detected and surfaced as an
  explicit error rather than silently broken out of or returned as a partial result, unless the task
  defines a different cycle policy.

Accept a small repair when there is no concrete supported blocking defect. Do not reject merely because
additional tests could exist. Never assume benchmark holdouts or hidden requirements.

Before accepting, evaluate every supplied static semantic risk cue against the changed function and record
any supported defect as a risk. A cue is only a question to investigate, never proof of a requirement.
Silently challenge each changed public function with at least three materially different input shapes,
including caller-provided fragments that are already normalized when the function composes delimiters,
and halfway values when the candidate performs numeric rounding or quantization.

Keep the response compact: at most three contracts, at most three risks, one evidence location per
contract/risk unless a second location is essential, and one counterexample per risk. Keep every prose
field under 240 characters. Do the analysis silently and return only the decision JSON.

Return this JSON shape:
{{
  "verdict": "accept | revise | abstain",
  "summary": "short conclusion",
  "contracts": [
    {{
      "id": "C1",
      "statement": "inferred contract",
      "evidence": [{{"path": "relative/path.py", "line": 1}}],
      "confidence": 0.8
    }}
  ],
  "risks": [
    {{
      "id": "R1",
      "contract_id": "C1",
      "category": "boundary | representation | numeric_precision | ordering | state_transition | error_handling | compatibility | other",
      "severity": "blocking | warning",
      "reason": "evidence-based reason",
      "evidence": [{{"path": "relative/path.py", "line": 1}}],
      "counterexamples": [
        {{"input_shape": "input category", "expected_property": "required property"}}
      ]
    }}
  ],
  "repair_feedback": "short actionable feedback, or empty string"
}}
"""


def build_review_prompt(request) -> str:
    return REVIEW_PROMPT.format(
        task=request.task,
        review_index=request.review_index,
        visible_test_output=request.visible_test_output,
        candidate_diff=request.candidate_diff,
        context=request.context.rendered,
    )


def build_parse_retry_prompt(prompt: str, error: str) -> str:
    return (
        prompt
        + "\n\nYour previous review response was invalid. Return only a corrected JSON object.\n"
        + f"Validation error: {error}"
    )
