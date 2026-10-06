from __future__ import annotations

import dataclasses

import pytest

from horizon.claims.evidence_backed import (
    ClaimEvidenceKind,
    ClaimEvidenceReference,
    ClaimEvidenceRelation,
    EvidenceBackedClaim,
    EvidenceBackedClaimError,
    make_claim_evidence_reference,
    make_evidence_backed_claim,
)


PROPOSITION = (
    "RetryFailedFlows determines retry eligibility "
    "in the tested flow orchestration scenario."
)

SCOPE = (
    "Prefect commit "
    "2338265f658845a9bef8ce7baf07519b89846dc8 "
    "using the tested default CoreFlowPolicy configuration."
)

STATIC_ID = (
    "python-structural-evidence:static-example"
)

RUNTIME_ID = (
    "runtime-observation:runtime-example"
)

CAUSAL_ID = (
    "source-intervention-comparison:causal-example"
)


def _supporting_reference(
    kind: ClaimEvidenceKind,
    evidence_id: str,
) -> ClaimEvidenceReference:
    return make_claim_evidence_reference(
        kind,
        ClaimEvidenceRelation.SUPPORTS,
        evidence_id,
    )


def _contradicting_reference(
    kind: ClaimEvidenceKind,
    evidence_id: str,
) -> ClaimEvidenceReference:
    return make_claim_evidence_reference(
        kind,
        ClaimEvidenceRelation.CONTRADICTS,
        evidence_id,
    )


def _claim(
    *evidence: ClaimEvidenceReference,
) -> EvidenceBackedClaim:
    return make_evidence_backed_claim(
        PROPOSITION,
        scope=SCOPE,
        evidence=evidence,
    )


def test_claim_preserves_proposition_scope_and_evidence() -> None:
    static = _supporting_reference(
        ClaimEvidenceKind.STATIC,
        STATIC_ID,
    )

    runtime = _supporting_reference(
        ClaimEvidenceKind.RUNTIME,
        RUNTIME_ID,
    )

    causal = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    claim = _claim(
        static,
        runtime,
        causal,
    )

    assert isinstance(
        claim,
        EvidenceBackedClaim,
    )

    assert claim.proposition == PROPOSITION
    assert claim.scope == SCOPE

    assert claim.evidence == (
        causal,
        runtime,
        static,
    )

    assert claim.claim_id.startswith(
        "evidence-backed-claim:"
    )


def test_evidence_reference_preserves_kind_relation_and_identity() -> None:
    reference = (
        make_claim_evidence_reference(
            ClaimEvidenceKind.CAUSAL,
            ClaimEvidenceRelation.SUPPORTS,
            CAUSAL_ID,
        )
    )

    assert isinstance(
        reference,
        ClaimEvidenceReference,
    )

    assert (
        reference.evidence_kind
        is ClaimEvidenceKind.CAUSAL
    )

    assert (
        reference.relation
        is ClaimEvidenceRelation.SUPPORTS
    )

    assert (
        reference.evidence_id
        == CAUSAL_ID
    )

    assert reference.reference_id.startswith(
        "claim-evidence-reference:"
    )


def test_evidence_kind_is_separate_from_epistemic_status() -> None:
    assert {
        member.value
        for member in ClaimEvidenceKind
    } == {
        "STATIC",
        "RUNTIME",
        "CAUSAL",
    }

    assert "PROVEN" not in {
        member.value
        for member in ClaimEvidenceKind
    }

    assert "SUPPORTED_HYPOTHESIS" not in {
        member.value
        for member in ClaimEvidenceKind
    }

    assert "DISPUTED" not in {
        member.value
        for member in ClaimEvidenceKind
    }

    assert "UNKNOWN" not in {
        member.value
        for member in ClaimEvidenceKind
    }


def test_claim_has_no_epistemic_status_field() -> None:
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


def test_claim_requires_explicit_scope() -> None:
    reference = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    with pytest.raises(
        EvidenceBackedClaimError,
        match="scope",
    ):
        make_evidence_backed_claim(
            PROPOSITION,
            scope="",
            evidence=(
                reference,
            ),
        )


def test_claim_requires_nonempty_proposition() -> None:
    reference = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    with pytest.raises(
        EvidenceBackedClaimError,
        match="proposition",
    ):
        make_evidence_backed_claim(
            "",
            scope=SCOPE,
            evidence=(
                reference,
            ),
        )


def test_claim_requires_evidence() -> None:
    with pytest.raises(
        EvidenceBackedClaimError,
        match="evidence",
    ):
        make_evidence_backed_claim(
            PROPOSITION,
            scope=SCOPE,
            evidence=(),
        )


def test_claim_rejects_duplicate_evidence_reference() -> None:
    reference = _supporting_reference(
        ClaimEvidenceKind.RUNTIME,
        RUNTIME_ID,
    )

    with pytest.raises(
        EvidenceBackedClaimError,
        match="duplicate",
    ):
        _claim(
            reference,
            reference,
        )


def test_same_evidence_cannot_support_and_contradict_same_claim() -> None:
    supporting = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    contradicting = _contradicting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    with pytest.raises(
        EvidenceBackedClaimError,
        match="support.*contradict|contradict.*support",
    ):
        _claim(
            supporting,
            contradicting,
        )


def test_claim_identity_is_independent_of_input_evidence_order() -> None:
    static = _supporting_reference(
        ClaimEvidenceKind.STATIC,
        STATIC_ID,
    )

    runtime = _supporting_reference(
        ClaimEvidenceKind.RUNTIME,
        RUNTIME_ID,
    )

    causal = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    first = _claim(
        static,
        runtime,
        causal,
    )

    second = _claim(
        causal,
        static,
        runtime,
    )

    assert first == second
    assert first.claim_id == second.claim_id
    assert first.evidence == second.evidence


def test_claim_identity_changes_when_scope_changes() -> None:
    reference = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    first = _claim(
        reference,
    )

    second = make_evidence_backed_claim(
        PROPOSITION,
        scope=(
            SCOPE
            + " Additional controlled condition."
        ),
        evidence=(
            reference,
        ),
    )

    assert first.claim_id != second.claim_id


def test_claim_identity_changes_when_evidence_changes() -> None:
    first_reference = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        CAUSAL_ID,
    )

    second_reference = _supporting_reference(
        ClaimEvidenceKind.CAUSAL,
        (
            "source-intervention-comparison:"
            "different-causal-example"
        ),
    )

    first = _claim(
        first_reference,
    )

    second = _claim(
        second_reference,
    )

    assert first.claim_id != second.claim_id


def test_evidence_reference_identity_is_deterministic() -> None:
    first = make_claim_evidence_reference(
        ClaimEvidenceKind.RUNTIME,
        ClaimEvidenceRelation.SUPPORTS,
        RUNTIME_ID,
    )

    second = make_claim_evidence_reference(
        ClaimEvidenceKind.RUNTIME,
        ClaimEvidenceRelation.SUPPORTS,
        RUNTIME_ID,
    )

    assert first == second

    assert (
        first.reference_id
        == second.reference_id
    )


def test_evidence_reference_requires_nonempty_evidence_id() -> None:
    with pytest.raises(
        EvidenceBackedClaimError,
        match="evidence",
    ):
        make_claim_evidence_reference(
            ClaimEvidenceKind.RUNTIME,
            ClaimEvidenceRelation.SUPPORTS,
            "",
        )
