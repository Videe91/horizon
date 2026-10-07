"""Evidence for direct Python project dependencies declared in pyproject.toml.

This module reads only PEP 621 ``[project].dependencies``.

It deliberately does not merge:

- ``[project.optional-dependencies]``;
- development dependency groups;
- build-system requirements;
- integration-specific manifests.

A declaration proves what the project metadata declares. It does not by
itself prove runtime use, architectural importance, or responsibility.
"""

from __future__ import annotations

import tomllib

from dataclasses import dataclass
from hashlib import sha256

from horizon.repository.git_blob import (
    GitBlobEvidence,
)


class PythonProjectDependencyEvidenceError(
    ValueError
):
    """Direct project dependency evidence could not be established."""


@dataclass(
    frozen=True,
    slots=True,
)
class PythonDeclaredProjectDependenciesEvidence:
    project_name: str

    dependencies: tuple[
        str,
        ...,
    ]

    source_evidence_id: str

    evidence_id: str

    @property
    def dependency_count(
        self,
    ) -> int:
        return len(
            self.dependencies
        )


def _hash_parts(
    prefix: bytes,
    *parts: str,
) -> str:
    digest = sha256()

    digest.update(
        prefix
    )

    for part in parts:
        digest.update(
            part.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )

        digest.update(
            b"\0"
        )

    return digest.hexdigest()


def discover_declared_project_dependencies(
    pyproject_blob: GitBlobEvidence,
) -> PythonDeclaredProjectDependenciesEvidence:
    """Extract exact direct project dependency declarations."""

    if not isinstance(
        pyproject_blob,
        GitBlobEvidence,
    ):
        raise PythonProjectDependencyEvidenceError(
            "pyproject_blob must be GitBlobEvidence"
        )

    try:
        source = pyproject_blob.content.decode(
            "utf-8"
        )
    except UnicodeDecodeError as exc:
        raise PythonProjectDependencyEvidenceError(
            "pyproject.toml is not valid UTF-8"
        ) from exc

    try:
        configuration = tomllib.loads(
            source
        )
    except tomllib.TOMLDecodeError as exc:
        raise PythonProjectDependencyEvidenceError(
            f"invalid pyproject.toml: {exc}"
        ) from exc

    try:
        project = configuration[
            "project"
        ]
    except (
        KeyError,
        TypeError,
    ) as exc:
        raise PythonProjectDependencyEvidenceError(
            "no explicit project table"
        ) from exc

    if not isinstance(
        project,
        dict,
    ):
        raise PythonProjectDependencyEvidenceError(
            "project declaration must be a table"
        )

    project_name = project.get(
        "name"
    )

    if (
        not isinstance(
            project_name,
            str,
        )
        or not project_name.strip()
    ):
        raise PythonProjectDependencyEvidenceError(
            "project name must be an explicit non-empty string"
        )

    if (
        "dependencies"
        not in project
    ):
        raise PythonProjectDependencyEvidenceError(
            "no explicit project dependencies declaration"
        )

    raw_dependencies = project[
        "dependencies"
    ]

    if not isinstance(
        raw_dependencies,
        list,
    ):
        raise PythonProjectDependencyEvidenceError(
            "project dependencies must be a list"
        )

    dependencies: list[
        str
    ] = []

    for dependency in raw_dependencies:
        if (
            not isinstance(
                dependency,
                str,
            )
            or not dependency.strip()
        ):
            raise PythonProjectDependencyEvidenceError(
                "each project dependency must be a non-empty string"
            )

        dependencies.append(
            dependency
        )

    declared_dependencies = tuple(
        dependencies
    )

    evidence_id = (
        "declared-python-dependency-set:"
        + _hash_parts(
            b"horizon.declared-python-dependency-set.v1\0",
            pyproject_blob.evidence_id,
            project_name,
            *declared_dependencies,
        )
    )

    return (
        PythonDeclaredProjectDependenciesEvidence(
            project_name=(
                project_name
            ),
            dependencies=(
                declared_dependencies
            ),
            source_evidence_id=(
                pyproject_blob.evidence_id
            ),
            evidence_id=(
                evidence_id
            ),
        )
    )
