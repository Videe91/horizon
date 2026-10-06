from __future__ import annotations

from decimal import Decimal

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
from horizon.investigator.execution import (
    execute_investigation,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    HorizonInvestigationView,
    compile_investigation_request,
)
from horizon.investigator.model import (
    InvestigatorModelInvocation,
    InvestigatorModelResult,
    ModelRunValidationResult,
)
from horizon.investigator.proposal import (
    InvestigationProposalKind,
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


class FakeInvestigatorModel:
    def __init__(
        self,
        result: InvestigatorModelResult,
    ) -> None:
        self.result = result
        self.calls: list[
            InvestigatorModelInvocation
        ] = []

    def invoke(
        self,
        invocation: InvestigatorModelInvocation,
    ) -> InvestigatorModelResult:
        self.calls.append(
            invocation
        )

        return self.result


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
        scope="Capability 021D execution-loop scenario.",
        evidence=(evidence,),
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "Evidence supports a candidate ownership "
            "interpretation without proving exclusivity."
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
            server[1],
            engine[1],
        ),
        assessments=(
            engine[2],
            server[2],
        ),
        assertions=(
            engine[3],
            server[3],
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

    return (
        snapshot,
        analysis,
        request,
    )


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


def _valid_refine_output(
    request,
) -> dict[str, object]:
    return {
        "type": "REFINE_OBJECT",
        **_common(
            request
        ),
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


def test_valid_fake_model_executes_once_and_produces_valid_proposal_and_run() -> None:
    (
        _snapshot,
        _analysis,
        request,
    ) = _request()

    result = InvestigatorModelResult(
        provider="FAKE_PROVIDER",
        model_id="fake-investigator-v1",
        output=_valid_refine_output(
            request
        ),
        input_tokens=800,
        output_tokens=160,
        cost_usd=Decimal("0.040000"),
        api_request_id="fake-request-001",
    )

    model = FakeInvestigatorModel(
        result
    )

    execution = execute_investigation(
        model=model,
        request=request,
        instruction=(
            b"AI proposes. Horizon verifies. "
            b"Evidence changes knowledge."
        ),
        temperature=0.0,
        cost_cap_usd=Decimal("0.100000"),
    )

    assert model.calls == [
        execution.invocation,
    ]

    assert execution.result is result

    assert execution.proposal is not None

    assert execution.proposal.kind is (
        InvestigationProposalKind.REFINE_OBJECT
    )

    assert execution.run.validation_result is (
        ModelRunValidationResult.VALID
    )

    assert execution.run.rejection_reason is None

    assert execution.run.provider == (
        "FAKE_PROVIDER"
    )

    assert execution.run.model_id == (
        "fake-investigator-v1"
    )

    assert execution.run.cost_usd == (
        Decimal("0.040000")
    )

    assert execution.run.cost_cap_usd == (
        Decimal("0.100000")
    )


def test_invalid_model_proposal_is_recorded_and_never_returned_as_proposal() -> None:
    (
        _snapshot,
        _analysis,
        request,
    ) = _request()

    invalid_output = {
        "type": "PROPOSE_INVESTIGATION",
        **_common(
            request
        ),
        "investigation_questions": [
            "What additional evidence is required?",
        ],
        "answer": (
            "The server wins."
        ),
    }

    result = InvestigatorModelResult(
        provider="FAKE_PROVIDER",
        model_id="fake-investigator-v1",
        output=invalid_output,
        input_tokens=700,
        output_tokens=90,
        cost_usd=Decimal("0.030000"),
        api_request_id="fake-request-invalid",
    )

    model = FakeInvestigatorModel(
        result
    )

    execution = execute_investigation(
        model=model,
        request=request,
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("0.100000"),
    )

    assert len(
        model.calls
    ) == 1

    assert execution.proposal is None

    assert execution.run.validation_result is (
        ModelRunValidationResult.INVALID
    )

    assert execution.run.rejection_reason is not None

    assert (
        "proposal validation failed"
        in execution.run.rejection_reason
    )

    assert (
        "strict schema"
        in execution.run.rejection_reason
    )


def test_invented_horizon_identifier_is_recorded_as_invalid() -> None:
    (
        _snapshot,
        _analysis,
        request,
    ) = _request()

    invalid_output = {
        "type": "PROPOSE_INVESTIGATION",
        **_common(
            request
        ),
        "assertion_ids": [
            "world-model-assertion:invented",
        ],
        "investigation_questions": [
            "What evidence should be gathered?",
        ],
    }

    model = FakeInvestigatorModel(
        InvestigatorModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-investigator-v1",
            output=invalid_output,
            input_tokens=700,
            output_tokens=90,
            cost_usd=Decimal("0.030000"),
            api_request_id="fake-request-invented",
        )
    )

    execution = execute_investigation(
        model=model,
        request=request,
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("0.100000"),
    )

    assert len(
        model.calls
    ) == 1

    assert execution.proposal is None

    assert execution.run.validation_result is (
        ModelRunValidationResult.INVALID
    )

    assert execution.run.rejection_reason is not None

    assert (
        "outside the investigation request"
        in execution.run.rejection_reason
    )


def test_over_cap_result_is_invalid_even_when_proposal_shape_is_valid() -> None:
    (
        _snapshot,
        _analysis,
        request,
    ) = _request()

    result = InvestigatorModelResult(
        provider="FAKE_PROVIDER",
        model_id="fake-investigator-v1",
        output=_valid_refine_output(
            request
        ),
        input_tokens=1200,
        output_tokens=220,
        cost_usd=Decimal("0.110000"),
        api_request_id="fake-request-over-cap",
    )

    model = FakeInvestigatorModel(
        result
    )

    execution = execute_investigation(
        model=model,
        request=request,
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("0.100000"),
    )

    assert len(
        model.calls
    ) == 1

    assert execution.proposal is None

    assert execution.run.validation_result is (
        ModelRunValidationResult.INVALID
    )

    assert execution.run.cost_usd == (
        Decimal("0.110000")
    )

    assert execution.run.cost_cap_usd == (
        Decimal("0.100000")
    )

    assert execution.run.rejection_reason == (
        "actual model cost exceeded "
        "pre-registered cost cap"
    )


def test_execution_does_not_mutate_request_or_horizon_world_model() -> None:
    (
        snapshot,
        analysis,
        request,
    ) = _request()

    snapshot_before = snapshot
    analysis_before = analysis
    request_before = request

    model = FakeInvestigatorModel(
        InvestigatorModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-investigator-v1",
            output=_valid_refine_output(
                request
            ),
            input_tokens=600,
            output_tokens=100,
            cost_usd=Decimal("0.020000"),
            api_request_id="fake-request-immutability",
        )
    )

    execute_investigation(
        model=model,
        request=request,
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("0.100000"),
    )

    assert snapshot == snapshot_before
    assert analysis == analysis_before
    assert request == request_before


def test_invalid_output_is_not_silently_retried() -> None:
    (
        _snapshot,
        _analysis,
        request,
    ) = _request()

    invalid_output = {
        "type": "ANSWER",
        **_common(
            request
        ),
    }

    model = FakeInvestigatorModel(
        InvestigatorModelResult(
            provider="FAKE_PROVIDER",
            model_id="fake-investigator-v1",
            output=invalid_output,
            input_tokens=500,
            output_tokens=50,
            cost_usd=Decimal("0.010000"),
            api_request_id="fake-request-no-retry",
        )
    )

    execution = execute_investigation(
        model=model,
        request=request,
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("0.100000"),
    )

    assert len(
        model.calls
    ) == 1

    assert execution.proposal is None

    assert execution.run.validation_result is (
        ModelRunValidationResult.INVALID
    )
