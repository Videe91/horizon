from __future__ import annotations

import json

from horizon.investigation.semantic_understanding_coordinator import (
    _hypothesis_round_typed_planner_instruction,
)
from horizon.investigation.typed_planner_address_hints import (
    MAX_CANDIDATES_PER_QUESTION,
    compile_typed_planner_repository_address_hints,
    typed_planner_repository_address_hints_payload,
)
from horizon.repository.python_index import (
    PythonIndexedFile,
    PythonRepositoryIndex,
)


QUESTION_ONE = (
    "Which implementation or test passages establish what "
    "software-understanding assertions "
    "build_repository_deterministic_world_model produces and "
    "RepositorySemanticWorldModelStore.load restores?"
)

QUESTION_TWO = (
    "Which implementation or test passages demonstrate how changes "
    "in repository source or evidence are incorporated into updated "
    "World Model state and regenerated Cards over time?"
)

QUESTION_THREE = (
    "Which implementation or test passages demonstrate how AI agents "
    "receive or retrieve Cards or other software-understanding context "
    "beyond render_repository_card returning a string?"
)


PATHS = (
    "src/acme/world_model/repository_deterministic.py",
    "src/acme/world_model/repository_semantic_store.py",
    "src/acme/world_model/snapshot.py",
    "src/acme/cards/repository.py",
    "src/acme/cards/repository_auto.py",
    "tests/unit/world_model/test_repository_deterministic.py",
    "tests/unit/world_model/test_repository_semantic_store.py",
    "tests/unit/cards/test_repository_world_model_projection.py",
    "tests/unit/cards/test_repository_card.py",
    "src/acme/transport/unrelated_socket.py",
)


def make_index(
    paths: tuple[str, ...] = PATHS,
) -> PythonRepositoryIndex:
    files = tuple(
        PythonIndexedFile(
            path=path,
            object_id=(
                f"{number:040x}"
            ),
            source_evidence_id=(
                "git-blob:test-"
                + str(
                    number
                )
            ),
            content_sha256=(
                "sha256:"
                + f"{number:064x}"
            ),
            cache_key_id=(
                "python-structure-cache-key:"
                + f"{number:064x}"
            ),
            cache_present=False,
            handle_id=(
                "python-indexed-file:test-"
                + str(
                    number
                )
            ),
        )
        for number, path
        in enumerate(
            paths,
            start=1,
        )
    )

    return PythonRepositoryIndex(
        commit_sha=(
            "a" * 40
        ),
        repository_observation_id=(
            "git-observation:test-address-hints"
        ),
        python_file_count=(
            len(
                files
            )
        ),
        cache_present_count=0,
        cache_missing_count=(
            len(
                files
            )
        ),
        files=files,
        index_id=(
            "python-repository-index:test-address-hints"
        ),
        blob_read_elapsed_ns=0,
        elapsed_ns=0,
    )


def candidates_for(
    hints,
    question: str,
):
    value = next(
        item
        for item
        in hints.question_hints
        if item.question
        == question
    )

    return tuple(
        candidate.path
        for candidate
        in value.candidates
    )


def test_named_world_model_entities_make_implementation_and_tests_addressable() -> None:
    hints = (
        compile_typed_planner_repository_address_hints(
            index=make_index(),
            planning_questions=(
                QUESTION_ONE,
            ),
        )
    )

    paths = set(
        candidates_for(
            hints,
            QUESTION_ONE,
        )
    )

    assert {
        "src/acme/world_model/repository_deterministic.py",
        "src/acme/world_model/repository_semantic_store.py",
        "tests/unit/world_model/test_repository_deterministic.py",
        "tests/unit/world_model/test_repository_semantic_store.py",
        "tests/unit/cards/test_repository_world_model_projection.py",
    }.issubset(
        paths
    )


def test_change_maintenance_question_surfaces_world_model_and_projection_paths() -> None:
    hints = (
        compile_typed_planner_repository_address_hints(
            index=make_index(),
            planning_questions=(
                QUESTION_TWO,
            ),
        )
    )

    paths = set(
        candidates_for(
            hints,
            QUESTION_TWO,
        )
    )

    assert (
        "src/acme/world_model/repository_deterministic.py"
        in paths
    )

    assert (
        "src/acme/world_model/repository_semantic_store.py"
        in paths
    )

    assert (
        "tests/unit/cards/test_repository_world_model_projection.py"
        in paths
    )


def test_agent_card_question_surfaces_card_implementation_paths() -> None:
    hints = (
        compile_typed_planner_repository_address_hints(
            index=make_index(),
            planning_questions=(
                QUESTION_THREE,
            ),
        )
    )

    paths = set(
        candidates_for(
            hints,
            QUESTION_THREE,
        )
    )

    assert (
        "src/acme/cards/repository.py"
        in paths
    )

    assert (
        "src/acme/cards/repository_auto.py"
        in paths
    )

    assert (
        "tests/unit/cards/test_repository_card.py"
        in paths
    )


def test_address_hints_are_bounded_and_deterministically_ordered() -> None:
    first = (
        compile_typed_planner_repository_address_hints(
            index=make_index(),
            planning_questions=(
                QUESTION_ONE,
                QUESTION_TWO,
                QUESTION_THREE,
            ),
        )
    )

    second = (
        compile_typed_planner_repository_address_hints(
            index=make_index(
                tuple(
                    reversed(
                        PATHS
                    )
                )
            ),
            planning_questions=(
                QUESTION_ONE,
                QUESTION_TWO,
                QUESTION_THREE,
            ),
        )
    )

    assert (
        first.question_hints
        == second.question_hints
    )

    assert (
        first.address_hints_id
        == second.address_hints_id
    )

    for value in first.question_hints:
        assert (
            len(
                value.candidates
            )
            <= MAX_CANDIDATES_PER_QUESTION
        )

        assert (
            value.candidates
            == tuple(
                sorted(
                    value.candidates,
                    key=lambda item: (
                        -item.lexical_score,
                        item.path,
                    ),
                )
            )
        )


def test_address_hint_payload_contains_navigation_metadata_not_source_content() -> None:
    hints = (
        compile_typed_planner_repository_address_hints(
            index=make_index(),
            planning_questions=(
                QUESTION_ONE,
            ),
        )
    )

    payload = (
        typed_planner_repository_address_hints_payload(
            hints
        )
    )

    encoded = json.dumps(
        payload,
        sort_keys=True,
    )

    assert (
        "canonical_payload"
        not in encoded
    )

    assert (
        "source_blob_evidence_id"
        not in encoded
    )

    assert (
        "content_sha256"
        not in encoded
    )

    assert (
        "repository_semantic_store.py"
        in encoded
    )


def test_planner_instruction_explicitly_marks_address_hints_non_evidentiary() -> None:
    hints = (
        compile_typed_planner_repository_address_hints(
            index=make_index(),
            planning_questions=(
                QUESTION_ONE,
            ),
        )
    )

    instruction = (
        _hypothesis_round_typed_planner_instruction(
            b"BASE",
            current_round=2,
            max_rounds=2,
            source_hypothesis=(
                "The repository has a declared software purpose."
            ),
            source_basis_paths=(
                "pyproject.toml",
            ),
            repository_address_hints=(
                hints
            ),
        )
    ).decode(
        "utf-8"
    )

    assert (
        "repository_address_hints="
        in instruction
    )

    assert (
        "navigation hints only"
        in instruction
    )

    assert (
        "They are NOT evidence"
        in instruction
    )

    assert (
        "repository_semantic_store.py"
        in instruction
    )

    assert (
        "final_hypothesis_round=true"
        in instruction
    )
