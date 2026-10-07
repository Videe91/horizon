from __future__ import annotations

import subprocess

from pathlib import Path

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.python_open import (
    open_python_repository,
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

    repository.mkdir(
        parents=True
    )

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
    message: str,
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


def cache(
    tmp_path: Path,
) -> ContentAddressedExtractionCache:
    return (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )


def test_open_automatically_discovers_all_tracked_python_files(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "alpha.py"
    ).write_text(
        "def alpha():\n"
        "    return 1\n"
    )

    package = (
        repository
        / "pkg"
    )

    package.mkdir()

    (
        package
        / "beta.py"
    ).write_text(
        "class Beta:\n"
        "    pass\n"
    )

    (
        repository
        / "README.md"
    ).write_text(
        "# ignored\n"
    )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    result = open_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    assert (
        result.python_file_count
        == 2
    )

    assert (
        result.analyzed_file_count
        == 2
    )

    assert (
        result.failed_file_count
        == 0
    )

    assert {
        file.path
        for file
        in result.files
    } == {
        "alpha.py",
        "pkg/beta.py",
    }


def test_first_open_populates_cache_and_second_open_reuses_it(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "alpha.py"
    ).write_text(
        "def alpha():\n"
        "    helper()\n"
    )

    (
        repository
        / "beta.py"
    ).write_text(
        "def beta():\n"
        "    return 2\n"
    )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    extraction_cache = cache(
        tmp_path
    )

    cold = open_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    warm = open_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    assert (
        cold.cache_hits
        + cold.cache_misses
        == cold.analyzed_file_count
    )

    assert (
        warm.cache_hits
        == warm.analyzed_file_count
    )

    assert (
        warm.cache_misses
        == 0
    )

    assert (
        cold.materialization_id
        == warm.materialization_id
    )

    assert [
        file.analysis
        for file
        in cold.files
    ] == [
        file.analysis
        for file
        in warm.files
    ]


def test_duplicate_file_bytes_are_reused_during_same_open(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    content = (
        "def same():\n"
        "    helper()\n"
    )

    (
        repository
        / "first.py"
    ).write_text(
        content
    )

    (
        repository
        / "second.py"
    ).write_text(
        content
    )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    result = open_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    assert (
        result.analyzed_file_count
        == 2
    )

    assert (
        result.cache_misses
        == 1
    )

    assert (
        result.cache_hits
        == 1
    )

    first, second = (
        result.files
    )

    assert (
        first.cache_key_id
        == second.cache_key_id
    )

    assert (
        first.source_evidence_id
        != second.source_evidence_id
    )

    assert (
        first.analysis.analysis_id
        != second.analysis.analysis_id
    )


def test_second_commit_recomputes_only_changed_file_content(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "stable.py"
    ).write_text(
        "def stable():\n"
        "    return 1\n"
    )

    (
        repository
        / "changed.py"
    ).write_text(
        "def changed():\n"
        "    return 1\n"
    )

    first_commit = commit_all(
        repository,
        "first",
    )

    first_observation = (
        observe_git_commit(
            repository,
            first_commit,
        )
    )

    extraction_cache = cache(
        tmp_path
    )

    first = open_python_repository(
        repository,
        first_observation,
        extraction_cache,
    )

    assert (
        first.analyzed_file_count
        == 2
    )

    (
        repository
        / "changed.py"
    ).write_text(
        "def changed():\n"
        "    return 999\n"
    )

    second_commit = commit_all(
        repository,
        "second",
    )

    second_observation = (
        observe_git_commit(
            repository,
            second_commit,
        )
    )

    second = open_python_repository(
        repository,
        second_observation,
        extraction_cache,
    )

    assert (
        second.analyzed_file_count
        == 2
    )

    assert (
        second.cache_hits
        == 1
    )

    assert (
        second.cache_misses
        == 1
    )

    stable = next(
        file
        for file
        in second.files
        if file.path
        == "stable.py"
    )

    changed = next(
        file
        for file
        in second.files
        if file.path
        == "changed.py"
    )

    assert stable.cache_hit is True
    assert changed.cache_hit is False

    assert (
        second.materialization_id
        != first.materialization_id
    )


def test_reused_file_gets_current_commit_provenance(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "stable.py"
    ).write_text(
        "def stable():\n"
        "    return 1\n"
    )

    (
        repository
        / "other.py"
    ).write_text(
        "value = 1\n"
    )

    first_commit = commit_all(
        repository,
        "first",
    )

    first_observation = (
        observe_git_commit(
            repository,
            first_commit,
        )
    )

    extraction_cache = cache(
        tmp_path
    )

    first = open_python_repository(
        repository,
        first_observation,
        extraction_cache,
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

    second_observation = (
        observe_git_commit(
            repository,
            second_commit,
        )
    )

    second = open_python_repository(
        repository,
        second_observation,
        extraction_cache,
    )

    first_stable = next(
        file
        for file
        in first.files
        if file.path
        == "stable.py"
    )

    second_stable = next(
        file
        for file
        in second.files
        if file.path
        == "stable.py"
    )

    assert (
        second_stable.cache_hit
        is True
    )

    assert (
        first_stable.cache_key_id
        == second_stable.cache_key_id
    )

    assert (
        first_stable.source_evidence_id
        != second_stable.source_evidence_id
    )

    assert (
        first_stable.analysis.analysis_id
        != second_stable.analysis.analysis_id
    )

    assert (
        second_stable.analysis.source_evidence_id
        == second_stable.source_evidence_id
    )


def test_invalid_python_is_reported_without_hiding_valid_files(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "valid.py"
    ).write_text(
        "def valid():\n"
        "    return 1\n"
    )

    (
        repository
        / "broken.py"
    ).write_text(
        "def broken(:\n"
    )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    result = open_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    assert (
        result.python_file_count
        == 2
    )

    assert (
        result.analyzed_file_count
        == 1
    )

    assert (
        result.failed_file_count
        == 1
    )

    assert (
        result.files[0].path
        == "valid.py"
    )

    assert (
        result.failures[0].path
        == "broken.py"
    )

    assert (
        result.failures[0].failure_id.startswith(
            "python-open-syntax-failure:"
        )
    )


def test_invalid_python_is_not_cached_as_success(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "broken.py"
    ).write_text(
        "def broken(:\n"
    )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    extraction_cache = cache(
        tmp_path
    )

    first = open_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    second = open_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    assert (
        first.failed_file_count
        == 1
    )

    assert (
        second.failed_file_count
        == 1
    )

    assert (
        first.analyzed_file_count
        == 0
    )

    assert (
        second.analyzed_file_count
        == 0
    )


def test_file_order_and_materialization_identity_are_deterministic(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    for name in (
        "z.py",
        "a.py",
        "m.py",
    ):
        (
            repository
            / name
        ).write_text(
            "value = "
            + repr(
                name
            )
            + "\n"
        )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    extraction_cache = cache(
        tmp_path
    )

    first = open_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    second = open_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    assert [
        file.path
        for file
        in first.files
    ] == [
        "a.py",
        "m.py",
        "z.py",
    ]

    assert (
        first.materialization_id
        == second.materialization_id
    )


def test_total_fact_count_matches_materialized_analyses(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "one.py"
    ).write_text(
        "def one():\n"
        "    helper()\n"
    )

    (
        repository
        / "two.py"
    ).write_text(
        "class Two:\n"
        "    pass\n"
    )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    result = open_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    assert (
        result.total_fact_count
        == sum(
            len(
                file.analysis.facts
            )
            for file
            in result.files
        )
    )


def test_non_regular_python_blob_mode_is_not_treated_as_source(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "real.py"
    ).write_text(
        "value = 1\n"
    )

    (
        repository
        / "target.txt"
    ).write_text(
        "not python\n"
    )

    (
        repository
        / "linked.py"
    ).symlink_to(
        "target.txt"
    )

    commit = commit_all(
        repository,
        "initial",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    result = open_python_repository(
        repository,
        observation,
        cache(
            tmp_path
        ),
    )

    assert [
        file.path
        for file
        in result.files
    ] == [
        "real.py",
    ]
