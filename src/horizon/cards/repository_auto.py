"""Automatic deterministic enrichment of the repository Card.

024A adds one evidence path only:

exact observed pyproject.toml
    -> existing Hatch package-layout evidence
    -> WHERE IT SITS

No directory heuristic is used.

If Horizon cannot establish an explicit supported package declaration,
the section remains UNKNOWN.
"""

from __future__ import annotations

from pathlib import Path

from horizon.cards.repository import (
    RepositoryCard,
    build_repository_card,
)
from horizon.languages.python.repository_modules import (
    PythonPackageLayoutEvidence,
    PythonPackageLayoutEvidenceError,
    discover_hatch_wheel_import_roots,
)
from horizon.repository.git_blob import (
    GitBlobError,
    read_observed_blob,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)
from horizon.repository.python_index import (
    PythonRepositoryIndex,
)


class RepositoryAutomaticCardError(
    ValueError
):
    """Automatic Card enrichment could not be bound to one snapshot."""


def _discover_package_layout(
    repository: Path,
    observation: GitCommitObservation,
) -> PythonPackageLayoutEvidence | None:
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
        pyproject_blob = read_observed_blob(
            repository,
            observation,
            "pyproject.toml",
        )
    except GitBlobError:
        return None

    try:
        return (
            discover_hatch_wheel_import_roots(
                pyproject_blob
            )
        )
    except PythonPackageLayoutEvidenceError:
        return None


def build_repository_card_automatically(
    repository: str | Path,
    observation: GitCommitObservation,
    index: PythonRepositoryIndex,
) -> RepositoryCard:
    """Build a repository Card and attach deterministic evidence available now."""

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
            "repository index and observation do not represent the same snapshot"
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

    package_layout = (
        _discover_package_layout(
            repository_path,
            observation,
        )
    )

    return build_repository_card(
        index,
        package_layout=(
            package_layout
        ),
    )
