from __future__ import annotations

import subprocess
from pathlib import Path

from horizon.repository.git_observation import (
    observe_git_commit,
)


def git(
    repo: Path,
    *args: str,
) -> str:
    result = subprocess.run(
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

    return result.stdout.strip()


def test_observation_is_bound_to_exact_commit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

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

    (
        repo
        / "app.py"
    ).write_text(
        "print('hello')\n",
        encoding="utf-8",
    )

    git(
        repo,
        "add",
        "app.py",
    )

    git(
        repo,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    assert observation.commit_sha == commit


def test_observation_lists_files_from_git_tree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

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

    (
        repo
        / "src"
    ).mkdir()

    (
        repo
        / "src"
        / "app.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    (
        repo
        / "README.md"
    ).write_text(
        "# Example\n",
        encoding="utf-8",
    )

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
        "fixture",
    )

    observation = observe_git_commit(
        repo,
        git(
            repo,
            "rev-parse",
            "HEAD",
        ),
    )

    assert tuple(
        item.path
        for item
        in observation.entries
    ) == (
        "README.md",
        "src/app.py",
    )


def test_observation_ignores_later_working_tree_mutation(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

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

    target = (
        repo
        / "app.py"
    )

    target.write_text(
        "VERSION = 1\n",
        encoding="utf-8",
    )

    git(
        repo,
        "add",
        "app.py",
    )

    git(
        repo,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    target.write_text(
        "VERSION = 999\n",
        encoding="utf-8",
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    assert len(
        observation.entries
    ) == 1

    assert (
        observation.entries[
            0
        ].path
        == "app.py"
    )


def test_observation_has_deterministic_identity(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

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

    (
        repo
        / "app.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    git(
        repo,
        "add",
        "app.py",
    )

    git(
        repo,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    first = observe_git_commit(
        repo,
        commit,
    )

    second = observe_git_commit(
        repo,
        commit,
    )

    assert first == second

    assert (
        first.observation_id
        == second.observation_id
    )
