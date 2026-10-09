from __future__ import annotations

import json

from dataclasses import replace
from decimal import Decimal

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
)
from horizon.investigation.hypothesis_test_planning import (
    HypothesisTestPlanningBridgeError,
    bridge_hypothesis_tests_to_typed_planning,
)
from horizon.investigation.plan import (
    InvestigationStepDraft,
    SearchSourceOperation,
)
from horizon.investigation.proposal_plan import (
    ProposedInvestigationStepDraft,
    compile_semantic_gap_proposal_plan,
)
from horizon.investigation.typed_planner_model import (
    make_semantic_gap_typed_planner_invocation,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
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
            "semantic-gap-followup-investigation-request:test"
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


def hypothesis_proposal(
    *,
    first: str = (
        "Read README.md purpose material."
    ),
    second: str = (
        "Read the Flow and Task docstrings."
    ),
):
    value = request()

    return parse_investigation_proposal(
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
                "The repository may implement "
                "workflow orchestration."
            ),
            "test_questions": [
                first,
                second,
            ],
        },
    )


def test_bridge_preserves_selected_source_backed_hypothesis_basis() -> None:
    evidence_id = (
        "git-blob-evidence:test-source-basis"
    )

    reference = (
        make_claim_evidence_reference(
            ClaimEvidenceKind.STATIC,
            ClaimEvidenceRelation.SUPPORTS,
            evidence_id,
        )
    )

    claim = (
        make_evidence_backed_claim(
            "The repository declares its purpose.",
            scope="repository purpose",
            evidence=(
                reference,
            ),
        )
    )

    record = (
        CanonicalEvidenceRecord(
            evidence_id=(
                evidence_id
            ),
            evidence_kind=(
                "GIT_BLOB_EVIDENCE"
            ),
            canonical_payload=(
                json.dumps(
                    {
                        "evidence_type": (
                            "GIT_BLOB_EVIDENCE"
                        ),
                        "evidence_id": (
                            evidence_id
                        ),
                        "commit_sha": (
                            "a" * 40
                        ),
                        "repository_observation_id": (
                            "git-observation:test"
                        ),
                        "path": (
                            "pyproject.toml"
                        ),
                        "object_id": (
                            "b" * 40
                        ),
                        "content_bytes": 10,
                        "content_base64": (
                            "dGVzdA=="
                        ),
                    },
                    sort_keys=True,
                    separators=(
                        ",",
                        ":",
                    ),
                )
            ),
        )
    )

    value = replace(
        request(),
        claims=(
            claim,
        ),
        evidence_reference_ids=(
            reference.reference_id,
        ),
        evidence_records=(
            record,
        ),
        request_id=(
            "semantic-gap-followup-investigation-request:"
            "source-basis"
        ),
    )

    source = (
        parse_investigation_proposal(
            value,
            {
                "type": (
                    "PROPOSE_HYPOTHESIS"
                ),
                "question_id": (
                    value.question_id
                ),
                "relationship_id": None,
                "assertion_ids": [],
                "claim_ids": [
                    claim.claim_id,
                ],
                "assessment_ids": [],
                "evidence_reference_ids": [
                    reference.reference_id,
                ],
                "hypothesis": (
                    "pyproject.toml declares "
                    "the repository purpose."
                ),
                "test_questions": [
                    (
                        "Verify the exact declared "
                        "repository purpose."
                    ),
                ],
            },
        )
    )

    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=source,
        )
    )

    assert (
        bridge.source_hypothesis
        == source.hypothesis
    )

    assert (
        bridge.source_basis_paths
        == (
            "pyproject.toml",
        )
    )


def test_hypothesis_test_questions_become_exact_planning_questions() -> None:
    value = request()
    source = hypothesis_proposal()

    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=source,
        )
    )

    assert (
        bridge.source_proposal_id
        == source.proposal_id
    )

    assert (
        bridge.source_hypothesis
        == source.hypothesis
    )

    assert (
        bridge.test_questions
        == source.test_questions
    )

    assert (
        bridge.planning_questions
        == source.test_questions
    )

    assert (
        bridge.source_basis_paths
        == ()
    )

    assert (
        bridge.planning_proposal
        .investigation_questions
        == source.test_questions
    )


def test_evaluator_followup_questions_replace_only_current_planning_questions() -> None:
    value = request()

    source = hypothesis_proposal()

    followup = (
        "Which exact implementation passage "
        "shows the remaining unresolved behavior?",
    )

    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=source,
            planning_questions=(
                followup
            ),
        )
    )

    assert (
        bridge.source_proposal_id
        == source.proposal_id
    )

    assert (
        bridge.source_hypothesis
        == source.hypothesis
    )

    assert (
        bridge.test_questions
        == source.test_questions
    )

    assert (
        bridge.planning_questions
        == followup
    )

    assert (
        bridge.planning_proposal
        .investigation_questions
        == followup
    )

    assert (
        source.test_questions
        != followup
    )


def test_followup_planning_questions_must_be_nonempty() -> None:
    with pytest.raises(
        HypothesisTestPlanningBridgeError,
        match=(
            "planning questions"
        ),
    ):
        bridge_hypothesis_tests_to_typed_planning(
            request=request(),
            proposal=(
                hypothesis_proposal()
            ),
            planning_questions=(),
        )


def test_derived_planning_proposal_is_not_source_hypothesis_proposal() -> None:
    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=request(),
            proposal=hypothesis_proposal(),
        )
    )

    assert (
        bridge.planning_proposal.kind.value
        == "PROPOSE_INVESTIGATION"
    )

    assert (
        bridge.planning_proposal.proposal_id
        != bridge.source_proposal_id
    )


def test_scope_identifiers_are_preserved_exactly() -> None:
    source = hypothesis_proposal()

    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=request(),
            proposal=source,
        )
    )

    derived = bridge.planning_proposal

    assert (
        derived.question_id
        == source.question_id
    )

    assert (
        derived.relationship_id
        == source.relationship_id
    )

    assert (
        derived.assertion_ids
        == source.assertion_ids
    )

    assert (
        derived.claim_ids
        == source.claim_ids
    )

    assert (
        derived.assessment_ids
        == source.assessment_ids
    )

    assert (
        derived.evidence_reference_ids
        == source.evidence_reference_ids
    )


def test_bridge_is_deterministic() -> None:
    value = request()
    source = hypothesis_proposal()

    first = (
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=source,
        )
    )

    second = (
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=source,
        )
    )

    assert first == second


def test_changed_test_question_changes_bridge_identity() -> None:
    first = (
        bridge_hypothesis_tests_to_typed_planning(
            request=request(),
            proposal=hypothesis_proposal(
                first="Read README one.",
            ),
        )
    )

    second = (
        bridge_hypothesis_tests_to_typed_planning(
            request=request(),
            proposal=hypothesis_proposal(
                first="Read README two.",
            ),
        )
    )

    assert (
        first.bridge_id
        != second.bridge_id
    )


def test_existing_typed_planner_model_boundary_accepts_derived_proposal() -> None:
    value = request()

    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=hypothesis_proposal(),
        )
    )

    invocation = (
        make_semantic_gap_typed_planner_invocation(
            request=value,
            proposal=(
                bridge.planning_proposal
            ),
            instruction=(
                b"Translate the supplied test questions "
                b"into legal typed Horizon operations."
            ),
            temperature=None,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )

    assert (
        invocation.proposal.proposal_id
        == bridge.planning_proposal.proposal_id
    )

    assert invocation.invocation_id.startswith(
        "semantic-gap-typed-planner-invocation:"
    )


def test_existing_plan_compiler_accepts_derived_planning_proposal() -> None:
    value = request()

    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=hypothesis_proposal(),
        )
    )

    first_question = (
        bridge.test_questions[
            0
        ]
    )

    second_question = (
        bridge.test_questions[
            1
        ]
    )

    plan = compile_semantic_gap_proposal_plan(
        request=value,
        proposal=(
            bridge.planning_proposal
        ),
        bindings=(
            ProposedInvestigationStepDraft(
                investigation_question=(
                    first_question
                ),
                draft=InvestigationStepDraft(
                    step_key="read-purpose",
                    purpose=(
                        "Gather evidence for first "
                        "hypothesis test."
                    ),
                    operation=(
                        SearchSourceOperation(
                            query="README",
                            path_prefix=None,
                        )
                    ),
                    depends_on_keys=(),
                    expected_information=(
                        "Evidence for first test."
                    ),
                    max_seconds=10,
                ),
            ),
            ProposedInvestigationStepDraft(
                investigation_question=(
                    second_question
                ),
                draft=InvestigationStepDraft(
                    step_key="read-symbols",
                    purpose=(
                        "Gather evidence for second "
                        "hypothesis test."
                    ),
                    operation=(
                        SearchSourceOperation(
                            query="class Flow",
                            path_prefix="src",
                        )
                    ),
                    depends_on_keys=(),
                    expected_information=(
                        "Evidence for second test."
                    ),
                    max_seconds=10,
                ),
            ),
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    assert (
        plan.proposal_id
        == bridge.planning_proposal.proposal_id
    )

    assert len(
        plan.steps
    ) == 2


def test_original_hypothesis_proposal_remains_non_executable_directly() -> None:
    value = request()
    source = hypothesis_proposal()

    with pytest.raises(
        Exception,
        match="PROPOSE_INVESTIGATION",
    ):
        compile_semantic_gap_proposal_plan(
            request=value,
            proposal=source,
            bindings=(),
            max_steps=4,
            max_total_seconds=120,
        )


def test_non_hypothesis_proposal_is_rejected() -> None:
    value = request()

    investigation = (
        parse_investigation_proposal(
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
                "investigation_questions": [
                    "Inspect source.",
                ],
            },
        )
    )

    with pytest.raises(
        HypothesisTestPlanningBridgeError,
        match="PROPOSE_HYPOTHESIS",
    ):
        bridge_hypothesis_tests_to_typed_planning(
            request=value,
            proposal=investigation,
        )


def test_request_question_mismatch_is_rejected() -> None:
    source_request = request()
    source = hypothesis_proposal()

    other = InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:other"
        ),
        question="Other question",
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "semantic-gap-followup-investigation-request:other"
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

    assert (
        source.question_id
        == source_request.question_id
    )

    with pytest.raises(
        HypothesisTestPlanningBridgeError,
        match="question",
    ):
        bridge_hypothesis_tests_to_typed_planning(
            request=other,
            proposal=source,
        )


def test_bridge_creates_no_horizon_truth() -> None:
    bridge = (
        bridge_hypothesis_tests_to_typed_planning(
            request=request(),
            proposal=hypothesis_proposal(),
        )
    )

    for value in (
        bridge,
        bridge.planning_proposal,
    ):
        assert not isinstance(
            value,
            EvidenceBackedClaim,
        )

        assert not isinstance(
            value,
            EpistemicAssessment,
        )

        assert not isinstance(
            value,
            WorldModelAssertion,
        )
