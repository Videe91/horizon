from __future__ import annotations

import subprocess

from pathlib import Path

import horizon.repository.git_blob as git_blob_module

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


def test_repository_open_reads_python_blobs_in_one_git_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = create_repository(
        tmp_path
    )

    for index in range(
        10
    ):
        (
            repository
            / f"{index}.py"
        ).write_text(
            (
                f"def function_{index}():\n"
                f"    return {index}\n"
            )
        )

    commit = commit_all(
        repository
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    original_popen = (
        git_blob_module
        .subprocess
        .Popen
    )

    process_count = 0

    def counted_popen(
        *args,
        **kwargs,
    ):
        nonlocal process_count

        process_count += 1

        return original_popen(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        git_blob_module.subprocess,
        "Popen",
        counted_popen,
    )

    result = open_python_repository(
        repository,
        observation,
        cache,
    )

    assert (
        result.python_file_count
        == 10
    )

    assert (
        result.analyzed_file_count
        == 10
    )

    assert (
        result.failed_file_count
        == 0
    )

    assert process_count == 1

    assert (
        result.blob_read_elapsed_ns
        >= 0
    )


def test_batch_open_preserves_warm_materialization_identity(
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
        "    helper()\n"
    )

    (
        repository
        / "b.py"
    ).write_text(
        "class B:\n"
        "    pass\n"
    )

    commit = commit_all(
        repository
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    cold = open_python_repository(
        repository,
        observation,
        cache,
    )

    warm = open_python_repository(
        repository,
        observation,
        cache,
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
