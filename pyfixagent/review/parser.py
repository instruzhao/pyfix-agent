from __future__ import annotations

import json

from pyfixagent.review.contracts import ReviewOutcome, ReviewRisk


_VERDICTS = {"accept", "revise", "abstain"}
_SEVERITIES = {"blocking", "warning"}
_CATEGORIES = {
    "boundary",
    "representation",
    "numeric_precision",
    "ordering",
    "state_transition",
    "error_handling",
    "compatibility",
    "other",
}


class ReviewParseError(ValueError):
    pass


class ReviewParser:
    def __init__(
        self,
        max_risks: int = 5,
        max_text_chars: int = 3000,
        max_contracts: int = 3,
    ):
        self.max_risks = max(1, max_risks)
        self.max_text_chars = max(200, max_text_chars)
        self.max_contracts = max(1, max_contracts)

    def parse(self, raw: str) -> ReviewOutcome:
        text = raw.strip()
        if not text or text.startswith("```"):
            raise ReviewParseError("review response must be a JSON object without Markdown fences")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReviewParseError(f"invalid review JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise ReviewParseError("review response must be a JSON object")

        verdict = str(data.get("verdict") or "")
        if verdict not in _VERDICTS:
            raise ReviewParseError("verdict must be accept, revise, or abstain")
        summary = self._text(data.get("summary"), "summary")
        contracts = self._contracts(data.get("contracts", []))
        risks = self._risks(data.get("risks", []))
        feedback = self._text(data.get("repair_feedback", ""), "repair_feedback", required=False)
        return ReviewOutcome(
            verdict=verdict,
            summary=summary,
            contracts=tuple(contracts),
            risks=tuple(risks),
            repair_feedback=feedback,
        )

    def _contracts(self, value) -> list[dict]:
        if not isinstance(value, list):
            raise ReviewParseError("contracts must be an array")
        if len(value) > self.max_contracts:
            raise ReviewParseError(f"contracts exceeds configured maximum of {self.max_contracts}")
        contracts: list[dict] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ReviewParseError("each contract must be an object")
            contract_id = self._text(item.get("id"), "contract.id")
            if contract_id in seen:
                raise ReviewParseError(f"duplicate contract id: {contract_id}")
            seen.add(contract_id)
            contracts.append(
                {
                    "id": contract_id,
                    "statement": self._text(item.get("statement"), "contract.statement"),
                    "evidence": self._evidence(item.get("evidence", [])),
                    "confidence": self._confidence(item.get("confidence")),
                }
            )
        return contracts

    def _risks(self, value) -> list[ReviewRisk]:
        if not isinstance(value, list):
            raise ReviewParseError("risks must be an array")
        if len(value) > self.max_risks:
            raise ReviewParseError(f"risks exceeds configured maximum of {self.max_risks}")
        risks: list[ReviewRisk] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                raise ReviewParseError("each risk must be an object")
            risk_id = self._text(item.get("id"), "risk.id")
            if risk_id in seen:
                raise ReviewParseError(f"duplicate risk id: {risk_id}")
            seen.add(risk_id)
            severity = str(item.get("severity") or "")
            if severity not in _SEVERITIES:
                raise ReviewParseError("risk severity must be blocking or warning")
            category = str(item.get("category") or "other")
            if category not in _CATEGORIES:
                category = "other"
            evidence = self._evidence(item.get("evidence", []))
            counterexamples = self._counterexamples(item.get("counterexamples", []))
            if severity == "blocking" and (not evidence or not counterexamples):
                raise ReviewParseError(
                    f"blocking risk {risk_id} requires evidence and at least one counterexample"
                )
            risks.append(
                ReviewRisk(
                    risk_id=risk_id,
                    contract_id=str(item.get("contract_id")) if item.get("contract_id") else None,
                    category=category,
                    severity=severity,
                    reason=self._text(item.get("reason"), "risk.reason"),
                    evidence=tuple(evidence),
                    counterexamples=tuple(counterexamples),
                )
            )
        return risks

    def _evidence(self, value) -> list[dict]:
        if not isinstance(value, list):
            raise ReviewParseError("evidence must be an array")
        result: list[dict] = []
        for item in value[:10]:
            if not isinstance(item, dict) or not item.get("path"):
                raise ReviewParseError("evidence entries require path")
            line = item.get("line")
            if line is not None and (not isinstance(line, int) or line < 1):
                raise ReviewParseError("evidence line must be a positive integer")
            result.append({"path": str(item["path"]).replace("\\", "/"), "line": line})
        return result

    def _counterexamples(self, value) -> list[dict]:
        if not isinstance(value, list):
            raise ReviewParseError("counterexamples must be an array")
        result: list[dict] = []
        for item in value[:5]:
            if not isinstance(item, dict):
                raise ReviewParseError("counterexamples must contain objects")
            result.append(
                {
                    "input_shape": self._text(item.get("input_shape"), "counterexample.input_shape"),
                    "expected_property": self._text(
                        item.get("expected_property"), "counterexample.expected_property"
                    ),
                }
            )
        return result

    def _text(self, value, name: str, required: bool = True) -> str:
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ReviewParseError(f"{name} must be a string")
        text = value.strip()
        if required and not text:
            raise ReviewParseError(f"{name} is required")
        if len(text) > self.max_text_chars:
            raise ReviewParseError(f"{name} exceeds {self.max_text_chars} characters")
        return text

    @staticmethod
    def _confidence(value) -> float | None:
        if value is None:
            return None
        try:
            confidence = float(value)
        except (TypeError, ValueError) as exc:
            raise ReviewParseError("confidence must be numeric") from exc
        if not 0.0 <= confidence <= 1.0:
            raise ReviewParseError("confidence must be between 0 and 1")
        return confidence
