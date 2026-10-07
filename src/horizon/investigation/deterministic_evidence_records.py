"""Canonical records for deterministic repository evidence.

These records connect already-proven repository evidence to Horizon's
investigation evidence boundary. They do not create new facts, claims,
assessments, assertions, or semantic conclusions.
"""

from __future__ import annotations

import base64
import json

from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
)
from horizon.languages.python.project_dependencies import (
    PythonDeclaredProjectDependenciesEvidence,
)
from horizon.languages.python.repository_modules import (
    PythonImportRootEvidence,
    PythonPackageLayoutEvidence,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)


GIT_BLOB_EVIDENCE_KIND = (
    "GIT_BLOB_EVIDENCE"
)

PACKAGE_LAYOUT_EVIDENCE_KIND = (
    "PYTHON_PACKAGE_LAYOUT_EVIDENCE"
)

PYTHON_IMPORT_ROOT_EVIDENCE_KIND = (
    "PYTHON_IMPORT_ROOT_EVIDENCE"
)

DECLARED_DEPENDENCIES_EVIDENCE_KIND = (
    "PYTHON_DECLARED_PROJECT_DEPENDENCIES_EVIDENCE"
)


class DeterministicEvidenceRecordError(
    ValueError
):
    """Deterministic repository evidence cannot be canonically represented."""


def _require_text(
    value: object,
    *,
    name: str,
    allow_empty: bool = False,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise DeterministicEvidenceRecordError(
            f"{name} must be text"
        )

    if (
        not allow_empty
        and not value.strip()
    ):
        raise DeterministicEvidenceRecordError(
            f"{name} must be nonempty text"
        )

    return value


def _canonical_json(
    value: object,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        allow_nan=False,
    )


def _root_payload(
    root: PythonImportRootEvidence,
) -> dict[str, object]:
    if not isinstance(
        root,
        PythonImportRootEvidence,
    ):
        raise DeterministicEvidenceRecordError(
            "import root must be PythonImportRootEvidence"
        )

    return {
        "evidence_id": _require_text(
            root.evidence_id,
            name="import root evidence id",
        ),
        "source_evidence_id": _require_text(
            root.source_evidence_id,
            name="import root source evidence id",
        ),
        "root_path": _require_text(
            root.root_path,
            name="import root path",
            allow_empty=True,
        ),
        "package_path": _require_text(
            root.package_path,
            name="package path",
        ),
        "top_level_package": _require_text(
            root.top_level_package,
            name="top-level package",
        ),
    }


def canonical_git_blob_evidence_record(
    blob: GitBlobEvidence,
) -> CanonicalEvidenceRecord:
    """Represent one exact frozen Git blob as canonical investigation evidence."""

    if not isinstance(
        blob,
        GitBlobEvidence,
    ):
        raise DeterministicEvidenceRecordError(
            "blob must be GitBlobEvidence"
        )

    evidence_id = _require_text(
        blob.evidence_id,
        name="blob evidence id",
    )

    commit_sha = _require_text(
        blob.commit_sha,
        name="blob commit sha",
    )

    repository_observation_id = (
        _require_text(
            blob.repository_observation_id,
            name="repository observation id",
        )
    )

    path = _require_text(
        blob.path,
        name="blob path",
    )

    object_id = _require_text(
        blob.object_id,
        name="blob object id",
    )

    if not isinstance(
        blob.content,
        bytes,
    ):
        raise DeterministicEvidenceRecordError(
            "blob content must be bytes"
        )

    payload = {
        "evidence_type": (
            GIT_BLOB_EVIDENCE_KIND
        ),
        "evidence_id": evidence_id,
        "commit_sha": commit_sha,
        "repository_observation_id": (
            repository_observation_id
        ),
        "path": path,
        "object_id": object_id,
        "content_bytes": len(
            blob.content
        ),
        "content_base64": (
            base64.b64encode(
                blob.content
            ).decode(
                "ascii"
            )
        ),
    }

    return CanonicalEvidenceRecord(
        evidence_id=evidence_id,
        evidence_kind=(
            GIT_BLOB_EVIDENCE_KIND
        ),
        canonical_payload=(
            _canonical_json(
                payload
            )
        ),
    )


def canonical_python_import_root_evidence_record(
    root: PythonImportRootEvidence,
) -> CanonicalEvidenceRecord:
    """Represent one exact Python import-root fact."""

    payload = _root_payload(
        root
    )

    payload = {
        "evidence_type": (
            PYTHON_IMPORT_ROOT_EVIDENCE_KIND
        ),
        **payload,
    }

    return CanonicalEvidenceRecord(
        evidence_id=(
            root.evidence_id
        ),
        evidence_kind=(
            PYTHON_IMPORT_ROOT_EVIDENCE_KIND
        ),
        canonical_payload=(
            _canonical_json(
                payload
            )
        ),
    )


def canonical_package_layout_evidence_record(
    layout: PythonPackageLayoutEvidence,
) -> CanonicalEvidenceRecord:
    """Represent one exact Python package-layout result."""

    if not isinstance(
        layout,
        PythonPackageLayoutEvidence,
    ):
        raise DeterministicEvidenceRecordError(
            "layout must be PythonPackageLayoutEvidence"
        )

    layout_id = _require_text(
        layout.layout_id,
        name="package layout id",
    )

    source_evidence_id = (
        _require_text(
            layout.source_evidence_id,
            name="package layout source evidence id",
        )
    )

    if not isinstance(
        layout.import_roots,
        tuple,
    ):
        raise DeterministicEvidenceRecordError(
            "package layout import roots must be a tuple"
        )

    root_ids = tuple(
        root.evidence_id
        for root
        in layout.import_roots
    )

    if (
        len(
            root_ids
        )
        != len(
            set(
                root_ids
            )
        )
    ):
        raise DeterministicEvidenceRecordError(
            "package layout contains duplicate import root identities"
        )

    payload = {
        "evidence_type": (
            PACKAGE_LAYOUT_EVIDENCE_KIND
        ),
        "layout_id": layout_id,
        "source_evidence_id": (
            source_evidence_id
        ),
        "import_root_count": len(
            layout.import_roots
        ),
        "import_roots": [
            _root_payload(
                root
            )
            for root
            in layout.import_roots
        ],
    }

    return CanonicalEvidenceRecord(
        evidence_id=layout_id,
        evidence_kind=(
            PACKAGE_LAYOUT_EVIDENCE_KIND
        ),
        canonical_payload=(
            _canonical_json(
                payload
            )
        ),
    )


def canonical_declared_dependencies_evidence_record(
    dependencies: PythonDeclaredProjectDependenciesEvidence,
) -> CanonicalEvidenceRecord:
    """Represent exact direct dependency declarations from pyproject.toml."""

    if not isinstance(
        dependencies,
        PythonDeclaredProjectDependenciesEvidence,
    ):
        raise DeterministicEvidenceRecordError(
            "dependencies must be "
            "PythonDeclaredProjectDependenciesEvidence"
        )

    evidence_id = _require_text(
        dependencies.evidence_id,
        name="dependency evidence id",
    )

    source_evidence_id = (
        _require_text(
            dependencies.source_evidence_id,
            name="dependency source evidence id",
        )
    )

    project_name = _require_text(
        dependencies.project_name,
        name="project name",
    )

    if not isinstance(
        dependencies.dependencies,
        tuple,
    ):
        raise DeterministicEvidenceRecordError(
            "dependencies must be a tuple"
        )

    declared = []

    for dependency in (
        dependencies.dependencies
    ):
        declared.append(
            _require_text(
                dependency,
                name="declared dependency",
            )
        )

    payload = {
        "evidence_type": (
            DECLARED_DEPENDENCIES_EVIDENCE_KIND
        ),
        "evidence_id": evidence_id,
        "source_evidence_id": (
            source_evidence_id
        ),
        "project_name": (
            project_name
        ),
        "dependency_count": len(
            declared
        ),
        "dependencies": declared,
    }

    return CanonicalEvidenceRecord(
        evidence_id=evidence_id,
        evidence_kind=(
            DECLARED_DEPENDENCIES_EVIDENCE_KIND
        ),
        canonical_payload=(
            _canonical_json(
                payload
            )
        ),
    )


def canonical_repository_deterministic_evidence_records(
    *,
    pyproject_blob: GitBlobEvidence,
    package_layout: PythonPackageLayoutEvidence,
    project_dependencies: PythonDeclaredProjectDependenciesEvidence,
) -> tuple[
    CanonicalEvidenceRecord,
    ...,
]:
    """Bridge one deterministic Python project evidence bundle.

    Ordering is stable:
    source blob, package layout, import roots in their declared order,
    then declared dependency set.
    """

    if not isinstance(
        pyproject_blob,
        GitBlobEvidence,
    ):
        raise DeterministicEvidenceRecordError(
            "pyproject_blob must be GitBlobEvidence"
        )

    if not isinstance(
        package_layout,
        PythonPackageLayoutEvidence,
    ):
        raise DeterministicEvidenceRecordError(
            "package_layout must be PythonPackageLayoutEvidence"
        )

    if not isinstance(
        project_dependencies,
        PythonDeclaredProjectDependenciesEvidence,
    ):
        raise DeterministicEvidenceRecordError(
            "project_dependencies must be "
            "PythonDeclaredProjectDependenciesEvidence"
        )

    if (
        package_layout.source_evidence_id
        != pyproject_blob.evidence_id
    ):
        raise DeterministicEvidenceRecordError(
            "package layout source does not match pyproject blob"
        )

    if any(
        root.source_evidence_id
        != pyproject_blob.evidence_id
        for root
        in package_layout.import_roots
    ):
        raise DeterministicEvidenceRecordError(
            "package import root source does not match pyproject blob"
        )

    if (
        project_dependencies.source_evidence_id
        != pyproject_blob.evidence_id
    ):
        raise DeterministicEvidenceRecordError(
            "project dependency source does not match pyproject blob"
        )

    root_ids = tuple(
        root.evidence_id
        for root
        in package_layout.import_roots
    )

    if (
        len(
            root_ids
        )
        != len(
            set(
                root_ids
            )
        )
    ):
        raise DeterministicEvidenceRecordError(
            "duplicate import root identity"
        )

    records = (
        canonical_git_blob_evidence_record(
            pyproject_blob
        ),
        canonical_package_layout_evidence_record(
            package_layout
        ),
        *(
            canonical_python_import_root_evidence_record(
                root
            )
            for root
            in package_layout.import_roots
        ),
        canonical_declared_dependencies_evidence_record(
            project_dependencies
        ),
    )

    record_ids = tuple(
        record.evidence_id
        for record
        in records
    )

    if (
        len(
            record_ids
        )
        != len(
            set(
                record_ids
            )
        )
    ):
        raise DeterministicEvidenceRecordError(
            "deterministic evidence bundle contains duplicate identities"
        )

    return records
