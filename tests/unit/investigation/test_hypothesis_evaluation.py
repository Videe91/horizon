from __future__ import annotations

from dataclasses import replace

import pytest

from horizon.investigation.hypothesis_evaluation import (
    HypothesisEvaluationError,
    HypothesisEvaluationVerdict,
    hypothesis_evaluation_schema,
    parse_hypothesis_evaluation,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)


def evidence(
    identity: str,
) -> CanonicalEvidenceRecord:
    return CanonicalEvidenceRecord(
        evidence_id=identity,
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload=(
            '{"observed":true}'
        ),
    )


def request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary "
            "software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(
            evidence(
                "evidence:source-a"
            ),
            evidence(
                "evidence:source-b"
            ),
            evidence(
                "evidence:source-c"
            ),
        ),
        request_id=(
            "semantic-gap-followup-investigation-request:test"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
        ),
        semantic_gap_section=(
            "WHAT_IT_IS"
        ),
    )


def hypothesis_proposal(
    value: InvestigationRequest,
):
    return parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_HYPOTHESIS",
            "question_id": (
                value.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "hypothesis": (
                "The repository primarily implements "
                "Python workflow orchestration."
            ),
            "test_questions": [
                (
                    "Does the repository's declared "
                    "purpose support this interpretation?"
                ),
                (
                    "Do the Flow and Task abstractions "
                    "support this interpretation?"
                ),
            ],
        },
    )


def common_raw(
    value: InvestigationRequest,
    proposal,
) -> dict[
    str,
    object,
]:
    return {
        "request_id": (
            value.request_id
        ),
        "question_id": (
            value.question_id
        ),
        "source_proposal_id": (
            proposal.proposal_id
        ),
    }


def supported_raw(
    value: InvestigationRequest,
    proposal,
) -> dict[
    str,
    object,
]:
    return {
        **common_raw(
            value,
            proposal,
        ),
        "verdict": "SUPPORTED",
        "supporting_evidence_ids": [
            "evidence:source-a",
            "evidence:source-b",
        ],
        "contradicting_evidence_ids": [],
        "missing_evidence_questions": [],
    }


def test_supported_evaluation_is_non_authoritative_and_content_addressed() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    result = parse_hypothesis_evaluation(
        request=value,
        source_proposal=proposal,
        raw=supported_raw(
            value,
            proposal,
        ),
    )

    assert (
        result.verdict
        is HypothesisEvaluationVerdict.SUPPORTED
    )

    assert (
        result.request_id
        == value.request_id
    )

    assert (
        result.question_id
        == value.question_id
    )

    assert (
        result.source_proposal_id
        == proposal.proposal_id
    )

    assert (
        result.hypothesis
        == proposal.hypothesis
    )

    assert (
        result.supporting_evidence_ids
        == (
            "evidence:source-a",
            "evidence:source-b",
        )
    )

    assert (
        result.contradicting_evidence_ids
        == ()
    )

    assert (
        result.missing_evidence_questions
        == ()
    )

    assert result.evaluation_id.startswith(
        "hypothesis-evidence-evaluation:"
    )

    assert not hasattr(
        result,
        "claim_id",
    )

    assert not hasattr(
        result,
        "assessment_id",
    )

    assert not hasattr(
        result,
        "world_model_assertion_id",
    )


def test_contradicted_requires_contradicting_evidence() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    result = parse_hypothesis_evaluation(
        request=value,
        source_proposal=proposal,
        raw={
            **common_raw(
                value,
                proposal,
            ),
            "verdict": "CONTRADICTED",
            "supporting_evidence_ids": [],
            "contradicting_evidence_ids": [
                "evidence:source-c",
            ],
            "missing_evidence_questions": [],
        },
    )

    assert (
        result.verdict
        is HypothesisEvaluationVerdict.CONTRADICTED
    )

    assert (
        result.contradicting_evidence_ids
        == (
            "evidence:source-c",
        )
    )


def test_incomplete_requires_explicit_missing_evidence_question() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    result = parse_hypothesis_evaluation(
        request=value,
        source_proposal=proposal,
        raw={
            **common_raw(
                value,
                proposal,
            ),
            "verdict": "STILL_INCOMPLETE",
            "supporting_evidence_ids": [
                "evidence:source-a",
            ],
            "contradicting_evidence_ids": [],
            "missing_evidence_questions": [
                (
                    "Which runtime behavior confirms "
                    "the repository-wide interpretation?"
                ),
            ],
        },
    )

    assert (
        result.verdict
        is HypothesisEvaluationVerdict
        .STILL_INCOMPLETE
    )

    assert (
        len(
            result.missing_evidence_questions
        )
        == 1
    )


@pytest.mark.parametrize(
    "verdict",
    [
        "",
        "PROVEN",
        "TRUE",
        "FALSE",
        "UNKNOWN",
    ],
)
def test_unregistered_verdict_is_rejected(
    verdict: str,
) -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    raw = supported_raw(
        value,
        proposal,
    )

    raw[
        "verdict"
    ] = verdict

    with pytest.raises(
        HypothesisEvaluationError,
        match="verdict",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw=raw,
        )


def test_extra_output_field_is_rejected() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    raw = supported_raw(
        value,
        proposal,
    )

    raw[
        "rationale"
    ] = "Trust me."

    with pytest.raises(
        HypothesisEvaluationError,
        match="fields",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw=raw,
        )


def test_missing_output_field_is_rejected() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    raw = supported_raw(
        value,
        proposal,
    )

    del raw[
        "supporting_evidence_ids"
    ]

    with pytest.raises(
        HypothesisEvaluationError,
        match="fields",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw=raw,
        )


@pytest.mark.parametrize(
    (
        "field",
        "foreign",
    ),
    [
        (
            "request_id",
            "semantic-gap-followup-investigation-request:foreign",
        ),
        (
            "question_id",
            "repository-semantic-gap-question:foreign",
        ),
        (
            "source_proposal_id",
            "investigation-proposal:foreign",
        ),
    ],
)
def test_lineage_identity_mismatch_is_rejected(
    field: str,
    foreign: str,
) -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    raw = supported_raw(
        value,
        proposal,
    )

    raw[
        field
    ] = foreign

    with pytest.raises(
        HypothesisEvaluationError,
        match=field.replace(
            "_",
            " ",
        ),
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw=raw,
        )


def test_only_hypothesis_proposal_can_be_evaluated() -> None:
    value = request()

    proposal = parse_investigation_proposal(
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
                "What should be inspected?"
            ],
        },
    )

    with pytest.raises(
        HypothesisEvaluationError,
        match="PROPOSE_HYPOTHESIS",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw={
                **common_raw(
                    value,
                    proposal,
                ),
                "verdict": "SUPPORTED",
                "supporting_evidence_ids": [
                    "evidence:source-a",
                ],
                "contradicting_evidence_ids": [],
                "missing_evidence_questions": [],
            },
        )


def test_source_proposal_context_must_remain_within_current_request() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    proposal = replace(
        proposal,
        evidence_reference_ids=(
            "evidence-reference:foreign",
        ),
    )

    with pytest.raises(
        HypothesisEvaluationError,
        match="source proposal context",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw=supported_raw(
                value,
                proposal,
            ),
        )


@pytest.mark.parametrize(
    "field",
    [
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
    ],
)
def test_evidence_ids_must_exist_in_exact_request(
    field: str,
) -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    raw = supported_raw(
        value,
        proposal,
    )

    if (
        field
        == "contradicting_evidence_ids"
    ):
        raw[
            "verdict"
        ] = "STILL_INCOMPLETE"

        raw[
            "supporting_evidence_ids"
        ] = []

        raw[
            "missing_evidence_questions"
        ] = [
            "What additional evidence is needed?"
        ]

    raw[
        field
    ] = [
        "evidence:not-in-request",
    ]

    with pytest.raises(
        HypothesisEvaluationError,
        match="outside the request",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw=raw,
        )


def test_duplicate_evidence_identity_is_rejected() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    raw = supported_raw(
        value,
        proposal,
    )

    raw[
        "supporting_evidence_ids"
    ] = [
        "evidence:source-a",
        "evidence:source-a",
    ]

    with pytest.raises(
        HypothesisEvaluationError,
        match="duplicate",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw=raw,
        )


def test_evidence_cannot_both_support_and_contradict() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    with pytest.raises(
        HypothesisEvaluationError,
        match="both",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw={
                **common_raw(
                    value,
                    proposal,
                ),
                "verdict": "STILL_INCOMPLETE",
                "supporting_evidence_ids": [
                    "evidence:source-a",
                ],
                "contradicting_evidence_ids": [
                    "evidence:source-a",
                ],
                "missing_evidence_questions": [
                    "What remains unresolved?"
                ],
            },
        )


@pytest.mark.parametrize(
    (
        "support",
        "contradict",
        "missing",
    ),
    [
        (
            [],
            [],
            [],
        ),
        (
            [
                "evidence:source-a",
            ],
            [
                "evidence:source-b",
            ],
            [],
        ),
        (
            [
                "evidence:source-a",
            ],
            [],
            [
                "What else is missing?"
            ],
        ),
    ],
)
def test_supported_has_strict_semantics(
    support,
    contradict,
    missing,
) -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    with pytest.raises(
        HypothesisEvaluationError,
        match="SUPPORTED",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw={
                **common_raw(
                    value,
                    proposal,
                ),
                "verdict": "SUPPORTED",
                "supporting_evidence_ids": (
                    support
                ),
                "contradicting_evidence_ids": (
                    contradict
                ),
                "missing_evidence_questions": (
                    missing
                ),
            },
        )


@pytest.mark.parametrize(
    (
        "support",
        "contradict",
        "missing",
    ),
    [
        (
            [],
            [],
            [],
        ),
        (
            [
                "evidence:source-a",
            ],
            [
                "evidence:source-b",
            ],
            [],
        ),
        (
            [],
            [
                "evidence:source-b",
            ],
            [
                "What else is missing?"
            ],
        ),
    ],
)
def test_contradicted_has_strict_semantics(
    support,
    contradict,
    missing,
) -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    with pytest.raises(
        HypothesisEvaluationError,
        match="CONTRADICTED",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw={
                **common_raw(
                    value,
                    proposal,
                ),
                "verdict": "CONTRADICTED",
                "supporting_evidence_ids": (
                    support
                ),
                "contradicting_evidence_ids": (
                    contradict
                ),
                "missing_evidence_questions": (
                    missing
                ),
            },
        )


def test_incomplete_without_missing_question_is_rejected() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    with pytest.raises(
        HypothesisEvaluationError,
        match="STILL_INCOMPLETE",
    ):
        parse_hypothesis_evaluation(
            request=value,
            source_proposal=proposal,
            raw={
                **common_raw(
                    value,
                    proposal,
                ),
                "verdict": "STILL_INCOMPLETE",
                "supporting_evidence_ids": [
                    "evidence:source-a",
                ],
                "contradicting_evidence_ids": [],
                "missing_evidence_questions": [],
            },
        )


def test_evidence_order_does_not_change_evaluation_identity() -> None:
    value = request()
    proposal = hypothesis_proposal(
        value
    )

    first = parse_hypothesis_evaluation(
        request=value,
        source_proposal=proposal,
        raw={
            **common_raw(
                value,
                proposal,
            ),
            "verdict": "SUPPORTED",
            "supporting_evidence_ids": [
                "evidence:source-b",
                "evidence:source-a",
            ],
            "contradicting_evidence_ids": [],
            "missing_evidence_questions": [],
        },
    )

    second = parse_hypothesis_evaluation(
        request=value,
        source_proposal=proposal,
        raw={
            **common_raw(
                value,
                proposal,
            ),
            "verdict": "SUPPORTED",
            "supporting_evidence_ids": [
                "evidence:source-a",
                "evidence:source-b",
            ],
            "contradicting_evidence_ids": [],
            "missing_evidence_questions": [],
        },
    )

    assert (
        first.evaluation_id
        == second.evaluation_id
    )

    assert (
        first.supporting_evidence_ids
        == second.supporting_evidence_ids
        == (
            "evidence:source-a",
            "evidence:source-b",
        )
    )


def test_schema_is_strict_and_has_exact_verdict_vocabulary() -> None:
    schema = (
        hypothesis_evaluation_schema()
    )

    assert (
        schema[
            "type"
        ]
        == "object"
    )

    assert (
        schema[
            "additionalProperties"
        ]
        is False
    )

    expected = {
        "request_id",
        "question_id",
        "source_proposal_id",
        "verdict",
        "supporting_evidence_ids",
        "contradicting_evidence_ids",
        "missing_evidence_questions",
    }

    assert (
        set(
            schema[
                "properties"
            ]
        )
        == expected
    )

    assert (
        set(
            schema[
                "required"
            ]
        )
        == expected
    )

    assert (
        schema[
            "properties"
        ][
            "verdict"
        ][
            "enum"
        ]
        == [
            "SUPPORTED",
            "CONTRADICTED",
            "STILL_INCOMPLETE",
        ]
    )

    assert (
        schema[
            "properties"
        ][
            "supporting_evidence_ids"
        ][
            "uniqueItems"
        ]
        is True
    )

    assert (
        schema[
            "properties"
        ][
            "contradicting_evidence_ids"
        ][
            "uniqueItems"
        ]
        is True
    )
