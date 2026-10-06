"""Immutable world-model snapshots.

A snapshot is a container over already-created claims, epistemic
assessments, and semantic assertions.

It validates closure and object identity, canonicalizes ordering, and
derives deterministic snapshot identity.

It performs no inference, reconciliation, conflict resolution, ownership
reasoning, or epistemic promotion.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from horizon.claims.evidence_backed import (
    EvidenceBackedClaim,
    EvidenceBackedClaimError,
    make_evidence_backed_claim,
)
from horizon.claims.epistemic import (
    EpistemicAssessment,
    EpistemicAssessmentError,
    make_epistemic_assessment,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
    WorldModelAssertionError,
    make_world_model_assertion,
)


class WorldModelSnapshotError(
    ValueError
):
    """A world-model snapshot is internally inconsistent."""


@dataclass(
    frozen=True,
    slots=True,
)
class WorldModelSnapshot:
    claims: tuple[
        EvidenceBackedClaim,
        ...,
    ]
    assessments: tuple[
        EpistemicAssessment,
        ...,
    ]
    assertions: tuple[
        WorldModelAssertion,
        ...,
    ]
    snapshot_id: str


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


def _reject_duplicate_ids(
    values: tuple[object, ...],
    *,
    attribute: str,
    label: str,
) -> None:
    identities = tuple(
        getattr(
            value,
            attribute,
        )
        for value in values
    )

    if len(
        identities
    ) != len(
        set(
            identities
        )
    ):
        raise WorldModelSnapshotError(
            f"duplicate {label} identity"
        )


def _validate_claim(
    claim: EvidenceBackedClaim,
) -> None:
    if not isinstance(
        claim,
        EvidenceBackedClaim,
    ):
        raise WorldModelSnapshotError(
            "claim must be an EvidenceBackedClaim"
        )

    try:
        canonical = make_evidence_backed_claim(
            claim.proposition,
            scope=claim.scope,
            evidence=claim.evidence,
        )
    except EvidenceBackedClaimError as exc:
        raise WorldModelSnapshotError(
            "claim is invalid"
        ) from exc

    if canonical != claim:
        raise WorldModelSnapshotError(
            "claim identity is invalid"
        )


def _validate_assessment(
    assessment: EpistemicAssessment,
    *,
    claims_by_id: dict[
        str,
        EvidenceBackedClaim,
    ],
) -> None:
    if not isinstance(
        assessment,
        EpistemicAssessment,
    ):
        raise WorldModelSnapshotError(
            "assessment must be an EpistemicAssessment"
        )

    claim = claims_by_id.get(
        assessment.claim_id
    )

    if claim is None:
        raise WorldModelSnapshotError(
            "assessment claim is absent from snapshot"
        )

    evidence_by_reference_id = {
        reference.reference_id: reference
        for reference in claim.evidence
    }

    try:
        basis = tuple(
            evidence_by_reference_id[
                reference_id
            ]
            for reference_id
            in assessment.basis_reference_ids
        )
    except KeyError as exc:
        raise WorldModelSnapshotError(
            "assessment basis is not attached to claim"
        ) from exc

    try:
        canonical = make_epistemic_assessment(
            claim,
            assessment.status,
            rationale=assessment.rationale,
            basis=basis,
        )
    except EpistemicAssessmentError as exc:
        raise WorldModelSnapshotError(
            "assessment is invalid"
        ) from exc

    if canonical != assessment:
        raise WorldModelSnapshotError(
            "assessment identity is invalid"
        )


def _validate_assertion(
    assertion: WorldModelAssertion,
    *,
    claims_by_id: dict[
        str,
        EvidenceBackedClaim,
    ],
    assessments_by_id: dict[
        str,
        EpistemicAssessment,
    ],
) -> None:
    if not isinstance(
        assertion,
        WorldModelAssertion,
    ):
        raise WorldModelSnapshotError(
            "assertion must be a WorldModelAssertion"
        )

    claim = claims_by_id.get(
        assertion.claim_id
    )

    if claim is None:
        raise WorldModelSnapshotError(
            "assertion claim is absent from snapshot"
        )

    assessment = assessments_by_id.get(
        assertion.assessment_id
    )

    if assessment is None:
        raise WorldModelSnapshotError(
            "assertion assessment is absent from snapshot"
        )

    if (
        assessment.claim_id
        != claim.claim_id
    ):
        raise WorldModelSnapshotError(
            "assertion assessment does not assess "
            "the assertion claim"
        )

    try:
        canonical = make_world_model_assertion(
            assertion.subject_id,
            assertion.relation,
            assertion.object_id,
            claim=claim,
            assessment=assessment,
        )
    except WorldModelAssertionError as exc:
        raise WorldModelSnapshotError(
            "assertion is invalid"
        ) from exc

    if canonical != assertion:
        raise WorldModelSnapshotError(
            "assertion identity is invalid"
        )


def make_world_model_snapshot(
    *,
    claims: Iterable[
        EvidenceBackedClaim
    ],
    assessments: Iterable[
        EpistemicAssessment
    ],
    assertions: Iterable[
        WorldModelAssertion
    ],
) -> WorldModelSnapshot:
    claim_values = tuple(
        claims
    )

    assessment_values = tuple(
        assessments
    )

    assertion_values = tuple(
        assertions
    )

    _reject_duplicate_ids(
        claim_values,
        attribute="claim_id",
        label="claim",
    )

    _reject_duplicate_ids(
        assessment_values,
        attribute="assessment_id",
        label="assessment",
    )

    _reject_duplicate_ids(
        assertion_values,
        attribute="assertion_id",
        label="assertion",
    )

    for claim in claim_values:
        _validate_claim(
            claim
        )

    claims_by_id = {
        claim.claim_id: claim
        for claim in claim_values
    }

    for assessment in assessment_values:
        _validate_assessment(
            assessment,
            claims_by_id=claims_by_id,
        )

    assessments_by_id = {
        assessment.assessment_id: assessment
        for assessment in assessment_values
    }

    for assertion in assertion_values:
        _validate_assertion(
            assertion,
            claims_by_id=claims_by_id,
            assessments_by_id=assessments_by_id,
        )

    canonical_claims = tuple(
        sorted(
            claim_values,
            key=lambda claim: (
                claim.claim_id
            ),
        )
    )

    canonical_assessments = tuple(
        sorted(
            assessment_values,
            key=lambda assessment: (
                assessment.assessment_id
            ),
        )
    )

    canonical_assertions = tuple(
        sorted(
            assertion_values,
            key=lambda assertion: (
                assertion.assertion_id
            ),
        )
    )

    snapshot_id = _identity(
        "world-model-snapshot:",
        {
            "claim_ids": [
                claim.claim_id
                for claim
                in canonical_claims
            ],
            "assessment_ids": [
                assessment.assessment_id
                for assessment
                in canonical_assessments
            ],
            "assertion_ids": [
                assertion.assertion_id
                for assertion
                in canonical_assertions
            ],
        },
    )

    return WorldModelSnapshot(
        claims=canonical_claims,
        assessments=canonical_assessments,
        assertions=canonical_assertions,
        snapshot_id=snapshot_id,
    )
