from __future__ import annotations

import json

from decimal import Decimal

from horizon.investigation.typed_planner_request_view import (
    make_typed_planner_request_view,
)
from horizon.investigation.typed_planner_model import (
    make_semantic_gap_typed_planner_invocation,
)
from horizon.investigation.providers.openai_responses import (
    _canonical_input_json,
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
    payload: str,
) -> CanonicalEvidenceRecord:
    return CanonicalEvidenceRecord(
        evidence_id=identity,
        evidence_kind=(
            "BOUNDED_INVESTIGATION_SEARCH_OBSERVATION"
        ),
        canonical_payload=payload,
    )


def request(
    *,
    payload: str = "x" * 100_000,
) -> InvestigationRequest:
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
        evidence_reference_ids=(
            "evidence-reference:test",
        ),
        evidence_records=(
            evidence(
                "evidence:large",
                payload,
            ),
            evidence(
                "evidence:small",
                '{"value":"small"}',
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


def proposal(
    value: InvestigationRequest,
):
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
            "evidence_reference_ids": list(
                value.evidence_reference_ids
            ),
            "investigation_questions": [
                (
                    "Read the named source passages "
                    "needed to test the hypothesis."
                ),
            ],
        },
    )


def invocation(
    value: InvestigationRequest,
):
    return (
        make_semantic_gap_typed_planner_invocation(
            request=value,
            proposal=proposal(
                value
            ),
            instruction=(
                b"Translate into legal typed operations."
            ),
            temperature=None,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )


def test_view_preserves_request_and_semantic_gap_identity() -> None:
    value = request()

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    assert (
        view.request_id
        == value.request_id
    )

    assert (
        view.question_id
        == value.question_id
    )

    assert (
        view.question
        == value.question
    )

    assert (
        view.origin
        == value.origin.value
    )

    assert (
        view.semantic_gap_id
        == value.semantic_gap_id
    )

    assert (
        view.semantic_gap_section
        == value.semantic_gap_section
    )


def test_view_preserves_scope_identifiers() -> None:
    value = request()

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    assert (
        view.relationship_id
        == value.relationship_id
    )

    assert (
        view.assertion_ids
        == value.assertion_ids
    )

    assert (
        view.claim_ids
        == value.claim_ids
    )

    assert (
        view.assessment_ids
        == value.assessment_ids
    )

    assert (
        view.evidence_reference_ids
        == value.evidence_reference_ids
    )


def test_evidence_body_becomes_hash_and_size_only() -> None:
    value = request()

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    assert len(
        view.evidence_records
    ) == 2

    first = view.evidence_records[0]

    assert (
        first.evidence_id
        == "evidence:large"
    )

    assert (
        first.evidence_kind
        == (
            "BOUNDED_INVESTIGATION_SEARCH_OBSERVATION"
        )
    )

    assert (
        first.canonical_payload_bytes
        == 100_000
    )

    assert (
        first.canonical_payload_sha256
        .startswith(
            "sha256:"
        )
    )

    assert not hasattr(
        first,
        "canonical_payload",
    )


def test_identical_request_produces_identical_view() -> None:
    value = request()

    first = (
        make_typed_planner_request_view(
            value
        )
    )

    second = (
        make_typed_planner_request_view(
            value
        )
    )

    assert first == second


def test_evidence_body_change_changes_view_identity() -> None:
    first = (
        make_typed_planner_request_view(
            request(
                payload="a" * 100_000,
            )
        )
    )

    second = (
        make_typed_planner_request_view(
            request(
                payload="b" * 100_000,
            )
        )
    )

    assert (
        first.view_id
        != second.view_id
    )


def test_invocation_retains_full_internal_request() -> None:
    value = request()

    sealed = invocation(
        value
    )

    assert (
        sealed.request
        == value
    )

    assert (
        sealed.request
        .evidence_records[0]
        .canonical_payload
        == "x" * 100_000
    )


def test_model_input_uses_compact_request_view() -> None:
    value = request()

    sealed = invocation(
        value
    )

    payload = json.loads(
        _canonical_input_json(
            sealed
        )
    )

    model_request = payload[
        "request"
    ]

    assert (
        model_request[
            "request_id"
        ]
        == value.request_id
    )

    assert (
        model_request[
            "view_id"
        ].startswith(
            "typed-planner-request-view:"
        )
    )

    assert len(
        model_request[
            "evidence_records"
        ]
    ) == 2

    for item in model_request[
        "evidence_records"
    ]:
        assert (
            "canonical_payload"
            not in item
        )

        assert set(
            item
        ) == {
            "evidence_id",
            "evidence_kind",
            "canonical_payload_sha256",
            "canonical_payload_bytes",
            "operational_context",
        }

        assert (
            item[
                "operational_context"
            ]
            is None
        )


def test_large_evidence_body_does_not_scale_provider_input() -> None:
    small = invocation(
        request(
            payload="x" * 100,
        )
    )

    huge = invocation(
        request(
            payload="x" * 1_000_000,
        )
    )

    small_bytes = len(
        _canonical_input_json(
            small
        ).encode(
            "utf-8"
        )
    )

    huge_bytes = len(
        _canonical_input_json(
            huge
        ).encode(
            "utf-8"
        )
    )

    assert (
        huge_bytes
        - small_bytes
        < 1_000
    )


def test_large_request_provider_input_is_bounded() -> None:
    sealed = invocation(
        request(
            payload="x" * 1_000_000,
        )
    )

    encoded = (
        _canonical_input_json(
            sealed
        ).encode(
            "utf-8"
        )
    )

    assert len(
        encoded
    ) < 20_000


def test_canonical_input_hash_changes_when_hidden_evidence_changes() -> None:
    first = invocation(
        request(
            payload="a" * 100_000,
        )
    )

    second = invocation(
        request(
            payload="b" * 100_000,
        )
    )

    assert (
        first.canonical_input_hash
        != second.canonical_input_hash
    )

    assert (
        first.invocation_id
        != second.invocation_id
    )
