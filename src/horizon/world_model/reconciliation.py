"""Declared relationship semantics for world-model reconciliation.

Capability 019 describes relationships between assertions. It never
decides which assertion is true.

Relationship cardinality is explicit human-authored policy data. It is
not inferred from graph shape, evidence strength, or epistemic status.

Evidence lineage is supplied explicitly. Reconciliation does not infer
lineage from evidence IDs. A future evidence-layer helper should derive
root sets by walking the existing evidence ``depends_on`` edges
transitively to their leaves and pass those roots into this module.

Supersession is an explicit event. It is never inferred from assertion
age, ordering, evidence strength, or ordinary relationship analysis.

Every conflict produces a deterministic open question for a later
investigator. This module does not investigate or resolve that question.
"""

from __future__ import annotations

import hashlib
import json
import re

from collections.abc import Mapping, Set
from dataclasses import dataclass
from enum import Enum
from itertools import combinations

from horizon.world_model.assertion import (
    WorldModelRelationKind,
)
from horizon.world_model.snapshot import (
    WorldModelSnapshot,
)


class WorldModelRelationshipCardinality(
    str,
    Enum,
):
    MANY_TO_MANY = "MANY_TO_MANY"
    ONE_SUBJECT_PER_OBJECT = "ONE_SUBJECT_PER_OBJECT"


@dataclass(
    frozen=True,
    slots=True,
)
class WorldModelRelationshipPolicy:
    cardinality: WorldModelRelationshipCardinality


WORLD_MODEL_RELATIONSHIP_POLICIES = {
    WorldModelRelationKind.CALLS: WorldModelRelationshipPolicy(
        cardinality=(
            WorldModelRelationshipCardinality.MANY_TO_MANY
        ),
    ),
    WorldModelRelationKind.DEPENDS_ON: WorldModelRelationshipPolicy(
        cardinality=(
            WorldModelRelationshipCardinality.MANY_TO_MANY
        ),
    ),
    WorldModelRelationKind.AFFECTS_BEHAVIOR_OF: (
        WorldModelRelationshipPolicy(
            cardinality=(
                WorldModelRelationshipCardinality.MANY_TO_MANY
            ),
        )
    ),
    WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR: (
        WorldModelRelationshipPolicy(
            cardinality=(
                WorldModelRelationshipCardinality.ONE_SUBJECT_PER_OBJECT
            ),
        )
    ),
}

# IMPLEMENTS is intentionally non-exclusive at the relationship layer.
#
# A repository may implement more than one capability or purpose.
# Repository-section selection decides which assertion represents
# WHAT_IT_IS; relationship reconciliation must not invent exclusivity.
WORLD_MODEL_RELATIONSHIP_POLICIES = {
    **WORLD_MODEL_RELATIONSHIP_POLICIES,
    WorldModelRelationKind.IMPLEMENTS: (
        WORLD_MODEL_RELATIONSHIP_POLICIES[
            WorldModelRelationKind.DEPENDS_ON
        ]
    ),
}



class WorldModelRelationshipKind(
    str,
    Enum,
):
    AGREE = "AGREE"
    CONFLICT = "CONFLICT"
    COEXIST = "COEXIST"


class WorldModelRelationshipReason(
    str,
    Enum,
):
    SHARED_ROOT = "shared_root"
    LINEAGE_UNKNOWN = "lineage_unknown"


@dataclass(
    frozen=True,
    slots=True,
)
class WorldModelRelationship:
    kind: WorldModelRelationshipKind
    assertion_ids: tuple[str, ...]
    relationship_id: str
    reason: WorldModelRelationshipReason | None = None


def _make_world_model_relationship(
    *,
    kind: WorldModelRelationshipKind,
    assertion_ids: tuple[str, ...],
    reason: WorldModelRelationshipReason | None = None,
) -> WorldModelRelationship:
    canonical_assertion_ids = tuple(
        sorted(assertion_ids)
    )

    payload = {
        "assertion_ids": canonical_assertion_ids,
        "kind": kind.value,
        "reason": (
            reason.value
            if reason is not None
            else None
        ),
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    relationship_id = (
        "world-model-relationship:"
        + hashlib.sha256(encoded).hexdigest()
    )

    return WorldModelRelationship(
        kind=kind,
        assertion_ids=canonical_assertion_ids,
        relationship_id=relationship_id,
        reason=reason,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class WorldModelSupersession:
    superseded_assertion_id: str
    replacement_assertion_id: str
    reason: str
    evidence_reference_ids: tuple[str, ...]
    supersession_id: str


def make_world_model_supersession(
    *,
    superseded_assertion_id: str,
    replacement_assertion_id: str,
    reason: str,
    evidence_reference_ids: tuple[str, ...],
) -> WorldModelSupersession:
    canonical_evidence_reference_ids = tuple(
        sorted(evidence_reference_ids)
    )

    payload = {
        "evidence_reference_ids": (
            canonical_evidence_reference_ids
        ),
        "reason": reason,
        "replacement_assertion_id": (
            replacement_assertion_id
        ),
        "superseded_assertion_id": (
            superseded_assertion_id
        ),
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    supersession_id = (
        "world-model-supersession:"
        + hashlib.sha256(encoded).hexdigest()
    )

    return WorldModelSupersession(
        superseded_assertion_id=(
            superseded_assertion_id
        ),
        replacement_assertion_id=(
            replacement_assertion_id
        ),
        reason=reason,
        evidence_reference_ids=(
            canonical_evidence_reference_ids
        ),
        supersession_id=supersession_id,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class WorldModelOpenQuestion:
    question: str
    relationship_id: str
    assertion_ids: tuple[str, ...]
    evidence_reference_ids: tuple[str, ...]
    question_id: str


def _humanize_identifier(
    value: str,
) -> str:
    _, separator, tail = value.partition(":")

    text = tail if separator else value

    text = re.sub(
        r"[._:/_-]+",
        " ",
        text,
    )

    return " ".join(text.split())


def _question_text_for_conflict(
    *,
    relation: WorldModelRelationKind,
    object_id: str,
) -> str:
    object_text = _humanize_identifier(
        object_id
    )

    if (
        relation
        is WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR
    ):
        return (
            "Who owns responsibility for "
            f"{object_text}?"
        )

    relation_text = (
        relation.value
        .lower()
        .replace("_", " ")
    )

    return (
        "How should the conflict over "
        f"{relation_text} for {object_text} "
        "be understood?"
    )


def _make_open_question(
    *,
    relationship: WorldModelRelationship,
    relation: WorldModelRelationKind,
    object_id: str,
    evidence_reference_ids: tuple[str, ...],
) -> WorldModelOpenQuestion:
    canonical_evidence_reference_ids = tuple(
        sorted(
            set(evidence_reference_ids)
        )
    )

    question = _question_text_for_conflict(
        relation=relation,
        object_id=object_id,
    )

    payload = {
        "assertion_ids": relationship.assertion_ids,
        "evidence_reference_ids": (
            canonical_evidence_reference_ids
        ),
        "question": question,
        "relationship_id": relationship.relationship_id,
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    question_id = (
        "world-model-open-question:"
        + hashlib.sha256(encoded).hexdigest()
    )

    return WorldModelOpenQuestion(
        question=question,
        relationship_id=(
            relationship.relationship_id
        ),
        assertion_ids=relationship.assertion_ids,
        evidence_reference_ids=(
            canonical_evidence_reference_ids
        ),
        question_id=question_id,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class WorldModelRelationshipAnalysis:
    relationships: tuple[WorldModelRelationship, ...]
    supersessions: tuple[WorldModelSupersession, ...] = ()
    open_questions: tuple[WorldModelOpenQuestion, ...] = ()


def _roots_for_assertion(
    *,
    assertion,
    claims_by_id,
    evidence_roots: Mapping[str, Set[str]] | None,
) -> frozenset[str] | None:
    if evidence_roots is None:
        return None

    claim = claims_by_id[
        assertion.claim_id
    ]

    roots: set[str] = set()

    for reference in claim.evidence:
        reference_roots = evidence_roots.get(
            reference.evidence_id
        )

        if not reference_roots:
            return None

        roots.update(
            reference_roots
        )

    if not roots:
        return None

    return frozenset(
        roots
    )


def analyze_world_model_snapshot(
    snapshot: WorldModelSnapshot,
    *,
    evidence_roots: Mapping[str, Set[str]] | None = None,
    supersessions: tuple[WorldModelSupersession, ...] = (),
) -> WorldModelRelationshipAnalysis:
    relationships: list[
        WorldModelRelationship
    ] = []

    claims_by_id = {
        claim.claim_id: claim
        for claim in snapshot.claims
    }

    assertions_by_id = {
        assertion.assertion_id: assertion
        for assertion in snapshot.assertions
    }

    for left, right in combinations(
        snapshot.assertions,
        2,
    ):
        if left.relation is not right.relation:
            continue

        if left.object_id != right.object_id:
            continue

        assertion_ids = (
            left.assertion_id,
            right.assertion_id,
        )

        if left.subject_id == right.subject_id:
            left_roots = _roots_for_assertion(
                assertion=left,
                claims_by_id=claims_by_id,
                evidence_roots=evidence_roots,
            )

            right_roots = _roots_for_assertion(
                assertion=right,
                claims_by_id=claims_by_id,
                evidence_roots=evidence_roots,
            )

            if (
                left_roots is None
                or right_roots is None
            ):
                relationships.append(
                    _make_world_model_relationship(
                        kind=(
                            WorldModelRelationshipKind.COEXIST
                        ),
                        assertion_ids=assertion_ids,
                        reason=(
                            WorldModelRelationshipReason.LINEAGE_UNKNOWN
                        ),
                    )
                )
                continue

            if left_roots.isdisjoint(
                right_roots
            ):
                relationships.append(
                    _make_world_model_relationship(
                        kind=(
                            WorldModelRelationshipKind.AGREE
                        ),
                        assertion_ids=assertion_ids,
                    )
                )
                continue

            relationships.append(
                _make_world_model_relationship(
                    kind=(
                        WorldModelRelationshipKind.COEXIST
                    ),
                    assertion_ids=assertion_ids,
                    reason=(
                        WorldModelRelationshipReason.SHARED_ROOT
                    ),
                )
            )
            continue

        policy = (
            WORLD_MODEL_RELATIONSHIP_POLICIES[
                left.relation
            ]
        )

        if (
            policy.cardinality
            is WorldModelRelationshipCardinality.ONE_SUBJECT_PER_OBJECT
        ):
            kind = (
                WorldModelRelationshipKind.CONFLICT
            )
        else:
            kind = (
                WorldModelRelationshipKind.COEXIST
            )

        relationships.append(
            _make_world_model_relationship(
                kind=kind,
                assertion_ids=assertion_ids,
            )
        )

    canonical_relationships = tuple(
        sorted(
            relationships,
            key=lambda item: item.relationship_id,
        )
    )

    canonical_supersessions = tuple(
        sorted(
            supersessions,
            key=lambda item: item.supersession_id,
        )
    )

    open_questions: list[
        WorldModelOpenQuestion
    ] = []

    for relationship in canonical_relationships:
        if (
            relationship.kind
            is not WorldModelRelationshipKind.CONFLICT
        ):
            continue

        related_assertions = tuple(
            assertions_by_id[
                assertion_id
            ]
            for assertion_id
            in relationship.assertion_ids
        )

        reference_ids = tuple(
            reference.reference_id
            for assertion in related_assertions
            for reference in (
                claims_by_id[
                    assertion.claim_id
                ].evidence
            )
        )

        representative = (
            related_assertions[0]
        )

        open_questions.append(
            _make_open_question(
                relationship=relationship,
                relation=representative.relation,
                object_id=representative.object_id,
                evidence_reference_ids=reference_ids,
            )
        )

    canonical_open_questions = tuple(
        sorted(
            open_questions,
            key=lambda item: item.question_id,
        )
    )

    return WorldModelRelationshipAnalysis(
        relationships=canonical_relationships,
        supersessions=canonical_supersessions,
        open_questions=canonical_open_questions,
    )
