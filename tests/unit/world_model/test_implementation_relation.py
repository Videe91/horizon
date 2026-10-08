from __future__ import annotations

from horizon.claims.epistemic import (
    EpistemicStatus,
    make_epistemic_assessment,
)
from horizon.claims.evidence_backed import (
    ClaimEvidenceKind,
    ClaimEvidenceRelation,
    make_claim_evidence_reference,
    make_evidence_backed_claim,
)
from horizon.world_model.assertion import (
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.reconciliation import (
    WORLD_MODEL_RELATIONSHIP_POLICIES,
)


def claim():
    evidence = (
        make_claim_evidence_reference(
            ClaimEvidenceKind.STATIC,
            ClaimEvidenceRelation.SUPPORTS,
            "investigation-source-observation:test-purpose",
        ),
    )

    return make_evidence_backed_claim(
        (
            "At the frozen repository snapshot, "
            "the repository primarily implements "
            "workflow orchestration software."
        ),
        scope=(
            "Exact frozen repository observation."
        ),
        evidence=evidence,
    )


def assessment(
    value,
):
    return make_epistemic_assessment(
        value,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "The hypothesis is supported by "
            "the registered repository evidence."
        ),
        basis=value.evidence,
    )


def test_implements_is_explicit_world_model_relation() -> None:
    assert (
        WorldModelRelationKind.IMPLEMENTS.value
        == "IMPLEMENTS"
    )


def test_relation_vocabulary_is_exactly_extended_once() -> None:
    assert {
        relation.value
        for relation
        in WorldModelRelationKind
    } == {
        "CALLS",
        "DEPENDS_ON",
        "AFFECTS_BEHAVIOR_OF",
        "OWNS_RESPONSIBILITY_FOR",
        "IMPLEMENTS",
    }


def test_implements_has_declared_reconciliation_policy() -> None:
    assert (
        WorldModelRelationKind.IMPLEMENTS
        in WORLD_MODEL_RELATIONSHIP_POLICIES
    )


def test_every_relation_still_has_policy() -> None:
    assert (
        set(
            WORLD_MODEL_RELATIONSHIP_POLICIES
        )
        == set(
            WorldModelRelationKind
        )
    )


def test_implements_uses_nonexclusive_relationship_policy() -> None:
    assert (
        WORLD_MODEL_RELATIONSHIP_POLICIES[
            WorldModelRelationKind.IMPLEMENTS
        ]
        == WORLD_MODEL_RELATIONSHIP_POLICIES[
            WorldModelRelationKind.DEPENDS_ON
        ]
    )


def test_existing_assertion_factory_accepts_implements() -> None:
    value = claim()

    epistemic = assessment(
        value
    )

    assertion = make_world_model_assertion(
        "git-observation:test-repository",
        WorldModelRelationKind.IMPLEMENTS,
        (
            "repository-purpose:"
            "workflow-orchestration"
        ),
        claim=value,
        assessment=epistemic,
    )

    assert (
        assertion.relation
        is WorldModelRelationKind.IMPLEMENTS
    )

    assert (
        assertion.claim_id
        == value.claim_id
    )

    assert (
        assertion.assessment_id
        == epistemic.assessment_id
    )


def test_implements_identity_is_not_dependency_identity() -> None:
    value = claim()

    epistemic = assessment(
        value
    )

    implements = make_world_model_assertion(
        "git-observation:test-repository",
        WorldModelRelationKind.IMPLEMENTS,
        (
            "repository-purpose:"
            "workflow-orchestration"
        ),
        claim=value,
        assessment=epistemic,
    )

    depends = make_world_model_assertion(
        "git-observation:test-repository",
        WorldModelRelationKind.DEPENDS_ON,
        (
            "repository-purpose:"
            "workflow-orchestration"
        ),
        claim=value,
        assessment=epistemic,
    )

    assert (
        implements.assertion_id
        != depends.assertion_id
    )
