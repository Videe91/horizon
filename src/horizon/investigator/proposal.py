"""Strict model-proposal boundary for Horizon investigation.

A model may propose only one of four typed actions:

- PROPOSE_INVESTIGATION
- PROPOSE_HYPOTHESIS
- REFINE_OBJECT
- DECLARE_INSUFFICIENT_EVIDENCE

A proposal is not evidence, a claim, an epistemic assessment, a
world-model assertion, or a world-model mutation.

Existing Horizon identifiers form a closed set derived from the exact
InvestigationRequest supplied to the model.

REFINE_OBJECT candidate identities are assigned deterministically by
Horizon after validation. A model may never author those identities.
"""

from __future__ import annotations

import hashlib
import json

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from horizon.investigator.middleware import (
    InvestigationRequest,
)


class InvestigationProposalError(
    ValueError
):
    """A model proposal failed the Horizon authority boundary."""


class InvestigationProposalKind(
    str,
    Enum,
):
    PROPOSE_INVESTIGATION = "PROPOSE_INVESTIGATION"
    PROPOSE_HYPOTHESIS = "PROPOSE_HYPOTHESIS"
    REFINE_OBJECT = "REFINE_OBJECT"
    DECLARE_INSUFFICIENT_EVIDENCE = (
        "DECLARE_INSUFFICIENT_EVIDENCE"
    )


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationCandidate:
    label: str
    investigation_question: str
    candidate_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationProposal:
    kind: InvestigationProposalKind

    question_id: str
    relationship_id: str | None

    assertion_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    assessment_ids: tuple[str, ...]
    evidence_reference_ids: tuple[str, ...]

    investigation_questions: tuple[str, ...] = ()
    hypothesis: str | None = None
    test_questions: tuple[str, ...] = ()
    candidates: tuple[
        InvestigationCandidate,
        ...,
    ] = ()
    missing_evidence_questions: tuple[str, ...] = ()

    proposal_id: str = ""


_COMMON_FIELDS = frozenset(
    {
        "type",
        "question_id",
        "relationship_id",
        "assertion_ids",
        "claim_ids",
        "assessment_ids",
        "evidence_reference_ids",
    }
)


_ALLOWED_FIELDS = {
    InvestigationProposalKind.PROPOSE_INVESTIGATION: (
        _COMMON_FIELDS
        | {
            "investigation_questions",
        }
    ),
    InvestigationProposalKind.PROPOSE_HYPOTHESIS: (
        _COMMON_FIELDS
        | {
            "hypothesis",
            "test_questions",
        }
    ),
    InvestigationProposalKind.REFINE_OBJECT: (
        _COMMON_FIELDS
        | {
            "candidates",
            "missing_evidence_questions",
        }
    ),
    InvestigationProposalKind.DECLARE_INSUFFICIENT_EVIDENCE: (
        _COMMON_FIELDS
        | {
            "missing_evidence_questions",
        }
    ),
}


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


def _require_text(
    value: object,
    *,
    field: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise InvestigationProposalError(
            f"{field} must be a nonempty string"
        )

    return value


def _require_text_sequence(
    value: object,
    *,
    field: str,
    minimum: int = 1,
) -> tuple[str, ...]:
    if (
        isinstance(
            value,
            str,
        )
        or not isinstance(
            value,
            Sequence,
        )
    ):
        raise InvestigationProposalError(
            f"{field} must be a sequence of strings"
        )

    values = tuple(
        _require_text(
            item,
            field=field,
        )
        for item in value
    )

    if len(
        values
    ) < minimum:
        raise InvestigationProposalError(
            f"{field} requires at least {minimum} value(s)"
        )

    if len(
        values
    ) != len(
        set(
            values
        )
    ):
        raise InvestigationProposalError(
            f"{field} contains duplicate values"
        )

    return values


def _require_identifier_subset(
    value: object,
    *,
    field: str,
    allowed: tuple[str, ...],
) -> tuple[str, ...]:
    identifiers = _require_text_sequence(
        value,
        field=field,
        minimum=(
            1
            if allowed
            else 0
        ),
    )

    allowed_set = set(
        allowed
    )

    if not set(
        identifiers
    ).issubset(
        allowed_set
    ):
        raise InvestigationProposalError(
            f"{field} contains an identifier "
            "outside the investigation request"
        )

    return tuple(
        sorted(
            identifiers
        )
    )


def _validate_exact_fields(
    raw: Mapping[str, Any],
    *,
    kind: InvestigationProposalKind,
) -> None:
    actual = set(
        raw
    )

    expected = set(
        _ALLOWED_FIELDS[
            kind
        ]
    )

    if actual != expected:
        extra = tuple(
            sorted(
                actual
                - expected
            )
        )

        missing = tuple(
            sorted(
                expected
                - actual
            )
        )

        detail = []

        if extra:
            detail.append(
                "extra="
                + ",".join(
                    extra
                )
            )

        if missing:
            detail.append(
                "missing="
                + ",".join(
                    missing
                )
            )

        raise InvestigationProposalError(
            "proposal fields do not match strict schema"
            + (
                ": "
                + "; ".join(
                    detail
                )
                if detail
                else ""
            )
        )


def _candidate_from_raw(
    request: InvestigationRequest,
    raw: object,
) -> InvestigationCandidate:
    if not isinstance(
        raw,
        Mapping,
    ):
        raise InvestigationProposalError(
            "REFINE_OBJECT candidates must be objects"
        )

    if set(
        raw
    ) != {
        "label",
        "investigation_question",
    }:
        raise InvestigationProposalError(
            "REFINE_OBJECT candidate fields "
            "do not match strict schema"
        )

    label = _require_text(
        raw[
            "label"
        ],
        field="candidate label",
    )

    investigation_question = _require_text(
        raw[
            "investigation_question"
        ],
        field="candidate investigation_question",
    )

    candidate_id = _identity(
        "investigation-candidate:",
        {
            "investigation_question": (
                investigation_question
            ),
            "label": label,
            "request_id": (
                request.request_id
            ),
        },
    )

    return InvestigationCandidate(
        label=label,
        investigation_question=(
            investigation_question
        ),
        candidate_id=candidate_id,
    )


def _parse_candidates(
    request: InvestigationRequest,
    value: object,
) -> tuple[
    InvestigationCandidate,
    ...,
]:
    if (
        isinstance(
            value,
            str,
        )
        or not isinstance(
            value,
            Sequence,
        )
    ):
        raise InvestigationProposalError(
            "candidates must be a sequence"
        )

    candidates = tuple(
        _candidate_from_raw(
            request,
            item,
        )
        for item
        in value
    )

    if len(
        candidates
    ) < 2:
        raise InvestigationProposalError(
            "REFINE_OBJECT requires at least two candidates"
        )

    candidate_ids = tuple(
        candidate.candidate_id
        for candidate
        in candidates
    )

    if len(
        candidate_ids
    ) != len(
        set(
            candidate_ids
        )
    ):
        raise InvestigationProposalError(
            "REFINE_OBJECT contains duplicate candidates"
        )

    return candidates


def _common_payload(
    *,
    kind: InvestigationProposalKind,
    question_id: str,
    relationship_id: str | None,
    assertion_ids: tuple[str, ...],
    claim_ids: tuple[str, ...],
    assessment_ids: tuple[str, ...],
    evidence_reference_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "assessment_ids": list(
            assessment_ids
        ),
        "assertion_ids": list(
            assertion_ids
        ),
        "claim_ids": list(
            claim_ids
        ),
        "evidence_reference_ids": list(
            evidence_reference_ids
        ),
        "question_id": question_id,
        "relationship_id": relationship_id,
        "type": kind.value,
    }


def parse_investigation_proposal(
    request: InvestigationRequest,
    raw: Mapping[str, Any],
) -> InvestigationProposal:
    """Validate one model proposal against an exact Horizon request."""

    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise InvestigationProposalError(
            "request must be an InvestigationRequest"
        )

    if not isinstance(
        raw,
        Mapping,
    ):
        raise InvestigationProposalError(
            "proposal must be an object"
        )

    raw_type = raw.get(
        "type"
    )

    try:
        kind = InvestigationProposalKind(
            raw_type
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise InvestigationProposalError(
            "unknown investigation proposal type"
        ) from exc

    _validate_exact_fields(
        raw,
        kind=kind,
    )

    question_id = _require_text(
        raw[
            "question_id"
        ],
        field="question_id",
    )

    if question_id != request.question_id:
        raise InvestigationProposalError(
            "question_id is outside the request"
        )

    raw_relationship_id = raw[
        "relationship_id"
    ]

    if request.relationship_id is None:
        if raw_relationship_id is not None:
            raise InvestigationProposalError(
                "relationship_id is outside the request"
            )

        relationship_id = None

    else:
        relationship_id = _require_text(
            raw_relationship_id,
            field="relationship_id",
        )

        if (
            relationship_id
            != request.relationship_id
        ):
            raise InvestigationProposalError(
                "relationship_id is outside the request"
            )

    assertion_ids = _require_identifier_subset(
        raw[
            "assertion_ids"
        ],
        field="assertion_ids",
        allowed=request.assertion_ids,
    )

    claim_ids = _require_identifier_subset(
        raw[
            "claim_ids"
        ],
        field="claim_ids",
        allowed=request.claim_ids,
    )

    assessment_ids = _require_identifier_subset(
        raw[
            "assessment_ids"
        ],
        field="assessment_ids",
        allowed=request.assessment_ids,
    )

    evidence_reference_ids = (
        _require_identifier_subset(
            raw[
                "evidence_reference_ids"
            ],
            field="evidence_reference_ids",
            allowed=(
                request.evidence_reference_ids
            ),
        )
    )

    investigation_questions: tuple[
        str,
        ...,
    ] = ()

    hypothesis: str | None = None

    test_questions: tuple[
        str,
        ...,
    ] = ()

    candidates: tuple[
        InvestigationCandidate,
        ...,
    ] = ()

    missing_evidence_questions: tuple[
        str,
        ...,
    ] = ()

    specific_payload: dict[
        str,
        object,
    ]

    if (
        kind
        is InvestigationProposalKind.PROPOSE_INVESTIGATION
    ):
        investigation_questions = (
            _require_text_sequence(
                raw[
                    "investigation_questions"
                ],
                field="investigation_questions",
            )
        )

        specific_payload = {
            "investigation_questions": list(
                investigation_questions
            ),
        }

    elif (
        kind
        is InvestigationProposalKind.PROPOSE_HYPOTHESIS
    ):
        hypothesis = _require_text(
            raw[
                "hypothesis"
            ],
            field="hypothesis",
        )

        test_questions = (
            _require_text_sequence(
                raw[
                    "test_questions"
                ],
                field="test_questions",
            )
        )

        specific_payload = {
            "hypothesis": hypothesis,
            "test_questions": list(
                test_questions
            ),
        }

    elif (
        kind
        is InvestigationProposalKind.REFINE_OBJECT
    ):
        candidates = _parse_candidates(
            request,
            raw[
                "candidates"
            ],
        )

        missing_evidence_questions = (
            _require_text_sequence(
                raw[
                    "missing_evidence_questions"
                ],
                field="missing_evidence_questions",
            )
        )

        specific_payload = {
            "candidates": [
                {
                    "candidate_id": (
                        candidate.candidate_id
                    ),
                    "investigation_question": (
                        candidate.investigation_question
                    ),
                    "label": (
                        candidate.label
                    ),
                }
                for candidate
                in candidates
            ],
            "missing_evidence_questions": list(
                missing_evidence_questions
            ),
        }

    else:
        missing_evidence_questions = (
            _require_text_sequence(
                raw[
                    "missing_evidence_questions"
                ],
                field="missing_evidence_questions",
            )
        )

        specific_payload = {
            "missing_evidence_questions": list(
                missing_evidence_questions
            ),
        }

    canonical_payload = _common_payload(
        kind=kind,
        question_id=question_id,
        relationship_id=relationship_id,
        assertion_ids=assertion_ids,
        claim_ids=claim_ids,
        assessment_ids=assessment_ids,
        evidence_reference_ids=(
            evidence_reference_ids
        ),
    )

    canonical_payload.update(
        specific_payload
    )

    proposal_id = _identity(
        "investigation-proposal:",
        canonical_payload,
    )

    return InvestigationProposal(
        kind=kind,
        question_id=question_id,
        relationship_id=relationship_id,
        assertion_ids=assertion_ids,
        claim_ids=claim_ids,
        assessment_ids=assessment_ids,
        evidence_reference_ids=(
            evidence_reference_ids
        ),
        investigation_questions=(
            investigation_questions
        ),
        hypothesis=hypothesis,
        test_questions=test_questions,
        candidates=candidates,
        missing_evidence_questions=(
            missing_evidence_questions
        ),
        proposal_id=proposal_id,
    )
