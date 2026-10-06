"""First-class claims backed by explicit evidence.

This module records:

- a proposition
- the explicit scope in which that proposition is asserted
- evidence references that support or contradict it

It deliberately does not assign epistemic status.

Evidence kind answers "what kind of evidence is this?"
Epistemic status answers "how strongly should Horizon believe the claim?"

Those are separate concerns.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class EvidenceBackedClaimError(
    ValueError
):
    """An evidence-backed claim could not be represented faithfully."""


class ClaimEvidenceKind(
    str,
    Enum,
):
    STATIC = "STATIC"
    RUNTIME = "RUNTIME"
    CAUSAL = "CAUSAL"


class ClaimEvidenceRelation(
    str,
    Enum,
):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"


@dataclass(
    frozen=True,
    slots=True,
)
class ClaimEvidenceReference:
    evidence_kind: ClaimEvidenceKind
    relation: ClaimEvidenceRelation
    evidence_id: str
    reference_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceBackedClaim:
    proposition: str
    scope: str
    evidence: tuple[
        ClaimEvidenceReference,
        ...,
    ]
    claim_id: str


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


def make_claim_evidence_reference(
    evidence_kind: ClaimEvidenceKind,
    relation: ClaimEvidenceRelation,
    evidence_id: str,
) -> ClaimEvidenceReference:
    if not isinstance(
        evidence_kind,
        ClaimEvidenceKind,
    ):
        raise EvidenceBackedClaimError(
            "evidence kind must be a ClaimEvidenceKind"
        )

    if not isinstance(
        relation,
        ClaimEvidenceRelation,
    ):
        raise EvidenceBackedClaimError(
            "evidence relation must be a ClaimEvidenceRelation"
        )

    if (
        not isinstance(
            evidence_id,
            str,
        )
        or not evidence_id.strip()
    ):
        raise EvidenceBackedClaimError(
            "evidence id must be nonempty"
        )

    reference_id = _identity(
        "claim-evidence-reference:",
        {
            "evidence_kind": (
                evidence_kind.value
            ),
            "relation": (
                relation.value
            ),
            "evidence_id": (
                evidence_id
            ),
        },
    )

    return ClaimEvidenceReference(
        evidence_kind=(
            evidence_kind
        ),
        relation=(
            relation
        ),
        evidence_id=(
            evidence_id
        ),
        reference_id=(
            reference_id
        ),
    )


def _evidence_sort_key(
    reference: ClaimEvidenceReference,
) -> tuple[
    str,
    str,
    str,
    str,
]:
    return (
        reference.evidence_kind.value,
        reference.relation.value,
        reference.evidence_id,
        reference.reference_id,
    )


def make_evidence_backed_claim(
    proposition: str,
    *,
    scope: str,
    evidence: Iterable[
        ClaimEvidenceReference
    ],
) -> EvidenceBackedClaim:
    if (
        not isinstance(
            proposition,
            str,
        )
        or not proposition.strip()
    ):
        raise EvidenceBackedClaimError(
            "proposition must be nonempty"
        )

    if (
        not isinstance(
            scope,
            str,
        )
        or not scope.strip()
    ):
        raise EvidenceBackedClaimError(
            "scope must be explicit and nonempty"
        )

    references = tuple(
        evidence
    )

    if not references:
        raise EvidenceBackedClaimError(
            "claim requires evidence"
        )

    for reference in references:
        if not isinstance(
            reference,
            ClaimEvidenceReference,
        ):
            raise EvidenceBackedClaimError(
                "claim evidence must contain "
                "ClaimEvidenceReference values"
            )

    reference_ids = [
        reference.reference_id
        for reference in references
    ]

    if len(
        set(
            reference_ids
        )
    ) != len(
        reference_ids
    ):
        raise EvidenceBackedClaimError(
            "duplicate evidence reference"
        )

    relations_by_evidence: dict[
        tuple[
            ClaimEvidenceKind,
            str,
        ],
        set[
            ClaimEvidenceRelation
        ],
    ] = {}

    for reference in references:
        key = (
            reference.evidence_kind,
            reference.evidence_id,
        )

        relations_by_evidence.setdefault(
            key,
            set(),
        ).add(
            reference.relation
        )

    for relations in (
        relations_by_evidence.values()
    ):
        if (
            ClaimEvidenceRelation.SUPPORTS
            in relations
            and ClaimEvidenceRelation.CONTRADICTS
            in relations
        ):
            raise EvidenceBackedClaimError(
                "the same evidence cannot "
                "support and contradict "
                "the same claim"
            )

    ordered_evidence = tuple(
        sorted(
            references,
            key=_evidence_sort_key,
        )
    )

    claim_id = _identity(
        "evidence-backed-claim:",
        {
            "proposition": (
                proposition
            ),
            "scope": (
                scope
            ),
            "evidence": [
                reference.reference_id
                for reference
                in ordered_evidence
            ],
        },
    )

    return EvidenceBackedClaim(
        proposition=(
            proposition
        ),
        scope=(
            scope
        ),
        evidence=(
            ordered_evidence
        ),
        claim_id=(
            claim_id
        ),
    )
