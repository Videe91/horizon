from __future__ import annotations

from decimal import Decimal

import pytest

from horizon.investigator.execution import (
    execute_investigation,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.model import (
    InvestigatorModelInvocation,
    InvestigatorModelResult,
    ModelRunValidationResult,
)
from horizon.investigator.proposal import (
    InvestigationProposalError,
    InvestigationProposalKind,
    parse_investigation_proposal,
)
from horizon.investigator.providers.openai_responses import (
    _proposal_schema,
)


class FakeSemanticGapModel:
    def __init__(
        self,
        result: InvestigatorModelResult,
    ) -> None:
        self.result = result

        self.calls: list[
            InvestigatorModelInvocation
        ] = []

    def invoke(
        self,
        invocation: InvestigatorModelInvocation,
    ) -> InvestigatorModelResult:
        self.calls.append(
            invocation
        )

        return self.result


def semantic_gap_request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary software purpose, "
            "and what evidence establishes it?"
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
            "investigation-request:semantic-gap-test"
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


def conflict_request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "world-model-open-question:test"
        ),
        question=(
            "Who owns responsibility for the test behavior?"
        ),
        relationship_id=(
            "world-model-relationship:test"
        ),
        relationship_kind="CONFLICT",
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:conflict-test"
        ),
        origin=(
            InvestigationRequestOrigin
            .WORLD_MODEL_CONFLICT
        ),
        semantic_gap_id=None,
        semantic_gap_section=None,
    )


def common(
    request: InvestigationRequest,
) -> dict[str, object]:
    return {
        "question_id": (
            request.question_id
        ),
        "relationship_id": (
            request.relationship_id
        ),
        "assertion_ids": list(
            request.assertion_ids
        ),
        "claim_ids": list(
            request.claim_ids
        ),
        "assessment_ids": list(
            request.assessment_ids
        ),
        "evidence_reference_ids": list(
            request.evidence_reference_ids
        ),
    }


def test_semantic_gap_can_propose_investigation_without_fake_relationship() -> None:
    request = semantic_gap_request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **common(
            request
        ),
        "investigation_questions": [
            (
                "Which source paths provide evidence "
                "for the repository's primary purpose?"
            ),
        ],
    }

    proposal = parse_investigation_proposal(
        request,
        raw,
    )

    assert proposal.kind is (
        InvestigationProposalKind
        .PROPOSE_INVESTIGATION
    )

    assert proposal.question_id == (
        request.question_id
    )

    assert proposal.relationship_id is None

    assert proposal.investigation_questions == (
        (
            "Which source paths provide evidence "
            "for the repository's primary purpose?"
        ),
    )


def test_semantic_gap_can_propose_hypothesis_without_promoting_truth() -> None:
    request = semantic_gap_request()

    proposal = parse_investigation_proposal(
        request,
        {
            "type": "PROPOSE_HYPOTHESIS",
            **common(
                request
            ),
            "hypothesis": (
                "The repository may implement "
                "workflow orchestration."
            ),
            "test_questions": [
                (
                    "Which runtime entry points and "
                    "execution paths support that interpretation?"
                ),
            ],
        },
    )

    assert proposal.kind is (
        InvestigationProposalKind
        .PROPOSE_HYPOTHESIS
    )

    assert proposal.relationship_id is None

    assert proposal.hypothesis == (
        "The repository may implement "
        "workflow orchestration."
    )


def test_empty_semantic_gap_context_can_still_request_investigation() -> None:
    request = semantic_gap_request()

    assert request.assertion_ids == ()
    assert request.claim_ids == ()
    assert request.assessment_ids == ()
    assert request.evidence_reference_ids == ()

    proposal = parse_investigation_proposal(
        request,
        {
            "type": "PROPOSE_INVESTIGATION",
            **common(
                request
            ),
            "investigation_questions": [
                (
                    "Which repository sources should "
                    "be inspected first?"
                ),
            ],
        },
    )

    assert proposal.assertion_ids == ()
    assert proposal.claim_ids == ()
    assert proposal.assessment_ids == ()
    assert (
        proposal.evidence_reference_ids
        == ()
    )


def test_semantic_gap_rejects_invented_relationship_identity() -> None:
    request = semantic_gap_request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **common(
            request
        ),
        "relationship_id": (
            "world-model-relationship:invented"
        ),
        "investigation_questions": [
            "What evidence should be gathered?",
        ],
    }

    with pytest.raises(
        InvestigationProposalError,
        match="relationship",
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


def test_conflict_request_still_requires_exact_relationship_identity() -> None:
    request = conflict_request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **common(
            request
        ),
        "relationship_id": None,
        "investigation_questions": [
            "What evidence should resolve the conflict?",
        ],
    }

    with pytest.raises(
        InvestigationProposalError,
        match="relationship",
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


def test_semantic_gap_still_rejects_unrestricted_answer_field() -> None:
    request = semantic_gap_request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **common(
            request
        ),
        "investigation_questions": [
            "What evidence should be gathered?",
        ],
        "answer": (
            "This repository definitely owns everything."
        ),
    }

    with pytest.raises(
        InvestigationProposalError,
        match="strict schema",
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


def test_four_action_vocabulary_is_unchanged() -> None:
    assert tuple(
        value.value
        for value
        in InvestigationProposalKind
    ) == (
        "PROPOSE_INVESTIGATION",
        "PROPOSE_HYPOTHESIS",
        "REFINE_OBJECT",
        "DECLARE_INSUFFICIENT_EVIDENCE",
    )


def test_existing_execution_boundary_accepts_semantic_gap_proposal() -> None:
    request = semantic_gap_request()

    result = InvestigatorModelResult(
        provider="FAKE_PROVIDER",
        model_id="fake-semantic-investigator-v1",
        output={
            "type": "PROPOSE_INVESTIGATION",
            **common(
                request
            ),
            "investigation_questions": [
                (
                    "Which source paths establish "
                    "the repository purpose?"
                ),
            ],
        },
        input_tokens=100,
        output_tokens=30,
        cost_usd=Decimal(
            "0.001000"
        ),
        api_request_id=(
            "fake-semantic-gap-request-1"
        ),
    )

    model = FakeSemanticGapModel(
        result
    )

    execution = execute_investigation(
        model=model,
        request=request,
        instruction=(
            b"AI proposes. Horizon verifies."
        ),
        temperature=0.0,
        cost_cap_usd=Decimal(
            "0.100000"
        ),
    )

    assert len(
        model.calls
    ) == 1

    assert execution.proposal is not None

    assert execution.proposal.kind is (
        InvestigationProposalKind
        .PROPOSE_INVESTIGATION
    )

    assert (
        execution.proposal.relationship_id
        is None
    )

    assert execution.run.validation_result is (
        ModelRunValidationResult.VALID
    )


def test_openai_strict_schema_allows_explicit_null_relationship() -> None:
    schema = _proposal_schema()

    alternatives = (
        schema[
            "properties"
        ][
            "proposal"
        ][
            "anyOf"
        ]
    )

    assert len(
        alternatives
    ) == 4

    for alternative in alternatives:
        relationship_schema = (
            alternative[
                "properties"
            ][
                "relationship_id"
            ]
        )

        assert {
            item[
                "type"
            ]
            for item
            in relationship_schema[
                "anyOf"
            ]
        } == {
            "string",
            "null",
        }

        assert (
            "relationship_id"
            in alternative[
                "required"
            ]
        )
