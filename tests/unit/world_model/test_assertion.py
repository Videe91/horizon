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
    WorldModelAssertionError,
    WorldModelRelationKind,
    make_world_model_assertion,
)


SUBJECT = (
    "python-symbol:"
    "prefect.server.orchestration."
    "core_policy.RetryFailedFlows"
)

OBJECT = (
    "behavior:"
    "flow-retry-eligibility"
)

PROPOSITION = (
    "Within the tested scenario, "
    "RetryFailedFlows affects retry eligibility."
)

SCOPE = (
    "Exact controlled source-intervention "
    "experiment under fixed runtime inputs."
)

RATIONALE = (
    "The controlled intervention changed "
    "the observed retry decision."
)


def _claim(
    *,
    suffix: str = "primary",
) -> EvidenceBackedClaim:
    reference = (
        make_claim_evidence_reference(
            ClaimEvidenceKind.CAUSAL,
            ClaimEvidenceRelation.SUPPORTS,
            (
                "source-intervention-comparison:"
                f"{suffix}"
            ),
        )
    )

    return make_evidence_backed_claim(
        PROPOSITION,
        scope=SCOPE,
        evidence=(
            reference,
        ),
    )


def _assessment(
    claim: EvidenceBackedClaim,
    *,
    status: EpistemicStatus = (
        EpistemicStatus.PROVEN
    ),
) -> EpistemicAssessment:
    return make_epistemic_assessment(
        claim,
        status,
        rationale=RATIONALE,
        basis=claim.evidence,
    )


def _assertion(
    claim: EvidenceBackedClaim,
    assessment: EpistemicAssessment,
    *,
    relation: WorldModelRelationKind = (
        WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
    ),
    subject_id: str = SUBJECT,
    object_id: str = OBJECT,
) -> WorldModelAssertion:
    return make_world_model_assertion(
        subject_id,
        relation,
        object_id,
        claim=claim,
        assessment=assessment,
    )


def test_world_model_assertion_preserves_structured_relation() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    assertion = _assertion(
        claim,
        assessment,
    )

    assert isinstance(
        assertion,
        WorldModelAssertion,
    )

    assert (
        assertion.subject_id
        == SUBJECT
    )

    assert (
        assertion.relation
        is WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
    )

    assert (
        assertion.object_id
        == OBJECT
    )

    assert (
        assertion.claim_id
        == claim.claim_id
    )

    assert (
        assertion.assessment_id
        == assessment.assessment_id
    )

    assert assertion.assertion_id.startswith(
        "world-model-assertion:"
    )


def test_call_relationship_is_distinct_from_responsibility_ownership() -> None:
    assert (
        WorldModelRelationKind.CALLS
        is not
        WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR
    )

    assert (
        WorldModelRelationKind.CALLS.value
        !=
        WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR.value
    )


def test_behavior_effect_is_distinct_from_call_relationship() -> None:
    assert (
        WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
        is not
        WorldModelRelationKind.CALLS
    )


def test_same_endpoints_can_have_different_semantic_relations() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    call = _assertion(
        claim,
        assessment,
        relation=(
            WorldModelRelationKind.CALLS
        ),
    )

    ownership = _assertion(
        claim,
        assessment,
        relation=(
            WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR
        ),
    )

    assert (
        call.assertion_id
        != ownership.assertion_id
    )

    assert (
        call.relation
        is WorldModelRelationKind.CALLS
    )

    assert (
        ownership.relation
        is WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR
    )


def test_assertion_does_not_duplicate_epistemic_status() -> None:
    field_names = {
        field.name
        for field in dataclasses.fields(
            WorldModelAssertion
        )
    }

    assert field_names == {
        "subject_id",
        "relation",
        "object_id",
        "claim_id",
        "assessment_id",
        "assertion_id",
    }

    assert "status" not in field_names
    assert "epistemic_status" not in field_names
    assert "confidence" not in field_names


def test_assertion_does_not_duplicate_claim_evidence_or_scope() -> None:
    field_names = {
        field.name
        for field in dataclasses.fields(
            WorldModelAssertion
        )
    }

    assert "evidence" not in field_names
    assert "scope" not in field_names
    assert "rationale" not in field_names
    assert "proposition" not in field_names


def test_assertion_requires_nonempty_subject() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    with pytest.raises(
        WorldModelAssertionError,
        match="subject",
    ):
        _assertion(
            claim,
            assessment,
            subject_id="",
        )


def test_assertion_requires_nonempty_object() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    with pytest.raises(
        WorldModelAssertionError,
        match="object",
    ):
        _assertion(
            claim,
            assessment,
            object_id="",
        )


def test_assertion_requires_assessment_for_same_claim() -> None:
    claim = _claim(
        suffix="claim-a"
    )

    other_claim = _claim(
        suffix="claim-b"
    )

    other_assessment = _assessment(
        other_claim
    )

    assert (
        claim.claim_id
        != other_claim.claim_id
    )

    with pytest.raises(
        WorldModelAssertionError,
        match="assessment.*claim|claim.*assessment",
    ):
        _assertion(
            claim,
            other_assessment,
        )


def test_assertion_rejects_forged_claim() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
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
        WorldModelAssertionError,
        match="claim",
    ):
        _assertion(
            forged,
            assessment,
        )


def test_assertion_rejects_forged_assessment() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
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
        WorldModelAssertionError,
        match="assessment",
    ):
        _assertion(
            claim,
            forged,
        )


def test_assertion_identity_is_deterministic() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    first = _assertion(
        claim,
        assessment,
    )

    second = _assertion(
        claim,
        assessment,
    )

    assert first == second

    assert (
        first.assertion_id
        == second.assertion_id
    )


def test_assertion_identity_changes_when_relation_changes() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    first = _assertion(
        claim,
        assessment,
        relation=(
            WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
        ),
    )

    second = _assertion(
        claim,
        assessment,
        relation=(
            WorldModelRelationKind.DEPENDS_ON
        ),
    )

    assert (
        first.assertion_id
        != second.assertion_id
    )


def test_assertion_identity_changes_when_subject_changes() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    first = _assertion(
        claim,
        assessment,
    )

    second = _assertion(
        claim,
        assessment,
        subject_id=(
            SUBJECT
            + ".alternate"
        ),
    )

    assert (
        first.assertion_id
        != second.assertion_id
    )


def test_assertion_identity_changes_when_object_changes() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    first = _assertion(
        claim,
        assessment,
    )

    second = _assertion(
        claim,
        assessment,
        object_id=(
            OBJECT
            + ".alternate"
        ),
    )

    assert (
        first.assertion_id
        != second.assertion_id
    )


def test_assertion_identity_changes_when_assessment_changes() -> None:
    claim = _claim()

    proven = _assessment(
        claim,
        status=(
            EpistemicStatus.PROVEN
        ),
    )

    hypothesis = _assessment(
        claim,
        status=(
            EpistemicStatus.SUPPORTED_HYPOTHESIS
        ),
    )

    first = _assertion(
        claim,
        proven,
    )

    second = _assertion(
        claim,
        hypothesis,
    )

    assert (
        first.assertion_id
        != second.assertion_id
    )


def test_relation_is_explicit_not_inferred_from_claim_text() -> None:
    claim = _claim()
    assessment = _assessment(
        claim
    )

    behavior = _assertion(
        claim,
        assessment,
        relation=(
            WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
        ),
    )

    dependency = _assertion(
        claim,
        assessment,
        relation=(
            WorldModelRelationKind.DEPENDS_ON
        ),
    )

    assert (
        behavior.relation
        is WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
    )

    assert (
        dependency.relation
        is WorldModelRelationKind.DEPENDS_ON
    )

    assert (
        behavior.assertion_id
        != dependency.assertion_id
    )
