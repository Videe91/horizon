"""Bind semantic-gap investigation proposals to typed Horizon plans.

The model-facing investigator proposes natural-language investigation
questions.

This module does not interpret those questions into operations.

Instead, it accepts already-typed InvestigationStepDraft values, requires
every typed draft to be explicitly bound to an exact model-proposed
investigation question, and then delegates plan construction to Horizon's
existing closed InvestigationPlan compiler.

This boundary therefore provides authority linkage without pretending
that deterministic code can understand arbitrary natural language.

It performs no operation execution and no World Model mutation.
"""

from __future__ import annotations

from dataclasses import dataclass

from horizon.investigation.plan import (
    InvestigationPlan,
    InvestigationStepDraft,
    compile_investigation_plan,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    InvestigationProposalKind,
)


class SemanticGapProposalPlanError(
    ValueError
):
    """A semantic-gap proposal cannot be bound safely to a typed plan."""


@dataclass(
    frozen=True,
    slots=True,
)
class ProposedInvestigationStepDraft:
    """One typed step explicitly tied to one model-proposed question."""

    investigation_question: str
    draft: InvestigationStepDraft

    def __post_init__(
        self,
    ) -> None:
        if (
            not isinstance(
                self.investigation_question,
                str,
            )
            or not self.investigation_question.strip()
        ):
            raise SemanticGapProposalPlanError(
                "investigation question must be nonempty"
            )

        if not isinstance(
            self.draft,
            InvestigationStepDraft,
        ):
            raise SemanticGapProposalPlanError(
                "draft must be an InvestigationStepDraft"
            )


def _validate_request(
    request: InvestigationRequest,
) -> None:
    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise SemanticGapProposalPlanError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not InvestigationRequestOrigin
        .REPOSITORY_SEMANTIC_GAP
    ):
        raise SemanticGapProposalPlanError(
            "request is not a repository semantic-gap request"
        )

    if request.relationship_id is not None:
        raise SemanticGapProposalPlanError(
            "semantic-gap request may not carry a conflict relationship"
        )

    if (
        request.semantic_gap_id is None
        or not request.semantic_gap_id.strip()
    ):
        raise SemanticGapProposalPlanError(
            "semantic-gap request requires semantic_gap_id"
        )

    if (
        request.semantic_gap_section is None
        or not request.semantic_gap_section.strip()
    ):
        raise SemanticGapProposalPlanError(
            "semantic-gap request requires semantic_gap_section"
        )


def _validate_proposal_binding(
    request: InvestigationRequest,
    proposal: InvestigationProposal,
) -> None:
    if not isinstance(
        proposal,
        InvestigationProposal,
    ):
        raise SemanticGapProposalPlanError(
            "proposal must be an InvestigationProposal"
        )

    if (
        proposal.kind
        is not InvestigationProposalKind
        .PROPOSE_INVESTIGATION
    ):
        raise SemanticGapProposalPlanError(
            "only PROPOSE_INVESTIGATION may become an execution plan"
        )

    if (
        proposal.question_id
        != request.question_id
    ):
        raise SemanticGapProposalPlanError(
            "proposal question does not match request question"
        )

    if (
        proposal.relationship_id
        != request.relationship_id
    ):
        raise SemanticGapProposalPlanError(
            "proposal relationship does not match request"
        )

    request_identifier_sets = (
        (
            set(
                proposal.assertion_ids
            ),
            set(
                request.assertion_ids
            ),
        ),
        (
            set(
                proposal.claim_ids
            ),
            set(
                request.claim_ids
            ),
        ),
        (
            set(
                proposal.assessment_ids
            ),
            set(
                request.assessment_ids
            ),
        ),
        (
            set(
                proposal.evidence_reference_ids
            ),
            set(
                request.evidence_reference_ids
            ),
        ),
    )

    if any(
        not proposed.issubset(
            allowed
        )
        for proposed, allowed
        in request_identifier_sets
    ):
        raise SemanticGapProposalPlanError(
            "proposal references identifiers outside its request"
        )

    if not proposal.proposal_id:
        raise SemanticGapProposalPlanError(
            "proposal identity must be nonempty"
        )

    if not proposal.investigation_questions:
        raise SemanticGapProposalPlanError(
            "PROPOSE_INVESTIGATION requires investigation questions"
        )


def compile_semantic_gap_proposal_plan(
    *,
    request: InvestigationRequest,
    proposal: InvestigationProposal,
    bindings: tuple[
        ProposedInvestigationStepDraft,
        ...,
    ],
    max_steps: int,
    max_total_seconds: int,
) -> InvestigationPlan:
    """Compile typed work for one exact semantic-gap proposal."""

    _validate_request(
        request
    )

    _validate_proposal_binding(
        request,
        proposal,
    )

    if not isinstance(
        bindings,
        tuple,
    ):
        raise SemanticGapProposalPlanError(
            "bindings must be a tuple"
        )

    if not bindings:
        raise SemanticGapProposalPlanError(
            "semantic-gap investigation requires typed step bindings"
        )

    if not all(
        isinstance(
            binding,
            ProposedInvestigationStepDraft,
        )
        for binding
        in bindings
    ):
        raise SemanticGapProposalPlanError(
            "bindings must contain ProposedInvestigationStepDraft values"
        )

    proposed_questions = set(
        proposal.investigation_questions
    )

    bound_questions = {
        binding.investigation_question
        for binding
        in bindings
    }

    outside = (
        bound_questions
        - proposed_questions
    )

    if outside:
        raise SemanticGapProposalPlanError(
            "typed step references a question that is not "
            "an exact proposed investigation question"
        )

    if (
        bound_questions
        != proposed_questions
    ):
        raise SemanticGapProposalPlanError(
            "typed step coverage does not include every "
            "proposed investigation question"
        )

    drafts = tuple(
        binding.draft
        for binding
        in bindings
    )

    return compile_investigation_plan(
        proposal_id=(
            proposal.proposal_id
        ),
        question_id=(
            request.question_id
        ),
        drafts=drafts,
        max_steps=max_steps,
        max_total_seconds=(
            max_total_seconds
        ),
    )
