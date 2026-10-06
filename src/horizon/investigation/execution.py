"""Execution boundary for typed Horizon investigation operations.

This module executes only operations Horizon explicitly implements.

The first executable operation is SEARCH_SOURCE. It delegates repository
search to Horizon's existing immutable Git observation/search evidence
layer.

Execution returns observations. It does not create claims, epistemic
assessments, architectural conclusions, or world-model assertions.
"""

from __future__ import annotations

import hashlib
import json
import subprocess

from dataclasses import dataclass
from pathlib import Path

from horizon.investigation.plan import (
    InvestigationOperation,
    SearchSourceOperation,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)
from horizon.repository.git_search import (
    GitTextMatch,
    search_observed_text,
)


class InvestigationExecutionError(
    ValueError
):
    """A typed investigation operation cannot be executed faithfully."""


class UnsupportedInvestigationOperationError(
    InvestigationExecutionError
):
    """The typed operation exists but has no executor yet."""


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationSearchObservation:
    query: str
    path_prefix: str | None

    commit_sha: str
    repository_observation_id: str

    source_search_id: str
    matches: tuple[
        GitTextMatch,
        ...,
    ]

    observation_id: str


def _git(
    repository: Path,
    *args: str,
) -> str:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(
                    repository
                ),
                *args,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise InvestigationExecutionError(
            "repository state could not be verified"
        ) from exc

    return completed.stdout.strip()


def _verify_repository_state(
    repository: Path,
    observation: GitCommitObservation,
) -> None:
    if not isinstance(
        observation,
        GitCommitObservation,
    ):
        raise InvestigationExecutionError(
            "observation must be a GitCommitObservation"
        )

    head = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    if (
        head
        != observation.commit_sha
    ):
        raise InvestigationExecutionError(
            "repository commit does not match observation"
        )

    status = _git(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )

    if status:
        raise InvestigationExecutionError(
            "repository working tree must be clean"
        )


def _path_is_within_prefix(
    path: str,
    prefix: str,
) -> bool:
    return (
        path == prefix
        or path.startswith(
            prefix
            + "/"
        )
    )


def _search_observation_identity(
    *,
    operation: SearchSourceOperation,
    observation: GitCommitObservation,
    source_search_id: str,
    matches: tuple[
        GitTextMatch,
        ...,
    ],
) -> str:
    payload = {
        "operation_kind": (
            operation.kind.value
        ),
        "query": (
            operation.query
        ),
        "path_prefix": (
            operation.path_prefix
        ),
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.observation_id
        ),
        "source_search_id": (
            source_search_id
        ),
        "match_evidence_ids": [
            match.evidence_id
            for match
            in matches
        ],
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        "investigation-search-observation:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _execute_search_source(
    repository: Path,
    observation: GitCommitObservation,
    operation: SearchSourceOperation,
) -> InvestigationSearchObservation:
    search = search_observed_text(
        repository,
        observation,
        operation.query,
    )

    if (
        operation.path_prefix
        is None
    ):
        matches = search.matches
    else:
        matches = tuple(
            match
            for match
            in search.matches
            if _path_is_within_prefix(
                match.path,
                operation.path_prefix,
            )
        )

    return InvestigationSearchObservation(
        query=operation.query,
        path_prefix=(
            operation.path_prefix
        ),
        commit_sha=(
            observation.commit_sha
        ),
        repository_observation_id=(
            observation.observation_id
        ),
        source_search_id=(
            search.search_id
        ),
        matches=matches,
        observation_id=(
            _search_observation_identity(
                operation=operation,
                observation=observation,
                source_search_id=(
                    search.search_id
                ),
                matches=matches,
            )
        ),
    )


def execute_investigation_operation(
    repository: str | Path,
    observation: GitCommitObservation,
    operation: InvestigationOperation,
) -> InvestigationSearchObservation:
    """Execute one supported typed operation against one observed repo."""

    repository_path = Path(
        repository
    ).resolve()

    if (
        not repository_path.exists()
        or not repository_path.is_dir()
    ):
        raise InvestigationExecutionError(
            "repository path must identify an existing directory"
        )

    _verify_repository_state(
        repository_path,
        observation,
    )

    if isinstance(
        operation,
        SearchSourceOperation,
    ):
        return _execute_search_source(
            repository_path,
            observation,
            operation,
        )

    kind = getattr(
        operation,
        "kind",
        None,
    )

    kind_text = (
        kind.value
        if kind is not None
        else type(
            operation
        ).__name__
    )

    raise UnsupportedInvestigationOperationError(
        "no executor exists yet for "
        f"{kind_text}"
    )
