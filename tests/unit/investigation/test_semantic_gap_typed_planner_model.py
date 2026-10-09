from __future__ import annotations

from decimal import Decimal

import pytest

from horizon.investigation.typed_planner_model import (
    SemanticGapTypedPlannerModelError,
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


class FakeTypedPlannerModel:
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
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary software purpose?"
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
            "investigation-request:test"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
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
                (
                    "Which frozen source locations provide "
                    "evidence for repository purpose?"
                ),
            ],
        },
    )


def valid_output() -> dict[str, object]:
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
                    "Which frozen source locations provide "
                    "evidence for repository purpose?"
                ),
                "step_key": (
                    "find-purpose-evidence"
                ),
                "purpose": (
                    "Locate source relevant to repository purpose."
                ),
                "operation": {
                    "type": "SEARCH_SOURCE",
                    "query": "flow",
                    "path_prefix": "src/acme",
                },
                "depends_on_keys": [],
                "expected_information": (
                    "Observed frozen source locations."
                ),
                "max_seconds": 20,
            },
        ],
    }


def test_invocation_is_deterministic_and_records_sealed_contract() -> None:
    value = request()
    proposed = proposal()

    first = (
        make_semantic_gap_typed_planner_invocation(
            request=value,
            proposal=proposed,
            instruction=(
                b"Translate only into legal typed "
                b"Horizon investigation operations."
            ),
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    second = (
        make_semantic_gap_typed_planner_invocation(
            request=value,
            proposal=proposed,
            instruction=(
                b"Translate only into legal typed "
                b"Horizon investigation operations."
            ),
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert first == second

    assert first.invocation_id.startswith(
        "semantic-gap-typed-planner-invocation:"
    )

    assert first.instruction_hash.startswith(
        "sha256:"
    )

    assert first.schema_hash.startswith(
        "sha256:"
    )

    assert first.canonical_input_hash.startswith(
        "sha256:"
    )


def test_changed_instruction_changes_invocation_identity() -> None:
    value = request()
    proposed = proposal()

    first = (
        make_semantic_gap_typed_planner_invocation(
            request=value,
            proposal=proposed,
            instruction=b"instruction one",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    second = (
        make_semantic_gap_typed_planner_invocation(
            request=value,
            proposal=proposed,
            instruction=b"instruction two",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert (
        first.instruction_hash
        != second.instruction_hash
    )

    assert (
        first.invocation_id
        != second.invocation_id
    )


def test_valid_fake_model_executes_once_and_returns_validated_output() -> None:
    value = request()
    proposed = proposal()

    result = (
        SemanticGapTypedPlannerModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-typed-planner-v1",
            output=valid_output(),
            input_tokens=500,
            output_tokens=120,
            cost_usd=Decimal(
                "0.020000"
            ),
            api_request_id=(
                "fake-planner-request-1"
            ),
        )
    )

    model = FakeTypedPlannerModel(
        result
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=model,
            request=value,
            proposal=proposed,
            instruction=(
                b"Translate the accepted investigation "
                b"proposal into legal typed operations."
            ),
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert len(
        model.calls
    ) == 1

    assert execution.result is result

    assert execution.planner_output is not None

    assert execution.run.validation_result is (
        SemanticGapTypedPlannerValidationResult
        .VALID
    )

    assert execution.run.rejection_reason is None

    assert execution.run.provider == (
        "FAKE_PROVIDER"
    )

    assert execution.run.model_id == (
        "fake-typed-planner-v1"
    )

    assert execution.run.input_tokens == 500
    assert execution.run.output_tokens == 120

    assert execution.run.cost_usd == (
        Decimal(
            "0.020000"
        )
    )

    assert execution.run.cost_cap_usd == (
        Decimal(
            "0.100000"
        )
    )


def test_invalid_output_is_recorded_and_not_returned_as_planner_output() -> None:
    value = request()
    proposed = proposal()

    invalid = valid_output()

    invalid[
        "bindings"
    ][0][
        "operation"
    ][
        "command"
    ] = "arbitrary-command"

    model = FakeTypedPlannerModel(
        SemanticGapTypedPlannerModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-typed-planner-v1",
            output=invalid,
            input_tokens=400,
            output_tokens=90,
            cost_usd=Decimal(
                "0.010000"
            ),
            api_request_id=(
                "fake-invalid"
            ),
        )
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=model,
            request=value,
            proposal=proposed,
            instruction=b"sealed instruction",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert len(
        model.calls
    ) == 1

    assert execution.planner_output is None

    assert execution.run.validation_result is (
        SemanticGapTypedPlannerValidationResult
        .INVALID
    )

    assert execution.run.rejection_reason is not None

    assert (
        "planner output validation failed"
        in execution.run.rejection_reason
    )


def test_invented_proposal_identity_is_invalid() -> None:
    value = request()
    proposed = proposal()

    invalid = valid_output()

    invalid[
        "proposal_id"
    ] = (
        "investigation-proposal:invented"
    )

    model = FakeTypedPlannerModel(
        SemanticGapTypedPlannerModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-typed-planner-v1",
            output=invalid,
            input_tokens=400,
            output_tokens=80,
            cost_usd=Decimal(
                "0.010000"
            ),
            api_request_id=None,
        )
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=model,
            request=value,
            proposal=proposed,
            instruction=b"sealed instruction",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert execution.planner_output is None

    assert execution.run.validation_result is (
        SemanticGapTypedPlannerValidationResult
        .INVALID
    )


def test_over_cap_result_is_retained_but_invalid() -> None:
    value = request()
    proposed = proposal()

    model = FakeTypedPlannerModel(
        SemanticGapTypedPlannerModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-typed-planner-v1",
            output=valid_output(),
            input_tokens=1000,
            output_tokens=200,
            cost_usd=Decimal(
                "0.110000"
            ),
            api_request_id=(
                "fake-over-cap"
            ),
        )
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=model,
            request=value,
            proposal=proposed,
            instruction=b"sealed instruction",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert len(
        model.calls
    ) == 1

    assert execution.planner_output is None

    assert execution.run.validation_result is (
        SemanticGapTypedPlannerValidationResult
        .INVALID
    )

    assert execution.run.cost_usd == (
        Decimal(
            "0.110000"
        )
    )

    assert execution.run.rejection_reason == (
        "actual model cost exceeded "
        "pre-registered cost cap"
    )


def test_invalid_output_is_not_silently_retried() -> None:
    value = request()
    proposed = proposal()

    model = FakeTypedPlannerModel(
        SemanticGapTypedPlannerModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-typed-planner-v1",
            output={
                "proposal_id": (
                    proposed.proposal_id
                ),
                "question_id": (
                    value.question_id
                ),
                "bindings": [],
            },
            input_tokens=300,
            output_tokens=50,
            cost_usd=Decimal(
                "0.005000"
            ),
            api_request_id=(
                "fake-no-retry"
            ),
        )
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=model,
            request=value,
            proposal=proposed,
            instruction=b"sealed instruction",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert len(
        model.calls
    ) == 1

    assert execution.planner_output is None

    assert execution.run.validation_result is (
        SemanticGapTypedPlannerValidationResult
        .INVALID
    )


def test_model_result_records_exact_provider_provenance() -> None:
    value = request()
    proposed = proposal()

    result = (
        SemanticGapTypedPlannerModelResult(
            provider="OPENAI",
            model_id="planner-model-exact",
            output=valid_output(),
            input_tokens=321,
            output_tokens=123,
            cost_usd=Decimal(
                "0.012345"
            ),
            api_request_id=(
                "provider-request-xyz"
            ),
        )
    )

    model = FakeTypedPlannerModel(
        result
    )

    execution = (
        execute_semantic_gap_typed_planner(
            model=model,
            request=value,
            proposal=proposed,
            instruction=b"sealed instruction",
            temperature=None,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    run = execution.run

    assert run.provider == "OPENAI"

    assert run.model_id == (
        "planner-model-exact"
    )

    assert run.temperature is None

    assert run.input_tokens == 321
    assert run.output_tokens == 123

    assert run.api_request_id == (
        "provider-request-xyz"
    )

    assert run.cost_usd == (
        Decimal(
            "0.012345"
        )
    )


@pytest.mark.parametrize(
    "cost_cap",
    (
        Decimal(
            "0"
        ),
        Decimal(
            "-0.01"
        ),
    ),
)
def test_invocation_requires_positive_cost_cap(
    cost_cap: Decimal,
) -> None:
    with pytest.raises(
        SemanticGapTypedPlannerModelError,
        match="cost cap",
    ):
        make_semantic_gap_typed_planner_invocation(
            request=request(),
            proposal=proposal(),
            instruction=b"sealed",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=cost_cap,
        )


def test_empty_instruction_is_rejected() -> None:
    with pytest.raises(
        SemanticGapTypedPlannerModelError,
        match="instruction",
    ):
        make_semantic_gap_typed_planner_invocation(
            request=request(),
            proposal=proposal(),
            instruction=b"",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )


def test_model_boundary_does_not_create_world_model_truth() -> None:
    from horizon.claims.evidence_backed import (
        EvidenceBackedClaim,
    )
    from horizon.claims.epistemic import (
        EpistemicAssessment,
    )
    from horizon.world_model.assertion import (
        WorldModelAssertion,
    )

    value = request()
    proposed = proposal()

    execution = (
        execute_semantic_gap_typed_planner(
            model=FakeTypedPlannerModel(
                SemanticGapTypedPlannerModelResult(
                    provider="FAKE",
                    model_id="fake",
                    output=valid_output(),
                    input_tokens=1,
                    output_tokens=1,
                    cost_usd=Decimal(
                        "0.001"
                    ),
                    api_request_id=None,
                )
            ),
            request=value,
            proposal=proposed,
            instruction=b"sealed",
            temperature=0.0,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100"
            ),
        )
    )

    for candidate in (
        execution.invocation,
        execution.result,
        execution.planner_output,
        execution.run,
    ):
        assert not isinstance(
            candidate,
            EvidenceBackedClaim,
        )

        assert not isinstance(
            candidate,
            EpistemicAssessment,
        )

        assert not isinstance(
            candidate,
            WorldModelAssertion,
        )
