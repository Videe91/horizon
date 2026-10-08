from __future__ import annotations

from dataclasses import replace

import pytest

import horizon.cards.repository as repository_card_module
import horizon.investigation.semantic_gap as semantic_gap_module

from horizon.cards.repository import (
    RepositorySemanticSection,
)
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
from horizon.investigation.hypothesis_evaluation import (
    HypothesisEvaluationVerdict,
    parse_hypothesis_evaluation,
)
from horizon.investigation.hypothesis_promotion import (
    SemanticHypothesisPromotionError,
    materialize_supported_what_it_is_hypothesis,
)
from horizon.investigation.semantic_gap import (
    RepositorySemanticGapSection,
    discover_repository_semantic_gaps,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    compile_semantic_gap_investigation_request,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)
from horizon.world_model.assertion import (
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.repository_deterministic import (
    RepositoryDeterministicWorldModel,
)
from horizon.world_model.snapshot import (
    make_world_model_snapshot,
)


COMMIT = "a" * 40

OBSERVATION_ID = (
    "git-observation:"
    "test-semantic-promotion"
)

HYPOTHESIS = (
    "At the frozen repository snapshot, "
    "this repository primarily implements "
    "workflow orchestration software."
)


class FakeIndex:
    def __init__(self) -> None:
        self.commit_sha = COMMIT

        self.repository_observation_id = (
            OBSERVATION_ID
        )


def evidence_record() -> CanonicalEvidenceRecord:
    return CanonicalEvidenceRecord(
        evidence_id=(
            "investigation-source-observation:"
            "semantic-purpose-test"
        ),
        evidence_kind=(
            "investigation-source-observation"
        ),
        canonical_payload=(
            '{"path":"README.md","text":"workflow orchestration"}'
        ),
    )


def base_model(
    record: CanonicalEvidenceRecord,
) -> RepositoryDeterministicWorldModel:
    reference = (
        make_claim_evidence_reference(
            ClaimEvidenceKind.STATIC,
            ClaimEvidenceRelation.SUPPORTS,
            record.evidence_id,
        )
    )

    claim = make_evidence_backed_claim(
        (
            "The repository has an established "
            "context assertion used while testing "
            "semantic promotion."
        ),
        scope=(
            "Exact synthetic repository snapshot."
        ),
        evidence=(
            reference,
        ),
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.PROVEN,
        rationale=(
            "Synthetic context evidence is "
            "deliberately proven for this test."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        OBSERVATION_ID,
        WorldModelRelationKind.DEPENDS_ON,
        "test-context:repository",
        claim=claim,
        assessment=assessment,
    )

    snapshot = make_world_model_snapshot(
        claims=(
            claim,
        ),
        assessments=(
            assessment,
        ),
        assertions=(
            assertion,
        ),
    )

    return RepositoryDeterministicWorldModel(
        source_commit=COMMIT,
        repository_observation_id=(
            OBSERVATION_ID
        ),
        snapshot=snapshot,
        where_it_sits_assertion_ids=(
            assertion.assertion_id,
        ),
        what_it_depends_on_assertion_ids=(),
    )


def setup_supported(
    monkeypatch,
):
    monkeypatch.setattr(
        semantic_gap_module,
        "PythonRepositoryIndex",
        FakeIndex,
    )

    index = FakeIndex()

    record = evidence_record()

    model = base_model(
        record
    )

    gaps = discover_repository_semantic_gaps(
        index,
        model,
    )

    question = next(
        question
        for question
        in gaps.questions
        if (
            question.section
            is RepositorySemanticGapSection
            .WHAT_IT_IS
        )
    )

    request = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=(
                record,
            ),
        )
    )

    proposal = parse_investigation_proposal(
        request,
        {
            "type": "PROPOSE_HYPOTHESIS",
            "question_id": request.question_id,
            "relationship_id": None,
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
            "hypothesis": HYPOTHESIS,
            "test_questions": [
                (
                    "Does the exact repository evidence "
                    "support workflow orchestration as "
                    "the repository's primary purpose?"
                ),
            ],
        },
    )

    evaluation = parse_hypothesis_evaluation(
        request=request,
        source_proposal=proposal,
        raw={
            "request_id": request.request_id,
            "question_id": request.question_id,
            "source_proposal_id": (
                proposal.proposal_id
            ),
            "verdict": "SUPPORTED",
            "supporting_evidence_ids": [
                record.evidence_id,
            ],
            "contradicting_evidence_ids": [],
            "missing_evidence_questions": [],
        },
    )

    return (
        index,
        record,
        model,
        request,
        proposal,
        evaluation,
    )


def promote(
    monkeypatch,
):
    (
        index,
        record,
        model,
        request,
        proposal,
        evaluation,
    ) = setup_supported(
        monkeypatch
    )

    promoted = (
        materialize_supported_what_it_is_hypothesis(
            index=index,
            model=model,
            request=request,
            source_proposal=proposal,
            evaluation=evaluation,
        )
    )

    return (
        index,
        record,
        model,
        request,
        proposal,
        evaluation,
        promoted,
    )


def test_supported_evaluation_materializes_canonical_world_model_chain(
    monkeypatch,
) -> None:
    (
        _,
        record,
        original,
        _,
        _,
        evaluation,
        promoted,
    ) = promote(
        monkeypatch
    )

    assert (
        original.what_it_is_assertion_ids
        == ()
    )

    assert len(
        promoted.what_it_is_assertion_ids
    ) == 1

    assertion_id = (
        promoted.what_it_is_assertion_ids[
            0
        ]
    )

    assertions = {
        assertion.assertion_id: assertion
        for assertion
        in promoted.snapshot.assertions
    }

    assertion = assertions[
        assertion_id
    ]

    assert (
        assertion.relation
        is WorldModelRelationKind.IMPLEMENTS
    )

    assert (
        assertion.subject_id
        == OBSERVATION_ID
    )

    assert (
        assertion.object_id.startswith(
            "repository-purpose:"
        )
    )

    claims = {
        claim.claim_id: claim
        for claim
        in promoted.snapshot.claims
    }

    claim = claims[
        assertion.claim_id
    ]

    assert (
        claim.proposition
        == evaluation.hypothesis
        == HYPOTHESIS
    )

    assert {
        reference.evidence_id
        for reference
        in claim.evidence
    } == {
        record.evidence_id,
    }

    assert all(
        (
            reference.evidence_kind
            is ClaimEvidenceKind.STATIC
            and reference.relation
            is ClaimEvidenceRelation.SUPPORTS
        )
        for reference
        in claim.evidence
    )

    assessments = {
        assessment.assessment_id: (
            assessment
        )
        for assessment
        in promoted.snapshot.assessments
    }

    assessment = assessments[
        assertion.assessment_id
    ]

    assert (
        assessment.status
        is EpistemicStatus
        .SUPPORTED_HYPOTHESIS
    )

    assert (
        evaluation.evaluation_id
        in assessment.rationale
    )

    assert set(
        assessment.basis_reference_ids
    ) == {
        reference.reference_id
        for reference
        in claim.evidence
    }

    assert (
        promoted.snapshot.snapshot_id
        != original.snapshot.snapshot_id
    )


def test_supported_promotion_closes_only_what_it_is_gap(
    monkeypatch,
) -> None:
    (
        index,
        _,
        _,
        _,
        _,
        _,
        promoted,
    ) = promote(
        monkeypatch
    )

    gaps = discover_repository_semantic_gaps(
        index,
        promoted,
    )

    remaining = {
        question.section
        for question
        in gaps.questions
    }

    assert (
        RepositorySemanticGapSection.WHAT_IT_IS
        not in remaining
    )

    assert (
        RepositorySemanticGapSection.WHAT_IT_OWNS
        in remaining
    )

    assert (
        RepositorySemanticGapSection
        .WHAT_MUST_REMAIN_TRUE
        in remaining
    )


def test_card_projects_promoted_what_it_is_as_supported_hypothesis(
    monkeypatch,
) -> None:
    (
        index,
        record,
        _,
        _,
        _,
        _,
        promoted,
    ) = promote(
        monkeypatch
    )

    monkeypatch.setattr(
        repository_card_module,
        "PythonRepositoryIndex",
        FakeIndex,
    )

    states = (
        repository_card_module
        ._semantic_states(
            index,
            promoted,
        )
    )

    state = next(
        state
        for state
        in states
        if (
            state.section
            is RepositorySemanticSection
            .WHAT_IT_IS
        )
    )

    assert (
        state.status
        is EpistemicStatus
        .SUPPORTED_HYPOTHESIS
    )

    assert (
        HYPOTHESIS
        in state.reason
    )

    assert (
        record.evidence_id
        in state.evidence_ids
    )


def test_contradicted_evaluation_cannot_cross_promotion_boundary(
    monkeypatch,
) -> None:
    (
        index,
        record,
        model,
        request,
        proposal,
        _,
    ) = setup_supported(
        monkeypatch
    )

    contradicted = (
        parse_hypothesis_evaluation(
            request=request,
            source_proposal=proposal,
            raw={
                "request_id": (
                    request.request_id
                ),
                "question_id": (
                    request.question_id
                ),
                "source_proposal_id": (
                    proposal.proposal_id
                ),
                "verdict": "CONTRADICTED",
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [
                    record.evidence_id,
                ],
                "missing_evidence_questions": [],
            },
        )
    )

    with pytest.raises(
        SemanticHypothesisPromotionError,
        match="SUPPORTED",
    ):
        materialize_supported_what_it_is_hypothesis(
            index=index,
            model=model,
            request=request,
            source_proposal=proposal,
            evaluation=contradicted,
        )


def test_incomplete_evaluation_cannot_cross_promotion_boundary(
    monkeypatch,
) -> None:
    (
        index,
        record,
        model,
        request,
        proposal,
        _,
    ) = setup_supported(
        monkeypatch
    )

    incomplete = (
        parse_hypothesis_evaluation(
            request=request,
            source_proposal=proposal,
            raw={
                "request_id": (
                    request.request_id
                ),
                "question_id": (
                    request.question_id
                ),
                "source_proposal_id": (
                    proposal.proposal_id
                ),
                "verdict": (
                    "STILL_INCOMPLETE"
                ),
                "supporting_evidence_ids": [
                    record.evidence_id,
                ],
                "contradicting_evidence_ids": [],
                "missing_evidence_questions": [
                    (
                        "Which additional source "
                        "establishes the primary purpose?"
                    ),
                ],
            },
        )
    )

    with pytest.raises(
        SemanticHypothesisPromotionError,
        match="SUPPORTED",
    ):
        materialize_supported_what_it_is_hypothesis(
            index=index,
            model=model,
            request=request,
            source_proposal=proposal,
            evaluation=incomplete,
        )


def test_forged_evaluation_identity_cannot_cross_boundary(
    monkeypatch,
) -> None:
    (
        index,
        _,
        model,
        request,
        proposal,
        evaluation,
    ) = setup_supported(
        monkeypatch
    )

    forged = replace(
        evaluation,
        evaluation_id=(
            "hypothesis-evidence-evaluation:"
            "forged"
        ),
    )

    with pytest.raises(
        SemanticHypothesisPromotionError,
        match="canonical",
    ):
        materialize_supported_what_it_is_hypothesis(
            index=index,
            model=model,
            request=request,
            source_proposal=proposal,
            evaluation=forged,
        )


def test_promotion_cannot_overwrite_existing_what_it_is_selection(
    monkeypatch,
) -> None:
    (
        index,
        _,
        _,
        request,
        proposal,
        evaluation,
        promoted,
    ) = promote(
        monkeypatch
    )

    with pytest.raises(
        SemanticHypothesisPromotionError,
        match="already",
    ):
        materialize_supported_what_it_is_hypothesis(
            index=index,
            model=promoted,
            request=request,
            source_proposal=proposal,
            evaluation=evaluation,
        )


def test_evaluation_verdict_remains_distinct_from_epistemic_status() -> None:
    assert (
        HypothesisEvaluationVerdict.SUPPORTED.value
        == "SUPPORTED"
    )

    assert (
        EpistemicStatus
        .SUPPORTED_HYPOTHESIS
        .value
        == "SUPPORTED_HYPOTHESIS"
    )

    assert (
        HypothesisEvaluationVerdict.SUPPORTED.value
        != EpistemicStatus
        .SUPPORTED_HYPOTHESIS
        .value
    )
