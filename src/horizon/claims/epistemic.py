"""Explicit epistemic assessments of evidence-backed claims.

Evidence-backed claims record propositions, scope, and evidence.

Epistemic assessments separately record Horizon's current judgment about
one of those claims.

This module deliberately does not infer epistemic status from evidence
kind. The status is an explicit judgment backed by an explicit rationale
and an explicit subset of the claim's evidence references.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from horizon.claims.evidence_backed import (
    ClaimEvidenceReference,
    EvidenceBackedClaim,
    EvidenceBackedClaimError,
    make_claim_evidence_reference,
    make_evidence_backed_claim,
)


class EpistemicAssessmentError(
    ValueError
):
    """An epistemic assessment could not be represented faithfully."""


class EpistemicStatus(
    str,
    Enum,
):
    PROVEN = "PROVEN"
    SUPPORTED_HYPOTHESIS = "SUPPORTED_HYPOTHESIS"
    DISPUTED = "DISPUTED"
    UNKNOWN = "UNKNOWN"


@dataclass(
    frozen=True,
    slots=True,
)
class EpistemicAssessment:
    claim_id: str
    status: EpistemicStatus
    rationale: str
    basis_reference_ids: tuple[
        str,
        ...,
    ]
    assessment_id: str


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

    digest = hashlib.sha256(
        encoded
    ).hexdigest()

    return (
        prefix
        + digest
    )


def _validate_reference_integrity(
    reference: ClaimEvidenceReference,
    *,
    context: str,
) -> None:
    if not isinstance(
        reference,
        ClaimEvidenceReference,
    ):
        raise EpistemicAssessmentError(
            f"{context} must contain "
            "ClaimEvidenceReference values"
        )

    try:
        canonical = (
            make_claim_evidence_reference(
                reference.evidence_kind,
                reference.relation,
                reference.evidence_id,
            )
        )
    except EvidenceBackedClaimError as exc:
        raise EpistemicAssessmentError(
            f"{context} evidence reference is invalid"
        ) from exc

    if canonical != reference:
        raise EpistemicAssessmentError(
            f"{context} evidence reference "
            "identity is invalid"
        )


def _validate_claim_integrity(
    claim: EvidenceBackedClaim,
) -> None:
    if not isinstance(
        claim,
        EvidenceBackedClaim,
    ):
        raise EpistemicAssessmentError(
            "claim must be an EvidenceBackedClaim"
        )

    for reference in claim.evidence:
        _validate_reference_integrity(
            reference,
            context="claim",
        )

    try:
        canonical = make_evidence_backed_claim(
            claim.proposition,
            scope=claim.scope,
            evidence=claim.evidence,
        )
    except EvidenceBackedClaimError as exc:
        raise EpistemicAssessmentError(
            "claim is invalid"
        ) from exc

    if canonical != claim:
        raise EpistemicAssessmentError(
            "claim identity is invalid"
        )


def make_epistemic_assessment(
    claim: EvidenceBackedClaim,
    status: EpistemicStatus,
    *,
    rationale: str,
    basis: Iterable[
        ClaimEvidenceReference
    ],
) -> EpistemicAssessment:
    _validate_claim_integrity(
        claim
    )

    if not isinstance(
        status,
        EpistemicStatus,
    ):
        raise EpistemicAssessmentError(
            "status must be an EpistemicStatus"
        )

    if (
        not isinstance(
            rationale,
            str,
        )
        or not rationale.strip()
    ):
        raise EpistemicAssessmentError(
            "rationale must be nonempty"
        )

    basis_references = tuple(
        basis
    )

    if not basis_references:
        raise EpistemicAssessmentError(
            "assessment requires basis evidence"
        )

    for reference in basis_references:
        _validate_reference_integrity(
            reference,
            context="basis",
        )

    basis_ids = [
        reference.reference_id
        for reference
        in basis_references
    ]

    if len(
        set(
            basis_ids
        )
    ) != len(
        basis_ids
    ):
        raise EpistemicAssessmentError(
            "duplicate basis reference"
        )

    for reference in basis_references:
        if reference not in claim.evidence:
            raise EpistemicAssessmentError(
                "basis reference is not "
                "attached to claim"
            )

    ordered_basis_ids = tuple(
        sorted(
            basis_ids
        )
    )

    assessment_id = _identity(
        "epistemic-assessment:",
        {
            "claim_id": (
                claim.claim_id
            ),
            "status": (
                status.value
            ),
            "rationale": (
                rationale
            ),
            "basis_reference_ids": (
                ordered_basis_ids
            ),
        },
    )

    return EpistemicAssessment(
        claim_id=(
            claim.claim_id
        ),
        status=(
            status
        ),
        rationale=(
            rationale
        ),
        basis_reference_ids=(
            ordered_basis_ids
        ),
        assessment_id=(
            assessment_id
        ),
    )
