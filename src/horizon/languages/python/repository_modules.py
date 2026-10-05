from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path, PurePosixPath
import tomllib

from horizon.repository.git_blob import (
    GitBlobEvidence,
    read_observed_blob,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)


class PythonPackageLayoutEvidenceError(Exception):
    """Repository package layout could not be established from evidence."""


class PythonRepositoryModuleKind(str, Enum):
    MODULE_FILE = "MODULE_FILE"
    PACKAGE_INIT = "PACKAGE_INIT"


class PythonRepositoryModuleStatus(str, Enum):
    UNIQUE = "UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class PythonImportRootEvidence:
    root_path: str
    package_path: str
    top_level_package: str
    source_evidence_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class PythonPackageLayoutEvidence:
    source_evidence_id: str
    import_roots: tuple[
        PythonImportRootEvidence,
        ...,
    ]
    layout_id: str


@dataclass(frozen=True, slots=True)
class PythonRepositoryModuleCandidate:
    module_name: str
    kind: PythonRepositoryModuleKind
    path: str
    object_id: str
    blob_evidence_id: str
    import_root_evidence_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class PythonRepositoryModuleResolution:
    module_name: str
    status: PythonRepositoryModuleStatus
    package_layout_id: str
    repository_observation_id: str
    candidates: tuple[
        PythonRepositoryModuleCandidate,
        ...,
    ]
    resolution_id: str


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


def _normalise_repository_path(
    value: str,
) -> str:
    path = PurePosixPath(
        value
    )

    if path.is_absolute():
        raise PythonPackageLayoutEvidenceError(
            "package paths must be repository-relative"
        )

    if ".." in path.parts:
        raise PythonPackageLayoutEvidenceError(
            "package paths may not escape the repository"
        )

    normalized = str(
        path
    )

    if normalized in {
        "",
        ".",
    }:
        raise PythonPackageLayoutEvidenceError(
            "package path must identify a package"
        )

    return normalized


def _root_text(
    path: PurePosixPath,
) -> str:
    value = str(
        path
    )

    if value == ".":
        return ""

    return value


def _join_root(
    root: str,
    *parts: str,
) -> str:
    if root:
        return str(
            PurePosixPath(
                root
            ).joinpath(
                *parts
            )
        )

    return str(
        PurePosixPath(
            *parts
        )
    )


def discover_hatch_wheel_import_roots(
    pyproject_blob: GitBlobEvidence,
) -> PythonPackageLayoutEvidence:
    try:
        source = pyproject_blob.content.decode(
            "utf-8"
        )
    except UnicodeDecodeError as exc:
        raise PythonPackageLayoutEvidenceError(
            "pyproject.toml is not valid UTF-8"
        ) from exc

    try:
        configuration = tomllib.loads(
            source
        )
    except tomllib.TOMLDecodeError as exc:
        raise PythonPackageLayoutEvidenceError(
            f"invalid pyproject.toml: {exc}"
        ) from exc

    try:
        packages = (
            configuration
            ["tool"]
            ["hatch"]
            ["build"]
            ["targets"]
            ["wheel"]
            ["packages"]
        )
    except (
        KeyError,
        TypeError,
    ) as exc:
        raise PythonPackageLayoutEvidenceError(
            "no explicit Hatch wheel packages declaration"
        ) from exc

    if (
        not isinstance(
            packages,
            list,
        )
        or not packages
    ):
        raise PythonPackageLayoutEvidenceError(
            "Hatch wheel packages must be a non-empty list"
        )

    roots: list[
        PythonImportRootEvidence
    ] = []

    for raw_package_path in packages:
        if (
            not isinstance(
                raw_package_path,
                str,
            )
            or not raw_package_path.strip()
        ):
            raise PythonPackageLayoutEvidenceError(
                "each Hatch wheel package must be a non-empty string"
            )

        package_path = (
            _normalise_repository_path(
                raw_package_path
            )
        )

        package = PurePosixPath(
            package_path
        )

        top_level_package = (
            package.name
        )

        root_path = _root_text(
            package.parent
        )

        evidence_id = (
            "python-import-root:"
            + _hash_parts(
                b"horizon.python-import-root.v1\0",
                pyproject_blob.evidence_id,
                root_path,
                package_path,
                top_level_package,
            )
        )

        roots.append(
            PythonImportRootEvidence(
                root_path=root_path,
                package_path=package_path,
                top_level_package=(
                    top_level_package
                ),
                source_evidence_id=(
                    pyproject_blob.evidence_id
                ),
                evidence_id=evidence_id,
            )
        )

    import_roots = tuple(
        roots
    )

    digest = sha256()
    digest.update(
        b"horizon.python-package-layout.v1\0"
    )
    digest.update(
        pyproject_blob.evidence_id.encode(
            "ascii"
        )
    )
    digest.update(
        b"\0"
    )

    for root in import_roots:
        digest.update(
            root.evidence_id.encode(
                "ascii"
            )
        )
        digest.update(
            b"\0"
        )

    layout_id = (
        "python-package-layout:"
        + digest.hexdigest()
    )

    return PythonPackageLayoutEvidence(
        source_evidence_id=(
            pyproject_blob.evidence_id
        ),
        import_roots=import_roots,
        layout_id=layout_id,
    )


def _candidate_identity(
    *,
    module_name: str,
    kind: PythonRepositoryModuleKind,
    path: str,
    object_id: str,
    blob_evidence_id: str,
    import_root_evidence_id: str,
) -> str:
    return (
        "python-repository-module-candidate:"
        + _hash_parts(
            b"horizon.python-repository-module-candidate.v1\0",
            module_name,
            kind.value,
            path,
            object_id,
            blob_evidence_id,
            import_root_evidence_id,
        )
    )


def _resolution_identity(
    *,
    module_name: str,
    status: PythonRepositoryModuleStatus,
    package_layout_id: str,
    repository_observation_id: str,
    candidates: tuple[
        PythonRepositoryModuleCandidate,
        ...,
    ],
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.python-repository-module-resolution.v1\0"
    )

    for value in (
        module_name,
        status.value,
        package_layout_id,
        repository_observation_id,
    ):
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(
            b"\0"
        )

    for candidate in candidates:
        digest.update(
            candidate.evidence_id.encode(
                "ascii"
            )
        )
        digest.update(
            b"\0"
        )

    return (
        "python-repository-module-resolution:"
        + digest.hexdigest()
    )


def resolve_repository_module(
    repository: Path,
    observation: GitCommitObservation,
    layout: PythonPackageLayoutEvidence,
    module_name: str,
) -> PythonRepositoryModuleResolution:
    module_parts = tuple(
        part
        for part in module_name.split(
            "."
        )
        if part
    )

    entries_by_path = {
        entry.path: entry
        for entry in observation.entries
    }

    candidates: list[
        PythonRepositoryModuleCandidate
    ] = []

    if module_parts:
        for root in layout.import_roots:
            if (
                module_parts[0]
                != root.top_level_package
            ):
                continue

            module_path = (
                _join_root(
                    root.root_path,
                    *module_parts,
                )
                + ".py"
            )

            package_init_path = (
                _join_root(
                    root.root_path,
                    *module_parts,
                    "__init__.py",
                )
            )

            possible = (
                (
                    PythonRepositoryModuleKind.MODULE_FILE,
                    module_path,
                ),
                (
                    PythonRepositoryModuleKind.PACKAGE_INIT,
                    package_init_path,
                ),
            )

            for kind, path in possible:
                entry = entries_by_path.get(
                    path
                )

                if entry is None:
                    continue

                if entry.object_type != "blob":
                    continue

                blob = read_observed_blob(
                    repository,
                    observation,
                    path,
                )

                evidence_id = (
                    _candidate_identity(
                        module_name=module_name,
                        kind=kind,
                        path=path,
                        object_id=(
                            entry.object_id
                        ),
                        blob_evidence_id=(
                            blob.evidence_id
                        ),
                        import_root_evidence_id=(
                            root.evidence_id
                        ),
                    )
                )

                candidates.append(
                    PythonRepositoryModuleCandidate(
                        module_name=module_name,
                        kind=kind,
                        path=path,
                        object_id=(
                            entry.object_id
                        ),
                        blob_evidence_id=(
                            blob.evidence_id
                        ),
                        import_root_evidence_id=(
                            root.evidence_id
                        ),
                        evidence_id=evidence_id,
                    )
                )

    ordered_candidates = tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.path,
                candidate.kind.value,
                candidate.import_root_evidence_id,
            ),
        )
    )

    if not ordered_candidates:
        status = (
            PythonRepositoryModuleStatus.NOT_FOUND
        )
    elif len(
        ordered_candidates
    ) == 1:
        status = (
            PythonRepositoryModuleStatus.UNIQUE
        )
    else:
        status = (
            PythonRepositoryModuleStatus.AMBIGUOUS
        )

    repository_observation_id = (
        observation.observation_id
    )

    resolution_id = (
        _resolution_identity(
            module_name=module_name,
            status=status,
            package_layout_id=(
                layout.layout_id
            ),
            repository_observation_id=(
                repository_observation_id
            ),
            candidates=(
                ordered_candidates
            ),
        )
    )

    return PythonRepositoryModuleResolution(
        module_name=module_name,
        status=status,
        package_layout_id=(
            layout.layout_id
        ),
        repository_observation_id=(
            repository_observation_id
        ),
        candidates=ordered_candidates,
        resolution_id=resolution_id,
    )
