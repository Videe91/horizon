"""Automatic Python source materialization for one observed repository.

This is the first repository-open path toward Horizon's instant layer.

It:

- discovers tracked regular Python source blobs automatically;
- reads each source from the immutable Git observation;
- runs cache-aware Python structural extraction;
- preserves current repository provenance on every materialization;
- reports explicit syntax failures without hiding healthy files;
- records cache hit/miss and timing information.

It does not infer architecture.
It does not create world-model assertions.
It does not call AI.
It does not render Cards.
"""

from __future__ import annotations

import hashlib
import json
import time

from dataclasses import dataclass
from pathlib import Path

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.languages.python.structure import (
    PythonStructureAnalysis,
    PythonSyntaxEvidenceError,
)
from horizon.languages.python.structure_cache import (
    analyze_python_blob_cached,
)
from horizon.repository.git_blob import (
    GitBlobError,
    read_observed_blobs,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
    GitTreeEntry,
)


class PythonRepositoryOpenError(
    ValueError
):
    """An observed repository could not be materialized faithfully."""


@dataclass(
    frozen=True,
    slots=True,
)
class PythonRepositoryFileMaterialization:
    path: str
    object_id: str

    source_evidence_id: str

    cache_key_id: str
    content_sha256: str
    cache_hit: bool

    analysis: PythonStructureAnalysis

    elapsed_ns: int


@dataclass(
    frozen=True,
    slots=True,
)
class PythonRepositorySyntaxFailure:
    path: str
    object_id: str

    source_evidence_id: str

    error_message: str
    failure_id: str

    elapsed_ns: int


@dataclass(
    frozen=True,
    slots=True,
)
class PythonRepositoryOpenReport:
    commit_sha: str
    repository_observation_id: str

    python_file_count: int
    analyzed_file_count: int
    failed_file_count: int

    cache_hits: int
    cache_misses: int

    total_fact_count: int

    blob_read_elapsed_ns: int

    files: tuple[
        PythonRepositoryFileMaterialization,
        ...,
    ]

    failures: tuple[
        PythonRepositorySyntaxFailure,
        ...,
    ]

    materialization_id: str

    elapsed_ns: int


_REGULAR_BLOB_MODES = {
    "100644",
    "100755",
}


def _python_entries(
    observation: GitCommitObservation,
) -> tuple[
    GitTreeEntry,
    ...,
]:
    return tuple(
        entry
        for entry
        in observation.entries
        if (
            entry.object_type
            == "blob"
            and entry.mode
            in _REGULAR_BLOB_MODES
            and entry.path.endswith(
                ".py"
            )
        )
    )


def _syntax_failure_identity(
    *,
    path: str,
    object_id: str,
    source_evidence_id: str,
    error_message: str,
) -> str:
    payload = {
        "schema_version": 1,
        "path": path,
        "object_id": (
            object_id
        ),
        "source_evidence_id": (
            source_evidence_id
        ),
        "error_message": (
            error_message
        ),
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
        "python-open-syntax-failure:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _materialization_identity(
    *,
    observation: GitCommitObservation,
    files: tuple[
        PythonRepositoryFileMaterialization,
        ...,
    ],
    failures: tuple[
        PythonRepositorySyntaxFailure,
        ...,
    ],
) -> str:
    payload = {
        "schema_version": 1,
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.observation_id
        ),
        "files": [
            {
                "path": (
                    file.path
                ),
                "object_id": (
                    file.object_id
                ),
                "source_evidence_id": (
                    file.source_evidence_id
                ),
                "analysis_id": (
                    file.analysis.analysis_id
                ),
            }
            for file
            in files
        ],
        "failures": [
            failure.failure_id
            for failure
            in failures
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
        "python-repository-materialization:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def open_python_repository(
    repository: str | Path,
    observation: GitCommitObservation,
    cache: ContentAddressedExtractionCache,
) -> PythonRepositoryOpenReport:
    """Materialize tracked Python structure for one observed repository."""

    started = (
        time.perf_counter_ns()
    )

    repository_path = Path(
        repository
    ).resolve()

    if (
        not repository_path.exists()
        or not repository_path.is_dir()
    ):
        raise PythonRepositoryOpenError(
            "repository path must identify an existing directory"
        )

    if not isinstance(
        observation,
        GitCommitObservation,
    ):
        raise PythonRepositoryOpenError(
            "observation must be a GitCommitObservation"
        )

    if not isinstance(
        cache,
        ContentAddressedExtractionCache,
    ):
        raise PythonRepositoryOpenError(
            "cache must be a ContentAddressedExtractionCache"
        )

    entries = _python_entries(
        observation
    )

    blob_read_started = (
        time.perf_counter_ns()
    )

    try:
        blobs = read_observed_blobs(
            repository_path,
            observation,
            tuple(
                entry.path
                for entry
                in entries
            ),
        )
    except GitBlobError as exc:
        raise PythonRepositoryOpenError(
            "observed Python blobs could not be batch-read"
        ) from exc

    blob_read_elapsed_ns = (
        time.perf_counter_ns()
        - blob_read_started
    )

    if len(
        blobs
    ) != len(
        entries
    ):
        raise PythonRepositoryOpenError(
            "batch blob result count does not match Python entries"
        )

    files: list[
        PythonRepositoryFileMaterialization
    ] = []

    failures: list[
        PythonRepositorySyntaxFailure
    ] = []

    for entry, blob in zip(
        entries,
        blobs,
        strict=True,
    ):
        file_started = (
            time.perf_counter_ns()
        )

        try:
            cached = (
                analyze_python_blob_cached(
                    blob,
                    cache,
                )
            )
        except PythonSyntaxEvidenceError as exc:
            elapsed_ns = (
                time.perf_counter_ns()
                - file_started
            )

            error_message = str(
                exc
            )

            failures.append(
                PythonRepositorySyntaxFailure(
                    path=entry.path,
                    object_id=(
                        entry.object_id
                    ),
                    source_evidence_id=(
                        blob.evidence_id
                    ),
                    error_message=(
                        error_message
                    ),
                    failure_id=(
                        _syntax_failure_identity(
                            path=entry.path,
                            object_id=(
                                entry.object_id
                            ),
                            source_evidence_id=(
                                blob.evidence_id
                            ),
                            error_message=(
                                error_message
                            ),
                        )
                    ),
                    elapsed_ns=(
                        elapsed_ns
                    ),
                )
            )

            continue

        elapsed_ns = (
            time.perf_counter_ns()
            - file_started
        )

        files.append(
            PythonRepositoryFileMaterialization(
                path=entry.path,
                object_id=(
                    entry.object_id
                ),
                source_evidence_id=(
                    blob.evidence_id
                ),
                cache_key_id=(
                    cached.cache_key.key_id
                ),
                content_sha256=(
                    cached.cache_key.content_sha256
                ),
                cache_hit=(
                    cached.cache_hit
                ),
                analysis=(
                    cached.analysis
                ),
                elapsed_ns=(
                    elapsed_ns
                ),
            )
        )

    materialized_files = tuple(
        files
    )

    materialized_failures = tuple(
        failures
    )

    cache_hits = sum(
        1
        for file
        in materialized_files
        if file.cache_hit
    )

    cache_misses = (
        len(
            materialized_files
        )
        - cache_hits
    )

    total_fact_count = sum(
        len(
            file.analysis.facts
        )
        for file
        in materialized_files
    )

    materialization_id = (
        _materialization_identity(
            observation=observation,
            files=(
                materialized_files
            ),
            failures=(
                materialized_failures
            ),
        )
    )

    elapsed_ns = (
        time.perf_counter_ns()
        - started
    )

    return PythonRepositoryOpenReport(
        commit_sha=(
            observation.commit_sha
        ),
        repository_observation_id=(
            observation.observation_id
        ),
        python_file_count=(
            len(
                entries
            )
        ),
        analyzed_file_count=(
            len(
                materialized_files
            )
        ),
        failed_file_count=(
            len(
                materialized_failures
            )
        ),
        cache_hits=(
            cache_hits
        ),
        cache_misses=(
            cache_misses
        ),
        total_fact_count=(
            total_fact_count
        ),
        blob_read_elapsed_ns=(
            blob_read_elapsed_ns
        ),
        files=(
            materialized_files
        ),
        failures=(
            materialized_failures
        ),
        materialization_id=(
            materialization_id
        ),
        elapsed_ns=(
            elapsed_ns
        ),
    )
