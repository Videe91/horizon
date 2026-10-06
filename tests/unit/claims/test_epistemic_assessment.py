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
    EpistemicAssessmentError,
    EpistemicStatus,
    make_epistemic_assessment,
)


PROPOSITION = (
    "Within the tested scenario, "
    "RetryFailedFlows changes retry eligibility."
)

SCOPE = (
    "Exact controlled source-intervention "
    "experiment under fixed runtime inputs."
)

RATIONALE = (
    "The assessment is based on the exact "
    "evidence references attached to this claim."
)


def _runtime_support(
    suffix: str = "runtime-support",
):
    return make_claim_evidence_reference(
        ClaimEvidenceKind.RUNTIME,
        ClaimEvidenceRelation.SUPPORTS,
        f"runtime-observation:{suffix}",
    )


def _causal_support(
    suffix: str = "causal-support",
):
    return make_claim_evidence_reference(
        ClaimEvidenceKind.CAUSAL,
        ClaimEvidenceRelation.SUPPORTS,
        (
            "source-intervention-comparison:"
            f"{suffix}"
        ),
    )


def _runtime_contradiction(
    suffix: str = "runtime-contradiction",
):
    return make_claim_evidence_reference(
        ClaimEvidenceKind.RUNTIME,
        ClaimEvidenceRelation.CONTRADICTS,
        f"runtime-observation:{suffix}",
    )


def _claim(
    *references,
) -> EvidenceBackedClaim:
    return make_evidence_backed_claim(
        PROPOSITION,
        scope=SCOPE,
        evidence=references,
    )


def _supported_claim() -> EvidenceBackedClaim:
    return _claim(
        _runtime_support(),
        _causal_support(),
    )


def test_epistemic_status_vocabulary_is_exact() -> None:
    assert {
        member.value
        for member in EpistemicStatus
    } == {
        "PROVEN",
        "SUPPORTED_HYPOTHESIS",
        "DISPUTED",
        "UNKNOWN",
    }


def test_epistemic_status_is_not_evidence_kind() -> None:
    assert {
        member.value
        for member in EpistemicStatus
    }.isdisjoint(
        {
            member.value
            for member in ClaimEvidenceKind
        }
    )


def test_assessment_preserves_claim_status_rationale_and_basis() -> None:
    claim = _supported_claim()

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=RATIONALE,
        basis=claim.evidence,
    )

    assert isinstance(
        assessment,
        EpistemicAssessment,
    )

    assert (
        assessment.claim_id
        == claim.claim_id
    )

    assert (
        assessment.status
        is EpistemicStatus.SUPPORTED_HYPOTHESIS
    )

    assert (
        assessment.rationale
        == RATIONALE
    )

    assert (
        assessment.basis_reference_ids
        == tuple(
            sorted(
                reference.reference_id
                for reference
                in claim.evidence
            )
        )
    )

    assert assessment.assessment_id.startswith(
        "epistemic-assessment:"
    )


def test_claim_remains_free_of_epistemic_fields() -> None:
    field_names = {
        field.name
        for field in dataclasses.fields(
            EvidenceBackedClaim
        )
    }

    assert "status" not in field_names
    assert "epistemic_status" not in field_names
    assert "confidence" not in field_names
    assert "proven" not in field_names


def test_assessment_has_no_numeric_confidence() -> None:
    field_names = {
        field.name
        for field in dataclasses.fields(
            EpistemicAssessment
        )
    }

    assert field_names == {
        "claim_id",
        "status",
        "rationale",
        "basis_reference_ids",
        "assessment_id",
    }

    assert "confidence" not in field_names
    assert "probability" not in field_names


def test_assessment_requires_nonempty_rationale() -> None:
    claim = _supported_claim()

    with pytest.raises(
        EpistemicAssessmentError,
        match="rationale",
    ):
        make_epistemic_assessment(
            claim,
            EpistemicStatus.SUPPORTED_HYPOTHESIS,
            rationale="",
            basis=claim.evidence,
        )


def test_assessment_requires_basis() -> None:
    claim = _supported_claim()

    with pytest.raises(
        EpistemicAssessmentError,
        match="basis",
    ):
        make_epistemic_assessment(
            claim,
            EpistemicStatus.UNKNOWN,
            rationale=RATIONALE,
            basis=(),
        )


def test_assessment_rejects_basis_not_attached_to_claim() -> None:
    claim = _supported_claim()

    foreign = _runtime_support(
        "foreign-runtime"
    )

    assert foreign not in claim.evidence

    with pytest.raises(
        EpistemicAssessmentError,
        match="basis",
    ):
        make_epistemic_assessment(
            claim,
            EpistemicStatus.SUPPORTED_HYPOTHESIS,
            rationale=RATIONALE,
            basis=(
                foreign,
            ),
        )


def test_assessment_rejects_duplicate_basis_reference() -> None:
    claim = _supported_claim()

    reference = claim.evidence[
        0
    ]

    with pytest.raises(
        EpistemicAssessmentError,
        match="duplicate",
    ):
        make_epistemic_assessment(
            claim,
            EpistemicStatus.SUPPORTED_HYPOTHESIS,
            rationale=RATIONALE,
            basis=(
                reference,
                reference,
            ),
        )


def test_assessment_rejects_forged_claim() -> None:
    claim = _supported_claim()

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
        EpistemicAssessmentError,
        match="claim",
    ):
        make_epistemic_assessment(
            forged,
            EpistemicStatus.SUPPORTED_HYPOTHESIS,
            rationale=RATIONALE,
            basis=forged.evidence,
        )


def test_assessment_rejects_forged_basis_reference() -> None:
    claim = _supported_claim()

    original = claim.evidence[
        0
    ]

    forged = dataclasses.replace(
        original,
        evidence_id=(
            original.evidence_id
            + "-forged"
        ),
    )

    assert (
        forged.reference_id
        == original.reference_id
    )

    assert forged not in claim.evidence

    with pytest.raises(
        EpistemicAssessmentError,
        match="basis",
    ):
        make_epistemic_assessment(
            claim,
            EpistemicStatus.SUPPORTED_HYPOTHESIS,
            rationale=RATIONALE,
            basis=(
                forged,
            ),
        )


def test_assessment_identity_is_independent_of_basis_order() -> None:
    claim = _supported_claim()

    first = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=RATIONALE,
        basis=claim.evidence,
    )

    second = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=RATIONALE,
        basis=reversed(
            claim.evidence
        ),
    )

    assert first == second

    assert (
        first.assessment_id
        == second.assessment_id
    )


def test_assessment_identity_changes_when_status_changes() -> None:
    claim = _supported_claim()

    first = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=RATIONALE,
        basis=claim.evidence,
    )

    second = make_epistemic_assessment(
        claim,
        EpistemicStatus.PROVEN,
        rationale=RATIONALE,
        basis=claim.evidence,
    )

    assert (
        first.assessment_id
        != second.assessment_id
    )


def test_assessment_identity_changes_when_rationale_changes() -> None:
    claim = _supported_claim()

    first = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=RATIONALE,
        basis=claim.evidence,
    )

    second = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            RATIONALE
            + " Additional reasoning."
        ),
        basis=claim.evidence,
    )

    assert (
        first.assessment_id
        != second.assessment_id
    )


def test_assessment_identity_changes_when_basis_changes() -> None:
    claim = _supported_claim()

    first = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=RATIONALE,
        basis=claim.evidence,
    )

    second = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=RATIONALE,
        basis=(
            claim.evidence[
                0
            ],
        ),
    )

    assert (
        first.assessment_id
        != second.assessment_id
    )


def test_status_is_explicit_not_automatically_inferred_from_evidence_kind() -> None:
    claim = _supported_claim()

    assessments = {
        status: make_epistemic_assessment(
            claim,
            status,
            rationale=(
                f"Explicit assessment: "
                f"{status.value}"
            ),
            basis=claim.evidence,
        )
        for status in EpistemicStatus
    }

    assert set(
        assessments
    ) == set(
        EpistemicStatus
    )

    assert len(
        {
            assessment.assessment_id
            for assessment
            in assessments.values()
        }
    ) == 4


def test_assessment_can_use_supporting_and_contradicting_claim_evidence() -> None:
    supporting = _runtime_support()
    contradicting = (
        _runtime_contradiction()
    )

    claim = _claim(
        supporting,
        contradicting,
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.DISPUTED,
        rationale=(
            "The claim currently has "
            "supporting and contradicting evidence."
        ),
        basis=claim.evidence,
    )

    assert (
        assessment.status
        is EpistemicStatus.DISPUTED
    )

    assert (
        assessment.basis_reference_ids
        == tuple(
            sorted(
                (
                    supporting.reference_id,
                    contradicting.reference_id,
                )
            )
        )
    )
