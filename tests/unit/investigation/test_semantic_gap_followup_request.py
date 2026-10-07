from __future__ import annotations

import json

import pytest

from horizon.investigation.followup_request import (
    SemanticGapFollowupRequestError,
    extend_semantic_gap_investigation_request,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)


def _record(
    identity: str,
    *,
    kind: str = "TEST_EVIDENCE",
    value: str = "value",
) -> CanonicalEvidenceRecord:
    return CanonicalEvidenceRecord(
        evidence_id=identity,
        evidence_kind=kind,
        canonical_payload=json.dumps(
            {
                "value": value,
            },
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )


def _request(
    *,
    evidence_records=(),
) -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=evidence_records,
        request_id=(
            "investigation-request:base"
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


def test_supplemental_evidence_is_added_to_request() -> None:
    base = _request(
        evidence_records=(
            _record(
                "evidence:base"
            ),
        )
    )

    supplemental = (
        _record(
            "evidence:new"
        ),
    )

    followup = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                supplemental
            ),
        )
    )

    assert [
        record.evidence_id
        for record
        in followup.evidence_records
    ] == [
        "evidence:base",
        "evidence:new",
    ]


def test_base_request_is_not_mutated() -> None:
    base = _request(
        evidence_records=(
            _record(
                "evidence:base"
            ),
        )
    )

    followup = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    _record(
                        "evidence:new"
                    ),
                )
            ),
        )
    )

    assert [
        record.evidence_id
        for record
        in base.evidence_records
    ] == [
        "evidence:base",
    ]

    assert len(
        followup.evidence_records
    ) == 2


def test_followup_gets_new_content_addressed_request_identity() -> None:
    base = _request()

    supplemental = (
        _record(
            "evidence:new"
        ),
    )

    followup = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                supplemental
            ),
        )
    )

    assert (
        followup.request_id
        != base.request_id
    )

    assert followup.request_id.startswith(
        "semantic-gap-followup-investigation-request:"
    )


def test_identical_input_produces_identical_identity() -> None:
    base = _request()

    supplemental = (
        _record(
            "evidence:new"
        ),
    )

    first = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                supplemental
            ),
        )
    )

    second = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                supplemental
            ),
        )
    )

    assert first == second


def test_supplemental_order_does_not_change_identity() -> None:
    base = _request()

    one = _record(
        "evidence:one"
    )

    two = _record(
        "evidence:two"
    )

    first = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    one,
                    two,
                )
            ),
        )
    )

    second = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    two,
                    one,
                )
            ),
        )
    )

    assert first == second


def test_payload_change_changes_followup_identity() -> None:
    base = _request()

    first = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    _record(
                        "evidence:new",
                        value="one",
                    ),
                )
            ),
        )
    )

    second = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    _record(
                        "evidence:new",
                        value="two",
                    ),
                )
            ),
        )
    )

    assert (
        first.request_id
        != second.request_id
    )


def test_base_evidence_collision_is_rejected() -> None:
    base = _request(
        evidence_records=(
            _record(
                "evidence:same"
            ),
        )
    )

    with pytest.raises(
        SemanticGapFollowupRequestError,
        match="already exists",
    ):
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    _record(
                        "evidence:same"
                    ),
                )
            ),
        )


def test_duplicate_supplemental_identity_is_rejected() -> None:
    base = _request()

    duplicate = _record(
        "evidence:duplicate"
    )

    with pytest.raises(
        SemanticGapFollowupRequestError,
        match="duplicate",
    ):
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    duplicate,
                    duplicate,
                )
            ),
        )


def test_non_semantic_gap_request_is_rejected() -> None:
    base = _request()

    object.__setattr__(
        base,
        "origin",
        (
            InvestigationRequestOrigin
            .WORLD_MODEL_CONFLICT
        ),
    )

    with pytest.raises(
        SemanticGapFollowupRequestError,
        match="semantic gap",
    ):
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    _record(
                        "evidence:new"
                    ),
                )
            ),
        )


def test_empty_supplemental_evidence_is_rejected() -> None:
    with pytest.raises(
        SemanticGapFollowupRequestError,
        match="at least one",
    ):
        extend_semantic_gap_investigation_request(
            _request(),
            supplemental_evidence_records=(),
        )


def test_bad_record_is_rejected() -> None:
    with pytest.raises(
        SemanticGapFollowupRequestError,
    ):
        extend_semantic_gap_investigation_request(
            _request(),
            supplemental_evidence_records=(
                (
                    object(),
                )
            ),
        )


def test_existing_semantic_gap_identity_is_preserved() -> None:
    base = _request()

    followup = (
        extend_semantic_gap_investigation_request(
            base,
            supplemental_evidence_records=(
                (
                    _record(
                        "evidence:new"
                    ),
                )
            ),
        )
    )

    assert (
        followup.question_id
        == base.question_id
    )

    assert (
        followup.semantic_gap_id
        == base.semantic_gap_id
    )

    assert (
        followup.semantic_gap_section
        == base.semantic_gap_section
    )

    assert (
        followup.origin
        == base.origin
    )
