"""Structured world-model assertions.

A world-model assertion connects:

    subject -> semantic relation -> object

and links that relationship to the exact evidence-backed claim and
epistemic assessment that justify representing it.

This module does not infer relations.

In particular:

- CALLS is not architectural ownership.
- AFFECTS_BEHAVIOR_OF is not CALLS.
- OWNS_RESPONSIBILITY_FOR must be asserted explicitly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

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


class WorldModelAssertionError(
    ValueError
):
    """A world-model assertion could not be represented faithfully."""


class WorldModelRelationKind(
    str,
    Enum,
):
    CALLS = "CALLS"
    DEPENDS_ON = "DEPENDS_ON"
    AFFECTS_BEHAVIOR_OF = "AFFECTS_BEHAVIOR_OF"
    OWNS_RESPONSIBILITY_FOR = "OWNS_RESPONSIBILITY_FOR"


@dataclass(
    frozen=True,
    slots=True,
)
class WorldModelAssertion:
    subject_id: str
    relation: WorldModelRelationKind
    object_id: str
    claim_id: str
    assessment_id: str
    assertion_id: str


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


def _validate_claim(
    claim: EvidenceBackedClaim,
) -> None:
    if not isinstance(
        claim,
        EvidenceBackedClaim,
    ):
        raise WorldModelAssertionError(
            "claim must be an EvidenceBackedClaim"
        )

    try:
        canonical = make_evidence_backed_claim(
            claim.proposition,
            scope=claim.scope,
            evidence=claim.evidence,
        )
    except EvidenceBackedClaimError as exc:
        raise WorldModelAssertionError(
            "claim is invalid"
        ) from exc

    if canonical != claim:
        raise WorldModelAssertionError(
            "claim identity is invalid"
        )


def _validate_assessment(
    claim: EvidenceBackedClaim,
    assessment: EpistemicAssessment,
) -> None:
    if not isinstance(
        assessment,
        EpistemicAssessment,
    ):
        raise WorldModelAssertionError(
            "assessment must be an EpistemicAssessment"
        )

    if (
        assessment.claim_id
        != claim.claim_id
    ):
        raise WorldModelAssertionError(
            "assessment claim does not match claim"
        )

    if len(
        assessment.basis_reference_ids
    ) != len(
        set(
            assessment.basis_reference_ids
        )
    ):
        raise WorldModelAssertionError(
            "assessment contains duplicate basis references"
        )

    references_by_id = {
        reference.reference_id: reference
        for reference in claim.evidence
    }

    try:
        basis = tuple(
            references_by_id[
                reference_id
            ]
            for reference_id
            in assessment.basis_reference_ids
        )
    except KeyError as exc:
        raise WorldModelAssertionError(
            "assessment basis does not belong to claim"
        ) from exc

    try:
        canonical = make_epistemic_assessment(
            claim,
            assessment.status,
            rationale=assessment.rationale,
            basis=basis,
        )
    except EpistemicAssessmentError as exc:
        raise WorldModelAssertionError(
            "assessment is invalid"
        ) from exc

    if canonical != assessment:
        raise WorldModelAssertionError(
            "assessment identity is invalid"
        )


def make_world_model_assertion(
    subject_id: str,
    relation: WorldModelRelationKind,
    object_id: str,
    *,
    claim: EvidenceBackedClaim,
    assessment: EpistemicAssessment,
) -> WorldModelAssertion:
    if (
        not isinstance(
            subject_id,
            str,
        )
        or not subject_id.strip()
    ):
        raise WorldModelAssertionError(
            "subject id must be nonempty"
        )

    if not isinstance(
        relation,
        WorldModelRelationKind,
    ):
        raise WorldModelAssertionError(
            "relation must be a WorldModelRelationKind"
        )

    if (
        not isinstance(
            object_id,
            str,
        )
        or not object_id.strip()
    ):
        raise WorldModelAssertionError(
            "object id must be nonempty"
        )

    _validate_claim(
        claim
    )

    _validate_assessment(
        claim,
        assessment,
    )

    assertion_id = _identity(
        "world-model-assertion:",
        {
            "subject_id": (
                subject_id
            ),
            "relation": (
                relation.value
            ),
            "object_id": (
                object_id
            ),
            "claim_id": (
                claim.claim_id
            ),
            "assessment_id": (
                assessment.assessment_id
            ),
        },
    )

    return WorldModelAssertion(
        subject_id=(
            subject_id
        ),
        relation=(
            relation
        ),
        object_id=(
            object_id
        ),
        claim_id=(
            claim.claim_id
        ),
        assessment_id=(
            assessment.assessment_id
        ),
        assertion_id=(
            assertion_id
        ),
    )
