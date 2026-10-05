from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.git_search import (
    EmptySearchQueryError,
    search_observed_text,
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


def test_finds_literal_text_across_observed_repository(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "alpha.py"
    ).write_bytes(
        b"first\n"
        b"needle here\n"
        b"third\n"
    )

    (
        repo
        / "beta.py"
    ).write_bytes(
        b"nothing\n"
        b"another needle\n"
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    result = search_observed_text(
        repo,
        observation,
        "needle",
    )

    assert result.query == "needle"
    assert result.commit_sha == commit
    assert (
        result.repository_observation_id
        == observation.observation_id
    )

    assert [
        (
            match.path,
            match.line_number,
            match.line,
        )
        for match in result.matches
    ] == [
        (
            "alpha.py",
            2,
            b"needle here",
        ),
        (
            "beta.py",
            2,
            b"another needle",
        ),
    ]


def test_search_uses_committed_content_not_working_tree(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    target = repo / "app.py"

    target.write_bytes(
        b'VALUE = "needle"\n',
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    target.write_bytes(
        b'VALUE = "changed"\n',
    )

    (
        repo
        / "untracked.py"
    ).write_bytes(
        b"needle\n",
    )

    result = search_observed_text(
        repo,
        observation,
        "needle",
    )

    assert [
        match.path
        for match in result.matches
    ] == [
        "app.py",
    ]

    assert (
        result.matches[0].line
        == b'VALUE = "needle"'
    )


def test_search_records_exact_byte_offsets(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "app.py"
    ).write_bytes(
        b"needle needle\n",
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    result = search_observed_text(
        repo,
        observation,
        "needle",
    )

    assert [
        (
            match.byte_start,
            match.byte_end,
            match.line_number,
        )
        for match in result.matches
    ] == [
        (
            0,
            6,
            1,
        ),
        (
            7,
            13,
            1,
        ),
    ]


def test_search_result_is_deterministic(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "app.py"
    ).write_bytes(
        b"needle\n",
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    first = search_observed_text(
        repo,
        observation,
        "needle",
    )

    second = search_observed_text(
        repo,
        observation,
        "needle",
    )

    assert first == second
    assert (
        first.search_id
        == second.search_id
    )


def test_same_git_blob_at_two_paths_creates_distinct_match_evidence(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    content = b"needle\n"

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

    result = search_observed_text(
        repo,
        observation,
        "needle",
    )

    assert len(
        result.matches
    ) == 2

    first, second = result.matches

    assert (
        first.object_id
        == second.object_id
    )

    assert first.path != second.path

    assert (
        first.evidence_id
        != second.evidence_id
    )


def test_no_match_is_explicit_empty_result(
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

    result = search_observed_text(
        repo,
        observation,
        "needle",
    )

    assert result.matches == ()


def test_search_is_binary_safe(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "data.bin"
    ).write_bytes(
        b"\x00before needle after\x00"
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    result = search_observed_text(
        repo,
        observation,
        "needle",
    )

    assert len(
        result.matches
    ) == 1

    assert (
        result.matches[0].path
        == "data.bin"
    )


def test_empty_query_is_rejected(
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

    with pytest.raises(
        EmptySearchQueryError,
    ):
        search_observed_text(
            repo,
            observation,
            "",
        )
