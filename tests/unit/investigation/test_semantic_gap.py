from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.investigation.semantic_gap import (
    RepositorySemanticGapError,
    RepositorySemanticGapSection,
    discover_repository_semantic_gaps,
)
from horizon.languages.python.project_dependencies import (
    discover_declared_project_dependencies,
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
from horizon.world_model.repository_deterministic import (
    build_repository_deterministic_world_model,
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


def prepare(
    tmp_path: Path,
):
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
dependencies = [
    "httpx>=0.27",
    "pydantic>=2,<3",
]

[tool.hatch.build.targets.wheel]
packages = ["src/acme"]
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

    observation = observe_git_commit(
        repository,
        commit,
    )

    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    index = index_python_repository(
        repository,
        observation,
        cache,
    )

    blob = read_observed_blob(
        repository,
        observation,
        "pyproject.toml",
    )

    layout = (
        discover_hatch_wheel_import_roots(
            blob
        )
    )

    dependencies = (
        discover_declared_project_dependencies(
            blob
        )
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    return (
        repository,
        observation,
        index,
        model,
    )


def test_two_proven_sections_leave_exactly_three_semantic_gaps(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        model,
    ) = prepare(
        tmp_path
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    assert tuple(
        question.section
        for question
        in gaps.questions
    ) == (
        RepositorySemanticGapSection.WHAT_IT_IS,
        RepositorySemanticGapSection.WHAT_IT_OWNS,
        RepositorySemanticGapSection.WHAT_MUST_REMAIN_TRUE,
    )


def test_proven_sections_do_not_become_semantic_gaps(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        model,
    ) = prepare(
        tmp_path
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    sections = {
        question.section
        for question
        in gaps.questions
    }

    assert (
        RepositorySemanticGapSection.WHERE_IT_SITS
        not in sections
    )

    assert (
        RepositorySemanticGapSection.WHAT_IT_DEPENDS_ON
        not in sections
    )


def test_semantic_gap_is_bound_to_exact_repository_and_world_model_snapshot(
    tmp_path: Path,
) -> None:
    (
        _,
        observation,
        index,
        model,
    ) = prepare(
        tmp_path
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    for question in gaps.questions:
        assert (
            question.source_commit
            == observation.commit_sha
        )

        assert (
            question.repository_observation_id
            == observation.observation_id
        )

        assert (
            question.world_model_snapshot_id
            == model.snapshot.snapshot_id
        )


def test_semantic_gap_context_is_closed_over_known_repository_assertions(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        model,
    ) = prepare(
        tmp_path
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    expected_assertion_ids = tuple(
        sorted(
            (
                *model.where_it_sits_assertion_ids,
                *model.what_it_depends_on_assertion_ids,
            )
        )
    )

    snapshot = model.snapshot

    assertions_by_id = {
        assertion.assertion_id: assertion
        for assertion
        in snapshot.assertions
    }

    expected_claim_ids = tuple(
        sorted(
            {
                assertions_by_id[
                    assertion_id
                ].claim_id
                for assertion_id
                in expected_assertion_ids
            }
        )
    )

    expected_assessment_ids = tuple(
        sorted(
            {
                assertions_by_id[
                    assertion_id
                ].assessment_id
                for assertion_id
                in expected_assertion_ids
            }
        )
    )

    for question in gaps.questions:
        assert (
            question.context_assertion_ids
            == expected_assertion_ids
        )

        assert (
            question.context_claim_ids
            == expected_claim_ids
        )

        assert (
            question.context_assessment_ids
            == expected_assessment_ids
        )

        assert (
            question.context_evidence_reference_ids
        )


def test_empty_repository_world_model_yields_all_five_gaps_with_empty_context(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "empty-cache"
        )
    )

    index = index_python_repository(
        repository,
        observation,
        cache,
    )

    model = (
        build_repository_deterministic_world_model(
            index
        )
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    assert tuple(
        question.section
        for question
        in gaps.questions
    ) == tuple(
        RepositorySemanticGapSection
    )

    assert all(
        question.context_assertion_ids
        == ()
        for question
        in gaps.questions
    )

    assert all(
        question.context_claim_ids
        == ()
        for question
        in gaps.questions
    )

    assert all(
        question.context_assessment_ids
        == ()
        for question
        in gaps.questions
    )

    assert all(
        question.context_evidence_reference_ids
        == ()
        for question
        in gaps.questions
    )


def test_questions_are_explicit_not_claims(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        model,
    ) = prepare(
        tmp_path
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    questions = {
        question.section: question.question
        for question
        in gaps.questions
    }

    assert (
        questions[
            RepositorySemanticGapSection.WHAT_IT_IS
        ].endswith(
            "?"
        )
    )

    assert (
        questions[
            RepositorySemanticGapSection.WHAT_IT_OWNS
        ].endswith(
            "?"
        )
    )

    assert (
        questions[
            RepositorySemanticGapSection.WHAT_MUST_REMAIN_TRUE
        ].endswith(
            "?"
        )
    )


def test_gap_and_question_identities_are_deterministic(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        model,
    ) = prepare(
        tmp_path
    )

    first = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    second = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    assert first == second

    assert (
        first.gap_set_id
        == second.gap_set_id
    )

    assert tuple(
        question.gap_id
        for question
        in first.questions
    ) == tuple(
        question.gap_id
        for question
        in second.questions
    )

    assert tuple(
        question.question_id
        for question
        in first.questions
    ) == tuple(
        question.question_id
        for question
        in second.questions
    )


def test_same_logical_gap_changes_question_identity_when_context_snapshot_changes(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    first_commit = commit_all(
        repository,
        "first",
    )

    first_observation = observe_git_commit(
        repository,
        first_commit,
    )

    first_cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache-one"
        )
    )

    first_index = index_python_repository(
        repository,
        first_observation,
        first_cache,
    )

    first_model = (
        build_repository_deterministic_world_model(
            first_index
        )
    )

    first = (
        discover_repository_semantic_gaps(
            first_index,
            first_model,
        )
    )

    (
        repository
        / "other.py"
    ).write_text(
        "value = 2\n",
        encoding="utf-8",
    )

    second_commit = commit_all(
        repository,
        "second",
    )

    second_observation = observe_git_commit(
        repository,
        second_commit,
    )

    second_cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache-two"
        )
    )

    second_index = index_python_repository(
        repository,
        second_observation,
        second_cache,
    )

    second_model = (
        build_repository_deterministic_world_model(
            second_index
        )
    )

    second = (
        discover_repository_semantic_gaps(
            second_index,
            second_model,
        )
    )

    first_by_section = {
        question.section: question
        for question
        in first.questions
    }

    second_by_section = {
        question.section: question
        for question
        in second.questions
    }

    for section in RepositorySemanticGapSection:
        assert (
            first_by_section[
                section
            ].gap_id
            != second_by_section[
                section
            ].gap_id
        )

        assert (
            first_by_section[
                section
            ].question_id
            != second_by_section[
                section
            ].question_id
        )


def test_mismatched_index_and_world_model_fail_closed(
    tmp_path: Path,
) -> None:
    (
        repository,
        _,
        _,
        first_model,
    ) = prepare(
        tmp_path
    )

    (
        repository
        / "later.py"
    ).write_text(
        "value = 3\n",
        encoding="utf-8",
    )

    second_commit = commit_all(
        repository,
        "second",
    )

    second_observation = observe_git_commit(
        repository,
        second_commit,
    )

    second_cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache-second"
        )
    )

    second_index = index_python_repository(
        repository,
        second_observation,
        second_cache,
    )

    with pytest.raises(
        RepositorySemanticGapError,
        match="snapshot",
    ):
        discover_repository_semantic_gaps(
            second_index,
            first_model,
        )


def test_gap_discovery_does_not_mutate_world_model(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        model,
    ) = prepare(
        tmp_path
    )

    before = model.snapshot

    discover_repository_semantic_gaps(
        index,
        model,
    )

    assert (
        model.snapshot
        == before
    )

    assert (
        model.snapshot.snapshot_id
        == before.snapshot_id
    )
