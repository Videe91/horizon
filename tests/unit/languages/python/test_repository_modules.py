from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from horizon.languages.python.repository_modules import (
    PythonPackageLayoutEvidenceError,
    PythonRepositoryModuleKind,
    PythonRepositoryModuleStatus,
    discover_hatch_wheel_import_roots,
    resolve_repository_module,
)
from horizon.repository.git_blob import (
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
        "fixture",
    )

    return git(
        repo,
        "rev-parse",
        "HEAD",
    )


def write_pyproject(
    repo: Path,
    *,
    project_name: str = "acme-project",
    packages: str = '["src/acme"]',
) -> None:
    (
        repo
        / "pyproject.toml"
    ).write_text(
        f"""\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{project_name}"
version = "1.0.0"

[tool.hatch.build.targets.wheel]
packages = {packages}
""",
        encoding="utf-8",
    )


def prepare_layout(
    repo: Path,
    commit: str,
):
    observation = observe_git_commit(
        repo,
        commit,
    )

    pyproject_blob = read_observed_blob(
        repo,
        observation,
        "pyproject.toml",
    )

    layout = (
        discover_hatch_wheel_import_roots(
            pyproject_blob
        )
    )

    return (
        observation,
        pyproject_blob,
        layout,
    )


def test_hatch_package_declaration_produces_evidence_backed_import_root(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    write_pyproject(
        repo
    )

    package = (
        repo
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
        repo
    )

    (
        _,
        pyproject_blob,
        layout,
    ) = prepare_layout(
        repo,
        commit,
    )

    assert len(
        layout.import_roots
    ) == 1

    root = layout.import_roots[0]

    assert root.root_path == "src"
    assert root.package_path == "src/acme"
    assert root.top_level_package == "acme"

    assert (
        root.source_evidence_id
        == pyproject_blob.evidence_id
    )

    assert (
        layout.source_evidence_id
        == pyproject_blob.evidence_id
    )


def test_module_file_resolves_to_unique_repository_candidate(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    write_pyproject(
        repo
    )

    package = (
        repo
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

    (
        package
        / "worker.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repo
    )

    (
        observation,
        _,
        layout,
    ) = prepare_layout(
        repo,
        commit,
    )

    resolution = resolve_repository_module(
        repo,
        observation,
        layout,
        "acme.worker",
    )

    assert (
        resolution.status
        == PythonRepositoryModuleStatus.UNIQUE
    )

    assert len(
        resolution.candidates
    ) == 1

    candidate = resolution.candidates[0]

    assert (
        candidate.kind
        == PythonRepositoryModuleKind.MODULE_FILE
    )

    assert (
        candidate.path
        == "src/acme/worker.py"
    )

    expected_blob = read_observed_blob(
        repo,
        observation,
        "src/acme/worker.py",
    )

    assert (
        candidate.object_id
        == expected_blob.object_id
    )

    assert (
        candidate.blob_evidence_id
        == expected_blob.evidence_id
    )


def test_package_init_resolves_to_unique_repository_candidate(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    write_pyproject(
        repo
    )

    package = (
        repo
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

    subpackage = (
        package
        / "worker"
    )
    subpackage.mkdir()

    (
        subpackage
        / "__init__.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repo
    )

    (
        observation,
        _,
        layout,
    ) = prepare_layout(
        repo,
        commit,
    )

    resolution = resolve_repository_module(
        repo,
        observation,
        layout,
        "acme.worker",
    )

    assert (
        resolution.status
        == PythonRepositoryModuleStatus.UNIQUE
    )

    assert len(
        resolution.candidates
    ) == 1

    candidate = resolution.candidates[0]

    assert (
        candidate.kind
        == PythonRepositoryModuleKind.PACKAGE_INIT
    )

    assert (
        candidate.path
        == "src/acme/worker/__init__.py"
    )


def test_repository_layer_reports_module_package_collision_as_ambiguous(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    write_pyproject(
        repo
    )

    package = (
        repo
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

    (
        package
        / "worker.py"
    ).write_text(
        "MODULE = True\n",
        encoding="utf-8",
    )

    subpackage = (
        package
        / "worker"
    )
    subpackage.mkdir()

    (
        subpackage
        / "__init__.py"
    ).write_text(
        "PACKAGE = True\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repo
    )

    (
        observation,
        _,
        layout,
    ) = prepare_layout(
        repo,
        commit,
    )

    resolution = resolve_repository_module(
        repo,
        observation,
        layout,
        "acme.worker",
    )

    assert (
        resolution.status
        == PythonRepositoryModuleStatus.AMBIGUOUS
    )

    assert {
        candidate.kind
        for candidate
        in resolution.candidates
    } == {
        PythonRepositoryModuleKind.MODULE_FILE,
        PythonRepositoryModuleKind.PACKAGE_INIT,
    }


def test_file_outside_declared_import_root_is_not_a_candidate(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    write_pyproject(
        repo
    )

    package = (
        repo
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

    outside = (
        repo
        / "other"
        / "acme"
    )
    outside.mkdir(
        parents=True
    )

    (
        outside
        / "worker.py"
    ).write_text(
        "WRONG = True\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repo
    )

    (
        observation,
        _,
        layout,
    ) = prepare_layout(
        repo,
        commit,
    )

    resolution = resolve_repository_module(
        repo,
        observation,
        layout,
        "acme.worker",
    )

    assert (
        resolution.status
        == PythonRepositoryModuleStatus.NOT_FOUND
    )

    assert (
        resolution.candidates
        == ()
    )


def test_distribution_name_does_not_define_python_import_name(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    write_pyproject(
        repo,
        project_name=(
            "totally-different-distribution-name"
        ),
    )

    package = (
        repo
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

    (
        package
        / "worker.py"
    ).write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repo
    )

    (
        observation,
        _,
        layout,
    ) = prepare_layout(
        repo,
        commit,
    )

    resolution = resolve_repository_module(
        repo,
        observation,
        layout,
        "acme.worker",
    )

    assert (
        resolution.status
        == PythonRepositoryModuleStatus.UNIQUE
    )

    assert (
        resolution.candidates[0].path
        == "src/acme/worker.py"
    )


def test_resolution_uses_frozen_git_evidence_not_working_tree(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    write_pyproject(
        repo
    )

    package = (
        repo
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

    worker = (
        package
        / "worker.py"
    )

    worker.write_text(
        "ORIGINAL = True\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repo
    )

    (
        observation,
        _,
        layout,
    ) = prepare_layout(
        repo,
        commit,
    )

    original_blob = read_observed_blob(
        repo,
        observation,
        "src/acme/worker.py",
    )

    worker.write_text(
        "CHANGED = True\n",
        encoding="utf-8",
    )

    first = resolve_repository_module(
        repo,
        observation,
        layout,
        "acme.worker",
    )

    second = resolve_repository_module(
        repo,
        observation,
        layout,
        "acme.worker",
    )

    assert first == second
    assert (
        first.resolution_id
        == second.resolution_id
    )

    candidate = first.candidates[0]

    assert (
        candidate.object_id
        == original_blob.object_id
    )

    assert (
        candidate.blob_evidence_id
        == original_blob.evidence_id
    )


def test_missing_explicit_hatch_package_declaration_is_not_guessed(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    (
        repo
        / "pyproject.toml"
    ).write_text(
        """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "acme"
version = "1.0.0"
""",
        encoding="utf-8",
    )

    commit = commit_all(
        repo
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    blob = read_observed_blob(
        repo,
        observation,
        "pyproject.toml",
    )

    with pytest.raises(
        PythonPackageLayoutEvidenceError
    ):
        discover_hatch_wheel_import_roots(
            blob
        )


def test_invalid_pyproject_is_explicit_evidence_error(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path
    )

    (
        repo
        / "pyproject.toml"
    ).write_bytes(
        b"[tool.hatch\n",
    )

    commit = commit_all(
        repo
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    blob = read_observed_blob(
        repo,
        observation,
        "pyproject.toml",
    )

    with pytest.raises(
        PythonPackageLayoutEvidenceError
    ):
        discover_hatch_wheel_import_roots(
            blob
        )
