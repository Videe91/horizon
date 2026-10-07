"""Bounded progressive Python structure extraction.

Repository indexing and detailed extraction are intentionally separate.

The index makes Horizon useful immediately.

This module converts missing indexed structure work into a deterministic,
content-deduplicated plan and executes only a bounded slice at a time.

Detailed PythonStructureAnalysis objects exist only while an individual
work item is being extracted or rematerialized. Batch results retain
compact completion metadata, not the full structural fact graph.
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
    PythonSyntaxEvidenceError,
)
from horizon.languages.python.structure_cache import (
    PythonStructureCacheError,
    analyze_python_blob_cached,
    make_python_structure_cache_key,
)
from horizon.repository.git_blob import (
    GitBlobError,
    read_observed_blobs,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)
from horizon.repository.python_index import (
    PythonIndexedFile,
    PythonRepositoryIndex,
)


class PythonProgressiveExtractionError(
    ValueError
):
    """Progressive Python extraction cannot proceed faithfully."""


@dataclass(
    frozen=True,
    slots=True,
)
class PythonStructureWorkItem:
    representative_path: str
    representative_source_evidence_id: str

    content_sha256: str
    cache_key_id: str

    covered_paths: tuple[
        str,
        ...,
    ]

    covered_handle_ids: tuple[
        str,
        ...,
    ]

    work_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class PythonStructureExtractionPlan:
    commit_sha: str
    repository_observation_id: str
    repository_index_id: str

    missing_file_count: int
    unique_work_item_count: int

    items: tuple[
        PythonStructureWorkItem,
        ...,
    ]

    plan_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class PythonStructureCompletion:
    work_id: str

    path: str
    source_evidence_id: str

    cache_key_id: str
    content_sha256: str

    cache_hit: bool
    fact_count: int

    covered_paths: tuple[
        str,
        ...,
    ]

    completion_id: str

    elapsed_ns: int


@dataclass(
    frozen=True,
    slots=True,
)
class PythonStructureExtractionFailure:
    work_id: str

    path: str
    source_evidence_id: str

    cache_key_id: str
    content_sha256: str

    covered_paths: tuple[
        str,
        ...,
    ]

    error_message: str
    failure_id: str

    elapsed_ns: int


@dataclass(
    frozen=True,
    slots=True,
)
class PythonStructureBatchResult:
    plan_id: str

    start_offset: int
    end_offset: int

    attempted_unique_items: int
    completed_unique_items: int
    failed_unique_items: int

    completed_file_count: int
    failed_file_count: int

    total_fact_count: int

    remaining_unique_items: int
    done: bool

    completions: tuple[
        PythonStructureCompletion,
        ...,
    ]

    failures: tuple[
        PythonStructureExtractionFailure,
        ...,
    ]

    batch_id: str

    elapsed_ns: int


def _canonical_json(
    value,
) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )


def _work_identity(
    *,
    representative: PythonIndexedFile,
    covered: tuple[
        PythonIndexedFile,
        ...,
    ],
) -> str:
    payload = {
        "schema_version": 1,
        "representative_handle_id": (
            representative.handle_id
        ),
        "cache_key_id": (
            representative.cache_key_id
        ),
        "content_sha256": (
            representative.content_sha256
        ),
        "covered_handle_ids": [
            file.handle_id
            for file
            in covered
        ],
    }

    return (
        "python-structure-work:"
        + hashlib.sha256(
            _canonical_json(
                payload
            )
        ).hexdigest()
    )


def _plan_identity(
    *,
    index: PythonRepositoryIndex,
    items: tuple[
        PythonStructureWorkItem,
        ...,
    ],
) -> str:
    payload = {
        "schema_version": 1,
        "repository_index_id": (
            index.index_id
        ),
        "work_ids": [
            item.work_id
            for item
            in items
        ],
    }

    return (
        "python-structure-plan:"
        + hashlib.sha256(
            _canonical_json(
                payload
            )
        ).hexdigest()
    )


def plan_python_structure_extraction(
    index: PythonRepositoryIndex,
) -> PythonStructureExtractionPlan:
    """Plan unique missing structure work from one immutable index."""

    if not isinstance(
        index,
        PythonRepositoryIndex,
    ):
        raise PythonProgressiveExtractionError(
            "index must be a PythonRepositoryIndex"
        )

    grouped: dict[
        str,
        list[
            PythonIndexedFile
        ],
    ] = {}

    for file in index.files:
        if file.cache_present:
            continue

        grouped.setdefault(
            file.cache_key_id,
            [],
        ).append(
            file
        )

    items: list[
        PythonStructureWorkItem
    ] = []

    covered_count = 0

    for (
        cache_key_id,
        grouped_files,
    ) in grouped.items():
        covered = tuple(
            grouped_files
        )

        representative = (
            covered[0]
        )

        if any(
            file.content_sha256
            != representative.content_sha256
            for file
            in covered
        ):
            raise PythonProgressiveExtractionError(
                "one cache identity maps to conflicting content digests"
            )

        if any(
            file.cache_key_id
            != cache_key_id
            for file
            in covered
        ):
            raise PythonProgressiveExtractionError(
                "grouped cache identity is inconsistent"
            )

        work_id = _work_identity(
            representative=(
                representative
            ),
            covered=covered,
        )

        items.append(
            PythonStructureWorkItem(
                representative_path=(
                    representative.path
                ),
                representative_source_evidence_id=(
                    representative.source_evidence_id
                ),
                content_sha256=(
                    representative.content_sha256
                ),
                cache_key_id=(
                    cache_key_id
                ),
                covered_paths=tuple(
                    file.path
                    for file
                    in covered
                ),
                covered_handle_ids=tuple(
                    file.handle_id
                    for file
                    in covered
                ),
                work_id=(
                    work_id
                ),
            )
        )

        covered_count += len(
            covered
        )

    if (
        covered_count
        != index.cache_missing_count
    ):
        raise PythonProgressiveExtractionError(
            "planned file coverage does not match index missing count"
        )

    planned_items = tuple(
        items
    )

    return PythonStructureExtractionPlan(
        commit_sha=(
            index.commit_sha
        ),
        repository_observation_id=(
            index.repository_observation_id
        ),
        repository_index_id=(
            index.index_id
        ),
        missing_file_count=(
            covered_count
        ),
        unique_work_item_count=(
            len(
                planned_items
            )
        ),
        items=planned_items,
        plan_id=_plan_identity(
            index=index,
            items=planned_items,
        ),
    )


def _completion_identity(
    *,
    work: PythonStructureWorkItem,
    source_evidence_id: str,
    fact_count: int,
) -> str:
    payload = {
        "schema_version": 1,
        "work_id": (
            work.work_id
        ),
        "source_evidence_id": (
            source_evidence_id
        ),
        "fact_count": (
            fact_count
        ),
    }

    return (
        "python-structure-completion:"
        + hashlib.sha256(
            _canonical_json(
                payload
            )
        ).hexdigest()
    )


def _failure_identity(
    *,
    work: PythonStructureWorkItem,
    source_evidence_id: str,
    error_message: str,
) -> str:
    payload = {
        "schema_version": 1,
        "work_id": (
            work.work_id
        ),
        "source_evidence_id": (
            source_evidence_id
        ),
        "error_message": (
            error_message
        ),
    }

    return (
        "python-progressive-syntax-failure:"
        + hashlib.sha256(
            _canonical_json(
                payload
            )
        ).hexdigest()
    )


def _batch_identity(
    *,
    plan: PythonStructureExtractionPlan,
    start_offset: int,
    end_offset: int,
    completions: tuple[
        PythonStructureCompletion,
        ...,
    ],
    failures: tuple[
        PythonStructureExtractionFailure,
        ...,
    ],
) -> str:
    payload = {
        "schema_version": 1,
        "plan_id": (
            plan.plan_id
        ),
        "start_offset": (
            start_offset
        ),
        "end_offset": (
            end_offset
        ),
        "completion_ids": [
            completion.completion_id
            for completion
            in completions
        ],
        "failure_ids": [
            failure.failure_id
            for failure
            in failures
        ],
    }

    return (
        "python-structure-batch:"
        + hashlib.sha256(
            _canonical_json(
                payload
            )
        ).hexdigest()
    )


def execute_python_structure_batch(
    repository: str | Path,
    observation: GitCommitObservation,
    plan: PythonStructureExtractionPlan,
    cache: ContentAddressedExtractionCache,
    *,
    offset: int,
    limit: int,
) -> PythonStructureBatchResult:
    """Execute one bounded slice of a deterministic extraction plan."""

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
        raise PythonProgressiveExtractionError(
            "repository path must identify an existing directory"
        )

    if not isinstance(
        observation,
        GitCommitObservation,
    ):
        raise PythonProgressiveExtractionError(
            "observation must be a GitCommitObservation"
        )

    if not isinstance(
        plan,
        PythonStructureExtractionPlan,
    ):
        raise PythonProgressiveExtractionError(
            "plan must be a PythonStructureExtractionPlan"
        )

    if not isinstance(
        cache,
        ContentAddressedExtractionCache,
    ):
        raise PythonProgressiveExtractionError(
            "cache must be ContentAddressedExtractionCache"
        )

    if (
        observation.commit_sha
        != plan.commit_sha
        or observation.observation_id
        != plan.repository_observation_id
    ):
        raise PythonProgressiveExtractionError(
            "plan does not belong to the supplied repository observation"
        )

    if (
        type(
            offset
        )
        is not int
        or offset < 0
        or offset
        > plan.unique_work_item_count
    ):
        raise PythonProgressiveExtractionError(
            "offset is outside the extraction plan"
        )

    if (
        type(
            limit
        )
        is not int
        or limit <= 0
    ):
        raise PythonProgressiveExtractionError(
            "limit must be a positive integer"
        )

    end_offset = min(
        plan.unique_work_item_count,
        offset
        + limit,
    )

    selected = plan.items[
        offset:
        end_offset
    ]

    if selected:
        try:
            blobs = read_observed_blobs(
                repository_path,
                observation,
                tuple(
                    item.representative_path
                    for item
                    in selected
                ),
            )
        except GitBlobError as exc:
            raise PythonProgressiveExtractionError(
                "planned source blobs could not be read"
            ) from exc
    else:
        blobs = ()

    if len(
        blobs
    ) != len(
        selected
    ):
        raise PythonProgressiveExtractionError(
            "batch blob count does not match planned work"
        )

    completions: list[
        PythonStructureCompletion
    ] = []

    failures: list[
        PythonStructureExtractionFailure
    ] = []

    for work, blob in zip(
        selected,
        blobs,
        strict=True,
    ):
        item_started = (
            time.perf_counter_ns()
        )

        if (
            blob.path
            != work.representative_path
        ):
            raise PythonProgressiveExtractionError(
                "planned path does not match observed blob"
            )

        if (
            blob.evidence_id
            != work.representative_source_evidence_id
        ):
            raise PythonProgressiveExtractionError(
                "planned source provenance does not match observed blob"
            )

        key = (
            make_python_structure_cache_key(
                blob.content
            )
        )

        if (
            key.key_id
            != work.cache_key_id
            or key.content_sha256
            != work.content_sha256
        ):
            raise PythonProgressiveExtractionError(
                "planned content identity does not match observed bytes"
            )

        try:
            extracted = (
                analyze_python_blob_cached(
                    blob,
                    cache,
                )
            )

        except PythonSyntaxEvidenceError as exc:
            elapsed_ns = (
                time.perf_counter_ns()
                - item_started
            )

            error_message = str(
                exc
            )

            failures.append(
                PythonStructureExtractionFailure(
                    work_id=(
                        work.work_id
                    ),
                    path=(
                        blob.path
                    ),
                    source_evidence_id=(
                        blob.evidence_id
                    ),
                    cache_key_id=(
                        work.cache_key_id
                    ),
                    content_sha256=(
                        work.content_sha256
                    ),
                    covered_paths=(
                        work.covered_paths
                    ),
                    error_message=(
                        error_message
                    ),
                    failure_id=(
                        _failure_identity(
                            work=work,
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

        except PythonStructureCacheError as exc:
            raise PythonProgressiveExtractionError(
                "cached Python structure could not be trusted"
            ) from exc

        fact_count = len(
            extracted.analysis.facts
        )

        elapsed_ns = (
            time.perf_counter_ns()
            - item_started
        )

        completions.append(
            PythonStructureCompletion(
                work_id=(
                    work.work_id
                ),
                path=(
                    blob.path
                ),
                source_evidence_id=(
                    blob.evidence_id
                ),
                cache_key_id=(
                    work.cache_key_id
                ),
                content_sha256=(
                    work.content_sha256
                ),
                cache_hit=(
                    extracted.cache_hit
                ),
                fact_count=(
                    fact_count
                ),
                covered_paths=(
                    work.covered_paths
                ),
                completion_id=(
                    _completion_identity(
                        work=work,
                        source_evidence_id=(
                            blob.evidence_id
                        ),
                        fact_count=(
                            fact_count
                        ),
                    )
                ),
                elapsed_ns=(
                    elapsed_ns
                ),
            )
        )

    completed = tuple(
        completions
    )

    failed = tuple(
        failures
    )

    completed_file_count = sum(
        len(
            completion.covered_paths
        )
        for completion
        in completed
    )

    failed_file_count = sum(
        len(
            failure.covered_paths
        )
        for failure
        in failed
    )

    total_fact_count = sum(
        completion.fact_count
        for completion
        in completed
    )

    remaining_unique_items = (
        plan.unique_work_item_count
        - end_offset
    )

    done = (
        remaining_unique_items
        == 0
    )

    elapsed_ns = (
        time.perf_counter_ns()
        - started
    )

    return PythonStructureBatchResult(
        plan_id=(
            plan.plan_id
        ),
        start_offset=(
            offset
        ),
        end_offset=(
            end_offset
        ),
        attempted_unique_items=(
            len(
                selected
            )
        ),
        completed_unique_items=(
            len(
                completed
            )
        ),
        failed_unique_items=(
            len(
                failed
            )
        ),
        completed_file_count=(
            completed_file_count
        ),
        failed_file_count=(
            failed_file_count
        ),
        total_fact_count=(
            total_fact_count
        ),
        remaining_unique_items=(
            remaining_unique_items
        ),
        done=(
            done
        ),
        completions=(
            completed
        ),
        failures=(
            failed
        ),
        batch_id=(
            _batch_identity(
                plan=plan,
                start_offset=(
                    offset
                ),
                end_offset=(
                    end_offset
                ),
                completions=(
                    completed
                ),
                failures=(
                    failed
                ),
            )
        ),
        elapsed_ns=(
            elapsed_ns
        ),
    )
