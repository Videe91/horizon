"""First-class repository semantic gaps.

A semantic gap means Horizon does not yet have a selected canonical
World Model assertion for one repository-understanding section.

A gap is not:

- evidence;
- a claim;
- a hypothesis;
- an epistemic assessment;
- a World Model assertion;
- an AI answer.

It is a deterministic question bound to an exact repository observation
and exact World Model snapshot.

Existing canonical repository assertions are attached only as bounded
read-only context for later investigation.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass
from enum import Enum

from horizon.repository.python_index import (
    PythonRepositoryIndex,
)
from horizon.world_model.repository_deterministic import (
    RepositoryDeterministicWorldModel,
)


class RepositorySemanticGapError(
    ValueError
):
    """Repository semantic gaps cannot be derived faithfully."""


class RepositorySemanticGapSection(
    str,
    Enum,
):
    WHAT_IT_IS = "WHAT_IT_IS"
    WHERE_IT_SITS = "WHERE_IT_SITS"
    WHAT_IT_OWNS = "WHAT_IT_OWNS"
    WHAT_IT_DEPENDS_ON = "WHAT_IT_DEPENDS_ON"
    WHAT_MUST_REMAIN_TRUE = "WHAT_MUST_REMAIN_TRUE"


_QUESTIONS = {
    RepositorySemanticGapSection.WHAT_IT_IS: (
        "What is this repository's primary software purpose, "
        "and what evidence establishes it?"
    ),
    RepositorySemanticGapSection.WHERE_IT_SITS: (
        "What package or architectural placement can be established "
        "for this repository, and what evidence establishes it?"
    ),
    RepositorySemanticGapSection.WHAT_IT_OWNS: (
        "Which responsibilities does this repository actually own, "
        "and what evidence establishes that ownership?"
    ),
    RepositorySemanticGapSection.WHAT_IT_DEPENDS_ON: (
        "Which dependencies materially characterize this repository, "
        "and what evidence establishes them?"
    ),
    RepositorySemanticGapSection.WHAT_MUST_REMAIN_TRUE: (
        "Which behavioral or architectural invariants must remain true "
        "for this repository, and what evidence establishes them?"
    ),
}


@dataclass(
    frozen=True,
    slots=True,
)
class RepositorySemanticGapQuestion:
    section: RepositorySemanticGapSection
    question: str

    source_commit: str
    repository_observation_id: str
    world_model_snapshot_id: str

    context_assertion_ids: tuple[
        str,
        ...,
    ]

    context_claim_ids: tuple[
        str,
        ...,
    ]

    context_assessment_ids: tuple[
        str,
        ...,
    ]

    context_evidence_reference_ids: tuple[
        str,
        ...,
    ]

    gap_id: str
    question_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class RepositorySemanticGapSet:
    source_commit: str
    repository_observation_id: str
    world_model_snapshot_id: str

    questions: tuple[
        RepositorySemanticGapQuestion,
        ...,
    ]

    gap_set_id: str


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


def _section_assertions(
    model: RepositoryDeterministicWorldModel,
) -> dict[
    RepositorySemanticGapSection,
    tuple[str, ...],
]:
    return {
        RepositorySemanticGapSection.WHAT_IT_IS: (),
        RepositorySemanticGapSection.WHERE_IT_SITS: (
            model.where_it_sits_assertion_ids
        ),
        RepositorySemanticGapSection.WHAT_IT_OWNS: (),
        RepositorySemanticGapSection.WHAT_IT_DEPENDS_ON: (
            model.what_it_depends_on_assertion_ids
        ),
        RepositorySemanticGapSection.WHAT_MUST_REMAIN_TRUE: (),
    }


def _context_closure(
    model: RepositoryDeterministicWorldModel,
    assertion_ids: tuple[
        str,
        ...,
    ],
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
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

    missing_assertions = (
        set(
            assertion_ids
        )
        - set(
            assertions_by_id
        )
    )

    if missing_assertions:
        raise RepositorySemanticGapError(
            "repository semantic context references "
            "an assertion outside the World Model snapshot"
        )

    claim_ids = tuple(
        sorted(
            {
                assertions_by_id[
                    assertion_id
                ].claim_id
                for assertion_id
                in assertion_ids
            }
        )
    )

    assessment_ids = tuple(
        sorted(
            {
                assertions_by_id[
                    assertion_id
                ].assessment_id
                for assertion_id
                in assertion_ids
            }
        )
    )

    if (
        set(
            claim_ids
        )
        - set(
            claims_by_id
        )
    ):
        raise RepositorySemanticGapError(
            "repository semantic context claim "
            "is outside the World Model snapshot"
        )

    if (
        set(
            assessment_ids
        )
        - set(
            assessments_by_id
        )
    ):
        raise RepositorySemanticGapError(
            "repository semantic context assessment "
            "is outside the World Model snapshot"
        )

    evidence_reference_ids: set[
        str
    ] = set()

    for assessment_id in assessment_ids:
        assessment = assessments_by_id[
            assessment_id
        ]

        claim = claims_by_id.get(
            assessment.claim_id
        )

        if claim is None:
            raise RepositorySemanticGapError(
                "repository semantic context assessment "
                "does not have its claim in the snapshot"
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
                raise RepositorySemanticGapError(
                    "repository semantic context assessment "
                    "basis is not attached to its claim"
                )

            evidence_reference_ids.add(
                reference_id
            )

    return (
        claim_ids,
        assessment_ids,
        tuple(
            sorted(
                evidence_reference_ids
            )
        ),
    )


def discover_repository_semantic_gaps(
    index: PythonRepositoryIndex,
    model: RepositoryDeterministicWorldModel,
) -> RepositorySemanticGapSet:
    """Discover unresolved repository semantic sections without inference."""

    if not isinstance(
        index,
        PythonRepositoryIndex,
    ):
        raise RepositorySemanticGapError(
            "index must be a PythonRepositoryIndex"
        )

    if not isinstance(
        model,
        RepositoryDeterministicWorldModel,
    ):
        raise RepositorySemanticGapError(
            "model must be a RepositoryDeterministicWorldModel"
        )

    if (
        model.source_commit
        != index.commit_sha
        or model.repository_observation_id
        != index.repository_observation_id
    ):
        raise RepositorySemanticGapError(
            "repository index and World Model "
            "do not represent the same snapshot"
        )

    selections = _section_assertions(
        model
    )

    context_assertion_ids = tuple(
        sorted(
            {
                assertion_id
                for assertion_ids
                in selections.values()
                for assertion_id
                in assertion_ids
            }
        )
    )

    (
        context_claim_ids,
        context_assessment_ids,
        context_evidence_reference_ids,
    ) = _context_closure(
        model,
        context_assertion_ids,
    )

    questions: list[
        RepositorySemanticGapQuestion
    ] = []

    for section in RepositorySemanticGapSection:
        if selections[
            section
        ]:
            continue

        question = _QUESTIONS[
            section
        ]

        gap_id = _identity(
            "repository-semantic-gap:",
            {
                "schema_version": 1,
                "repository_observation_id": (
                    index.repository_observation_id
                ),
                "section": (
                    section.value
                ),
            },
        )

        question_id = _identity(
            "repository-semantic-gap-question:",
            {
                "schema_version": 1,
                "gap_id": (
                    gap_id
                ),
                "question": (
                    question
                ),
                "world_model_snapshot_id": (
                    model.snapshot.snapshot_id
                ),
                "context_assertion_ids": list(
                    context_assertion_ids
                ),
                "context_claim_ids": list(
                    context_claim_ids
                ),
                "context_assessment_ids": list(
                    context_assessment_ids
                ),
                "context_evidence_reference_ids": list(
                    context_evidence_reference_ids
                ),
            },
        )

        questions.append(
            RepositorySemanticGapQuestion(
                section=section,
                question=question,
                source_commit=(
                    index.commit_sha
                ),
                repository_observation_id=(
                    index.repository_observation_id
                ),
                world_model_snapshot_id=(
                    model.snapshot.snapshot_id
                ),
                context_assertion_ids=(
                    context_assertion_ids
                ),
                context_claim_ids=(
                    context_claim_ids
                ),
                context_assessment_ids=(
                    context_assessment_ids
                ),
                context_evidence_reference_ids=(
                    context_evidence_reference_ids
                ),
                gap_id=gap_id,
                question_id=question_id,
            )
        )

    canonical_questions = tuple(
        questions
    )

    gap_set_id = _identity(
        "repository-semantic-gap-set:",
        {
            "schema_version": 1,
            "source_commit": (
                index.commit_sha
            ),
            "repository_observation_id": (
                index.repository_observation_id
            ),
            "world_model_snapshot_id": (
                model.snapshot.snapshot_id
            ),
            "question_ids": [
                question.question_id
                for question
                in canonical_questions
            ],
        },
    )

    return RepositorySemanticGapSet(
        source_commit=(
            index.commit_sha
        ),
        repository_observation_id=(
            index.repository_observation_id
        ),
        world_model_snapshot_id=(
            model.snapshot.snapshot_id
        ),
        questions=(
            canonical_questions
        ),
        gap_set_id=(
            gap_set_id
        ),
    )
