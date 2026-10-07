from __future__ import annotations

import subprocess

from pathlib import Path

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.languages.python.structure_cache import (
    analyze_python_blob_cached,
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


def extraction_cache(
    tmp_path: Path,
) -> ContentAddressedExtractionCache:
    return ContentAddressedExtractionCache(
        tmp_path
        / "cache"
    )


def test_index_discovers_python_without_parsing(
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

    (
        repository
        / "broken.py"
    ).write_text(
        "def broken(:\n"
    )

    (
        repository
        / "README.md"
    ).write_text(
        "# ignored\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    result = index_python_repository(
        repository,
        observation,
        extraction_cache(
            tmp_path
        ),
    )

    assert result.python_file_count == 2

    assert [
        file.path
        for file
        in result.files
    ] == [
        "broken.py",
        "good.py",
    ]

    assert result.cache_present_count == 0
    assert result.cache_missing_count == 2


def test_index_does_not_populate_missing_cache(
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

    cache = extraction_cache(
        tmp_path
    )

    first = index_python_repository(
        repository,
        observation,
        cache,
    )

    second = index_python_repository(
        repository,
        observation,
        cache,
    )

    assert first.cache_present_count == 0
    assert first.cache_missing_count == 1

    assert second.cache_present_count == 0
    assert second.cache_missing_count == 1

    assert first.index_id == second.index_id


def test_index_reports_existing_structure_cache(
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

    blob = read_observed_blob(
        repository,
        observation,
        "app.py",
    )

    cache = extraction_cache(
        tmp_path
    )

    analyze_python_blob_cached(
        blob,
        cache,
    )

    result = index_python_repository(
        repository,
        observation,
        cache,
    )

    assert result.cache_present_count == 1
    assert result.cache_missing_count == 0

    assert result.files[0].cache_present is True


def test_same_bytes_share_cache_identity_but_not_source_identity(
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
        / "a.py"
    ).write_text(
        content
    )

    (
        repository
        / "b.py"
    ).write_text(
        content
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    result = index_python_repository(
        repository,
        observation,
        extraction_cache(
            tmp_path
        ),
    )

    first, second = result.files

    assert (
        first.cache_key_id
        == second.cache_key_id
    )

    assert (
        first.content_sha256
        == second.content_sha256
    )

    assert (
        first.source_evidence_id
        != second.source_evidence_id
    )

    assert (
        first.handle_id
        != second.handle_id
    )


def test_changed_file_changes_content_identity(
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

    first_commit = commit_all(
        repository
    )

    first_observation = observe_git_commit(
        repository,
        first_commit,
    )

    cache = extraction_cache(
        tmp_path
    )

    first = index_python_repository(
        repository,
        first_observation,
        cache,
    )

    (
        repository
        / "app.py"
    ).write_text(
        "value = 2\n"
    )

    second_commit = commit_all(
        repository
    )

    second_observation = observe_git_commit(
        repository,
        second_commit,
    )

    second = index_python_repository(
        repository,
        second_observation,
        cache,
    )

    assert (
        first.files[0].content_sha256
        != second.files[0].content_sha256
    )

    assert (
        first.files[0].cache_key_id
        != second.files[0].cache_key_id
    )

    assert (
        first.index_id
        != second.index_id
    )


def test_index_identity_is_deterministic(
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
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    cache = extraction_cache(
        tmp_path
    )

    first = index_python_repository(
        repository,
        observation,
        cache,
    )

    second = index_python_repository(
        repository,
        observation,
        cache,
    )

    assert first.index_id == second.index_id

    assert [
        file.path
        for file
        in first.files
    ] == [
        "a.py",
        "m.py",
        "z.py",
    ]


def test_symlink_python_path_is_not_indexed(
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
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    result = index_python_repository(
        repository,
        observation,
        extraction_cache(
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
