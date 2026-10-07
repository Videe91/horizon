from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.cards.repository import (
    RepositorySemanticSection,
    render_repository_card,
)
from horizon.cards.repository_auto import (
    RepositoryAutomaticCardError,
    build_repository_card_automatically,
)
from horizon.claims.epistemic import (
    EpistemicStatus,
)
from horizon.languages.python.repository_modules import (
    discover_hatch_wheel_import_roots,
)
from horizon.repository.git_blob import (
    read_observed_blob,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.python_index import (
    index_python_repository,
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
    message: str = "fixture",
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
        message,
    )

    return git(
        repository,
        "rev-parse",
        "HEAD",
    )


def write_hatch_project(
    repository: Path,
    *,
    package_path: str = "src/acme",
) -> None:
    (
        repository
        / "pyproject.toml"
    ).write_text(
        f"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "acme-project"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = ["{package_path}"]
""",
        encoding="utf-8",
    )


def extraction_cache(
    tmp_path: Path,
) -> ContentAddressedExtractionCache:
    return (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )


def prepare_index(
    repository: Path,
    commit: str,
    tmp_path: Path,
):
    observation = observe_git_commit(
        repository,
        commit,
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache(
            tmp_path
        ),
    )

    return observation, index


def semantic_state(
    card,
    section: RepositorySemanticSection,
):
    return next(
        state
        for state
        in card.semantic_sections
        if state.section
        is section
    )


def test_explicit_hatch_layout_automatically_proves_where_it_sits(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_hatch_project(
        repository
    )

    package = (
        repository
        / "src"
        / "acme"
    )

    package.mkdir(
        parents=True
    )

    (
        package
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    where = semantic_state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    assert (
        where.status
        is EpistemicStatus.PROVEN
    )

    assert (
        "package path is 'src/acme'"
        in where.reason
    )

    assert (
        "import root 'src'"
        in where.reason
    )

    assert (
        "top-level package 'acme'"
        in where.reason
    )


def test_package_placement_uses_existing_layout_evidence_ids(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_hatch_project(
        repository
    )

    package = (
        repository
        / "src"
        / "acme"
    )

    package.mkdir(
        parents=True
    )

    (
        package
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    pyproject_blob = read_observed_blob(
        repository,
        observation,
        "pyproject.toml",
    )

    layout = (
        discover_hatch_wheel_import_roots(
            pyproject_blob
        )
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    where = semantic_state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    expected = {
        layout.source_evidence_id,
        layout.layout_id,
        *(
            root.evidence_id
            for root
            in layout.import_roots
        ),
    }

    assert set(
        where.evidence_ids
    ) == expected


def test_package_placement_does_not_promote_other_semantic_sections(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_hatch_project(
        repository
    )

    package = (
        repository
        / "src"
        / "acme"
    )

    package.mkdir(
        parents=True
    )

    (
        package
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    states = {
        state.section: state
        for state
        in card.semantic_sections
    }

    assert (
        states[
            RepositorySemanticSection.WHERE_IT_SITS
        ].status
        is EpistemicStatus.PROVEN
    )

    for section in (
        RepositorySemanticSection.WHAT_IT_IS,
        RepositorySemanticSection.WHAT_IT_OWNS,
        RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
        RepositorySemanticSection.WHAT_MUST_REMAIN_TRUE,
    ):
        assert (
            states[
                section
            ].status
            is EpistemicStatus.UNKNOWN
        )


def test_missing_pyproject_keeps_where_it_sits_unknown(
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

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    where = semantic_state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    assert (
        where.status
        is EpistemicStatus.UNKNOWN
    )

    assert where.evidence_ids == ()


def test_unsupported_pyproject_is_not_guessed_from_directory_shape(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "pyproject.toml"
    ).write_text(
        """\
[project]
name = "acme"
version = "1.0.0"
""",
        encoding="utf-8",
    )

    package = (
        repository
        / "src"
        / "acme"
    )

    package.mkdir(
        parents=True
    )

    (
        package
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    where = semantic_state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    assert (
        where.status
        is EpistemicStatus.UNKNOWN
    )

    assert where.evidence_ids == ()


def test_frozen_pyproject_evidence_beats_working_tree_mutation(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_hatch_project(
        repository,
        package_path="src/acme",
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    write_hatch_project(
        repository,
        package_path="wrong/location",
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    where = semantic_state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    assert (
        "package path is 'src/acme'"
        in where.reason
    )

    assert (
        "wrong/location"
        not in where.reason
    )


def test_card_identity_stays_stable_when_deterministic_enrichment_arrives(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_hatch_project(
        repository
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    from horizon.cards.repository import (
        build_repository_card,
    )

    plain = build_repository_card(
        index
    )

    enriched = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    assert (
        plain.card_id
        == enriched.card_id
    )

    assert (
        plain.revision_id
        != enriched.revision_id
    )


def test_render_exposes_package_evidence(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_hatch_project(
        repository
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation, index = prepare_index(
        repository,
        commit,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    rendered = render_repository_card(
        card
    )

    assert (
        "WHERE IT SITS"
        in rendered
    )

    assert (
        "[PROVEN] At frozen commit "
        in rendered
    )

    assert (
        "python-package-layout:"
        in rendered
    )

    assert (
        "python-import-root:"
        in rendered
    )


def test_mismatched_observation_and_index_fail_closed(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_hatch_project(
        repository
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    first_commit = commit_all(
        repository,
        "first",
    )

    first_observation, first_index = (
        prepare_index(
            repository,
            first_commit,
            tmp_path,
        )
    )

    (
        repository
        / "other.py"
    ).write_text(
        "value = 2\n"
    )

    second_commit = commit_all(
        repository,
        "second",
    )

    second_observation = observe_git_commit(
        repository,
        second_commit,
    )

    assert (
        first_observation.observation_id
        != second_observation.observation_id
    )

    with pytest.raises(
        RepositoryAutomaticCardError
    ):
        build_repository_card_automatically(
            repository,
            second_observation,
            first_index,
        )
