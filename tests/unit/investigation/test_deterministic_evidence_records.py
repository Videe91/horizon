from __future__ import annotations

import base64
import json
import subprocess

from dataclasses import replace
from pathlib import Path

import pytest

from horizon.investigation.deterministic_evidence_records import (
    DECLARED_DEPENDENCIES_EVIDENCE_KIND,
    GIT_BLOB_EVIDENCE_KIND,
    PACKAGE_LAYOUT_EVIDENCE_KIND,
    PYTHON_IMPORT_ROOT_EVIDENCE_KIND,
    DeterministicEvidenceRecordError,
    canonical_declared_dependencies_evidence_record,
    canonical_git_blob_evidence_record,
    canonical_package_layout_evidence_record,
    canonical_python_import_root_evidence_record,
    canonical_repository_deterministic_evidence_records,
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


def fixture(
    tmp_path: Path,
):
    repository = (
        tmp_path
        / "repository"
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

    (
        repository
        / "pyproject.toml"
    ).write_text(
        """\
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2",
]

[tool.hatch.build.targets.wheel]
packages = ["src/demo"]
""",
        encoding="utf-8",
    )

    package = (
        repository
        / "src"
        / "demo"
    )

    package.mkdir(
        parents=True,
    )

    (
        package
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    git(
        repository,
        "add",
        ".",
    )

    git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = git(
        repository,
        "rev-parse",
        "HEAD",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
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

    return (
        blob,
        layout,
        dependencies,
    )


def payload(
    record,
):
    return json.loads(
        record.canonical_payload
    )


def test_bridge_produces_exact_repository_evidence_identities(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        dependencies,
    ) = fixture(
        tmp_path
    )

    assert len(
        layout.import_roots
    ) == 1

    root = (
        layout.import_roots[0]
    )

    records = (
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    assert [
        record.evidence_id
        for record
        in records
    ] == [
        blob.evidence_id,
        layout.layout_id,
        root.evidence_id,
        dependencies.evidence_id,
    ]

    assert [
        record.evidence_kind
        for record
        in records
    ] == [
        GIT_BLOB_EVIDENCE_KIND,
        PACKAGE_LAYOUT_EVIDENCE_KIND,
        PYTHON_IMPORT_ROOT_EVIDENCE_KIND,
        DECLARED_DEPENDENCIES_EVIDENCE_KIND,
    ]


def test_git_blob_record_preserves_exact_frozen_bytes(
    tmp_path: Path,
) -> None:
    (
        blob,
        _,
        _,
    ) = fixture(
        tmp_path
    )

    record = (
        canonical_git_blob_evidence_record(
            blob
        )
    )

    value = payload(
        record
    )

    assert (
        record.evidence_id
        == blob.evidence_id
    )

    assert (
        value["evidence_id"]
        == blob.evidence_id
    )

    assert (
        value["path"]
        == blob.path
        == "pyproject.toml"
    )

    assert (
        value["commit_sha"]
        == blob.commit_sha
    )

    assert (
        value[
            "repository_observation_id"
        ]
        == blob.repository_observation_id
    )

    assert (
        value["object_id"]
        == blob.object_id
    )

    decoded = base64.b64decode(
        value[
            "content_base64"
        ],
        validate=True,
    )

    assert decoded == blob.content

    assert (
        value["content_bytes"]
        == len(
            blob.content
        )
    )


def test_package_layout_record_preserves_import_roots(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        _,
    ) = fixture(
        tmp_path
    )

    record = (
        canonical_package_layout_evidence_record(
            layout
        )
    )

    value = payload(
        record
    )

    assert (
        record.evidence_id
        == layout.layout_id
    )

    assert (
        value["layout_id"]
        == layout.layout_id
    )

    assert (
        value[
            "source_evidence_id"
        ]
        == blob.evidence_id
    )

    assert (
        value[
            "import_root_count"
        ]
        == 1
    )

    assert (
        value[
            "import_roots"
        ][0][
            "evidence_id"
        ]
        == layout.import_roots[
            0
        ].evidence_id
    )

    assert (
        value[
            "import_roots"
        ][0][
            "root_path"
        ]
        == "src"
    )

    assert (
        value[
            "import_roots"
        ][0][
            "package_path"
        ]
        == "src/demo"
    )

    assert (
        value[
            "import_roots"
        ][0][
            "top_level_package"
        ]
        == "demo"
    )


def test_import_root_record_preserves_exact_fields(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        _,
    ) = fixture(
        tmp_path
    )

    root = (
        layout.import_roots[0]
    )

    record = (
        canonical_python_import_root_evidence_record(
            root
        )
    )

    value = payload(
        record
    )

    assert (
        record.evidence_id
        == root.evidence_id
    )

    assert (
        value[
            "source_evidence_id"
        ]
        == blob.evidence_id
    )

    assert (
        value[
            "root_path"
        ]
        == root.root_path
    )

    assert (
        value[
            "package_path"
        ]
        == root.package_path
    )

    assert (
        value[
            "top_level_package"
        ]
        == root.top_level_package
    )


def test_dependency_record_preserves_all_declared_dependencies(
    tmp_path: Path,
) -> None:
    (
        blob,
        _,
        dependencies,
    ) = fixture(
        tmp_path
    )

    record = (
        canonical_declared_dependencies_evidence_record(
            dependencies
        )
    )

    value = payload(
        record
    )

    assert (
        record.evidence_id
        == dependencies.evidence_id
    )

    assert (
        value[
            "source_evidence_id"
        ]
        == blob.evidence_id
    )

    assert (
        value[
            "project_name"
        ]
        == "demo"
    )

    assert (
        value[
            "dependencies"
        ]
        == [
            "httpx>=0.27",
            "pydantic>=2",
        ]
    )

    assert (
        value[
            "dependency_count"
        ]
        == 2
    )


def test_bundle_is_deterministic(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        dependencies,
    ) = fixture(
        tmp_path
    )

    first = (
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    second = (
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    assert first == second


def test_bundle_rejects_layout_from_different_source(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        dependencies,
    ) = fixture(
        tmp_path
    )

    stale = replace(
        layout,
        source_evidence_id=(
            "git-blob-evidence:other"
        ),
    )

    with pytest.raises(
        DeterministicEvidenceRecordError,
        match="layout source",
    ):
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=blob,
            package_layout=stale,
            project_dependencies=dependencies,
        )


def test_bundle_rejects_root_from_different_source(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        dependencies,
    ) = fixture(
        tmp_path
    )

    root = replace(
        layout.import_roots[0],
        source_evidence_id=(
            "git-blob-evidence:other"
        ),
    )

    stale = replace(
        layout,
        import_roots=(
            root,
        ),
    )

    with pytest.raises(
        DeterministicEvidenceRecordError,
        match="import root source",
    ):
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=blob,
            package_layout=stale,
            project_dependencies=dependencies,
        )


def test_bundle_rejects_dependencies_from_different_source(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        dependencies,
    ) = fixture(
        tmp_path
    )

    stale = replace(
        dependencies,
        source_evidence_id=(
            "git-blob-evidence:other"
        ),
    )

    with pytest.raises(
        DeterministicEvidenceRecordError,
        match="dependency source",
    ):
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=stale,
        )


def test_bundle_rejects_duplicate_import_root_identity(
    tmp_path: Path,
) -> None:
    (
        blob,
        layout,
        dependencies,
    ) = fixture(
        tmp_path
    )

    root = (
        layout.import_roots[0]
    )

    duplicate = replace(
        layout,
        import_roots=(
            root,
            root,
        ),
    )

    with pytest.raises(
        DeterministicEvidenceRecordError,
        match="duplicate import root",
    ):
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=blob,
            package_layout=duplicate,
            project_dependencies=dependencies,
        )
