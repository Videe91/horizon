from __future__ import annotations

from decimal import Decimal

import json

from horizon.investigation.providers.openai_responses import (
    _canonical_input_json,
)
from horizon.investigation.typed_planner_model import (
    SemanticGapTypedPlannerModelInvocation,
    SemanticGapTypedPlannerModelResult,
    SemanticGapTypedPlannerValidationResult,
    execute_semantic_gap_typed_planner,
    make_semantic_gap_typed_planner_invocation,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)


QUESTION = (
    "Which frozen source locations provide "
    "evidence for repository purpose?"
)


class FakePlanner:
    def __init__(
        self,
        result: SemanticGapTypedPlannerModelResult,
    ) -> None:
        self.result = result
        self.calls: list[
            SemanticGapTypedPlannerModelInvocation
        ] = []

    def invoke(
        self,
        invocation: SemanticGapTypedPlannerModelInvocation,
    ) -> SemanticGapTypedPlannerModelResult:
        self.calls.append(
            invocation
        )

        return self.result


def request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:r54"
        ),
        question=(
            "What is this repository's "
            "primary software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:r54"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:r54"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )


def proposal():
    value = request()

    return parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_INVESTIGATION",
            "question_id": (
                value.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": [
                QUESTION,
            ],
        },
    )


def planner_output(
    *,
    max_seconds: int,
) -> dict[str, object]:
    value = request()
    proposed = proposal()

    return {
        "proposal_id": (
            proposed.proposal_id
        ),
        "question_id": (
            value.question_id
        ),
        "bindings": [
            {
                "investigation_question": (
                    QUESTION
                ),
                "step_key": "read-purpose",
                "purpose": (
                    "Read exact frozen purpose evidence."
                ),
                "operation": {
                    "type": "READ_SOURCE",
                    "path": "pyproject.toml",
                    "start_line": 1,
                    "end_line": None,
                },
                "depends_on_keys": [],
                "expected_information": (
                    "Observed source evidence."
                ),
                "max_seconds": (
                    max_seconds
                ),
            },
        ],
    }


def invocation(
    *,
    max_plan_total_seconds: int,
):
    return (
        make_semantic_gap_typed_planner_invocation(
            request=request(),
            proposal=proposal(),
            instruction=(
                b"Translate only into legal typed "
                b"Horizon investigation operations."
            ),
            temperature=None,
            max_plan_total_seconds=(
                max_plan_total_seconds
            ),
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )


def test_plan_time_budget_is_immutable_invocation_authority():
    first = invocation(
        max_plan_total_seconds=120
    )

    second = invocation(
        max_plan_total_seconds=121
    )

    assert (
        first.max_plan_total_seconds
        == 120
    )

    assert (
        second.max_plan_total_seconds
        == 121
    )

    assert (
        first.canonical_input_hash
        != second.canonical_input_hash
    )

    assert (
        first.invocation_id
        != second.invocation_id
    )


def test_plan_time_budget_is_exposed_in_model_facing_input():
    value = invocation(
        max_plan_total_seconds=120
    )

    payload = json.loads(
        _canonical_input_json(
            value
        )
    )

    assert (
        payload["plan_budget"]
        == {
            "max_total_seconds": 120,
        }
    )


def test_plan_equal_to_aggregate_budget_is_valid():
    result = (
        SemanticGapTypedPlannerModelResult(
            provider="FAKE",
            model_id="fake-planner",
            output=planner_output(
                max_seconds=120
            ),
            input_tokens=1,
            output_tokens=1,
            cost_usd=Decimal(
                "0.001"
            ),
            api_request_id="req-r54-valid",
        )
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=FakePlanner(
                result
            ),
            request=request(),
            proposal=proposal(),
            instruction=b"sealed",
            temperature=None,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert (
        execution.run.validation_result
        is SemanticGapTypedPlannerValidationResult
        .VALID
    )

    assert execution.planner_output is not None


def test_over_aggregate_budget_is_invalid_before_plan_compilation():
    result = (
        SemanticGapTypedPlannerModelResult(
            provider="FAKE",
            model_id="fake-planner",
            output=planner_output(
                max_seconds=121
            ),
            input_tokens=1,
            output_tokens=1,
            cost_usd=Decimal(
                "0.001"
            ),
            api_request_id="req-r54-over-budget",
        )
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=FakePlanner(
                result
            ),
            request=request(),
            proposal=proposal(),
            instruction=b"sealed",
            temperature=None,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert (
        execution.run.validation_result
        is SemanticGapTypedPlannerValidationResult
        .INVALID
    )

    assert execution.planner_output is None

    assert (
        execution.run.rejection_reason
        == (
            "planner output aggregate max_seconds "
            "exceeds pre-registered plan time budget"
        )
    )
