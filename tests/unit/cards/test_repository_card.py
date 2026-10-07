from __future__ import annotations

import subprocess

from pathlib import Path

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.cards.repository import (
    RepositoryCardPhase,
    RepositorySemanticSection,
    build_repository_card,
    render_repository_card,
)
from horizon.claims.epistemic import (
    EpistemicStatus,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.python_index import (
    index_python_repository,
)
from horizon.repository.python_progressive import (
    execute_python_structure_batch,
    plan_python_structure_extraction,
)


def git(
    repository: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            *args,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return completed.stdout.strip()


def create_repository(
    tmp_path: Path,
) -> Path:
    repository = (
        tmp_path
        / "repo"
    )

    repository.mkdir()

    git(
        repository,
        "init",
        "-q",
        "-b",
        "main",
    )

    git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    return repository


def commit_all(
    repository: Path,
) -> str:
    git(
        repository,
        "add",
        "-A",
    )

    git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    return git(
        repository,
        "rev-parse",
        "HEAD",
    )


def cache(
    tmp_path: Path,
) -> ContentAddressedExtractionCache:
    return (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )


def test_card_is_available_from_index_without_parsing(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "good.py"
    ).write_text(
        "def good():\n"
        "    return 1\n"
    )

    # Deliberately invalid Python.
    #
    # The instant Card must still appear because indexing does not
    # require structural parsing.
    (
        repository
        / "broken.py"
    ).write_text(
        "def broken(:\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    index = index_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    card = build_repository_card(
        index
    )

    assert (
        card.tracked_python_file_count
        == 2
    )

    assert (
        card.phase
        is RepositoryCardPhase.INDEXED
    )

    assert (
        card.structure_cache_present_count
        == 0
    )

    assert (
        card.structure_cache_missing_count
        == 2
    )


def test_instant_card_proves_only_deterministic_inventory(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "def app():\n"
        "    return 1\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    index = index_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    card = build_repository_card(
        index
    )

    assert (
        card.source_snapshot.status
        is EpistemicStatus.PROVEN
    )

    assert (
        card.python_inventory.status
        is EpistemicStatus.PROVEN
    )

    assert (
        card.source_snapshot.evidence_ids
        == (
            observation.observation_id,
        )
    )

    assert (
        card.python_inventory.evidence_ids
        == (
            index.index_id,
        )
    )


def test_semantic_sections_are_unknown_at_instant_index_stage(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "class Service:\n"
        "    pass\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    index = index_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    card = build_repository_card(
        index
    )

    assert {
        section.section
        for section
        in card.semantic_sections
    } == set(
        RepositorySemanticSection
    )

    assert all(
        section.status
        is EpistemicStatus.UNKNOWN
        for section
        in card.semantic_sections
    )

    assert all(
        section.evidence_ids
        == ()
        for section
        in card.semantic_sections
    )


def test_card_progresses_after_background_extraction(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "a.py"
    ).write_text(
        "def a():\n"
        "    return 1\n"
    )

    (
        repository
        / "b.py"
    ).write_text(
        "def b():\n"
        "    return 2\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    initial_index = (
        index_python_repository(
            repository,
            observation,
            extraction_cache,
        )
    )

    initial_card = (
        build_repository_card(
            initial_index
        )
    )

    plan = (
        plan_python_structure_extraction(
            initial_index
        )
    )

    batch = (
        execute_python_structure_batch(
            repository,
            observation,
            plan,
            extraction_cache,
            offset=0,
            limit=1,
        )
    )

    assert (
        batch.completed_file_count
        == 1
    )

    updated_index = (
        index_python_repository(
            repository,
            observation,
            extraction_cache,
        )
    )

    updated_card = (
        build_repository_card(
            updated_index
        )
    )

    assert (
        initial_card.card_id
        == updated_card.card_id
    )

    assert (
        initial_card.revision_id
        != updated_card.revision_id
    )

    assert (
        initial_card.phase
        is RepositoryCardPhase.INDEXED
    )

    assert (
        updated_card.phase
        is RepositoryCardPhase.STRUCTURE_CACHE_PARTIAL
    )

    assert (
        updated_card.structure_cache_present_count
        == 1
    )

    assert (
        updated_card.structure_cache_missing_count
        == 1
    )


def test_card_reaches_structure_cache_present_phase(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "a.py"
    ).write_text(
        "value = 1\n"
    )

    (
        repository
        / "b.py"
    ).write_text(
        "value = 2\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = (
        plan_python_structure_extraction(
            index
        )
    )

    execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=(
            plan.unique_work_item_count
        ),
    )

    final_index = (
        index_python_repository(
            repository,
            observation,
            extraction_cache,
        )
    )

    card = build_repository_card(
        final_index
    )

    assert (
        card.phase
        is RepositoryCardPhase.STRUCTURE_CACHE_PRESENT
    )

    assert (
        card.structure_cache_present_count
        == 2
    )

    assert (
        card.structure_cache_missing_count
        == 0
    )


def test_progress_does_not_turn_semantic_unknowns_into_fake_truth(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "engine.py"
    ).write_text(
        "class Engine:\n"
        "    def run(self):\n"
        "        helper()\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = (
        plan_python_structure_extraction(
            index
        )
    )

    execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=1,
    )

    updated = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    card = build_repository_card(
        updated
    )

    assert (
        card.phase
        is RepositoryCardPhase.STRUCTURE_CACHE_PRESENT
    )

    assert all(
        section.status
        is EpistemicStatus.UNKNOWN
        for section
        in card.semantic_sections
    )


def test_card_identity_is_deterministic(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "value = 1\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    first = build_repository_card(
        index
    )

    second = build_repository_card(
        index
    )

    assert first == second
    assert first.card_id == second.card_id
    assert first.revision_id == second.revision_id


def test_card_does_not_retain_structural_analysis_objects(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "def app():\n"
        "    helper()\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    index = index_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    card = build_repository_card(
        index
    )

    assert not hasattr(
        card,
        "analysis",
    )

    assert not hasattr(
        card,
        "facts",
    )


def test_render_is_explicit_about_proven_and_unknown_state(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "value = 1\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    index = index_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    card = build_repository_card(
        index
    )

    rendered = render_repository_card(
        card
    )

    assert (
        "[PROVEN] Source snapshot:"
        in rendered
    )

    assert (
        "[PROVEN] Tracked regular Python source files: 1"
        in rendered
    )

    assert (
        "COMPILATION PROGRESS"
        in rendered
    )

    assert (
        "STRUCTURE CACHE PRESENT: 0"
        in rendered
    )

    assert (
        "STRUCTURE CACHE MISSING: 1"
        in rendered
    )

    for heading in (
        "WHAT IT IS",
        "WHERE IT SITS",
        "WHAT IT OWNS",
        "WHAT IT DEPENDS ON",
        "WHAT MUST REMAIN TRUE",
    ):
        assert heading in rendered

    assert rendered.count(
        "[UNKNOWN]"
    ) == 5


def test_zero_python_repository_still_has_card(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "README.md"
    ).write_text(
        "# repository\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    index = index_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    card = build_repository_card(
        index
    )

    assert (
        card.tracked_python_file_count
        == 0
    )

    assert (
        card.phase
        is RepositoryCardPhase.INDEXED
    )
