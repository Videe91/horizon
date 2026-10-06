from __future__ import annotations

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
    EpistemicStatus,
    make_epistemic_assessment,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.render import (
    WorldModelCardSection,
    WorldModelRenderError,
    render_world_model_card,
)
from horizon.world_model.snapshot import (
    WorldModelSnapshot,
    make_world_model_snapshot,
)


def _bundle(
    suffix: str,
    *,
    status: EpistemicStatus = EpistemicStatus.PROVEN,
    relation: WorldModelRelationKind = (
        WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
    ),
) -> tuple[
    EvidenceBackedClaim,
    EpistemicAssessment,
    WorldModelAssertion,
]:
    evidence = make_claim_evidence_reference(
        ClaimEvidenceKind.CAUSAL,
        ClaimEvidenceRelation.SUPPORTS,
        (
            "source-intervention-comparison:"
            f"{suffix}"
        ),
    )

    claim = make_evidence_backed_claim(
        f"Proposition {suffix}.",
        scope=f"Scope {suffix}.",
        evidence=(evidence,),
    )

    assessment = make_epistemic_assessment(
        claim,
        status,
        rationale=f"Rationale {suffix}.",
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        f"subject:{suffix}",
        relation,
        f"object:{suffix}",
        claim=claim,
        assessment=assessment,
    )

    return (
        claim,
        assessment,
        assertion,
    )


def _snapshot(
    *bundles: tuple[
        EvidenceBackedClaim,
        EpistemicAssessment,
        WorldModelAssertion,
    ],
) -> WorldModelSnapshot:
    return make_world_model_snapshot(
        claims=tuple(
            bundle[0]
            for bundle in bundles
        ),
        assessments=tuple(
            bundle[1]
            for bundle in bundles
        ),
        assertions=tuple(
            bundle[2]
            for bundle in bundles
        ),
    )


def _section_block(
    rendered: str,
    heading: str,
    next_heading: str,
) -> str:
    return rendered.split(
        f"\n{heading}\n",
        1,
    )[1].split(
        f"\n{next_heading}\n",
        1,
    )[0]


def test_card_section_vocabulary_and_order_are_exact() -> None:
    assert [
        section.value
        for section in WorldModelCardSection
    ] == [
        "WHAT_IT_IS",
        "WHERE_IT_SITS",
        "WHAT_IT_OWNS",
        "WHAT_IT_DEPENDS_ON",
        "WHAT_MUST_REMAIN_TRUE",
    ]


def test_renderer_emits_title_question_and_card_section_order() -> None:
    bundle = _bundle(
        "shape"
    )

    snapshot = _snapshot(
        bundle
    )

    rendered = render_world_model_card(
        snapshot,
        title="Prefect retry behaviour",
        question=(
            "Who decides whether a failed "
            "Prefect flow retries?"
        ),
        sections={
            WorldModelCardSection.WHAT_IT_IS: (
                bundle[2].assertion_id,
            ),
        },
    )

    assert (
        "TITLE: Prefect retry behaviour"
        in rendered
    )

    assert (
        "QUESTION: Who decides whether a failed "
        "Prefect flow retries?"
        in rendered
    )

    headings = [
        "WHAT IT IS",
        "WHERE IT SITS",
        "WHAT IT OWNS",
        "WHAT IT DEPENDS ON",
        "WHAT MUST REMAIN TRUE",
        "HOW WE KNOW",
    ]

    positions = [
        rendered.index(
            f"\n{heading}\n"
        )
        for heading in headings
    ]

    assert positions == sorted(
        positions
    )


def test_selected_assertion_renders_meaning_status_and_chain() -> None:
    claim, assessment, assertion = _bundle(
        "readable",
        status=(
            EpistemicStatus.PROVEN
        ),
    )

    snapshot = _snapshot(
        (
            claim,
            assessment,
            assertion,
        )
    )

    rendered = render_world_model_card(
        snapshot,
        title="Retry behaviour",
        question="Who decides?",
        sections={
            WorldModelCardSection.WHAT_IT_IS: (
                assertion.assertion_id,
            ),
        },
    )

    evidence_id = (
        assessment.basis_reference_ids[0]
    )

    assert "[PROVEN]" in rendered

    assert (
        "subject:readable "
        "AFFECTS_BEHAVIOR_OF "
        "object:readable"
        in rendered
    )

    assert (
        'claim="Proposition readable."'
        in rendered
    )

    assert (
        f"assertion_id={assertion.assertion_id}"
        in rendered
    )

    assert (
        f"claim_id={claim.claim_id}"
        in rendered
    )

    assert (
        f"assessment_id={assessment.assessment_id}"
        in rendered
    )

    assert (
        f"evidence={evidence_id}"
        in rendered
    )


def test_epistemic_stamp_comes_from_exact_assessment() -> None:
    claim, assessment, assertion = _bundle(
        "disputed",
        status=(
            EpistemicStatus.DISPUTED
        ),
    )

    rendered = render_world_model_card(
        _snapshot(
            (
                claim,
                assessment,
                assertion,
            )
        ),
        title="Disputed fact",
        question="What is disputed?",
        sections={
            WorldModelCardSection.WHAT_IT_IS: (
                assertion.assertion_id,
            ),
        },
    )

    assert "[DISPUTED]" in rendered
    assert "[PROVEN]" not in rendered


def test_empty_semantic_section_displays_explicit_absence() -> None:
    bundle = _bundle(
        "absence"
    )

    rendered = render_world_model_card(
        _snapshot(
            bundle
        ),
        title="Absence",
        question="What is known?",
        sections={},
    )

    block = _section_block(
        rendered,
        "WHAT IT OWNS",
        "WHAT IT DEPENDS ON",
    )

    assert (
        "NO JUSTIFIED ASSERTION SELECTED"
        in block
    )

    assert (
        bundle[2].assertion_id
        not in block
    )


def test_unknown_assertion_id_is_rejected() -> None:
    bundle = _bundle(
        "unknown-id"
    )

    with pytest.raises(
        WorldModelRenderError,
        match="assertion",
    ):
        render_world_model_card(
            _snapshot(
                bundle
            ),
            title="Unknown",
            question="What is known?",
            sections={
                WorldModelCardSection.WHAT_IT_IS: (
                    "world-model-assertion:not-present",
                ),
            },
        )


def test_section_assignment_is_caller_controlled_not_relation_inferred() -> None:
    claim, assessment, assertion = _bundle(
        "caller-controlled",
        relation=(
            WorldModelRelationKind.CALLS
        ),
    )

    rendered = render_world_model_card(
        _snapshot(
            (
                claim,
                assessment,
                assertion,
            )
        ),
        title="Caller controlled",
        question="Where should this appear?",
        sections={
            WorldModelCardSection.WHAT_IT_OWNS: (
                assertion.assertion_id,
            ),
        },
    )

    owns_block = _section_block(
        rendered,
        "WHAT IT OWNS",
        "WHAT IT DEPENDS ON",
    )

    sits_block = _section_block(
        rendered,
        "WHERE IT SITS",
        "WHAT IT OWNS",
    )

    assert (
        assertion.assertion_id
        in owns_block
    )

    assert (
        "subject:caller-controlled "
        "CALLS "
        "object:caller-controlled"
        in owns_block
    )

    assert (
        assertion.assertion_id
        not in sits_block
    )


def test_rendering_is_stable_across_mapping_and_id_order() -> None:
    first = _bundle(
        "stable-a"
    )

    second = _bundle(
        "stable-b",
        status=(
            EpistemicStatus.SUPPORTED_HYPOTHESIS
        ),
    )

    snapshot = _snapshot(
        first,
        second,
    )

    rendered_a = render_world_model_card(
        snapshot,
        title="Stable",
        question="Is rendering stable?",
        sections={
            WorldModelCardSection.WHAT_IT_IS: (
                first[2].assertion_id,
                second[2].assertion_id,
            ),
            WorldModelCardSection.WHAT_IT_OWNS: (),
        },
    )

    rendered_b = render_world_model_card(
        snapshot,
        title="Stable",
        question="Is rendering stable?",
        sections={
            WorldModelCardSection.WHAT_IT_OWNS: (),
            WorldModelCardSection.WHAT_IT_IS: (
                second[2].assertion_id,
                first[2].assertion_id,
            ),
        },
    )

    assert rendered_a == rendered_b


def test_how_we_know_contains_only_selected_assertion_evidence() -> None:
    selected = _bundle(
        "selected"
    )

    unselected = _bundle(
        "unselected"
    )

    rendered = render_world_model_card(
        _snapshot(
            selected,
            unselected,
        ),
        title="Evidence",
        question="How do we know?",
        sections={
            WorldModelCardSection.WHAT_IT_IS: (
                selected[2].assertion_id,
            ),
        },
    )

    how_we_know = rendered.split(
        "\nHOW WE KNOW\n",
        1,
    )[1]

    selected_evidence = (
        selected[1].basis_reference_ids[0]
    )

    unselected_evidence = (
        unselected[1].basis_reference_ids[0]
    )

    assert (
        selected[2].assertion_id
        in how_we_know
    )

    assert (
        selected[0].claim_id
        in how_we_know
    )

    assert (
        selected[1].assessment_id
        in how_we_know
    )

    assert (
        selected_evidence
        in how_we_know
    )

    assert (
        unselected[2].assertion_id
        not in how_we_know
    )

    assert (
        unselected_evidence
        not in how_we_know
    )


def test_all_four_epistemic_states_are_renderable_without_reconciliation() -> None:
    statuses = (
        EpistemicStatus.PROVEN,
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        EpistemicStatus.DISPUTED,
        EpistemicStatus.UNKNOWN,
    )

    bundles = tuple(
        _bundle(
            f"state-{status.value}",
            status=status,
        )
        for status in statuses
    )

    snapshot = _snapshot(
        *bundles
    )

    rendered = render_world_model_card(
        snapshot,
        title="Epistemic states",
        question="What does Horizon believe?",
        sections={
            WorldModelCardSection.WHAT_IT_IS: tuple(
                bundle[2].assertion_id
                for bundle in bundles
            ),
        },
    )

    for status in statuses:
        assert (
            f"[{status.value}]"
            in rendered
        )

    for bundle in bundles:
        assert (
            bundle[2].assertion_id
            in rendered
        )


def test_renderer_leads_with_human_claim_before_machine_trace() -> None:
    claim, assessment, assertion = _bundle(
        "human-readable",
        status=EpistemicStatus.PROVEN,
    )

    rendered = render_world_model_card(
        _snapshot(
            (
                claim,
                assessment,
                assertion,
            )
        ),
        title="Readable",
        question="What actually happened?",
        sections={
            WorldModelCardSection.WHAT_IT_IS: (
                assertion.assertion_id,
            ),
        },
    )

    block = _section_block(
        rendered,
        "WHAT IT IS",
        "WHERE IT SITS",
    ).strip()

    lines = block.splitlines()

    evidence_id = (
        assessment.basis_reference_ids[0]
    )

    assert lines[0] == (
        "[PROVEN] Proposition human-readable. "
        f"| evidence={evidence_id}"
    )

    assert (
        "assertion_id="
        not in lines[0]
    )

    assert (
        "claim_id="
        not in lines[0]
    )

    assert (
        "assessment_id="
        not in lines[0]
    )

    assert (
        "  relation: "
        "subject:human-readable "
        "AFFECTS_BEHAVIOR_OF "
        "object:human-readable"
        in lines
    )

    assert (
        "  rationale: "
        "Rationale human-readable."
        in lines
    )

    assert (
        (
            "  trace: "
            f"assertion_id={assertion.assertion_id} "
            f"| claim_id={claim.claim_id} "
            f"| assessment_id={assessment.assessment_id}"
        )
        in lines
    )


def test_how_we_know_explains_reason_before_raw_trace() -> None:
    claim, assessment, assertion = _bundle(
        "evidence-readable",
        status=EpistemicStatus.SUPPORTED_HYPOTHESIS,
    )

    rendered = render_world_model_card(
        _snapshot(
            (
                claim,
                assessment,
                assertion,
            )
        ),
        title="Readable evidence",
        question="Why does Horizon believe this?",
        sections={
            WorldModelCardSection.WHAT_IT_OWNS: (
                assertion.assertion_id,
            ),
        },
    )

    how_we_know = rendered.split(
        "\nHOW WE KNOW\n",
        1,
    )[1]

    evidence_id = (
        assessment.basis_reference_ids[0]
    )

    assert (
        "[SUPPORTED_HYPOTHESIS] "
        "Proposition evidence-readable."
        in how_we_know
    )

    assert (
        "  rationale: "
        "Rationale evidence-readable."
        in how_we_know
    )

    assert (
        f"  evidence: {evidence_id}"
        in how_we_know
    )

    assert (
        (
            "  trace: "
            f"assertion_id={assertion.assertion_id} "
            f"| claim_id={claim.claim_id} "
            f"| assessment_id={assessment.assessment_id}"
        )
        in how_we_know
    )
