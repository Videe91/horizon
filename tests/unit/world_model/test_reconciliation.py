from __future__ import annotations

import importlib

from horizon.world_model.assertion import (
    WorldModelRelationKind,
)


def test_relationship_cardinality_is_declared_per_relation_kind() -> None:
    reconciliation = importlib.import_module(
        "horizon.world_model.reconciliation"
    )

    cardinality = (
        reconciliation.WorldModelRelationshipCardinality
    )

    policies = (
        reconciliation.WORLD_MODEL_RELATIONSHIP_POLICIES
    )

    assert (
        policies[
            WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR
        ].cardinality
        is cardinality.ONE_SUBJECT_PER_OBJECT
    )

    assert (
        policies[
            WorldModelRelationKind.CALLS
        ].cardinality
        is cardinality.MANY_TO_MANY
    )

    assert (
        policies[
            WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
        ].cardinality
        is cardinality.MANY_TO_MANY
    )

    assert (
        policies[
            WorldModelRelationKind.DEPENDS_ON
        ].cardinality
        is cardinality.MANY_TO_MANY
    )


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
from horizon.world_model.assertion import (
    make_world_model_assertion,
)
from horizon.world_model.snapshot import (
    make_world_model_snapshot,
)


def _make_ownership_assertion(
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
            "the retry-eligibility decision."
        ),
        scope="019 exclusive-ownership unit scenario.",
        evidence=(evidence,),
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "Unit scenario carries an explicit ownership assertion."
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

    return claim, assessment, assertion


def test_different_subjects_conflict_when_exclusive_relation_targets_same_object() -> None:
    reconciliation = importlib.import_module(
        "horizon.world_model.reconciliation"
    )

    server = _make_ownership_assertion(
        subject_id="component:server-orchestration",
        evidence_id="static-evidence:server",
    )

    engine = _make_ownership_assertion(
        subject_id="component:flow-run-engine",
        evidence_id="static-evidence:engine",
    )

    snapshot = make_world_model_snapshot(
        claims=(
            server[0],
            engine[0],
        ),
        assessments=(
            server[1],
            engine[1],
        ),
        assertions=(
            server[2],
            engine[2],
        ),
    )

    analyze = reconciliation.analyze_world_model_snapshot

    analysis = analyze(snapshot)

    assert len(analysis.relationships) == 1

    relationship = analysis.relationships[0]

    assert relationship.kind.value == "CONFLICT"

    assert relationship.assertion_ids == tuple(
        sorted(
            (
                server[2].assertion_id,
                engine[2].assertion_id,
            )
        )
    )


def _make_relation_assertion(
    *,
    subject_id: str,
    relation: WorldModelRelationKind,
    object_id: str,
    evidence_id: str,
):
    evidence = make_claim_evidence_reference(
        ClaimEvidenceKind.STATIC,
        ClaimEvidenceRelation.SUPPORTS,
        evidence_id,
    )

    claim = make_evidence_backed_claim(
        (
            f"{subject_id} {relation.value} "
            f"{object_id}."
        ),
        scope="019 relationship-classification unit scenario.",
        evidence=(evidence,),
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "Unit scenario carries an explicit relationship assertion."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        subject_id,
        relation,
        object_id,
        claim=claim,
        assessment=assessment,
    )

    return claim, assessment, assertion


def test_different_subjects_coexist_when_nonexclusive_relation_targets_same_object() -> None:
    reconciliation = importlib.import_module(
        "horizon.world_model.reconciliation"
    )

    caller_a = _make_relation_assertion(
        subject_id="component:caller-a",
        relation=WorldModelRelationKind.CALLS,
        object_id="python-symbol:shared-target",
        evidence_id="static-evidence:caller-a",
    )

    caller_b = _make_relation_assertion(
        subject_id="component:caller-b",
        relation=WorldModelRelationKind.CALLS,
        object_id="python-symbol:shared-target",
        evidence_id="static-evidence:caller-b",
    )

    snapshot = make_world_model_snapshot(
        claims=(
            caller_a[0],
            caller_b[0],
        ),
        assessments=(
            caller_a[1],
            caller_b[1],
        ),
        assertions=(
            caller_a[2],
            caller_b[2],
        ),
    )

    analysis = reconciliation.analyze_world_model_snapshot(
        snapshot
    )

    assert len(analysis.relationships) == 1

    relationship = analysis.relationships[0]

    assert relationship.kind.value == "COEXIST"

    assert relationship.assertion_ids == tuple(
        sorted(
            (
                caller_a[2].assertion_id,
                caller_b[2].assertion_id,
            )
        )
    )


# Capability 019 receives evidence roots as explicit input.
#
# Long-term supplier:
# the evidence layer should compute these roots by walking its existing
# depends_on edges transitively to leaf evidence. Reconciliation must not
# infer lineage from IDs or create a second lineage system.


def _make_same_semantic_pair(
    *,
    left_evidence_id: str,
    right_evidence_id: str,
):
    left = _make_relation_assertion(
        subject_id="component:retry-policy",
        relation=WorldModelRelationKind.AFFECTS_BEHAVIOR_OF,
        object_id="behavior:retry-eligibility",
        evidence_id=left_evidence_id,
    )

    right = _make_relation_assertion(
        subject_id="component:retry-policy",
        relation=WorldModelRelationKind.AFFECTS_BEHAVIOR_OF,
        object_id="behavior:retry-eligibility",
        evidence_id=right_evidence_id,
    )

    snapshot = make_world_model_snapshot(
        claims=(
            left[0],
            right[0],
        ),
        assessments=(
            left[1],
            right[1],
        ),
        assertions=(
            left[2],
            right[2],
        ),
    )

    return left, right, snapshot


def test_same_assertion_agrees_only_when_evidence_roots_are_independent() -> None:
    reconciliation = importlib.import_module(
        "horizon.world_model.reconciliation"
    )

    left, right, snapshot = _make_same_semantic_pair(
        left_evidence_id="runtime-observation:left",
        right_evidence_id="static-evidence:right",
    )

    analysis = reconciliation.analyze_world_model_snapshot(
        snapshot,
        evidence_roots={
            "runtime-observation:left": frozenset(
                {
                    "evidence-root:runtime-left",
                }
            ),
            "static-evidence:right": frozenset(
                {
                    "evidence-root:static-right",
                }
            ),
        },
    )

    assert len(analysis.relationships) == 1

    relationship = analysis.relationships[0]

    assert relationship.kind.value == "AGREE"

    assert relationship.assertion_ids == tuple(
        sorted(
            (
                left[2].assertion_id,
                right[2].assertion_id,
            )
        )
    )


def test_same_assertion_with_shared_evidence_root_coexists_as_echo() -> None:
    reconciliation = importlib.import_module(
        "horizon.world_model.reconciliation"
    )

    left, right, snapshot = _make_same_semantic_pair(
        left_evidence_id="runtime-observation:base",
        right_evidence_id="source-intervention-comparison:derived",
    )

    analysis = reconciliation.analyze_world_model_snapshot(
        snapshot,
        evidence_roots={
            "runtime-observation:base": frozenset(
                {
                    "evidence-root:base-runtime",
                }
            ),
            "source-intervention-comparison:derived": frozenset(
                {
                    "evidence-root:base-runtime",
                }
            ),
        },
    )

    assert len(analysis.relationships) == 1

    relationship = analysis.relationships[0]

    assert relationship.kind.value == "COEXIST"
    assert relationship.reason.value == "shared_root"

    assert relationship.assertion_ids == tuple(
        sorted(
            (
                left[2].assertion_id,
                right[2].assertion_id,
            )
        )
    )


def test_same_assertion_with_unknown_lineage_coexists_without_claiming_agreement() -> None:
    reconciliation = importlib.import_module(
        "horizon.world_model.reconciliation"
    )

    left, right, snapshot = _make_same_semantic_pair(
        left_evidence_id="runtime-observation:known",
        right_evidence_id="runtime-observation:unknown",
    )

    analysis = reconciliation.analyze_world_model_snapshot(
        snapshot,
        evidence_roots={
            "runtime-observation:known": frozenset(
                {
                    "evidence-root:known",
                }
            ),
        },
    )

    assert len(analysis.relationships) == 1

    relationship = analysis.relationships[0]

    assert relationship.kind.value == "COEXIST"
    assert relationship.reason.value == "lineage_unknown"

    assert relationship.assertion_ids == tuple(
        sorted(
            (
                left[2].assertion_id,
                right[2].assertion_id,
            )
        )
    )


def test_supersession_exists_only_when_explicitly_declared() -> None:
    reconciliation = importlib.import_module(
        "horizon.world_model.reconciliation"
    )

    old, replacement, snapshot = _make_same_semantic_pair(
        left_evidence_id="static-evidence:old",
        right_evidence_id="runtime-observation:replacement",
    )

    # Two assertions by themselves never become a supersession merely
    # because one is intended to be newer.
    plain_analysis = reconciliation.analyze_world_model_snapshot(
        snapshot
    )

    assert all(
        relationship.kind.value != "SUPERSEDE"
        for relationship in plain_analysis.relationships
    )

    replacement_evidence_reference_id = (
        replacement[0].evidence[0].reference_id
    )

    supersession = reconciliation.make_world_model_supersession(
        superseded_assertion_id=old[2].assertion_id,
        replacement_assertion_id=replacement[2].assertion_id,
        reason=(
            "A later investigation explicitly replaces the older "
            "assertion."
        ),
        evidence_reference_ids=(
            replacement_evidence_reference_id,
        ),
    )

    same_supersession = reconciliation.make_world_model_supersession(
        superseded_assertion_id=old[2].assertion_id,
        replacement_assertion_id=replacement[2].assertion_id,
        reason=(
            "A later investigation explicitly replaces the older "
            "assertion."
        ),
        evidence_reference_ids=(
            replacement_evidence_reference_id,
        ),
    )

    assert supersession == same_supersession

    assert (
        supersession.superseded_assertion_id
        == old[2].assertion_id
    )

    assert (
        supersession.replacement_assertion_id
        == replacement[2].assertion_id
    )

    assert supersession.reason == (
        "A later investigation explicitly replaces the older "
        "assertion."
    )

    assert supersession.evidence_reference_ids == (
        replacement_evidence_reference_id,
    )

    assert supersession.supersession_id.startswith(
        "world-model-supersession:"
    )

    analysis = reconciliation.analyze_world_model_snapshot(
        snapshot,
        supersessions=(
            supersession,
        ),
    )

    assert analysis.supersessions == (
        supersession,
    )

    # SUPERSEDE is not smuggled into ordinary pair classification.
    assert all(
        relationship.kind.value != "SUPERSEDE"
        for relationship in analysis.relationships
    )
