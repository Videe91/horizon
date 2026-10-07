"""Typed, non-authoritative evaluation of an investigator hypothesis.

This module answers only one bounded question:

Does the evidence in an exact InvestigationRequest support, contradict,
or still fail to resolve an existing PROPOSE_HYPOTHESIS proposal?

An evaluation is not an EvidenceBackedClaim, EpistemicAssessment,
WorldModelAssertion, or semantic-gap closure event. It carries no
authority to mutate Horizon truth.
"""

from __future__ import annotations

import hashlib
import json

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
)


class HypothesisEvaluationError(
    ValueError
):
    """A hypothesis evaluation violates the sealed evidence contract."""


class HypothesisEvaluationVerdict(
    str,
    Enum,
):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    STILL_INCOMPLETE = "STILL_INCOMPLETE"


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvidenceEvaluation:
    request_id: str
    question_id: str

    source_proposal_id: str
    hypothesis: str

    verdict: HypothesisEvaluationVerdict

    supporting_evidence_ids: tuple[
        str,
        ...,
    ]

    contradicting_evidence_ids: tuple[
        str,
        ...,
    ]

    missing_evidence_questions: tuple[
        str,
        ...,
    ]

    evaluation_id: str


_FIELDS = {
    "request_id",
    "question_id",
    "source_proposal_id",
    "verdict",
    "supporting_evidence_ids",
    "contradicting_evidence_ids",
    "missing_evidence_questions",
}


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
        raise HypothesisEvaluationError(
            field
            + " must be a nonempty string"
        )

    return value


def _require_text_list(
    value: object,
    *,
    field: str,
) -> tuple[
    str,
    ...,
]:
    if not isinstance(
        value,
        list,
    ):
        raise HypothesisEvaluationError(
            field
            + " must be an array"
        )

    items = tuple(
        _require_text(
            item,
            field=field,
        )
        for item
        in value
    )

    if (
        len(
            items
        )
        != len(
            set(
                items
            )
        )
    ):
        raise HypothesisEvaluationError(
            field
            + " contains duplicate values"
        )

    return items


def _proposal_kind(
    proposal: InvestigationProposal,
) -> str:
    value = getattr(
        proposal.kind,
        "value",
        proposal.kind,
    )

    if not isinstance(
        value,
        str,
    ):
        raise HypothesisEvaluationError(
            "source proposal kind is invalid"
        )

    return value


def _validate_source_context(
    request: InvestigationRequest,
    proposal: InvestigationProposal,
) -> None:
    for selected, allowed in (
        (
            proposal.assertion_ids,
            request.assertion_ids,
        ),
        (
            proposal.claim_ids,
            request.claim_ids,
        ),
        (
            proposal.assessment_ids,
            request.assessment_ids,
        ),
        (
            proposal.evidence_reference_ids,
            request.evidence_reference_ids,
        ),
    ):
        if not set(
            selected
        ).issubset(
            set(
                allowed
            )
        ):
            raise HypothesisEvaluationError(
                "source proposal context is outside the current request"
            )


def _validate_request_and_proposal(
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
) -> str:
    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise HypothesisEvaluationError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not InvestigationRequestOrigin
        .REPOSITORY_SEMANTIC_GAP
    ):
        raise HypothesisEvaluationError(
            "request must be a repository semantic-gap request"
        )

    if (
        request.relationship_id
        is not None
    ):
        raise HypothesisEvaluationError(
            "semantic-gap hypothesis evaluation may not carry a relationship"
        )

    if not isinstance(
        source_proposal,
        InvestigationProposal,
    ):
        raise HypothesisEvaluationError(
            "source proposal must be an InvestigationProposal"
        )

    if (
        _proposal_kind(
            source_proposal
        )
        != "PROPOSE_HYPOTHESIS"
    ):
        raise HypothesisEvaluationError(
            "source proposal must be PROPOSE_HYPOTHESIS"
        )

    if (
        source_proposal.question_id
        != request.question_id
    ):
        raise HypothesisEvaluationError(
            "source proposal question is outside the current request"
        )

    if (
        source_proposal.relationship_id
        != request.relationship_id
    ):
        raise HypothesisEvaluationError(
            "source proposal relationship is outside the current request"
        )

    _validate_source_context(
        request,
        source_proposal,
    )

    hypothesis = (
        source_proposal.hypothesis
    )

    return _require_text(
        hypothesis,
        field="source hypothesis",
    )


def _request_evidence_ids(
    request: InvestigationRequest,
) -> tuple[
    str,
    ...,
]:
    evidence_ids = tuple(
        record.evidence_id
        for record
        in request.evidence_records
    )

    if (
        len(
            evidence_ids
        )
        != len(
            set(
                evidence_ids
            )
        )
    ):
        raise HypothesisEvaluationError(
            "request contains duplicate evidence identities"
        )

    return evidence_ids


def _validate_evidence_subset(
    values: tuple[
        str,
        ...,
    ],
    *,
    allowed: set[
        str
    ],
    field: str,
) -> tuple[
    str,
    ...,
]:
    outside = (
        set(
            values
        )
        - allowed
    )

    if outside:
        raise HypothesisEvaluationError(
            field
            + " contains evidence outside the request"
        )

    return tuple(
        sorted(
            values
        )
    )


def hypothesis_evaluation_schema() -> dict[
    str,
    object,
]:
    """Strict structured-output schema for one evidence evaluation."""

    evidence_array = {
        "type": "array",
        "items": {
            "type": "string",
        },
        "uniqueItems": True,
    }

    return {
        "type": "object",
        "properties": {
            "request_id": {
                "type": "string",
            },
            "question_id": {
                "type": "string",
            },
            "source_proposal_id": {
                "type": "string",
            },
            "verdict": {
                "type": "string",
                "enum": [
                    (
                        HypothesisEvaluationVerdict
                        .SUPPORTED
                        .value
                    ),
                    (
                        HypothesisEvaluationVerdict
                        .CONTRADICTED
                        .value
                    ),
                    (
                        HypothesisEvaluationVerdict
                        .STILL_INCOMPLETE
                        .value
                    ),
                ],
            },
            "supporting_evidence_ids": (
                dict(
                    evidence_array
                )
            ),
            "contradicting_evidence_ids": (
                dict(
                    evidence_array
                )
            ),
            "missing_evidence_questions": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "uniqueItems": True,
            },
        },
        "required": [
            "request_id",
            "question_id",
            "source_proposal_id",
            "verdict",
            "supporting_evidence_ids",
            "contradicting_evidence_ids",
            "missing_evidence_questions",
        ],
        "additionalProperties": False,
    }


def parse_hypothesis_evaluation(
    *,
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
    raw: Mapping[
        str,
        Any,
    ],
) -> HypothesisEvidenceEvaluation:
    """Validate one model evaluation without creating Horizon truth."""

    hypothesis = (
        _validate_request_and_proposal(
            request,
            source_proposal,
        )
    )

    if not isinstance(
        raw,
        Mapping,
    ):
        raise HypothesisEvaluationError(
            "evaluation must be an object"
        )

    if set(
        raw
    ) != _FIELDS:
        raise HypothesisEvaluationError(
            "evaluation fields do not exactly match the contract"
        )

    request_id = _require_text(
        raw[
            "request_id"
        ],
        field="request id",
    )

    if (
        request_id
        != request.request_id
    ):
        raise HypothesisEvaluationError(
            "request id does not match the current request"
        )

    question_id = _require_text(
        raw[
            "question_id"
        ],
        field="question id",
    )

    if (
        question_id
        != request.question_id
    ):
        raise HypothesisEvaluationError(
            "question id does not match the current request"
        )

    source_proposal_id = _require_text(
        raw[
            "source_proposal_id"
        ],
        field="source proposal id",
    )

    if (
        source_proposal_id
        != source_proposal.proposal_id
    ):
        raise HypothesisEvaluationError(
            "source proposal id does not match the supplied hypothesis"
        )

    try:
        verdict = (
            HypothesisEvaluationVerdict(
                raw[
                    "verdict"
                ]
            )
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise HypothesisEvaluationError(
            "verdict is outside the registered evaluation vocabulary"
        ) from exc

    allowed_evidence = set(
        _request_evidence_ids(
            request
        )
    )

    supporting = (
        _validate_evidence_subset(
            _require_text_list(
                raw[
                    "supporting_evidence_ids"
                ],
                field=(
                    "supporting evidence ids"
                ),
            ),
            allowed=allowed_evidence,
            field=(
                "supporting evidence ids"
            ),
        )
    )

    contradicting = (
        _validate_evidence_subset(
            _require_text_list(
                raw[
                    "contradicting_evidence_ids"
                ],
                field=(
                    "contradicting evidence ids"
                ),
            ),
            allowed=allowed_evidence,
            field=(
                "contradicting evidence ids"
            ),
        )
    )

    missing_questions = (
        _require_text_list(
            raw[
                "missing_evidence_questions"
            ],
            field=(
                "missing evidence questions"
            ),
        )
    )

    overlap = (
        set(
            supporting
        )
        & set(
            contradicting
        )
    )

    if overlap:
        raise HypothesisEvaluationError(
            "the same evidence may not both support and contradict a hypothesis"
        )

    if (
        verdict
        is HypothesisEvaluationVerdict
        .SUPPORTED
    ):
        if (
            not supporting
            or contradicting
            or missing_questions
        ):
            raise HypothesisEvaluationError(
                "SUPPORTED requires supporting evidence, "
                "no contradicting evidence, and no missing evidence questions"
            )

    elif (
        verdict
        is HypothesisEvaluationVerdict
        .CONTRADICTED
    ):
        if (
            supporting
            or not contradicting
            or missing_questions
        ):
            raise HypothesisEvaluationError(
                "CONTRADICTED requires contradicting evidence, "
                "no supporting evidence, and no missing evidence questions"
            )

    else:
        if not missing_questions:
            raise HypothesisEvaluationError(
                "STILL_INCOMPLETE requires at least one missing evidence question"
            )

    canonical_payload = {
        "request_id": (
            request_id
        ),
        "question_id": (
            question_id
        ),
        "source_proposal_id": (
            source_proposal_id
        ),
        "hypothesis": (
            hypothesis
        ),
        "verdict": (
            verdict.value
        ),
        "supporting_evidence_ids": list(
            supporting
        ),
        "contradicting_evidence_ids": list(
            contradicting
        ),
        "missing_evidence_questions": list(
            missing_questions
        ),
    }

    evaluation_id = _identity(
        "hypothesis-evidence-evaluation:",
        canonical_payload,
    )

    return HypothesisEvidenceEvaluation(
        request_id=request_id,
        question_id=question_id,
        source_proposal_id=(
            source_proposal_id
        ),
        hypothesis=hypothesis,
        verdict=verdict,
        supporting_evidence_ids=(
            supporting
        ),
        contradicting_evidence_ids=(
            contradicting
        ),
        missing_evidence_questions=(
            missing_questions
        ),
        evaluation_id=evaluation_id,
    )
