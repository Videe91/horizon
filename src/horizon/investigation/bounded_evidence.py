"""Deterministic bounded views over complete investigation evidence.

Complete executed observations remain the authoritative evidence.

This module creates smaller, content-addressed evidence views for later
model-facing investigation rounds. A bounded view:

- identifies and hashes its complete parent evidence;
- retains repository and search provenance;
- exposes a deterministic path manifest;
- retains a deterministic, path-diverse subset of exact matches;
- binds every omitted match through manifest hashes and counts;
- never creates semantic truth.

The bounded view is derived evidence, not a replacement for the complete
observation.
"""

from __future__ import annotations

import base64
import hashlib
import json

from collections import defaultdict
from typing import Any

from horizon.investigation.evidence_records import (
    SEARCH_OBSERVATION_EVIDENCE_KIND,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
)


class BoundedInvestigationEvidenceError(
    ValueError
):
    """Investigation evidence cannot be bounded faithfully."""


BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND = (
    "BOUNDED_INVESTIGATION_SEARCH_OBSERVATION"
)

_MINIMUM_PAYLOAD_BUDGET = 2048


def _canonical_text(
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
    )


def _canonical_bytes(
    value: object,
) -> bytes:
    return _canonical_text(
        value
    ).encode(
        "utf-8"
    )


def _sha256(
    value: bytes,
) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            value
        ).hexdigest()
    )


def _identity(
    prefix: str,
    value: object,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            _canonical_bytes(
                value
            )
        ).hexdigest()
    )


def _require_text(
    value: object,
    *,
    field: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise BoundedInvestigationEvidenceError(
            f"{field} must be nonempty text"
        )

    return value


def _require_nonnegative_integer(
    value: object,
    *,
    field: str,
) -> int:
    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            int,
        )
        or value < 0
    ):
        raise BoundedInvestigationEvidenceError(
            f"{field} must be a nonnegative integer"
        )

    return value


def _parse_source_record(
    record: CanonicalEvidenceRecord,
) -> dict[
    str,
    Any,
]:
    if not isinstance(
        record,
        CanonicalEvidenceRecord,
    ):
        raise BoundedInvestigationEvidenceError(
            "record must be a CanonicalEvidenceRecord"
        )

    if (
        record.evidence_kind
        != SEARCH_OBSERVATION_EVIDENCE_KIND
    ):
        raise BoundedInvestigationEvidenceError(
            "record evidence kind must be "
            "INVESTIGATION_SEARCH_OBSERVATION"
        )

    _require_text(
        record.evidence_id,
        field="source evidence id",
    )

    try:
        payload = json.loads(
            record.canonical_payload
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise BoundedInvestigationEvidenceError(
            "source canonical payload must be valid JSON"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise BoundedInvestigationEvidenceError(
            "source canonical payload must be an object"
        )

    required_text = (
        "operation_kind",
        "observation_id",
        "query",
        "commit_sha",
        "repository_observation_id",
        "source_search_id",
    )

    for field in required_text:
        _require_text(
            payload.get(
                field
            ),
            field=field,
        )

    if (
        payload[
            "operation_kind"
        ]
        != "SEARCH_SOURCE"
    ):
        raise BoundedInvestigationEvidenceError(
            "source operation kind must be SEARCH_SOURCE"
        )

    path_prefix = payload.get(
        "path_prefix"
    )

    if path_prefix is not None:
        _require_text(
            path_prefix,
            field="path_prefix",
        )

    matches = payload.get(
        "matches"
    )

    if not isinstance(
        matches,
        list,
    ):
        raise BoundedInvestigationEvidenceError(
            "source matches must be a list"
        )

    match_count = (
        _require_nonnegative_integer(
            payload.get(
                "match_count"
            ),
            field="match_count",
        )
    )

    if (
        match_count
        != len(
            matches
        )
    ):
        raise BoundedInvestigationEvidenceError(
            "source match count does not match payload"
        )

    evidence_ids: list[
        str
    ] = []

    for match in matches:
        if not isinstance(
            match,
            dict,
        ):
            raise BoundedInvestigationEvidenceError(
                "source matches must be objects"
            )

        for field in (
            "evidence_id",
            "path",
            "object_id",
            "line_base64",
        ):
            _require_text(
                match.get(
                    field
                ),
                field=(
                    "match "
                    + field
                ),
            )

        for field in (
            "line_number",
            "byte_start",
            "byte_end",
        ):
            _require_nonnegative_integer(
                match.get(
                    field
                ),
                field=(
                    "match "
                    + field
                ),
            )

        if (
            match[
                "line_number"
            ]
            <= 0
        ):
            raise BoundedInvestigationEvidenceError(
                "match line number must be positive"
            )

        if (
            match[
                "byte_end"
            ]
            < match[
                "byte_start"
            ]
        ):
            raise BoundedInvestigationEvidenceError(
                "match byte end precedes byte start"
            )

        try:
            base64.b64decode(
                match[
                    "line_base64"
                ],
                validate=True,
            )
        except Exception as exc:
            raise BoundedInvestigationEvidenceError(
                "match line_base64 is invalid"
            ) from exc

        evidence_ids.append(
            match[
                "evidence_id"
            ]
        )

    if (
        len(
            evidence_ids
        )
        != len(
            set(
                evidence_ids
            )
        )
    ):
        raise BoundedInvestigationEvidenceError(
            "source contains duplicate match evidence ids"
        )

    if (
        payload[
            "observation_id"
        ]
        != record.evidence_id
    ):
        raise BoundedInvestigationEvidenceError(
            "source observation identity does not match evidence id"
        )

    return payload


def _visible_match(
    match: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    object,
]:
    raw = base64.b64decode(
        match[
            "line_base64"
        ],
        validate=True,
    )

    try:
        line_utf8: str | None = (
            raw.decode(
                "utf-8"
            )
        )
    except UnicodeDecodeError:
        line_utf8 = None

    return {
        "evidence_id": (
            match[
                "evidence_id"
            ]
        ),
        "path": (
            match[
                "path"
            ]
        ),
        "object_id": (
            match[
                "object_id"
            ]
        ),
        "line_number": (
            match[
                "line_number"
            ]
        ),
        "line_base64": (
            match[
                "line_base64"
            ]
        ),
        "line_utf8": (
            line_utf8
        ),
        "byte_start": (
            match[
                "byte_start"
            ]
        ),
        "byte_end": (
            match[
                "byte_end"
            ]
        ),
    }


def _path_diverse_match_order(
    matches: list[
        dict[
            str,
            Any,
        ]
    ],
) -> tuple[
    dict[
        str,
        Any,
    ],
    ...,
]:
    grouped: dict[
        str,
        list[
            dict[
                str,
                Any,
            ]
        ],
    ] = defaultdict(
        list
    )

    for match in matches:
        grouped[
            match[
                "path"
            ]
        ].append(
            match
        )

    for items in grouped.values():
        items.sort(
            key=lambda item: (
                item[
                    "line_number"
                ],
                item[
                    "byte_start"
                ],
                item[
                    "evidence_id"
                ],
            )
        )

    paths = tuple(
        sorted(
            grouped
        )
    )

    max_depth = max(
        (
            len(
                grouped[
                    path
                ]
            )
            for path
            in paths
        ),
        default=0,
    )

    ordered: list[
        dict[
            str,
            Any,
        ]
    ] = []

    for depth in range(
        max_depth
    ):
        for path in paths:
            items = grouped[
                path
            ]

            if depth < len(
                items
            ):
                ordered.append(
                    items[
                        depth
                    ]
                )

    return tuple(
        ordered
    )


def _view_payload(
    *,
    source_record: CanonicalEvidenceRecord,
    source: dict[
        str,
        Any,
    ],
    max_payload_bytes: int,
    path_manifest: list[
        str
    ],
    all_paths: tuple[
        str,
        ...,
    ],
    selected_matches: list[
        dict[
            str,
            object,
        ]
    ],
) -> dict[
    str,
    object,
]:
    all_match_ids = [
        match[
            "evidence_id"
        ]
        for match
        in source[
            "matches"
        ]
    ]

    return {
        "schema_version": 1,
        "source_evidence_id": (
            source_record.evidence_id
        ),
        "source_evidence_kind": (
            source_record.evidence_kind
        ),
        "source_payload_sha256": (
            _sha256(
                source_record
                .canonical_payload
                .encode(
                    "utf-8"
                )
            )
        ),
        "operation_kind": (
            source[
                "operation_kind"
            ]
        ),
        "observation_id": (
            source[
                "observation_id"
            ]
        ),
        "query": (
            source[
                "query"
            ]
        ),
        "path_prefix": (
            source[
                "path_prefix"
            ]
        ),
        "commit_sha": (
            source[
                "commit_sha"
            ]
        ),
        "repository_observation_id": (
            source[
                "repository_observation_id"
            ]
        ),
        "source_search_id": (
            source[
                "source_search_id"
            ]
        ),
        "max_payload_bytes": (
            max_payload_bytes
        ),
        "selection_policy": (
            "PATH_DIVERSITY_ROUND_ROBIN_BY_SOURCE_POSITION"
        ),
        "total_match_count": len(
            source[
                "matches"
            ]
        ),
        "selected_match_count": len(
            selected_matches
        ),
        "omitted_match_count": (
            len(
                source[
                    "matches"
                ]
            )
            - len(
                selected_matches
            )
        ),
        "all_match_evidence_ids_sha256": (
            _sha256(
                _canonical_bytes(
                    all_match_ids
                )
            )
        ),
        "total_unique_path_count": len(
            all_paths
        ),
        "path_manifest_count": len(
            path_manifest
        ),
        "omitted_path_count": (
            len(
                all_paths
            )
            - len(
                path_manifest
            )
        ),
        "path_manifest_complete": (
            len(
                path_manifest
            )
            == len(
                all_paths
            )
        ),
        "all_unique_paths_sha256": (
            _sha256(
                _canonical_bytes(
                    list(
                        all_paths
                    )
                )
            )
        ),
        "path_manifest": (
            path_manifest
        ),
        "selected_matches": (
            selected_matches
        ),
        "truncated": (
            len(
                selected_matches
            )
            != len(
                source[
                    "matches"
                ]
            )
            or len(
                path_manifest
            )
            != len(
                all_paths
            )
        ),
    }


def bound_search_observation_evidence_record(
    record: CanonicalEvidenceRecord,
    *,
    max_payload_bytes: int,
) -> CanonicalEvidenceRecord:
    """Create one bounded model-facing view over complete search evidence."""

    if (
        isinstance(
            max_payload_bytes,
            bool,
        )
        or not isinstance(
            max_payload_bytes,
            int,
        )
        or max_payload_bytes
        < _MINIMUM_PAYLOAD_BUDGET
    ):
        raise BoundedInvestigationEvidenceError(
            "max payload bytes must be an integer "
            f"at least {_MINIMUM_PAYLOAD_BUDGET}"
        )

    source = _parse_source_record(
        record
    )

    all_paths = tuple(
        sorted(
            {
                match[
                    "path"
                ]
                for match
                in source[
                    "matches"
                ]
            }
        )
    )

    # Reserve at most one quarter of the record budget for the
    # path manifest. The remainder is available for exact match
    # evidence and fixed provenance metadata.
    path_manifest_budget = max(
        512,
        max_payload_bytes
        // 4,
    )

    path_manifest: list[
        str
    ] = []

    for path in all_paths:
        candidate = (
            path_manifest
            + [
                path
            ]
        )

        if (
            len(
                _canonical_bytes(
                    candidate
                )
            )
            <= path_manifest_budget
        ):
            path_manifest.append(
                path
            )

    selected_matches: list[
        dict[
            str,
            object,
        ]
    ] = []

    base = _view_payload(
        source_record=record,
        source=source,
        max_payload_bytes=(
            max_payload_bytes
        ),
        path_manifest=(
            path_manifest
        ),
        all_paths=all_paths,
        selected_matches=(
            selected_matches
        ),
    )

    if (
        len(
            _canonical_bytes(
                base
            )
        )
        > max_payload_bytes
    ):
        raise BoundedInvestigationEvidenceError(
            "bounded evidence metadata exceeds payload budget"
        )

    for raw_match in (
        _path_diverse_match_order(
            source[
                "matches"
            ]
        )
    ):
        visible = _visible_match(
            raw_match
        )

        candidate_matches = (
            selected_matches
            + [
                visible
            ]
        )

        candidate_payload = (
            _view_payload(
                source_record=record,
                source=source,
                max_payload_bytes=(
                    max_payload_bytes
                ),
                path_manifest=(
                    path_manifest
                ),
                all_paths=all_paths,
                selected_matches=(
                    candidate_matches
                ),
            )
        )

        if (
            len(
                _canonical_bytes(
                    candidate_payload
                )
            )
            <= max_payload_bytes
        ):
            selected_matches.append(
                visible
            )

    payload = _view_payload(
        source_record=record,
        source=source,
        max_payload_bytes=(
            max_payload_bytes
        ),
        path_manifest=(
            path_manifest
        ),
        all_paths=all_paths,
        selected_matches=(
            selected_matches
        ),
    )

    canonical_payload = _canonical_text(
        payload
    )

    if (
        len(
            canonical_payload.encode(
                "utf-8"
            )
        )
        > max_payload_bytes
    ):
        raise BoundedInvestigationEvidenceError(
            "bounded evidence exceeded payload budget"
        )

    evidence_id = _identity(
        "bounded-investigation-search-evidence:",
        payload,
    )

    return CanonicalEvidenceRecord(
        evidence_id=evidence_id,
        evidence_kind=(
            BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND
        ),
        canonical_payload=(
            canonical_payload
        ),
    )
