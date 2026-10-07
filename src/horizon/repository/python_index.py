"""Instant cache-aware index for tracked Python source.

This layer deliberately does not materialize PythonStructureFact objects.

Its purpose is to let Horizon know immediately:

- which Python source files exist;
- their exact current Git provenance;
- their content-addressed extraction identity;
- whether reusable structural computation is already present.

Detailed structural evidence is materialized separately when required.
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
from horizon.languages.python.structure_cache import (
    make_python_structure_cache_key,
)
from horizon.repository.git_blob import (
    GitBlobError,
    read_observed_blobs,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
    GitTreeEntry,
)


class PythonRepositoryIndexError(
    ValueError
):
    """A Python repository index could not be formed faithfully."""


@dataclass(
    frozen=True,
    slots=True,
)
class PythonIndexedFile:
    path: str
    object_id: str

    source_evidence_id: str

    content_sha256: str
    cache_key_id: str

    cache_present: bool

    handle_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class PythonRepositoryIndex:
    commit_sha: str
    repository_observation_id: str

    python_file_count: int

    cache_present_count: int
    cache_missing_count: int

    files: tuple[
        PythonIndexedFile,
        ...,
    ]

    index_id: str

    blob_read_elapsed_ns: int
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


def _handle_identity(
    *,
    path: str,
    object_id: str,
    source_evidence_id: str,
    content_sha256: str,
    cache_key_id: str,
) -> str:
    payload = {
        "schema_version": 1,
        "path": path,
        "object_id": object_id,
        "source_evidence_id": (
            source_evidence_id
        ),
        "content_sha256": (
            content_sha256
        ),
        "cache_key_id": (
            cache_key_id
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
        "python-indexed-file:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _index_identity(
    *,
    observation: GitCommitObservation,
    files: tuple[
        PythonIndexedFile,
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
                "handle_id": (
                    file.handle_id
                ),
            }
            for file
            in files
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
        "python-repository-index:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def index_python_repository(
    repository: str | Path,
    observation: GitCommitObservation,
    cache: ContentAddressedExtractionCache,
) -> PythonRepositoryIndex:
    """Index tracked regular Python source without materializing facts."""

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
        raise PythonRepositoryIndexError(
            "repository path must identify an existing directory"
        )

    if not isinstance(
        observation,
        GitCommitObservation,
    ):
        raise PythonRepositoryIndexError(
            "observation must be a GitCommitObservation"
        )

    if not isinstance(
        cache,
        ContentAddressedExtractionCache,
    ):
        raise PythonRepositoryIndexError(
            "cache must be ContentAddressedExtractionCache"
        )

    entries = _python_entries(
        observation
    )

    blob_started = (
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
        raise PythonRepositoryIndexError(
            "observed Python blobs could not be batch-read"
        ) from exc

    blob_read_elapsed_ns = (
        time.perf_counter_ns()
        - blob_started
    )

    if len(
        blobs
    ) != len(
        entries
    ):
        raise PythonRepositoryIndexError(
            "batch blob count does not match Python entries"
        )

    indexed: list[
        PythonIndexedFile
    ] = []

    for entry, blob in zip(
        entries,
        blobs,
        strict=True,
    ):
        key = (
            make_python_structure_cache_key(
                blob.content
            )
        )

        present = cache.contains(
            key
        )

        indexed.append(
            PythonIndexedFile(
                path=entry.path,
                object_id=(
                    entry.object_id
                ),
                source_evidence_id=(
                    blob.evidence_id
                ),
                content_sha256=(
                    key.content_sha256
                ),
                cache_key_id=(
                    key.key_id
                ),
                cache_present=(
                    present
                ),
                handle_id=(
                    _handle_identity(
                        path=(
                            entry.path
                        ),
                        object_id=(
                            entry.object_id
                        ),
                        source_evidence_id=(
                            blob.evidence_id
                        ),
                        content_sha256=(
                            key.content_sha256
                        ),
                        cache_key_id=(
                            key.key_id
                        ),
                    )
                ),
            )
        )

    files = tuple(
        indexed
    )

    cache_present_count = sum(
        1
        for file
        in files
        if file.cache_present
    )

    elapsed_ns = (
        time.perf_counter_ns()
        - started
    )

    return PythonRepositoryIndex(
        commit_sha=(
            observation.commit_sha
        ),
        repository_observation_id=(
            observation.observation_id
        ),
        python_file_count=(
            len(
                files
            )
        ),
        cache_present_count=(
            cache_present_count
        ),
        cache_missing_count=(
            len(
                files
            )
            - cache_present_count
        ),
        files=files,
        index_id=(
            _index_identity(
                observation=observation,
                files=files,
            )
        ),
        blob_read_elapsed_ns=(
            blob_read_elapsed_ns
        ),
        elapsed_ns=(
            elapsed_ns
        ),
    )
