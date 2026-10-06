from __future__ import annotations

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
    object_id: str = (
        "responsibility:"
        "retry-eligibility-decision"
    ),
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
        scope=(
            "Capability 021 middleware unit scenario."
        ),
        evidence=(evidence,),
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "The evidence supports an ownership hypothesis "
            "but does not yet prove exclusive responsibility."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        subject_id,
        (
            WorldModelRelationKind
            .OWNS_RESPONSIBILITY_FOR
        ),
        object_id,
        claim=claim,
        assessment=assessment,
    )

    return (
        evidence,
        claim,
        assessment,
        assertion,
    )


def _fixture():
    server = _ownership_fact(
        subject_id=(
            "component:server-orchestration"
        ),
        evidence_id=(
            "static-evidence:server-retry-rule"
        ),
    )

    engine = _ownership_fact(
        subject_id=(
            "component:flow-run-engine"
        ),
        evidence_id=(
            "runtime-observation:"
            "engine-reexecution"
        ),
    )

    unrelated = _ownership_fact(
        subject_id=(
            "component:unrelated"
        ),
        evidence_id=(
            "static-evidence:unrelated"
        ),
        object_id=(
            "responsibility:"
            "unrelated-decision"
        ),
    )

    snapshot = make_world_model_snapshot(
        claims=(
            unrelated[1],
            engine[1],
            server[1],
        ),
        assessments=(
            unrelated[2],
            server[2],
            engine[2],
        ),
        assertions=(
            engine[3],
            unrelated[3],
            server[3],
        ),
    )

    analysis = (
        analyze_world_model_snapshot(
            snapshot
        )
    )

    retry_questions = tuple(
        question
        for question
        in analysis.open_questions
        if (
            "retry eligibility decision"
            in question.question.lower()
        )
    )

    assert len(retry_questions) == 1

    evidence_records = (
        CanonicalEvidenceRecord(
            evidence_id=(
                "runtime-observation:"
                "engine-reexecution"
            ),
            evidence_kind="RUNTIME",
            canonical_payload=(
                '{"event":"engine-reexecution"}'
            ),
        ),
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
                "static-evidence:unrelated"
            ),
            evidence_kind="STATIC",
            canonical_payload=(
                '{"symbol":"unrelated"}'
            ),
        ),
    )

    view = HorizonInvestigationView(
        snapshot=snapshot,
        analysis=analysis,
        evidence_records=evidence_records,
    )

    return (
        server,
        engine,
        unrelated,
        retry_questions[0],
        view,
    )


def test_middleware_compiles_bounded_horizon_context() -> None:
    (
        server,
        engine,
        unrelated,
        question,
        view,
    ) = _fixture()

    request = compile_investigation_request(
        view,
        question_id=question.question_id,
    )

    assert request.question_id == (
        question.question_id
    )

    assert request.relationship_id == (
        question.relationship_id
    )

    assert request.question == (
        question.question
    )

    assert request.assertion_ids == tuple(
        sorted(
            (
                server[3].assertion_id,
                engine[3].assertion_id,
            )
        )
    )

    assert unrelated[3].assertion_id not in (
        request.assertion_ids
    )

    assert request.claim_ids == tuple(
        sorted(
            (
                server[1].claim_id,
                engine[1].claim_id,
            )
        )
    )

    assert unrelated[1].claim_id not in (
        request.claim_ids
    )

    assert request.assessment_ids == tuple(
        sorted(
            (
                server[2].assessment_id,
                engine[2].assessment_id,
            )
        )
    )

    assert unrelated[2].assessment_id not in (
        request.assessment_ids
    )

    assert tuple(
        record.evidence_id
        for record
        in request.evidence_records
    ) == tuple(
        sorted(
            (
                (
                    "runtime-observation:"
                    "engine-reexecution"
                ),
                (
                    "static-evidence:"
                    "server-retry-rule"
                ),
            )
        )
    )

    assert (
        "static-evidence:unrelated"
        not in {
            record.evidence_id
            for record
            in request.evidence_records
        }
    )


def test_middleware_request_is_deterministic_and_content_addressed() -> None:
    (
        _server,
        _engine,
        _unrelated,
        question,
        view,
    ) = _fixture()

    first = compile_investigation_request(
        view,
        question_id=question.question_id,
    )

    reordered_view = HorizonInvestigationView(
        snapshot=view.snapshot,
        analysis=view.analysis,
        evidence_records=tuple(
            reversed(
                view.evidence_records
            )
        ),
    )

    second = compile_investigation_request(
        reordered_view,
        question_id=question.question_id,
    )

    assert first == second

    assert first.request_id.startswith(
        "investigation-request:"
    )


def test_middleware_contains_canonical_evidence_content_not_only_ids() -> None:
    (
        _server,
        _engine,
        _unrelated,
        question,
        view,
    ) = _fixture()

    request = compile_investigation_request(
        view,
        question_id=question.question_id,
    )

    payloads = {
        record.evidence_id:
        record.canonical_payload
        for record
        in request.evidence_records
    }

    assert payloads[
        "static-evidence:server-retry-rule"
    ] == (
        '{"symbol":"server-retry-rule"}'
    )

    assert payloads[
        "runtime-observation:"
        "engine-reexecution"
    ] == (
        '{"event":"engine-reexecution"}'
    )


def test_middleware_does_not_mutate_horizon_world_model() -> None:
    (
        _server,
        _engine,
        _unrelated,
        question,
        view,
    ) = _fixture()

    snapshot_before = view.snapshot
    analysis_before = view.analysis

    compile_investigation_request(
        view,
        question_id=question.question_id,
    )

    assert view.snapshot == snapshot_before
    assert view.analysis == analysis_before
