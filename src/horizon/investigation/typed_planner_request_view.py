"""Compact model-facing view of a semantic-gap investigation request.

The full InvestigationRequest remains Horizon's internal authority for
validation, provenance, and planner-output parsing.

The typed-planner model does not need complete evidence bodies merely to
translate already-selected questions into legal repository operations.
It receives stable evidence descriptors instead:

- evidence identity,
- evidence kind,
- exact UTF-8 payload hash,
- exact UTF-8 payload byte count.

No evidence content is discarded from Horizon. It is omitted only from
this model-facing planning projection.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass

from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
)


class TypedPlannerRequestViewError(
    ValueError
):
    """A compact typed-planner request view cannot be constructed."""


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerEvidenceRecordView:
    evidence_id: str
    evidence_kind: str

    canonical_payload_sha256: str
    canonical_payload_bytes: int


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerRequestView:
    request_id: str

    question_id: str
    question: str

    origin: str

    relationship_id: str | None
    relationship_kind: str | None
    relationship_reason: str | None

    assertion_ids: tuple[
        str,
        ...,
    ]

    claim_ids: tuple[
        str,
        ...,
    ]

    assessment_ids: tuple[
        str,
        ...,
    ]

    evidence_reference_ids: tuple[
        str,
        ...,
    ]

    evidence_records: tuple[
        TypedPlannerEvidenceRecordView,
        ...,
    ]

    semantic_gap_id: str | None
    semantic_gap_section: str | None

    view_id: str


def _canonical_bytes(
    value: object,
) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        allow_nan=False,
    ).encode(
        "utf-8"
    )


def _sha256(
    value: bytes,
) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            value
        ).hexdigest()
    )


def _identity(
    prefix: str,
    value: object,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            _canonical_bytes(
                value
            )
        ).hexdigest()
    )


def _relationship_kind(
    request: InvestigationRequest,
) -> str | None:
    value = request.relationship_kind

    if value is None:
        return None

    enum_value = getattr(
        value,
        "value",
        None,
    )

    if isinstance(
        enum_value,
        str,
    ):
        return enum_value

    if isinstance(
        value,
        str,
    ):
        return value

    raise TypedPlannerRequestViewError(
        "relationship kind cannot be represented compactly"
    )


def _evidence_view(
    record: CanonicalEvidenceRecord,
) -> TypedPlannerEvidenceRecordView:
    if not isinstance(
        record,
        CanonicalEvidenceRecord,
    ):
        raise TypedPlannerRequestViewError(
            "request evidence must contain "
            "CanonicalEvidenceRecord values"
        )

    if (
        not isinstance(
            record.canonical_payload,
            str,
        )
        or not record.canonical_payload
    ):
        raise TypedPlannerRequestViewError(
            "canonical evidence payload must be nonempty text"
        )

    payload_bytes = (
        record.canonical_payload
        .encode(
            "utf-8"
        )
    )

    return TypedPlannerEvidenceRecordView(
        evidence_id=(
            record.evidence_id
        ),
        evidence_kind=(
            record.evidence_kind
        ),
        canonical_payload_sha256=(
            _sha256(
                payload_bytes
            )
        ),
        canonical_payload_bytes=(
            len(
                payload_bytes
            )
        ),
    )


def make_typed_planner_request_view(
    request: InvestigationRequest,
) -> TypedPlannerRequestView:
    """Project a full request into a compact planning-only model view."""

    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise TypedPlannerRequestViewError(
            "request must be an InvestigationRequest"
        )

    evidence_records = tuple(
        _evidence_view(
            record
        )
        for record
        in request.evidence_records
    )

    origin_value = getattr(
        request.origin,
        "value",
        request.origin,
    )

    if not isinstance(
        origin_value,
        str,
    ):
        raise TypedPlannerRequestViewError(
            "request origin cannot be represented compactly"
        )

    relationship_kind = (
        _relationship_kind(
            request
        )
    )

    identity_payload = {
        "request_id": (
            request.request_id
        ),
        "question_id": (
            request.question_id
        ),
        "question": (
            request.question
        ),
        "origin": (
            origin_value
        ),
        "relationship_id": (
            request.relationship_id
        ),
        "relationship_kind": (
            relationship_kind
        ),
        "relationship_reason": (
            request.relationship_reason
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
        "evidence_records": [
            {
                "evidence_id": (
                    record.evidence_id
                ),
                "evidence_kind": (
                    record.evidence_kind
                ),
                "canonical_payload_sha256": (
                    record
                    .canonical_payload_sha256
                ),
                "canonical_payload_bytes": (
                    record
                    .canonical_payload_bytes
                ),
            }
            for record
            in evidence_records
        ],
        "semantic_gap_id": (
            request.semantic_gap_id
        ),
        "semantic_gap_section": (
            request.semantic_gap_section
        ),
    }

    view_id = _identity(
        "typed-planner-request-view:",
        identity_payload,
    )

    return TypedPlannerRequestView(
        request_id=(
            request.request_id
        ),
        question_id=(
            request.question_id
        ),
        question=(
            request.question
        ),
        origin=(
            origin_value
        ),
        relationship_id=(
            request.relationship_id
        ),
        relationship_kind=(
            relationship_kind
        ),
        relationship_reason=(
            request.relationship_reason
        ),
        assertion_ids=(
            request.assertion_ids
        ),
        claim_ids=(
            request.claim_ids
        ),
        assessment_ids=(
            request.assessment_ids
        ),
        evidence_reference_ids=(
            request.evidence_reference_ids
        ),
        evidence_records=(
            evidence_records
        ),
        semantic_gap_id=(
            request.semantic_gap_id
        ),
        semantic_gap_section=(
            request.semantic_gap_section
        ),
        view_id=view_id,
    )
