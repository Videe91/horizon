from __future__ import annotations

import pytest

from horizon.claims.evidence_backed import (
    ClaimEvidenceKind,
    ClaimEvidenceRelation,
    make_claim_evidence_reference,
    make_evidence_backed_claim,
)
from horizon.claims.epistemic import (
    EpistemicStatus,
    make_epistemic_assessment,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposalError,
    parse_investigation_proposal,
)
from horizon.world_model.assertion import (
    WorldModelRelationKind,
    make_world_model_assertion,
)


def _semantic_gap_request_with_cross_section_context():
    reference = make_claim_evidence_reference(
        ClaimEvidenceKind.STATIC,
        ClaimEvidenceRelation.SUPPORTS,
        "git-blob-evidence:test-pyproject",
    )

    claim = make_evidence_backed_claim(
        (
            "At the frozen test commit, the project "
            "declares one direct dependency."
        ),
        scope=(
            "Synthetic frozen repository observation "
            "for semantic-gap context-selection testing."
        ),
        evidence=(
            reference,
        ),
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.PROVEN,
        rationale=(
            "The dependency declaration is directly "
            "established by the supplied source evidence."
        ),
        basis=(
            reference,
        ),
    )

    assertion = make_world_model_assertion(
        "python-project:test",
        WorldModelRelationKind.DEPENDS_ON,
        "declared-python-dependency-set:test",
        claim=claim,
        assessment=assessment,
    )

    record = CanonicalEvidenceRecord(
        evidence_id=reference.evidence_id,
        evidence_kind="GIT_BLOB_EVIDENCE",
        canonical_payload=(
            '{"path":"pyproject.toml",'
            '"description":"Test project purpose",'
            '"dependencies":["openai"]}'
        ),
    )

    request = InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test-purpose"
        ),
        question=(
            "What is this repository's primary software purpose, "
            "and what evidence establishes it?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(
            assertion,
        ),
        claims=(
            claim,
        ),
        assessments=(
            assessment,
        ),
        evidence_reference_ids=(
            reference.reference_id,
        ),
        evidence_records=(
            record,
        ),
        request_id=(
            "investigation-request:test-purpose-with-cross-section-context"
        ),
        origin=(
            InvestigationRequestOrigin.REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test-purpose"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )

    return (
        request,
        reference,
    )


def test_semantic_gap_proposal_may_ignore_available_cross_section_ids():
    request, _ = (
        _semantic_gap_request_with_cross_section_context()
    )

    assert len(
        request.assertion_ids
    ) == 1

    assert len(
        request.claim_ids
    ) == 1

    assert len(
        request.assessment_ids
    ) == 1

    assert len(
        request.evidence_reference_ids
    ) == 1

    proposal = parse_investigation_proposal(
        request,
        {
            "type": "PROPOSE_HYPOTHESIS",
            "question_id": request.question_id,
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "hypothesis": (
                "The repository may implement a purpose "
                "not established by the supplied dependency context."
            ),
            "test_questions": [
                (
                    "Which repository evidence directly "
                    "establishes that purpose?"
                ),
            ],
        },
    )

    assert proposal.assertion_ids == ()
    assert proposal.claim_ids == ()
    assert proposal.assessment_ids == ()
    assert proposal.evidence_reference_ids == ()


def test_semantic_gap_proposal_still_rejects_ids_outside_request():
    request, _ = (
        _semantic_gap_request_with_cross_section_context()
    )

    with pytest.raises(
        InvestigationProposalError,
        match="outside the investigation request",
    ):
        parse_investigation_proposal(
            request,
            {
                "type": "PROPOSE_HYPOTHESIS",
                "question_id": request.question_id,
                "relationship_id": None,
                "assertion_ids": [
                    "world-model-assertion:not-in-request",
                ],
                "claim_ids": [],
                "assessment_ids": [],
                "evidence_reference_ids": [],
                "hypothesis": (
                    "The repository may have another purpose."
                ),
                "test_questions": [
                    (
                        "Which repository evidence "
                        "would establish it?"
                    ),
                ],
            },
        )
