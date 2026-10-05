from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from horizon.repository.git_blob import (
    GitBlobNotFoundError,
    GitObjectIsNotBlobError,
    read_observed_blob,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)


def git(
    repo: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
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
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)

    git(
        repo,
        "init",
        "-q",
        "-b",
        "main",
    )

    git(
        repo,
        "config",
        "user.name",
        "Horizon Test",
    )

    git(
        repo,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    return repo


def commit_all(
    repo: Path,
    message: str = "fixture",
) -> str:
    git(
        repo,
        "add",
        "-A",
    )

    git(
        repo,
        "commit",
        "-q",
        "-m",
        message,
    )

    return git(
        repo,
        "rev-parse",
        "HEAD",
    )


def test_reads_exact_bytes_from_observed_blob(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    content = (
        b"VALUE = 1\n"
        b"\x00binary-safe\n"
    )

    (
        repo
        / "example.bin"
    ).write_bytes(
        content,
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    blob = read_observed_blob(
        repo,
        observation,
        "example.bin",
    )

    assert blob.content == content
    assert blob.path == "example.bin"
    assert blob.commit_sha == commit
    assert (
        blob.repository_observation_id
        == observation.observation_id
    )


def test_reads_committed_blob_not_working_tree(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    target = repo / "app.py"

    target.write_bytes(
        b"VERSION = 1\n",
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    target.write_bytes(
        b"VERSION = 999\n",
    )

    blob = read_observed_blob(
        repo,
        observation,
        "app.py",
    )

    assert (
        blob.content
        == b"VERSION = 1\n"
    )


def test_blob_is_bound_to_observed_object_id(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "app.py"
    ).write_bytes(
        b"VALUE = 1\n",
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    expected_entry = next(
        entry
        for entry in observation.entries
        if entry.path == "app.py"
    )

    blob = read_observed_blob(
        repo,
        observation,
        "app.py",
    )

    assert (
        blob.object_id
        == expected_entry.object_id
    )


def test_blob_identity_is_deterministic(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "app.py"
    ).write_bytes(
        b"VALUE = 1\n",
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    first = read_observed_blob(
        repo,
        observation,
        "app.py",
    )

    second = read_observed_blob(
        repo,
        observation,
        "app.py",
    )

    assert first == second
    assert (
        first.evidence_id
        == second.evidence_id
    )


def test_same_content_at_different_paths_has_distinct_evidence_identity(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    content = b"SAME = True\n"

    (
        repo
        / "a.py"
    ).write_bytes(
        content,
    )

    (
        repo
        / "b.py"
    ).write_bytes(
        content,
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    first = read_observed_blob(
        repo,
        observation,
        "a.py",
    )

    second = read_observed_blob(
        repo,
        observation,
        "b.py",
    )

    assert first.object_id == second.object_id

    assert (
        first.evidence_id
        != second.evidence_id
    )


def test_missing_path_is_explicit(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "app.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    with pytest.raises(
        GitBlobNotFoundError,
    ):
        read_observed_blob(
            repo,
            observation,
            "missing.py",
        )


def test_non_blob_git_object_is_rejected(
    tmp_path: Path,
) -> None:
    child = create_repository(
        tmp_path / "child-parent",
    )

    (
        child
        / "child.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    commit_all(
        child,
    )

    parent_root = tmp_path / "parent-root"
    parent_root.mkdir()

    parent = create_repository(
        parent_root,
    )

    subprocess.run(
        [
            "git",
            "-C",
            str(parent),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(child),
            "vendor/child",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    commit = commit_all(
        parent,
    )

    observation = observe_git_commit(
        parent,
        commit,
    )

    with pytest.raises(
        GitObjectIsNotBlobError,
    ):
        read_observed_blob(
            parent,
            observation,
            "vendor/child",
        )
