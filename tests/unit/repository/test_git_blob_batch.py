from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

import horizon.repository.git_blob as git_blob_module

from horizon.repository.git_blob import (
    GitBlobNotFoundError,
    read_observed_blob,
    read_observed_blobs,
)
from horizon.repository.git_observation import (
    observe_git_commit,
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


def test_batch_matches_individual_blob_reads(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "a.py"
    ).write_bytes(
        b"alpha = 1\n"
    )

    (
        repository
        / "b.py"
    ).write_bytes(
        b"beta = 2\n"
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

    batch = read_observed_blobs(
        repository,
        observation,
        (
            "a.py",
            "b.py",
        ),
    )

    individual = (
        read_observed_blob(
            repository,
            observation,
            "a.py",
        ),
        read_observed_blob(
            repository,
            observation,
            "b.py",
        ),
    )

    assert batch == individual


def test_batch_preserves_requested_path_order(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "a.py"
    ).write_bytes(
        b"a = 1\n"
    )

    (
        repository
        / "z.py"
    ).write_bytes(
        b"z = 1\n"
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

    batch = read_observed_blobs(
        repository,
        observation,
        (
            "z.py",
            "a.py",
        ),
    )

    assert [
        blob.path
        for blob
        in batch
    ] == [
        "z.py",
        "a.py",
    ]


def test_identical_git_object_reused_for_distinct_paths_keeps_distinct_evidence(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    content = b"value = 1\n"

    (
        repository
        / "first.py"
    ).write_bytes(
        content
    )

    (
        repository
        / "second.py"
    ).write_bytes(
        content
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

    first, second = (
        read_observed_blobs(
            repository,
            observation,
            (
                "first.py",
                "second.py",
            ),
        )
    )

    assert (
        first.object_id
        == second.object_id
    )

    assert (
        first.content
        == second.content
        == content
    )

    assert (
        first.evidence_id
        != second.evidence_id
    )

    assert (
        first.path
        != second.path
    )


def test_batch_uses_one_git_process_for_many_objects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = create_repository(
        tmp_path
    )

    for index in range(
        12
    ):
        (
            repository
            / f"{index}.py"
        ).write_text(
            f"value = {index}\n"
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

    blobs = read_observed_blobs(
        repository,
        observation,
        tuple(
            f"{index}.py"
            for index
            in range(
                12
            )
        ),
    )

    assert len(
        blobs
    ) == 12

    assert process_count == 1


def test_duplicate_object_ids_are_requested_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = create_repository(
        tmp_path
    )

    content = b"same = True\n"

    for name in (
        "a.py",
        "b.py",
        "c.py",
    ):
        (
            repository
            / name
        ).write_bytes(
            content
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

    original_popen = (
        git_blob_module
        .subprocess
        .Popen
    )

    sent_input = b""

    class WrappedProcess:
        def __init__(
            self,
            process,
        ) -> None:
            self._process = process

        @property
        def returncode(
            self,
        ):
            return self._process.returncode

        def communicate(
            self,
            input=None,
        ):
            nonlocal sent_input

            sent_input = (
                input
                if input is not None
                else b""
            )

            return self._process.communicate(
                input=input
            )

    def wrapped_popen(
        *args,
        **kwargs,
    ):
        return WrappedProcess(
            original_popen(
                *args,
                **kwargs,
            )
        )

    monkeypatch.setattr(
        git_blob_module.subprocess,
        "Popen",
        wrapped_popen,
    )

    blobs = read_observed_blobs(
        repository,
        observation,
        (
            "a.py",
            "b.py",
            "c.py",
        ),
    )

    assert len(
        blobs
    ) == 3

    requested = [
        line
        for line
        in sent_input.splitlines()
        if line
    ]

    assert len(
        requested
    ) == 1


def test_empty_batch_starts_no_git_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "README.md"
    ).write_text(
        "# fixture\n"
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

    def forbidden(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "empty batch must not start git"
        )

    monkeypatch.setattr(
        git_blob_module.subprocess,
        "Popen",
        forbidden,
    )

    assert read_observed_blobs(
        repository,
        observation,
        (),
    ) == ()


def test_missing_path_is_explicit(
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

    commit = commit_all(
        repository
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    with pytest.raises(
        GitBlobNotFoundError,
    ):
        read_observed_blobs(
            repository,
            observation,
            (
                "missing.py",
            ),
        )
