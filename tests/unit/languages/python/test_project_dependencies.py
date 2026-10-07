from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from horizon.languages.python.project_dependencies import (
    PythonProjectDependencyEvidenceError,
    discover_declared_project_dependencies,
)
from horizon.repository.git_blob import (
    read_observed_blob,
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


def observed_pyproject(
    repository: Path,
    commit: str,
):
    observation = observe_git_commit(
        repository,
        commit,
    )

    blob = read_observed_blob(
        repository,
        observation,
        "pyproject.toml",
    )

    return observation, blob


def test_direct_project_dependencies_are_preserved_exactly(
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
dependencies = [
    "httpx[http2]>=0.27",
    "pydantic>=2,<3",
    "pendulum>=3; python_version<'3.13'",
]
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    evidence = (
        discover_declared_project_dependencies(
            blob
        )
    )

    assert evidence.project_name == "acme"

    assert evidence.dependencies == (
        "httpx[http2]>=0.27",
        "pydantic>=2,<3",
        "pendulum>=3; python_version<'3.13'",
    )

    assert evidence.dependency_count == 3

    assert (
        evidence.source_evidence_id
        == blob.evidence_id
    )

    assert (
        evidence.evidence_id.startswith(
            "declared-python-dependency-set:"
        )
    )


def test_optional_and_development_dependencies_are_not_direct_dependencies(
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
dependencies = [
    "runtime-one>=1",
    "runtime-two>=2",
]

[project.optional-dependencies]
aws = [
    "boto3>=1",
    "botocore>=1",
]

[dependency-groups]
dev = [
    "pytest>=9",
    "ruff>=1",
]
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    evidence = (
        discover_declared_project_dependencies(
            blob
        )
    )

    assert evidence.dependencies == (
        "runtime-one>=1",
        "runtime-two>=2",
    )

    assert evidence.dependency_count == 2


def test_empty_direct_dependency_declaration_is_valid_evidence(
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
dependencies = []
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    evidence = (
        discover_declared_project_dependencies(
            blob
        )
    )

    assert evidence.dependencies == ()
    assert evidence.dependency_count == 0


def test_missing_direct_dependency_declaration_is_explicit(
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

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    with pytest.raises(
        PythonProjectDependencyEvidenceError,
        match=(
            "no explicit project dependencies declaration"
        ),
    ):
        discover_declared_project_dependencies(
            blob
        )


def test_dependencies_must_be_a_list(
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
dependencies = "httpx"
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    with pytest.raises(
        PythonProjectDependencyEvidenceError,
    ):
        discover_declared_project_dependencies(
            blob
        )


def test_dependencies_must_contain_nonempty_strings(
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
dependencies = [
    "httpx",
    "",
]
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    with pytest.raises(
        PythonProjectDependencyEvidenceError,
    ):
        discover_declared_project_dependencies(
            blob
        )


def test_project_name_must_be_explicit(
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
version = "1.0.0"
dependencies = ["httpx"]
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    with pytest.raises(
        PythonProjectDependencyEvidenceError,
    ):
        discover_declared_project_dependencies(
            blob
        )


def test_dependency_evidence_is_deterministic(
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
dependencies = [
    "httpx>=0.27",
    "pydantic>=2",
]
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    first = (
        discover_declared_project_dependencies(
            blob
        )
    )

    second = (
        discover_declared_project_dependencies(
            blob
        )
    )

    assert first == second

    assert (
        first.evidence_id
        == second.evidence_id
    )


def test_frozen_blob_evidence_is_independent_of_working_tree_mutation(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    pyproject = (
        repository
        / "pyproject.toml"
    )

    pyproject.write_text(
        """\
[project]
name = "acme"
version = "1.0.0"
dependencies = ["old-runtime"]
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    _, blob = observed_pyproject(
        repository,
        commit,
    )

    pyproject.write_text(
        """\
[project]
name = "acme"
version = "1.0.0"
dependencies = ["new-runtime"]
""",
        encoding="utf-8",
    )

    evidence = (
        discover_declared_project_dependencies(
            blob
        )
    )

    assert evidence.dependencies == (
        "old-runtime",
    )
