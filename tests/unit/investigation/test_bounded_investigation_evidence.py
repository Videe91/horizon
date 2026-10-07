from __future__ import annotations

import base64
import hashlib
import json

import pytest

from horizon.claims.evidence_backed import (
    EvidenceBackedClaim,
)
from horizon.claims.epistemic import (
    EpistemicAssessment,
)
from horizon.investigation.bounded_evidence import (
    BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND,
    BoundedInvestigationEvidenceError,
    bound_search_observation_evidence_record,
)
from horizon.investigation.evidence_records import (
    SEARCH_OBSERVATION_EVIDENCE_KIND,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
)


def _source_record(
    *,
    match_count: int = 4,
) -> CanonicalEvidenceRecord:
    matches = []

    for index in range(
        match_count
    ):
        path = (
            "src/pkg/a.py"
            if index % 2 == 0
            else "src/pkg/b.py"
        )

        line = (
            f"class Example{index}:\n"
            .encode(
                "utf-8"
            )
        )

        matches.append(
            {
                "evidence_id": (
                    f"git-search-match:{index}"
                ),
                "path": path,
                "object_id": (
                    f"{index:040x}"
                ),
                "line_number": (
                    index + 1
                ),
                "line_base64": (
                    base64.b64encode(
                        line
                    ).decode(
                        "ascii"
                    )
                ),
                "byte_start": (
                    index * 100
                ),
                "byte_end": (
                    index * 100 + 5
                ),
            }
        )

    payload = {
        "operation_kind": (
            "SEARCH_SOURCE"
        ),
        "observation_id": (
            "investigation-search-observation:test"
        ),
        "query": "class Example",
        "path_prefix": "src/pkg",
        "commit_sha": (
            "a" * 40
        ),
        "repository_observation_id": (
            "git-commit-observation:test"
        ),
        "source_search_id": (
            "git-text-search:test"
        ),
        "match_count": (
            len(
                matches
            )
        ),
        "matches": matches,
    }

    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    )

    return CanonicalEvidenceRecord(
        evidence_id=(
            "investigation-search-observation:test"
        ),
        evidence_kind=(
            SEARCH_OBSERVATION_EVIDENCE_KIND
        ),
        canonical_payload=(
            canonical_payload
        ),
    )


def test_small_record_becomes_bounded_derived_evidence() -> None:
    source = _source_record()

    record = (
        bound_search_observation_evidence_record(
            source,
            max_payload_bytes=65536,
        )
    )

    assert isinstance(
        record,
        CanonicalEvidenceRecord,
    )

    assert (
        record.evidence_kind
        == BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND
    )

    assert (
        record.evidence_id
        != source.evidence_id
    )

    assert record.evidence_id.startswith(
        "bounded-investigation-search-evidence:"
    )


def test_small_record_preserves_every_match() -> None:
    record = (
        bound_search_observation_evidence_record(
            _source_record(),
            max_payload_bytes=65536,
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert payload[
        "total_match_count"
    ] == 4

    assert payload[
        "selected_match_count"
    ] == 4

    assert payload[
        "omitted_match_count"
    ] == 0

    assert payload[
        "truncated"
    ] is False


def test_readable_selected_lines_have_utf8_and_exact_bytes() -> None:
    record = (
        bound_search_observation_evidence_record(
            _source_record(),
            max_payload_bytes=65536,
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    match = payload[
        "selected_matches"
    ][
        0
    ]

    raw = base64.b64decode(
        match[
            "line_base64"
        ]
    )

    assert (
        match[
            "line_utf8"
        ]
        == raw.decode(
            "utf-8"
        )
    )


def test_large_record_is_strictly_bounded() -> None:
    source = _source_record(
        match_count=500
    )

    record = (
        bound_search_observation_evidence_record(
            source,
            max_payload_bytes=8192,
        )
    )

    payload_bytes = len(
        record.canonical_payload.encode(
            "utf-8"
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert payload_bytes <= 8192

    assert payload[
        "truncated"
    ] is True

    assert (
        payload[
            "selected_match_count"
        ]
        < payload[
            "total_match_count"
        ]
    )

    assert (
        payload[
            "omitted_match_count"
        ]
        > 0
    )


def test_all_source_match_ids_are_bound_by_manifest_hash() -> None:
    source = _source_record(
        match_count=20
    )

    record = (
        bound_search_observation_evidence_record(
            source,
            max_payload_bytes=8192,
        )
    )

    source_payload = json.loads(
        source.canonical_payload
    )

    evidence_ids = [
        match[
            "evidence_id"
        ]
        for match
        in source_payload[
            "matches"
        ]
    ]

    encoded = json.dumps(
        evidence_ids,
        sort_keys=False,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    expected = (
        "sha256:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert (
        payload[
            "all_match_evidence_ids_sha256"
        ]
        == expected
    )


def test_path_manifest_is_sorted_and_complete_when_it_fits() -> None:
    record = (
        bound_search_observation_evidence_record(
            _source_record(
                match_count=20
            ),
            max_payload_bytes=65536,
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert payload[
        "path_manifest"
    ] == [
        "src/pkg/a.py",
        "src/pkg/b.py",
    ]

    assert payload[
        "path_manifest_complete"
    ] is True

    assert payload[
        "omitted_path_count"
    ] == 0


def test_selection_is_deterministic() -> None:
    source = _source_record(
        match_count=100
    )

    first = (
        bound_search_observation_evidence_record(
            source,
            max_payload_bytes=8192,
        )
    )

    second = (
        bound_search_observation_evidence_record(
            source,
            max_payload_bytes=8192,
        )
    )

    assert first == second


def test_selected_match_ids_are_subset_of_parent_evidence() -> None:
    source = _source_record(
        match_count=100
    )

    record = (
        bound_search_observation_evidence_record(
            source,
            max_payload_bytes=8192,
        )
    )

    source_payload = json.loads(
        source.canonical_payload
    )

    source_ids = {
        item[
            "evidence_id"
        ]
        for item
        in source_payload[
            "matches"
        ]
    }

    payload = json.loads(
        record.canonical_payload
    )

    selected_ids = {
        item[
            "evidence_id"
        ]
        for item
        in payload[
            "selected_matches"
        ]
    }

    assert selected_ids
    assert selected_ids <= source_ids


def test_wrong_source_kind_is_rejected() -> None:
    source = _source_record()

    wrong = CanonicalEvidenceRecord(
        evidence_id=(
            source.evidence_id
        ),
        evidence_kind="OTHER",
        canonical_payload=(
            source.canonical_payload
        ),
    )

    with pytest.raises(
        BoundedInvestigationEvidenceError,
        match="evidence kind",
    ):
        bound_search_observation_evidence_record(
            wrong,
            max_payload_bytes=8192,
        )


@pytest.mark.parametrize(
    "limit",
    (
        0,
        -1,
        512,
        True,
    ),
)
def test_invalid_or_too_small_budget_is_rejected(
    limit,
) -> None:
    with pytest.raises(
        BoundedInvestigationEvidenceError,
    ):
        bound_search_observation_evidence_record(
            _source_record(),
            max_payload_bytes=limit,
        )


def test_derived_evidence_is_not_horizon_truth() -> None:
    record = (
        bound_search_observation_evidence_record(
            _source_record(),
            max_payload_bytes=65536,
        )
    )

    assert not isinstance(
        record,
        EvidenceBackedClaim,
    )

    assert not isinstance(
        record,
        EpistemicAssessment,
    )

    assert not isinstance(
        record,
        WorldModelAssertion,
    )
