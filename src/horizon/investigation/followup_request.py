"""Follow-up semantic-gap investigation requests.

The initial semantic-gap compiler intentionally includes only the exact
evidence closure already justified by Horizon's current state.

Evidence produced by an executed investigation round has no claim or
World Model assertion yet, so it must not silently enter that initial
closure.

This module provides the explicit boundary for the next autonomous round:

    initial semantic-gap InvestigationRequest
        + explicitly supplied investigation evidence
        -> follow-up InvestigationRequest

The original request is not mutated. Supplemental evidence creates no
claim, epistemic assessment, or World Model assertion.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import replace

from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)


class SemanticGapFollowupRequestError(
    ValueError
):
    """A semantic-gap follow-up request cannot be constructed safely."""


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
    payload: object,
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        prefix
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _validate_record(
    record: CanonicalEvidenceRecord,
) -> None:
    if not isinstance(
        record,
        CanonicalEvidenceRecord,
    ):
        raise SemanticGapFollowupRequestError(
            "supplemental evidence must contain "
            "CanonicalEvidenceRecord values"
        )

    if (
        not isinstance(
            record.evidence_id,
            str,
        )
        or not record.evidence_id.strip()
    ):
        raise SemanticGapFollowupRequestError(
            "supplemental evidence id must be nonempty"
        )

    if (
        not isinstance(
            record.evidence_kind,
            str,
        )
        or not record.evidence_kind.strip()
    ):
        raise SemanticGapFollowupRequestError(
            "supplemental evidence kind must be nonempty"
        )

    if (
        not isinstance(
            record.canonical_payload,
            str,
        )
        or not record.canonical_payload.strip()
    ):
        raise SemanticGapFollowupRequestError(
            "supplemental canonical payload must be nonempty"
        )


def extend_semantic_gap_investigation_request(
    request: InvestigationRequest,
    *,
    supplemental_evidence_records: tuple[
        CanonicalEvidenceRecord,
        ...,
    ],
) -> InvestigationRequest:
    """Create one content-addressed follow-up request with new evidence."""

    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise SemanticGapFollowupRequestError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not
        InvestigationRequestOrigin.REPOSITORY_SEMANTIC_GAP
    ):
        raise SemanticGapFollowupRequestError(
            "request must originate from a repository semantic gap"
        )

    if (
        not isinstance(
            supplemental_evidence_records,
            tuple,
        )
        or not supplemental_evidence_records
    ):
        raise SemanticGapFollowupRequestError(
            "follow-up requires at least one supplemental evidence record"
        )

    for record in supplemental_evidence_records:
        _validate_record(
            record
        )

    supplemental_ids = tuple(
        record.evidence_id
        for record
        in supplemental_evidence_records
    )

    if (
        len(
            supplemental_ids
        )
        != len(
            set(
                supplemental_ids
            )
        )
    ):
        raise SemanticGapFollowupRequestError(
            "supplemental evidence contains duplicate identities"
        )

    existing_ids = {
        record.evidence_id
        for record
        in request.evidence_records
    }

    collisions = tuple(
        evidence_id
        for evidence_id
        in supplemental_ids
        if evidence_id
        in existing_ids
    )

    if collisions:
        raise SemanticGapFollowupRequestError(
            "supplemental evidence already exists in base request"
        )

    ordered_supplemental = tuple(
        sorted(
            supplemental_evidence_records,
            key=lambda record: (
                record.evidence_id,
                record.evidence_kind,
            ),
        )
    )

    evidence_identity_payload = [
        {
            "evidence_id": (
                record.evidence_id
            ),
            "evidence_kind": (
                record.evidence_kind
            ),
            "canonical_payload_sha256": (
                _sha256(
                    record
                    .canonical_payload
                    .encode(
                        "utf-8"
                    )
                )
            ),
        }
        for record
        in ordered_supplemental
    ]

    request_id = _identity(
        "semantic-gap-followup-investigation-request:",
        {
            "base_request_id": (
                request.request_id
            ),
            "semantic_gap_id": (
                request.semantic_gap_id
            ),
            "semantic_gap_section": (
                request.semantic_gap_section
            ),
            "supplemental_evidence": (
                evidence_identity_payload
            ),
        },
    )

    return replace(
        request,
        evidence_records=(
            request.evidence_records
            + ordered_supplemental
        ),
        request_id=request_id,
    )
