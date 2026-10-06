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
    HorizonInvestigationView,
    compile_investigation_request,
)
from horizon.investigator.proposal import (
    InvestigationProposalError,
    InvestigationProposalKind,
    parse_investigation_proposal,
)
from horizon.world_model.assertion import (
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.reconciliation import (
    analyze_world_model_snapshot,
)
from horizon.world_model.snapshot import (
    make_world_model_snapshot,
)


def _ownership_fact(
    *,
    subject_id: str,
    evidence_id: str,
):
    evidence = make_claim_evidence_reference(
        ClaimEvidenceKind.STATIC,
        ClaimEvidenceRelation.SUPPORTS,
        evidence_id,
    )

    claim = make_evidence_backed_claim(
        (
            f"{subject_id} owns responsibility for "
            "the retry eligibility decision."
        ),
        scope="Capability 021B proposal-schema scenario.",
        evidence=(evidence,),
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "Evidence supports a candidate ownership interpretation "
            "without proving exclusive ownership."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        subject_id,
        WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR,
        "responsibility:retry-eligibility-decision",
        claim=claim,
        assessment=assessment,
    )

    return (
        evidence,
        claim,
        assessment,
        assertion,
    )


def _request():
    server = _ownership_fact(
        subject_id="component:server-orchestration",
        evidence_id="static-evidence:server-retry-rule",
    )

    engine = _ownership_fact(
        subject_id="component:flow-run-engine",
        evidence_id="static-evidence:engine-reexecution",
    )

    snapshot = make_world_model_snapshot(
        claims=(
            engine[1],
            server[1],
        ),
        assessments=(
            server[2],
            engine[2],
        ),
        assertions=(
            server[3],
            engine[3],
        ),
    )

    analysis = analyze_world_model_snapshot(
        snapshot
    )

    assert len(
        analysis.open_questions
    ) == 1

    question = analysis.open_questions[0]

    view = HorizonInvestigationView(
        snapshot=snapshot,
        analysis=analysis,
        evidence_records=(
            CanonicalEvidenceRecord(
                evidence_id=(
                    "static-evidence:"
                    "server-retry-rule"
                ),
                evidence_kind="STATIC",
                canonical_payload=(
                    '{"symbol":"server-retry-rule"}'
                ),
            ),
            CanonicalEvidenceRecord(
                evidence_id=(
                    "static-evidence:"
                    "engine-reexecution"
                ),
                evidence_kind="STATIC",
                canonical_payload=(
                    '{"symbol":"engine-reexecution"}'
                ),
            ),
        ),
    )

    request = compile_investigation_request(
        view,
        question_id=question.question_id,
    )

    return request


def _common(
    request,
) -> dict[str, object]:
    return {
        "question_id": request.question_id,
        "relationship_id": (
            request.relationship_id
        ),
        "assertion_ids": list(
            request.assertion_ids
        ),
        "claim_ids": list(
            request.claim_ids
        ),
        "assessment_ids": list(
            request.assessment_ids
        ),
        "evidence_reference_ids": list(
            request.evidence_reference_ids
        ),
    }


def test_proposal_vocabulary_is_exactly_four_types() -> None:
    assert tuple(
        item.value
        for item
        in InvestigationProposalKind
    ) == (
        "PROPOSE_INVESTIGATION",
        "PROPOSE_HYPOTHESIS",
        "REFINE_OBJECT",
        "DECLARE_INSUFFICIENT_EVIDENCE",
    )


def test_valid_propose_investigation_is_content_addressed() -> None:
    request = _request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **_common(request),
        "investigation_questions": [
            (
                "Which component schedules the retry "
                "state transition?"
            ),
            (
                "Which component triggers the next "
                "user-code attempt?"
            ),
        ],
    }

    proposal = parse_investigation_proposal(
        request,
        raw,
    )

    assert proposal.kind is (
        InvestigationProposalKind.PROPOSE_INVESTIGATION
    )

    assert proposal.question_id == (
        request.question_id
    )

    assert proposal.proposal_id.startswith(
        "investigation-proposal:"
    )

    assert proposal.investigation_questions == (
        (
            "Which component schedules the retry "
            "state transition?"
        ),
        (
            "Which component triggers the next "
            "user-code attempt?"
        ),
    )


def test_valid_hypothesis_is_only_a_candidate_interpretation() -> None:
    request = _request()

    raw = {
        "type": "PROPOSE_HYPOTHESIS",
        **_common(request),
        "hypothesis": (
            "Retry policy ownership and retry execution "
            "ownership may belong to different components."
        ),
        "test_questions": [
            (
                "What evidence distinguishes policy "
                "selection from execution?"
            ),
        ],
    }

    proposal = parse_investigation_proposal(
        request,
        raw,
    )

    assert proposal.kind is (
        InvestigationProposalKind.PROPOSE_HYPOTHESIS
    )

    assert proposal.hypothesis == (
        "Retry policy ownership and retry execution "
        "ownership may belong to different components."
    )


def test_valid_refine_object_creates_horizon_candidate_ids() -> None:
    request = _request()

    raw = {
        "type": "REFINE_OBJECT",
        **_common(request),
        "candidates": [
            {
                "label": (
                    "retry policy eligibility ownership"
                ),
                "investigation_question": (
                    "Who decides whether retry is eligible?"
                ),
            },
            {
                "label": (
                    "retry scheduling and re-execution ownership"
                ),
                "investigation_question": (
                    "Who schedules the state transition and "
                    "triggers the next user-code attempt?"
                ),
            },
        ],
        "missing_evidence_questions": [
            (
                "Who schedules the retry state transition?"
            ),
            (
                "Who triggers the next user-code attempt?"
            ),
        ],
    }

    proposal = parse_investigation_proposal(
        request,
        raw,
    )

    assert proposal.kind is (
        InvestigationProposalKind.REFINE_OBJECT
    )

    assert len(
        proposal.candidates
    ) == 2

    assert all(
        candidate.candidate_id.startswith(
            "investigation-candidate:"
        )
        for candidate
        in proposal.candidates
    )

    assert len(
        {
            candidate.candidate_id
            for candidate
            in proposal.candidates
        }
    ) == 2


def test_valid_insufficient_evidence_records_missing_questions() -> None:
    request = _request()

    raw = {
        "type": "DECLARE_INSUFFICIENT_EVIDENCE",
        **_common(request),
        "missing_evidence_questions": [
            (
                "Which component performs the retry "
                "transition scheduling?"
            ),
        ],
    }

    proposal = parse_investigation_proposal(
        request,
        raw,
    )

    assert proposal.kind is (
        InvestigationProposalKind
        .DECLARE_INSUFFICIENT_EVIDENCE
    )

    assert proposal.missing_evidence_questions == (
        (
            "Which component performs the retry "
            "transition scheduling?"
        ),
    )


@pytest.mark.parametrize(
    (
        "field",
        "invented",
    ),
    (
        (
            "question_id",
            "world-model-open-question:invented",
        ),
        (
            "relationship_id",
            "world-model-relationship:invented",
        ),
        (
            "assertion_ids",
            [
                "world-model-assertion:invented",
            ],
        ),
        (
            "claim_ids",
            [
                "evidence-backed-claim:invented",
            ],
        ),
        (
            "assessment_ids",
            [
                "epistemic-assessment:invented",
            ],
        ),
        (
            "evidence_reference_ids",
            [
                "claim-evidence-reference:invented",
            ],
        ),
    ),
)
def test_any_invented_existing_identifier_rejects_whole_proposal(
    field: str,
    invented: object,
) -> None:
    request = _request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **_common(request),
        "investigation_questions": [
            "What additional evidence is required?",
        ],
    }

    raw[field] = invented

    with pytest.raises(
        InvestigationProposalError
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "answer",
        "winner",
        "conclusion",
        "status",
        "rationale",
    ),
)
def test_unrestricted_semantic_fields_are_rejected(
    forbidden_field: str,
) -> None:
    request = _request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **_common(request),
        "investigation_questions": [
            "What additional evidence is required?",
        ],
        forbidden_field: (
            "The server wins."
        ),
    }

    with pytest.raises(
        InvestigationProposalError
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


def test_unknown_proposal_type_is_rejected() -> None:
    request = _request()

    raw = {
        "type": "ANSWER",
        **_common(request),
    }

    with pytest.raises(
        InvestigationProposalError
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


def test_refine_object_rejects_model_authored_candidate_id() -> None:
    request = _request()

    raw = {
        "type": "REFINE_OBJECT",
        **_common(request),
        "candidates": [
            {
                "candidate_id": (
                    "model-invented:candidate"
                ),
                "label": (
                    "retry policy ownership"
                ),
                "investigation_question": (
                    "Who owns retry eligibility policy?"
                ),
            },
            {
                "label": (
                    "retry execution ownership"
                ),
                "investigation_question": (
                    "Who triggers the next attempt?"
                ),
            },
        ],
        "missing_evidence_questions": [
            "Who schedules the state transition?",
        ],
    }

    with pytest.raises(
        InvestigationProposalError
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


def test_refine_object_requires_at_least_two_candidates() -> None:
    request = _request()

    raw = {
        "type": "REFINE_OBJECT",
        **_common(request),
        "candidates": [
            {
                "label": (
                    "retry ownership"
                ),
                "investigation_question": (
                    "Who owns retry?"
                ),
            },
        ],
        "missing_evidence_questions": [
            "What evidence separates the responsibilities?",
        ],
    }

    with pytest.raises(
        InvestigationProposalError
    ):
        parse_investigation_proposal(
            request,
            raw,
        )


def test_duplicate_reference_ids_are_rejected_not_deduplicated() -> None:
    request = _request()

    raw = {
        "type": "PROPOSE_INVESTIGATION",
        **_common(request),
        "assertion_ids": [
            request.assertion_ids[0],
            request.assertion_ids[0],
        ],
        "investigation_questions": [
            "What additional evidence is required?",
        ],
    }

    with pytest.raises(
        InvestigationProposalError
    ):
        parse_investigation_proposal(
            request,
            raw,
        )
