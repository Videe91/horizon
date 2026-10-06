from __future__ import annotations

import dataclasses

import pytest

from horizon.claims.evidence_backed import (
    ClaimEvidenceKind,
    ClaimEvidenceRelation,
    EvidenceBackedClaim,
    make_claim_evidence_reference,
    make_evidence_backed_claim,
)
from horizon.claims.epistemic import (
    EpistemicAssessment,
    EpistemicStatus,
    make_epistemic_assessment,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.snapshot import (
    WorldModelSnapshot,
    WorldModelSnapshotError,
    make_world_model_snapshot,
)


def _bundle(
    suffix: str,
    *,
    status: EpistemicStatus = EpistemicStatus.PROVEN,
    relation: WorldModelRelationKind = (
        WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
    ),
) -> tuple[
    EvidenceBackedClaim,
    EpistemicAssessment,
    WorldModelAssertion,
]:
    evidence = make_claim_evidence_reference(
        ClaimEvidenceKind.CAUSAL,
        ClaimEvidenceRelation.SUPPORTS,
        f"source-intervention-comparison:{suffix}",
    )

    claim = make_evidence_backed_claim(
        f"Proposition {suffix}.",
        scope=f"Scope {suffix}.",
        evidence=(evidence,),
    )

    assessment = make_epistemic_assessment(
        claim,
        status,
        rationale=f"Rationale {suffix}.",
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        f"subject:{suffix}",
        relation,
        f"object:{suffix}",
        claim=claim,
        assessment=assessment,
    )

    return (
        claim,
        assessment,
        assertion,
    )


def _single_snapshot() -> WorldModelSnapshot:
    claim, assessment, assertion = _bundle(
        "single"
    )

    return make_world_model_snapshot(
        claims=(claim,),
        assessments=(assessment,),
        assertions=(assertion,),
    )


def test_snapshot_preserves_exact_objects_in_canonical_order() -> None:
    claim_a, assessment_a, assertion_a = _bundle(
        "a"
    )

    claim_b, assessment_b, assertion_b = _bundle(
        "b"
    )

    snapshot = make_world_model_snapshot(
        claims=(
            claim_b,
            claim_a,
        ),
        assessments=(
            assessment_b,
            assessment_a,
        ),
        assertions=(
            assertion_b,
            assertion_a,
        ),
    )

    assert isinstance(
        snapshot,
        WorldModelSnapshot,
    )

    assert {
        field.name
        for field in dataclasses.fields(
            WorldModelSnapshot
        )
    } == {
        "claims",
        "assessments",
        "assertions",
        "snapshot_id",
    }

    assert snapshot.claims == tuple(
        sorted(
            (
                claim_a,
                claim_b,
            ),
            key=lambda claim: claim.claim_id,
        )
    )

    assert snapshot.assessments == tuple(
        sorted(
            (
                assessment_a,
                assessment_b,
            ),
            key=lambda assessment: assessment.assessment_id,
        )
    )

    assert snapshot.assertions == tuple(
        sorted(
            (
                assertion_a,
                assertion_b,
            ),
            key=lambda assertion: assertion.assertion_id,
        )
    )

    assert snapshot.snapshot_id.startswith(
        "world-model-snapshot:"
    )


def test_snapshot_is_immutable() -> None:
    snapshot = _single_snapshot()

    with pytest.raises(
        dataclasses.FrozenInstanceError
    ):
        snapshot.snapshot_id = "forged"  # type: ignore[misc]


def test_snapshot_identity_is_independent_of_input_order() -> None:
    claim_a, assessment_a, assertion_a = _bundle(
        "order-a"
    )

    claim_b, assessment_b, assertion_b = _bundle(
        "order-b"
    )

    first = make_world_model_snapshot(
        claims=(
            claim_a,
            claim_b,
        ),
        assessments=(
            assessment_a,
            assessment_b,
        ),
        assertions=(
            assertion_a,
            assertion_b,
        ),
    )

    second = make_world_model_snapshot(
        claims=reversed(
            (
                claim_a,
                claim_b,
            )
        ),
        assessments=reversed(
            (
                assessment_a,
                assessment_b,
            )
        ),
        assertions=reversed(
            (
                assertion_a,
                assertion_b,
            )
        ),
    )

    assert first == second

    assert (
        first.snapshot_id
        == second.snapshot_id
    )


def test_duplicate_claim_identity_is_rejected() -> None:
    claim, assessment, assertion = _bundle(
        "duplicate-claim"
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match="duplicate.*claim|claim.*duplicate",
    ):
        make_world_model_snapshot(
            claims=(
                claim,
                claim,
            ),
            assessments=(assessment,),
            assertions=(assertion,),
        )


def test_duplicate_assessment_identity_is_rejected() -> None:
    claim, assessment, assertion = _bundle(
        "duplicate-assessment"
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match=(
            "duplicate.*assessment|"
            "assessment.*duplicate"
        ),
    ):
        make_world_model_snapshot(
            claims=(claim,),
            assessments=(
                assessment,
                assessment,
            ),
            assertions=(assertion,),
        )


def test_duplicate_assertion_identity_is_rejected() -> None:
    claim, assessment, assertion = _bundle(
        "duplicate-assertion"
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match=(
            "duplicate.*assertion|"
            "assertion.*duplicate"
        ),
    ):
        make_world_model_snapshot(
            claims=(claim,),
            assessments=(assessment,),
            assertions=(
                assertion,
                assertion,
            ),
        )


def test_assessment_requires_its_claim_in_snapshot() -> None:
    _, assessment, _ = _bundle(
        "missing-assessment-claim"
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match="assessment.*claim|claim.*assessment",
    ):
        make_world_model_snapshot(
            claims=(),
            assessments=(assessment,),
            assertions=(),
        )


def test_assertion_requires_its_claim_in_snapshot() -> None:
    _, _, assertion = _bundle(
        "missing-assertion-claim"
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match="assertion.*claim|claim.*assertion",
    ):
        make_world_model_snapshot(
            claims=(),
            assessments=(),
            assertions=(assertion,),
        )


def test_assertion_requires_its_assessment_in_snapshot() -> None:
    claim, _, assertion = _bundle(
        "missing-assertion-assessment"
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match=(
            "assertion.*assessment|"
            "assessment.*assertion"
        ),
    ):
        make_world_model_snapshot(
            claims=(claim,),
            assessments=(),
            assertions=(assertion,),
        )


def test_assertion_assessment_must_assess_same_claim() -> None:
    claim_a, assessment_a, assertion_a = _bundle(
        "link-a"
    )

    claim_b, assessment_b, _ = _bundle(
        "link-b"
    )

    assert (
        assessment_a.claim_id
        == claim_a.claim_id
    )

    assert (
        assessment_b.claim_id
        == claim_b.claim_id
    )

    forged = dataclasses.replace(
        assertion_a,
        assessment_id=(
            assessment_b.assessment_id
        ),
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match="assessment.*claim|claim.*assessment",
    ):
        make_world_model_snapshot(
            claims=(
                claim_a,
                claim_b,
            ),
            assessments=(
                assessment_a,
                assessment_b,
            ),
            assertions=(forged,),
        )


def test_forged_claim_is_rejected() -> None:
    claim, _, _ = _bundle(
        "forged-claim"
    )

    forged = dataclasses.replace(
        claim,
        proposition=(
            claim.proposition
            + " Forged mutation."
        ),
    )

    assert (
        forged.claim_id
        == claim.claim_id
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match="claim",
    ):
        make_world_model_snapshot(
            claims=(forged,),
            assessments=(),
            assertions=(),
        )


def test_forged_assessment_is_rejected() -> None:
    claim, assessment, _ = _bundle(
        "forged-assessment"
    )

    forged = dataclasses.replace(
        assessment,
        status=(
            EpistemicStatus.UNKNOWN
        ),
    )

    assert (
        forged.assessment_id
        == assessment.assessment_id
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match="assessment",
    ):
        make_world_model_snapshot(
            claims=(claim,),
            assessments=(forged,),
            assertions=(),
        )


def test_forged_assertion_is_rejected() -> None:
    claim, assessment, assertion = _bundle(
        "forged-assertion"
    )

    forged = dataclasses.replace(
        assertion,
        relation=(
            WorldModelRelationKind.CALLS
        ),
    )

    assert (
        forged.assertion_id
        == assertion.assertion_id
    )

    with pytest.raises(
        WorldModelSnapshotError,
        match="assertion",
    ):
        make_world_model_snapshot(
            claims=(claim,),
            assessments=(assessment,),
            assertions=(forged,),
        )


def test_snapshot_identity_changes_when_membership_changes() -> None:
    claim_a, assessment_a, assertion_a = _bundle(
        "membership-a"
    )

    claim_b, assessment_b, assertion_b = _bundle(
        "membership-b"
    )

    first = make_world_model_snapshot(
        claims=(claim_a,),
        assessments=(assessment_a,),
        assertions=(assertion_a,),
    )

    second = make_world_model_snapshot(
        claims=(
            claim_a,
            claim_b,
        ),
        assessments=(
            assessment_a,
            assessment_b,
        ),
        assertions=(
            assertion_a,
            assertion_b,
        ),
    )

    assert (
        first.snapshot_id
        != second.snapshot_id
    )
