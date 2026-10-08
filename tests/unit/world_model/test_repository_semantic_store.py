from __future__ import annotations

import json

from dataclasses import replace
from pathlib import Path

import pytest

import horizon.cards.repository_auto as repository_auto_module

from horizon.cards.repository_auto import (
    RepositoryAutomaticCardError,
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
from horizon.world_model.assertion import (
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.repository_deterministic import (
    RepositoryDeterministicWorldModel,
)
from horizon.world_model.repository_semantic_store import (
    RepositorySemanticWorldModelStore,
    RepositorySemanticWorldModelStoreError,
    default_repository_semantic_world_model_store_root,
    repository_world_model_snapshot_payload,
    restore_repository_world_model_from_promotion_payload,
)
from horizon.world_model.snapshot import (
    make_world_model_snapshot,
)


COMMIT = "a" * 40

OBSERVATION_ID = (
    "git-observation:"
    "semantic-store-test"
)


def base_model() -> RepositoryDeterministicWorldModel:
    reference = (
        make_claim_evidence_reference(
            ClaimEvidenceKind.STATIC,
            ClaimEvidenceRelation.SUPPORTS,
            "git-blob:test-pyproject",
        )
    )

    claim = make_evidence_backed_claim(
        "The repository declares one deterministic dependency.",
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
            "Synthetic deterministic evidence."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        "python-project:test",
        WorldModelRelationKind.DEPENDS_ON,
        "python-dependencies:test",
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
        where_it_sits_assertion_ids=(),
        what_it_depends_on_assertion_ids=(
            assertion.assertion_id,
        ),
        what_it_is_assertion_ids=(),
    )


def promoted_model() -> RepositoryDeterministicWorldModel:
    base = base_model()

    reference = (
        make_claim_evidence_reference(
            ClaimEvidenceKind.STATIC,
            ClaimEvidenceRelation.SUPPORTS,
            (
                "investigation-source-observation:"
                "purpose"
            ),
        )
    )

    claim = make_evidence_backed_claim(
        (
            "At the frozen repository snapshot, "
            "this repository primarily implements "
            "workflow orchestration software."
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
        EpistemicStatus.SUPPORTED_HYPOTHESIS,
        rationale=(
            "A canonical supported hypothesis "
            "was promoted through Horizon."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        OBSERVATION_ID,
        WorldModelRelationKind.IMPLEMENTS,
        (
            "repository-purpose:"
            "workflow-orchestration"
        ),
        claim=claim,
        assessment=assessment,
    )

    snapshot = make_world_model_snapshot(
        claims=(
            *base.snapshot.claims,
            claim,
        ),
        assessments=(
            *base.snapshot.assessments,
            assessment,
        ),
        assertions=(
            *base.snapshot.assertions,
            assertion,
        ),
    )

    return replace(
        base,
        snapshot=snapshot,
        what_it_is_assertion_ids=(
            assertion.assertion_id,
        ),
    )


def test_missing_overlay_returns_exact_base_model(
    tmp_path: Path,
) -> None:
    base = base_model()

    store = RepositorySemanticWorldModelStore(
        tmp_path
    )

    assert store.load(
        base
    ) == base


def test_store_round_trip_survives_new_store_instance(
    tmp_path: Path,
) -> None:
    base = base_model()
    promoted = promoted_model()

    first = RepositorySemanticWorldModelStore(
        tmp_path
    )

    path = first.save(
        base,
        promoted,
    )

    assert path.is_file()

    second = RepositorySemanticWorldModelStore(
        tmp_path
    )

    loaded = second.load(
        base
    )

    assert loaded == promoted

    assert (
        loaded.snapshot.snapshot_id
        == promoted.snapshot.snapshot_id
    )

    assert (
        loaded.what_it_is_assertion_ids
        == promoted.what_it_is_assertion_ids
    )


def test_same_overlay_save_is_idempotent(
    tmp_path: Path,
) -> None:
    base = base_model()
    promoted = promoted_model()

    store = RepositorySemanticWorldModelStore(
        tmp_path
    )

    first = store.save(
        base,
        promoted,
    )

    before = first.read_bytes()

    second = store.save(
        base,
        promoted,
    )

    after = second.read_bytes()

    assert first == second
    assert before == after


def test_tampered_overlay_fails_closed(
    tmp_path: Path,
) -> None:
    base = base_model()
    promoted = promoted_model()

    store = RepositorySemanticWorldModelStore(
        tmp_path
    )

    path = store.save(
        base,
        promoted,
    )

    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    value[
        "claims"
    ][
        0
    ][
        "proposition"
    ] = "tampered"

    path.write_text(
        json.dumps(
            value,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RepositorySemanticWorldModelStoreError
    ):
        RepositorySemanticWorldModelStore(
            tmp_path
        ).load(
            base
        )


def test_full_promoted_snapshot_payload_reconstructs_exact_model() -> None:
    base = base_model()
    promoted = promoted_model()

    restored = (
        restore_repository_world_model_from_promotion_payload(
            base_model=base,
            promoted_snapshot_payload=(
                repository_world_model_snapshot_payload(
                    promoted.snapshot
                )
            ),
            what_it_is_assertion_ids=(
                promoted.what_it_is_assertion_ids
            ),
        )
    )

    assert restored == promoted


def test_default_store_root_is_configurable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configured = (
        tmp_path
        / "state"
    )

    monkeypatch.setenv(
        "HORIZON_STATE_HOME",
        str(
            configured
        ),
    )

    assert (
        default_repository_semantic_world_model_store_root()
        == (
            configured
            / "repository-semantic-world-model"
        )
    )


def test_automatic_card_reload_helper_recovers_persisted_semantics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_home = (
        tmp_path
        / "state"
    )

    monkeypatch.setenv(
        "HORIZON_STATE_HOME",
        str(
            state_home
        ),
    )

    base = base_model()
    promoted = promoted_model()

    store = RepositorySemanticWorldModelStore(
        default_repository_semantic_world_model_store_root()
    )

    store.save(
        base,
        promoted,
    )

    loaded = (
        repository_auto_module
        ._load_persisted_semantic_world_model(
            base
        )
    )

    assert loaded == promoted


def test_automatic_reload_fails_closed_on_corrupt_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_home = (
        tmp_path
        / "state"
    )

    monkeypatch.setenv(
        "HORIZON_STATE_HOME",
        str(
            state_home
        ),
    )

    base = base_model()
    promoted = promoted_model()

    store = RepositorySemanticWorldModelStore(
        default_repository_semantic_world_model_store_root()
    )

    path = store.save(
        base,
        promoted,
    )

    path.write_text(
        "{}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        RepositoryAutomaticCardError,
        match="semantic",
    ):
        (
            repository_auto_module
            ._load_persisted_semantic_world_model(
                base
            )
        )
