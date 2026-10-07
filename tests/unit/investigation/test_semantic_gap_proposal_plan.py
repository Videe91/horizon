from __future__ import annotations

import pytest

from horizon.investigation.plan import (
    InvestigationStepDraft,
    SearchSourceOperation,
)
from horizon.investigation.proposal_plan import (
    ProposedInvestigationStepDraft,
    SemanticGapProposalPlanError,
    compile_semantic_gap_proposal_plan,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)


def request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:test"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )


def proposal(
    investigation_questions: list[str],
):
    value = request()

    return parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_INVESTIGATION",
            "question_id": (
                value.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": (
                investigation_questions
            ),
        },
    )


def binding(
    *,
    question: str,
    key: str,
    query: str,
) -> ProposedInvestigationStepDraft:
    return ProposedInvestigationStepDraft(
        investigation_question=question,
        draft=InvestigationStepDraft(
            step_key=key,
            purpose=(
                "Gather frozen repository evidence "
                "for the proposed investigation."
            ),
            operation=SearchSourceOperation(
                query=query,
                path_prefix="src/acme",
            ),
            depends_on_keys=(),
            expected_information=(
                "Observed source locations relevant "
                "to the investigation question."
            ),
            max_seconds=20,
        ),
    )


def test_semantic_gap_proposal_compiles_through_existing_plan_boundary() -> None:
    value = request()

    question = (
        "Where is the primary execution behavior implemented?"
    )

    proposed = proposal(
        [
            question,
        ]
    )

    plan = compile_semantic_gap_proposal_plan(
        request=value,
        proposal=proposed,
        bindings=(
            binding(
                question=question,
                key="find-execution",
                query="run",
            ),
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    assert (
        plan.proposal_id
        == proposed.proposal_id
    )

    assert (
        plan.question_id
        == value.question_id
    )

    assert len(
        plan.steps
    ) == 1

    assert isinstance(
        plan.steps[0].operation,
        SearchSourceOperation,
    )


def test_every_typed_step_must_bind_to_an_exact_proposed_question() -> None:
    value = request()

    proposed = proposal(
        [
            "Which source establishes repository purpose?",
        ]
    )

    with pytest.raises(
        SemanticGapProposalPlanError,
        match="proposed investigation question",
    ):
        compile_semantic_gap_proposal_plan(
            request=value,
            proposal=proposed,
            bindings=(
                binding(
                    question=(
                        "A question the model never proposed."
                    ),
                    key="invented",
                    query="invented",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_no_model_proposed_question_may_be_silently_dropped() -> None:
    value = request()

    first = (
        "Which entry point begins repository execution?"
    )

    second = (
        "Which source defines the primary runtime abstraction?"
    )

    proposed = proposal(
        [
            first,
            second,
        ]
    )

    with pytest.raises(
        SemanticGapProposalPlanError,
        match="coverage",
    ):
        compile_semantic_gap_proposal_plan(
            request=value,
            proposal=proposed,
            bindings=(
                binding(
                    question=first,
                    key="first",
                    query="run",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_one_proposed_question_may_require_multiple_typed_steps() -> None:
    value = request()

    question = (
        "Which source defines and invokes the primary execution path?"
    )

    proposed = proposal(
        [
            question,
        ]
    )

    plan = compile_semantic_gap_proposal_plan(
        request=value,
        proposal=proposed,
        bindings=(
            binding(
                question=question,
                key="find-definition",
                query="def run",
            ),
            binding(
                question=question,
                key="find-calls",
                query="run(",
            ),
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    assert len(
        plan.steps
    ) == 2


def test_non_investigation_proposal_cannot_become_execution_plan() -> None:
    value = request()

    proposed = (
        parse_investigation_proposal(
            value,
            {
                "type": "PROPOSE_HYPOTHESIS",
                "question_id": (
                    value.question_id
                ),
                "relationship_id": None,
                "assertion_ids": [],
                "claim_ids": [],
                "assessment_ids": [],
                "evidence_reference_ids": [],
                "hypothesis": (
                    "The repository may provide "
                    "workflow orchestration."
                ),
                "test_questions": [
                    (
                        "Which execution paths support "
                        "that interpretation?"
                    ),
                ],
            },
        )
    )

    with pytest.raises(
        SemanticGapProposalPlanError,
        match="PROPOSE_INVESTIGATION",
    ):
        compile_semantic_gap_proposal_plan(
            request=value,
            proposal=proposed,
            bindings=(),
            max_steps=4,
            max_total_seconds=120,
        )


def test_conflict_request_cannot_enter_semantic_gap_plan_path() -> None:
    value = InvestigationRequest(
        question_id=(
            "world-model-open-question:test"
        ),
        question="Who owns the behavior?",
        relationship_id=(
            "world-model-relationship:test"
        ),
        relationship_kind="CONFLICT",
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:conflict"
        ),
        origin=(
            InvestigationRequestOrigin
            .WORLD_MODEL_CONFLICT
        ),
        semantic_gap_id=None,
        semantic_gap_section=None,
    )

    proposed = parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_INVESTIGATION",
            "question_id": (
                value.question_id
            ),
            "relationship_id": (
                value.relationship_id
            ),
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": [
                "What evidence should be gathered?",
            ],
        },
    )

    with pytest.raises(
        SemanticGapProposalPlanError,
        match="semantic-gap",
    ):
        compile_semantic_gap_proposal_plan(
            request=value,
            proposal=proposed,
            bindings=(
                binding(
                    question=(
                        "What evidence should be gathered?"
                    ),
                    key="search",
                    query="behavior",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_proposal_and_request_question_identity_must_match() -> None:
    value = request()

    other = InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:other"
        ),
        question="Another semantic question?",
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:other"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:other"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )

    proposed = parse_investigation_proposal(
        other,
        {
            "type": "PROPOSE_INVESTIGATION",
            "question_id": (
                other.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": [
                "Which source should be inspected?",
            ],
        },
    )

    with pytest.raises(
        SemanticGapProposalPlanError,
        match="question",
    ):
        compile_semantic_gap_proposal_plan(
            request=value,
            proposal=proposed,
            bindings=(
                binding(
                    question=(
                        "Which source should be inspected?"
                    ),
                    key="search",
                    query="source",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_plan_compiler_retains_existing_step_and_time_budgets() -> None:
    value = request()

    question = (
        "Which source should be inspected?"
    )

    proposed = proposal(
        [
            question,
        ]
    )

    with pytest.raises(
        Exception,
        match="step limit",
    ):
        compile_semantic_gap_proposal_plan(
            request=value,
            proposal=proposed,
            bindings=(
                binding(
                    question=question,
                    key="one",
                    query="one",
                ),
                binding(
                    question=question,
                    key="two",
                    query="two",
                ),
            ),
            max_steps=1,
            max_total_seconds=120,
        )


def test_binding_and_plan_are_not_world_model_truth() -> None:
    from horizon.claims.evidence_backed import (
        EvidenceBackedClaim,
    )
    from horizon.claims.epistemic import (
        EpistemicAssessment,
    )
    from horizon.world_model.assertion import (
        WorldModelAssertion,
    )

    value = request()

    question = (
        "Where should Horizon look for execution evidence?"
    )

    proposed = proposal(
        [
            question,
        ]
    )

    typed_binding = binding(
        question=question,
        key="search",
        query="execute",
    )

    plan = compile_semantic_gap_proposal_plan(
        request=value,
        proposal=proposed,
        bindings=(
            typed_binding,
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    for candidate in (
        typed_binding,
        plan,
    ):
        assert not isinstance(
            candidate,
            EvidenceBackedClaim,
        )

        assert not isinstance(
            candidate,
            EpistemicAssessment,
        )

        assert not isinstance(
            candidate,
            WorldModelAssertion,
        )
