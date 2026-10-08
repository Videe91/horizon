"""Automatic deterministic repository Card pipeline.

Repository evidence is not written directly into Card semantic state.

The pipeline is:

exact observed repository metadata
    -> deterministic evidence
    -> canonical World Model
    -> Card projection

Unsupported evidence remains UNKNOWN.
"""

from __future__ import annotations

from pathlib import Path

from horizon.cards.repository import (
    RepositoryCard,
    build_repository_card,
)
from horizon.languages.python.project_dependencies import (
    PythonDeclaredProjectDependenciesEvidence,
    PythonProjectDependencyEvidenceError,
    discover_declared_project_dependencies,
)
from horizon.languages.python.repository_modules import (
    PythonPackageLayoutEvidence,
    PythonPackageLayoutEvidenceError,
    discover_hatch_wheel_import_roots,
)
from horizon.repository.git_blob import (
    GitBlobError,
    GitBlobEvidence,
    read_observed_blob,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)
from horizon.repository.python_index import (
    PythonRepositoryIndex,
)
from horizon.world_model.repository_deterministic import (
    build_repository_deterministic_world_model,
)


from horizon.world_model.repository_semantic_store import (
    RepositorySemanticWorldModelStore,
    RepositorySemanticWorldModelStoreError,
    default_repository_semantic_world_model_store_root,
)


class RepositoryAutomaticCardError(
    ValueError
):
    """Automatic Card enrichment could not be bound to one snapshot."""


def _read_pyproject_blob(
    repository: Path,
    observation: GitCommitObservation,
) -> GitBlobEvidence | None:
    pyproject_entry = next(
        (
            entry
            for entry
            in observation.entries
            if entry.path
            == "pyproject.toml"
        ),
        None,
    )

    if pyproject_entry is None:
        return None

    if (
        pyproject_entry.object_type
        != "blob"
    ):
        return None

    try:
        return read_observed_blob(
            repository,
            observation,
            "pyproject.toml",
        )
    except GitBlobError:
        return None


def _discover_package_layout(
    pyproject_blob: GitBlobEvidence | None,
) -> PythonPackageLayoutEvidence | None:
    if pyproject_blob is None:
        return None

    try:
        return (
            discover_hatch_wheel_import_roots(
                pyproject_blob
            )
        )
    except PythonPackageLayoutEvidenceError:
        return None


def _discover_project_dependencies(
    pyproject_blob: GitBlobEvidence | None,
) -> PythonDeclaredProjectDependenciesEvidence | None:
    if pyproject_blob is None:
        return None

    try:
        return (
            discover_declared_project_dependencies(
                pyproject_blob
            )
        )
    except PythonProjectDependencyEvidenceError:
        return None


def _load_persisted_semantic_world_model(
    world_model,
):
    try:
        store = RepositorySemanticWorldModelStore(
            default_repository_semantic_world_model_store_root()
        )

        return store.load(
            world_model
        )

    except RepositorySemanticWorldModelStoreError as exc:
        raise RepositoryAutomaticCardError(
            "persisted semantic World Model is invalid"
        ) from exc


def build_repository_card_automatically(
    repository: str | Path,
    observation: GitCommitObservation,
    index: PythonRepositoryIndex,
) -> RepositoryCard:
    """Build an automatic Card through Horizon's canonical World Model."""

    if not isinstance(
        observation,
        GitCommitObservation,
    ):
        raise RepositoryAutomaticCardError(
            "observation must be a GitCommitObservation"
        )

    if not isinstance(
        index,
        PythonRepositoryIndex,
    ):
        raise RepositoryAutomaticCardError(
            "index must be a PythonRepositoryIndex"
        )

    if (
        index.commit_sha
        != observation.commit_sha
        or index.repository_observation_id
        != observation.observation_id
    ):
        raise RepositoryAutomaticCardError(
            "repository index and observation "
            "do not represent the same snapshot"
        )

    repository_path = Path(
        repository
    ).resolve()

    if (
        not repository_path.exists()
        or not repository_path.is_dir()
    ):
        raise RepositoryAutomaticCardError(
            "repository path must identify an existing directory"
        )

    pyproject_blob = _read_pyproject_blob(
        repository_path,
        observation,
    )

    package_layout = (
        _discover_package_layout(
            pyproject_blob
        )
    )

    project_dependencies = (
        _discover_project_dependencies(
            pyproject_blob
        )
    )

    world_model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=(
                pyproject_blob
            ),
            package_layout=(
                package_layout
            ),
            project_dependencies=(
                project_dependencies
            ),
        )
    )

    world_model = (
        _load_persisted_semantic_world_model(
            world_model
        )
    )

    return build_repository_card(
        index,
        world_model=(
            world_model
        ),
    )
