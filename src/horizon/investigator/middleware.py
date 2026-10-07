"""Read-only Horizon context compilation for AI investigation.

The middleware boundary receives already-created Horizon world-model
objects and compiles the exact bounded context associated with one
open question.

This module deliberately does not:

- call a model provider;
- select a model provider;
- create an investigation proposal;
- alter a claim or epistemic assessment;
- alter a world-model assertion;
- resolve a conflict;
- mutate Horizon state.

Models receive compiled Horizon context.

They do not receive direct Horizon access.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass
from enum import Enum

from horizon.claims.epistemic import (
    EpistemicAssessment,
)
from horizon.claims.evidence_backed import (
    EvidenceBackedClaim,
)
from horizon.investigation.semantic_gap import (
    RepositorySemanticGapQuestion,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
)
from horizon.world_model.reconciliation import (
    WorldModelRelationshipAnalysis,
)
from horizon.world_model.repository_deterministic import (
    RepositoryDeterministicWorldModel,
)
from horizon.world_model.snapshot import (
    WorldModelSnapshot,
)


class InvestigationMiddlewareError(
    ValueError
):
    """Bounded investigation context could not be compiled faithfully."""


class InvestigationRequestOrigin(
    str,
    Enum,
):
    WORLD_MODEL_CONFLICT = (
        "WORLD_MODEL_CONFLICT"
    )

    REPOSITORY_SEMANTIC_GAP = (
        "REPOSITORY_SEMANTIC_GAP"
    )


@dataclass(
    frozen=True,
    slots=True,
)
class CanonicalEvidenceRecord:
    """Canonical content for one Horizon evidence identity."""

    evidence_id: str
    evidence_kind: str
    canonical_payload: str


@dataclass(
    frozen=True,
    slots=True,
)
class HorizonInvestigationView:
    """Read-only Horizon state made available to the middleware."""

    snapshot: WorldModelSnapshot
    analysis: WorldModelRelationshipAnalysis
    evidence_records: tuple[
        CanonicalEvidenceRecord,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationRequest:
    """Deterministic bounded context for one unresolved question."""

    question_id: str
    question: str

    relationship_id: str | None
    relationship_kind: str | None
    relationship_reason: str | None

    assertions: tuple[
        WorldModelAssertion,
        ...,
    ]

    claims: tuple[
        EvidenceBackedClaim,
        ...,
    ]

    assessments: tuple[
        EpistemicAssessment,
        ...,
    ]

    evidence_reference_ids: tuple[
        str,
        ...,
    ]

    evidence_records: tuple[
        CanonicalEvidenceRecord,
        ...,
    ]

    request_id: str

    origin: InvestigationRequestOrigin = (
        InvestigationRequestOrigin
        .WORLD_MODEL_CONFLICT
    )

    semantic_gap_id: str | None = None
    semantic_gap_section: str | None = None

    @property
    def assertion_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            assertion.assertion_id
            for assertion
            in self.assertions
        )

    @property
    def claim_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            claim.claim_id
            for claim
            in self.claims
        )

    @property
    def assessment_ids(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            assessment.assessment_id
            for assessment
            in self.assessments
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


def _validate_evidence_record(
    record: CanonicalEvidenceRecord,
) -> None:
    if not isinstance(
        record,
        CanonicalEvidenceRecord,
    ):
        raise InvestigationMiddlewareError(
            "evidence records must contain "
            "CanonicalEvidenceRecord values"
        )

    if (
        not isinstance(
            record.evidence_id,
            str,
        )
        or not record.evidence_id.strip()
    ):
        raise InvestigationMiddlewareError(
            "evidence id must be nonempty"
        )

    if (
        not isinstance(
            record.evidence_kind,
            str,
        )
        or not record.evidence_kind.strip()
    ):
        raise InvestigationMiddlewareError(
            "evidence kind must be nonempty"
        )

    if (
        not isinstance(
            record.canonical_payload,
            str,
        )
        or not record.canonical_payload.strip()
    ):
        raise InvestigationMiddlewareError(
            "canonical evidence payload must be nonempty"
        )


def _claim_payload(
    claim: EvidenceBackedClaim,
) -> dict[str, object]:
    return {
        "claim_id": claim.claim_id,
        "proposition": claim.proposition,
        "scope": claim.scope,
        "evidence": [
            {
                "evidence_id": reference.evidence_id,
                "evidence_kind": (
                    reference.evidence_kind.value
                ),
                "reference_id": (
                    reference.reference_id
                ),
                "relation": (
                    reference.relation.value
                ),
            }
            for reference
            in claim.evidence
        ],
    }


def _assessment_payload(
    assessment: EpistemicAssessment,
) -> dict[str, object]:
    return {
        "assessment_id": assessment.assessment_id,
        "basis_reference_ids": list(
            assessment.basis_reference_ids
        ),
        "claim_id": assessment.claim_id,
        "rationale": assessment.rationale,
        "status": assessment.status.value,
    }


def _assertion_payload(
    assertion: WorldModelAssertion,
) -> dict[str, object]:
    return {
        "assertion_id": assertion.assertion_id,
        "assessment_id": assertion.assessment_id,
        "claim_id": assertion.claim_id,
        "object_id": assertion.object_id,
        "relation": assertion.relation.value,
        "subject_id": assertion.subject_id,
    }


def _evidence_record_payload(
    record: CanonicalEvidenceRecord,
) -> dict[str, object]:
    return {
        "canonical_payload": (
            record.canonical_payload
        ),
        "evidence_id": record.evidence_id,
        "evidence_kind": record.evidence_kind,
    }


def compile_investigation_request(
    view: HorizonInvestigationView,
    *,
    question_id: str,
) -> InvestigationRequest:
    """Compile one exact open-question context without mutating Horizon."""

    if not isinstance(
        view,
        HorizonInvestigationView,
    ):
        raise InvestigationMiddlewareError(
            "view must be a HorizonInvestigationView"
        )

    if not isinstance(
        view.snapshot,
        WorldModelSnapshot,
    ):
        raise InvestigationMiddlewareError(
            "view snapshot must be a WorldModelSnapshot"
        )

    if not isinstance(
        view.analysis,
        WorldModelRelationshipAnalysis,
    ):
        raise InvestigationMiddlewareError(
            "view analysis must be a "
            "WorldModelRelationshipAnalysis"
        )

    if (
        not isinstance(
            question_id,
            str,
        )
        or not question_id.strip()
    ):
        raise InvestigationMiddlewareError(
            "question id must be nonempty"
        )

    questions = tuple(
        question
        for question
        in view.analysis.open_questions
        if question.question_id == question_id
    )

    if len(
        questions
    ) != 1:
        raise InvestigationMiddlewareError(
            "question id must identify exactly one open question"
        )

    question = questions[0]

    relationships = tuple(
        relationship
        for relationship
        in view.analysis.relationships
        if (
            relationship.relationship_id
            == question.relationship_id
        )
    )

    if len(
        relationships
    ) != 1:
        raise InvestigationMiddlewareError(
            "open question relationship must exist exactly once"
        )

    relationship = relationships[0]

    if (
        tuple(
            sorted(
                question.assertion_ids
            )
        )
        != tuple(
            sorted(
                relationship.assertion_ids
            )
        )
    ):
        raise InvestigationMiddlewareError(
            "open question assertions do not match relationship"
        )

    assertions_by_id = {
        assertion.assertion_id: assertion
        for assertion
        in view.snapshot.assertions
    }

    claims_by_id = {
        claim.claim_id: claim
        for claim
        in view.snapshot.claims
    }

    assessments_by_id = {
        assessment.assessment_id: assessment
        for assessment
        in view.snapshot.assessments
    }

    try:
        assertions = tuple(
            sorted(
                (
                    assertions_by_id[
                        assertion_id
                    ]
                    for assertion_id
                    in question.assertion_ids
                ),
                key=lambda item: (
                    item.assertion_id
                ),
            )
        )
    except KeyError as exc:
        raise InvestigationMiddlewareError(
            "open question references an assertion "
            "outside the snapshot"
        ) from exc

    claim_ids = tuple(
        sorted(
            {
                assertion.claim_id
                for assertion
                in assertions
            }
        )
    )

    assessment_ids = tuple(
        sorted(
            {
                assertion.assessment_id
                for assertion
                in assertions
            }
        )
    )

    try:
        claims = tuple(
            claims_by_id[
                claim_id
            ]
            for claim_id
            in claim_ids
        )

        assessments = tuple(
            assessments_by_id[
                assessment_id
            ]
            for assessment_id
            in assessment_ids
        )
    except KeyError as exc:
        raise InvestigationMiddlewareError(
            "open question context is not closed "
            "over claims and assessments"
        ) from exc

    if any(
        assessment.claim_id
        not in {
            claim.claim_id
            for claim
            in claims
        }
        for assessment
        in assessments
    ):
        raise InvestigationMiddlewareError(
            "assessment references a claim "
            "outside the bounded request"
        )

    references_by_id = {
        reference.reference_id: reference
        for claim
        in claims
        for reference
        in claim.evidence
    }

    requested_reference_ids = tuple(
        sorted(
            set(
                question.evidence_reference_ids
            )
        )
    )

    if (
        len(
            requested_reference_ids
        )
        != len(
            question.evidence_reference_ids
        )
    ):
        raise InvestigationMiddlewareError(
            "open question contains duplicate "
            "evidence references"
        )

    missing_reference_ids = (
        set(
            requested_reference_ids
        )
        - set(
            references_by_id
        )
    )

    if missing_reference_ids:
        raise InvestigationMiddlewareError(
            "open question references evidence "
            "outside its bounded claims"
        )

    evidence_ids = tuple(
        sorted(
            {
                references_by_id[
                    reference_id
                ].evidence_id
                for reference_id
                in requested_reference_ids
            }
        )
    )

    records_by_id: dict[
        str,
        CanonicalEvidenceRecord,
    ] = {}

    for record in view.evidence_records:
        _validate_evidence_record(
            record
        )

        if record.evidence_id in records_by_id:
            raise InvestigationMiddlewareError(
                "duplicate canonical evidence identity"
            )

        records_by_id[
            record.evidence_id
        ] = record

    missing_evidence_ids = (
        set(
            evidence_ids
        )
        - set(
            records_by_id
        )
    )

    if missing_evidence_ids:
        raise InvestigationMiddlewareError(
            "canonical evidence content is missing "
            "for the bounded request"
        )

    evidence_records = tuple(
        records_by_id[
            evidence_id
        ]
        for evidence_id
        in evidence_ids
    )

    relationship_reason = (
        relationship.reason.value
        if relationship.reason is not None
        else None
    )

    canonical_payload = {
        "assessments": [
            _assessment_payload(
                assessment
            )
            for assessment
            in assessments
        ],
        "assertions": [
            _assertion_payload(
                assertion
            )
            for assertion
            in assertions
        ],
        "claims": [
            _claim_payload(
                claim
            )
            for claim
            in claims
        ],
        "evidence_records": [
            _evidence_record_payload(
                record
            )
            for record
            in evidence_records
        ],
        "evidence_reference_ids": list(
            requested_reference_ids
        ),
        "question": question.question,
        "question_id": question.question_id,
        "relationship_id": (
            relationship.relationship_id
        ),
        "relationship_kind": (
            relationship.kind.value
        ),
        "relationship_reason": (
            relationship_reason
        ),
    }

    request_id = _identity(
        "investigation-request:",
        canonical_payload,
    )

    return InvestigationRequest(
        question_id=question.question_id,
        question=question.question,
        relationship_id=(
            relationship.relationship_id
        ),
        relationship_kind=(
            relationship.kind.value
        ),
        relationship_reason=(
            relationship_reason
        ),
        assertions=assertions,
        claims=claims,
        assessments=assessments,
        evidence_reference_ids=(
            requested_reference_ids
        ),
        evidence_records=(
            evidence_records
        ),
        request_id=request_id,
    )


def _semantic_gap_context(
    question: RepositorySemanticGapQuestion,
    model: RepositoryDeterministicWorldModel,
) -> tuple[
    tuple[
        WorldModelAssertion,
        ...,
    ],
    tuple[
        EvidenceBackedClaim,
        ...,
    ],
    tuple[
        EpistemicAssessment,
        ...,
    ],
    tuple[
        str,
        ...,
    ],
]:
    snapshot = model.snapshot

    assertions_by_id = {
        assertion.assertion_id: assertion
        for assertion
        in snapshot.assertions
    }

    claims_by_id = {
        claim.claim_id: claim
        for claim
        in snapshot.claims
    }

    assessments_by_id = {
        assessment.assessment_id: assessment
        for assessment
        in snapshot.assessments
    }

    try:
        assertions = tuple(
            sorted(
                (
                    assertions_by_id[
                        assertion_id
                    ]
                    for assertion_id
                    in question.context_assertion_ids
                ),
                key=lambda item: (
                    item.assertion_id
                ),
            )
        )
    except KeyError as exc:
        raise InvestigationMiddlewareError(
            "semantic gap context references "
            "an assertion outside its World Model snapshot"
        ) from exc

    expected_claim_ids = tuple(
        sorted(
            {
                assertion.claim_id
                for assertion
                in assertions
            }
        )
    )

    expected_assessment_ids = tuple(
        sorted(
            {
                assertion.assessment_id
                for assertion
                in assertions
            }
        )
    )

    if (
        question.context_claim_ids
        != expected_claim_ids
    ):
        raise InvestigationMiddlewareError(
            "semantic gap context claims do not "
            "match its assertion closure"
        )

    if (
        question.context_assessment_ids
        != expected_assessment_ids
    ):
        raise InvestigationMiddlewareError(
            "semantic gap context assessments do not "
            "match its assertion closure"
        )

    try:
        claims = tuple(
            claims_by_id[
                claim_id
            ]
            for claim_id
            in expected_claim_ids
        )

        assessments = tuple(
            assessments_by_id[
                assessment_id
            ]
            for assessment_id
            in expected_assessment_ids
        )
    except KeyError as exc:
        raise InvestigationMiddlewareError(
            "semantic gap context is not closed "
            "over claims and assessments"
        ) from exc

    claims_for_assessment = {
        claim.claim_id: claim
        for claim
        in claims
    }

    basis_reference_ids: set[
        str
    ] = set()

    for assessment in assessments:
        claim = claims_for_assessment.get(
            assessment.claim_id
        )

        if claim is None:
            raise InvestigationMiddlewareError(
                "semantic gap context assessment "
                "references a claim outside the context"
            )

        references_by_id = {
            reference.reference_id: reference
            for reference
            in claim.evidence
        }

        for reference_id in (
            assessment.basis_reference_ids
        ):
            if (
                reference_id
                not in references_by_id
            ):
                raise InvestigationMiddlewareError(
                    "semantic gap context assessment "
                    "basis is not attached to its claim"
                )

            basis_reference_ids.add(
                reference_id
            )

    expected_reference_ids = tuple(
        sorted(
            basis_reference_ids
        )
    )

    if (
        question.context_evidence_reference_ids
        != expected_reference_ids
    ):
        raise InvestigationMiddlewareError(
            "semantic gap context evidence references "
            "do not match its assessment basis closure"
        )

    return (
        assertions,
        claims,
        assessments,
        expected_reference_ids,
    )


def compile_semantic_gap_investigation_request(
    question: RepositorySemanticGapQuestion,
    *,
    model: RepositoryDeterministicWorldModel,
    evidence_records: tuple[
        CanonicalEvidenceRecord,
        ...,
    ],
) -> InvestigationRequest:
    """Compile one ordinary semantic gap into bounded read-only context.

    This path does not create or pretend that a World Model relationship
    exists. Relationship fields are explicitly absent.

    It performs no model call and no World Model mutation.
    """

    if not isinstance(
        question,
        RepositorySemanticGapQuestion,
    ):
        raise InvestigationMiddlewareError(
            "question must be a RepositorySemanticGapQuestion"
        )

    if not isinstance(
        model,
        RepositoryDeterministicWorldModel,
    ):
        raise InvestigationMiddlewareError(
            "model must be a RepositoryDeterministicWorldModel"
        )

    if (
        question.source_commit
        != model.source_commit
        or question.repository_observation_id
        != model.repository_observation_id
        or question.world_model_snapshot_id
        != model.snapshot.snapshot_id
    ):
        raise InvestigationMiddlewareError(
            "semantic gap question and World Model "
            "do not represent the same snapshot"
        )

    if not isinstance(
        evidence_records,
        tuple,
    ):
        raise InvestigationMiddlewareError(
            "evidence_records must be a tuple"
        )

    (
        assertions,
        claims,
        assessments,
        evidence_reference_ids,
    ) = _semantic_gap_context(
        question,
        model,
    )

    references_by_id = {
        reference.reference_id: reference
        for claim
        in claims
        for reference
        in claim.evidence
    }

    try:
        required_evidence_ids = tuple(
            sorted(
                {
                    references_by_id[
                        reference_id
                    ].evidence_id
                    for reference_id
                    in evidence_reference_ids
                }
            )
        )
    except KeyError as exc:
        raise InvestigationMiddlewareError(
            "semantic gap evidence reference "
            "is outside the bounded claims"
        ) from exc

    records_by_id: dict[
        str,
        CanonicalEvidenceRecord,
    ] = {}

    for record in evidence_records:
        _validate_evidence_record(
            record
        )

        if (
            record.evidence_id
            in records_by_id
        ):
            raise InvestigationMiddlewareError(
                "duplicate canonical evidence identity"
            )

        records_by_id[
            record.evidence_id
        ] = record

    missing_evidence_ids = (
        set(
            required_evidence_ids
        )
        - set(
            records_by_id
        )
    )

    if missing_evidence_ids:
        raise InvestigationMiddlewareError(
            "canonical evidence content is missing "
            "for the bounded semantic gap request"
        )

    selected_records = tuple(
        records_by_id[
            evidence_id
        ]
        for evidence_id
        in required_evidence_ids
    )

    canonical_payload = {
        "origin": (
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
            .value
        ),
        "question": (
            question.question
        ),
        "question_id": (
            question.question_id
        ),
        "semantic_gap_id": (
            question.gap_id
        ),
        "semantic_gap_section": (
            question.section.value
        ),
        "relationship_id": None,
        "relationship_kind": None,
        "relationship_reason": None,
        "assertions": [
            _assertion_payload(
                assertion
            )
            for assertion
            in assertions
        ],
        "claims": [
            _claim_payload(
                claim
            )
            for claim
            in claims
        ],
        "assessments": [
            _assessment_payload(
                assessment
            )
            for assessment
            in assessments
        ],
        "evidence_reference_ids": list(
            evidence_reference_ids
        ),
        "evidence_records": [
            _evidence_record_payload(
                record
            )
            for record
            in selected_records
        ],
    }

    request_id = _identity(
        "investigation-request:",
        canonical_payload,
    )

    return InvestigationRequest(
        question_id=(
            question.question_id
        ),
        question=(
            question.question
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=assertions,
        claims=claims,
        assessments=assessments,
        evidence_reference_ids=(
            evidence_reference_ids
        ),
        evidence_records=(
            selected_records
        ),
        request_id=request_id,
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            question.gap_id
        ),
        semantic_gap_section=(
            question.section.value
        ),
    )
