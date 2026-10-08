"""Evidence-gated promotion of supported repository-purpose hypotheses.

A model evaluation is not Horizon truth.

This module is the explicit boundary that may materialize one already-valid,
SUPPORTED repository WHAT_IT_IS hypothesis into Horizon's existing:

    evidence-backed claim
        -> epistemic assessment
        -> world-model assertion
        -> canonical snapshot

The resulting epistemic status is SUPPORTED_HYPOTHESIS, never PROVEN.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import replace

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
    HypothesisEvidenceEvaluation,
    HypothesisEvaluationError,
    HypothesisEvaluationVerdict,
    parse_hypothesis_evaluation,
)
from horizon.investigation.semantic_gap import (
    RepositorySemanticGapSection,
    discover_repository_semantic_gaps,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    InvestigationProposalError,
    InvestigationProposalKind,
    parse_investigation_proposal,
)
from horizon.repository.python_index import (
    PythonRepositoryIndex,
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


class SemanticHypothesisPromotionError(
    ValueError
):
    """A hypothesis may not cross Horizon's semantic authority boundary."""


def _purpose_object_id(
    hypothesis: str,
) -> str:
    encoded = json.dumps(
        {
            "schema_version": 1,
            "semantic_section": (
                RepositorySemanticGapSection
                .WHAT_IT_IS
                .value
            ),
            "hypothesis": hypothesis,
        },
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
        "repository-purpose:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _proposal_raw(
    proposal: InvestigationProposal,
) -> dict[
    str,
    object,
]:
    return {
        "type": proposal.kind.value,
        "question_id": (
            proposal.question_id
        ),
        "relationship_id": (
            proposal.relationship_id
        ),
        "assertion_ids": list(
            proposal.assertion_ids
        ),
        "claim_ids": list(
            proposal.claim_ids
        ),
        "assessment_ids": list(
            proposal.assessment_ids
        ),
        "evidence_reference_ids": list(
            proposal.evidence_reference_ids
        ),
        "hypothesis": (
            proposal.hypothesis
        ),
        "test_questions": list(
            proposal.test_questions
        ),
    }


def _evaluation_raw(
    evaluation: HypothesisEvidenceEvaluation,
) -> dict[
    str,
    object,
]:
    return {
        "request_id": (
            evaluation.request_id
        ),
        "question_id": (
            evaluation.question_id
        ),
        "source_proposal_id": (
            evaluation.source_proposal_id
        ),
        "verdict": (
            evaluation.verdict.value
        ),
        "supporting_evidence_ids": list(
            evaluation.supporting_evidence_ids
        ),
        "contradicting_evidence_ids": list(
            evaluation.contradicting_evidence_ids
        ),
        "missing_evidence_questions": list(
            evaluation.missing_evidence_questions
        ),
    }


def _validate_current_gap(
    *,
    index: PythonRepositoryIndex,
    model: RepositoryDeterministicWorldModel,
    request: InvestigationRequest,
) -> None:
    if not isinstance(
        model,
        RepositoryDeterministicWorldModel,
    ):
        raise SemanticHypothesisPromotionError(
            "model must be a RepositoryDeterministicWorldModel"
        )

    if (
        model.what_it_is_assertion_ids
    ):
        raise SemanticHypothesisPromotionError(
            "WHAT_IT_IS already has a selected assertion"
        )

    gaps = discover_repository_semantic_gaps(
        index,
        model,
    )

    matches = tuple(
        question
        for question
        in gaps.questions
        if (
            question.section
            is RepositorySemanticGapSection
            .WHAT_IT_IS
        )
    )

    if len(
        matches
    ) != 1:
        raise SemanticHypothesisPromotionError(
            "WHAT_IT_IS is not exactly one open semantic gap"
        )

    question = matches[
        0
    ]

    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise SemanticHypothesisPromotionError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not InvestigationRequestOrigin
        .REPOSITORY_SEMANTIC_GAP
    ):
        raise SemanticHypothesisPromotionError(
            "request is not a repository semantic-gap request"
        )

    if (
        request.semantic_gap_section
        != RepositorySemanticGapSection
        .WHAT_IT_IS
        .value
    ):
        raise SemanticHypothesisPromotionError(
            "request is not for WHAT_IT_IS"
        )

    if (
        request.relationship_id
        is not None
        or request.relationship_kind
        is not None
        or request.relationship_reason
        is not None
    ):
        raise SemanticHypothesisPromotionError(
            "WHAT_IT_IS semantic-gap request may not carry a relationship"
        )

    if (
        request.semantic_gap_id
        != question.gap_id
        or request.question_id
        != question.question_id
        or request.question
        != question.question
    ):
        raise SemanticHypothesisPromotionError(
            "request does not match the current canonical WHAT_IT_IS gap"
        )

    if (
        request.assertion_ids
        != question.context_assertion_ids
        or request.claim_ids
        != question.context_claim_ids
        or request.assessment_ids
        != question.context_assessment_ids
        or request.evidence_reference_ids
        != question.context_evidence_reference_ids
    ):
        raise SemanticHypothesisPromotionError(
            "request context does not match the current World Model snapshot"
        )


def _validate_proposal(
    *,
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
) -> InvestigationProposal:
    if not isinstance(
        source_proposal,
        InvestigationProposal,
    ):
        raise SemanticHypothesisPromotionError(
            "source proposal must be an InvestigationProposal"
        )

    if (
        source_proposal.kind
        is not InvestigationProposalKind
        .PROPOSE_HYPOTHESIS
    ):
        raise SemanticHypothesisPromotionError(
            "promotion requires a PROPOSE_HYPOTHESIS source proposal"
        )

    if (
        source_proposal.hypothesis
        is None
    ):
        raise SemanticHypothesisPromotionError(
            "source proposal does not contain a hypothesis"
        )

    try:
        canonical = (
            parse_investigation_proposal(
                request,
                _proposal_raw(
                    source_proposal
                ),
            )
        )

    except InvestigationProposalError as exc:
        raise SemanticHypothesisPromotionError(
            "source proposal is not canonical for the request"
        ) from exc

    if (
        canonical
        != source_proposal
    ):
        raise SemanticHypothesisPromotionError(
            "source proposal identity is not canonical"
        )

    return canonical


def _validate_evaluation(
    *,
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
    evaluation: HypothesisEvidenceEvaluation,
) -> HypothesisEvidenceEvaluation:
    if not isinstance(
        evaluation,
        HypothesisEvidenceEvaluation,
    ):
        raise SemanticHypothesisPromotionError(
            "evaluation must be a HypothesisEvidenceEvaluation"
        )

    try:
        canonical = (
            parse_hypothesis_evaluation(
                request=request,
                source_proposal=source_proposal,
                raw=_evaluation_raw(
                    evaluation
                ),
            )
        )

    except HypothesisEvaluationError as exc:
        raise SemanticHypothesisPromotionError(
            "hypothesis evaluation is not canonical"
        ) from exc

    if (
        canonical
        != evaluation
    ):
        raise SemanticHypothesisPromotionError(
            "hypothesis evaluation identity is not canonical"
        )

    if (
        canonical.verdict
        is not HypothesisEvaluationVerdict
        .SUPPORTED
    ):
        raise SemanticHypothesisPromotionError(
            "only a canonical SUPPORTED evaluation may be promoted"
        )

    return canonical


def materialize_supported_what_it_is_hypothesis(
    *,
    index: PythonRepositoryIndex,
    model: RepositoryDeterministicWorldModel,
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
    evaluation: HypothesisEvidenceEvaluation,
) -> RepositoryDeterministicWorldModel:
    """Materialize one supported WHAT_IT_IS hypothesis without upgrading it to PROVEN."""

    _validate_current_gap(
        index=index,
        model=model,
        request=request,
    )

    canonical_proposal = (
        _validate_proposal(
            request=request,
            source_proposal=source_proposal,
        )
    )

    canonical_evaluation = (
        _validate_evaluation(
            request=request,
            source_proposal=(
                canonical_proposal
            ),
            evaluation=evaluation,
        )
    )

    request_evidence_ids = {
        record.evidence_id
        for record
        in request.evidence_records
    }

    supporting_ids = (
        canonical_evaluation
        .supporting_evidence_ids
    )

    if (
        not supporting_ids
        or any(
            evidence_id
            not in request_evidence_ids
            for evidence_id
            in supporting_ids
        )
    ):
        raise SemanticHypothesisPromotionError(
            "supporting evidence is outside the exact investigation request"
        )

    references = tuple(
        make_claim_evidence_reference(
            ClaimEvidenceKind.STATIC,
            ClaimEvidenceRelation.SUPPORTS,
            evidence_id,
        )
        for evidence_id
        in supporting_ids
    )

    claim = make_evidence_backed_claim(
        canonical_evaluation.hypothesis,
        scope=(
            "Exact repository observation "
            + model.repository_observation_id
            + " at frozen commit "
            + model.source_commit
            + "."
        ),
        evidence=references,
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "Horizon materialized canonical hypothesis evaluation "
            + canonical_evaluation.evaluation_id
            + " after it returned SUPPORTED for exact request "
            + request.request_id
            + ". This is a supported hypothesis, not PROVEN truth."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        model.repository_observation_id,
        WorldModelRelationKind.IMPLEMENTS,
        _purpose_object_id(
            canonical_evaluation.hypothesis
        ),
        claim=claim,
        assessment=assessment,
    )

    existing_claim_ids = {
        value.claim_id
        for value
        in model.snapshot.claims
    }

    existing_assessment_ids = {
        value.assessment_id
        for value
        in model.snapshot.assessments
    }

    existing_assertion_ids = {
        value.assertion_id
        for value
        in model.snapshot.assertions
    }

    if (
        claim.claim_id
        in existing_claim_ids
        or assessment.assessment_id
        in existing_assessment_ids
        or assertion.assertion_id
        in existing_assertion_ids
    ):
        raise SemanticHypothesisPromotionError(
            "promotion would duplicate an existing World Model object"
        )

    snapshot = make_world_model_snapshot(
        claims=(
            *model.snapshot.claims,
            claim,
        ),
        assessments=(
            *model.snapshot.assessments,
            assessment,
        ),
        assertions=(
            *model.snapshot.assertions,
            assertion,
        ),
    )

    return replace(
        model,
        snapshot=snapshot,
        what_it_is_assertion_ids=(
            assertion.assertion_id,
        ),
    )
