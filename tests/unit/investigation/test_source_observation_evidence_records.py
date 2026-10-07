from __future__ import annotations

import base64
import json

from dataclasses import replace

import pytest

from horizon.investigation.evidence_records import (
    SOURCE_OBSERVATION_EVIDENCE_KIND,
    InvestigationEvidenceRecordError,
    canonical_source_observation_evidence_record,
    canonical_source_observation_evidence_records,
)
from horizon.investigation.execution import (
    InvestigationSourceLine,
    InvestigationSourceObservation,
)


def observation(
    *,
    identity: str = (
        "investigation-source-observation:test"
    ),
    lines: tuple[
        InvestigationSourceLine,
        ...,
    ] | None = None,
) -> InvestigationSourceObservation:
    if lines is None:
        lines = (
            InvestigationSourceLine(
                line_number=10,
                content=b"alpha",
            ),
            InvestigationSourceLine(
                line_number=11,
                content=b"\xffbeta",
            ),
        )

    return InvestigationSourceObservation(
        path="src/acme.py",
        start_line=10,
        end_line=11,
        commit_sha=(
            "a" * 40
        ),
        repository_observation_id=(
            "git-observation:test"
        ),
        source_blob_evidence_id=(
            "git-blob-evidence:test"
        ),
        source_object_id=(
            "b" * 40
        ),
        lines=lines,
        observation_id=identity,
    )


def test_source_observation_becomes_exact_canonical_evidence() -> None:
    value = observation()

    record = (
        canonical_source_observation_evidence_record(
            value
        )
    )

    assert (
        record.evidence_id
        == value.observation_id
    )

    assert (
        record.evidence_kind
        == SOURCE_OBSERVATION_EVIDENCE_KIND
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert payload == {
        "commit_sha": (
            "a" * 40
        ),
        "end_line": 11,
        "line_count": 2,
        "lines": [
            {
                "content_base64": (
                    base64.b64encode(
                        b"alpha"
                    ).decode(
                        "ascii"
                    )
                ),
                "line_number": 10,
            },
            {
                "content_base64": (
                    base64.b64encode(
                        b"\xffbeta"
                    ).decode(
                        "ascii"
                    )
                ),
                "line_number": 11,
            },
        ],
        "observation_id": (
            "investigation-source-observation:test"
        ),
        "operation_kind": "READ_SOURCE",
        "path": "src/acme.py",
        "repository_observation_id": (
            "git-observation:test"
        ),
        "source_blob_evidence_id": (
            "git-blob-evidence:test"
        ),
        "source_object_id": (
            "b" * 40
        ),
        "start_line": 10,
    }


def test_source_payload_is_deterministic() -> None:
    first = (
        canonical_source_observation_evidence_record(
            observation()
        )
    )

    second = (
        canonical_source_observation_evidence_record(
            observation()
        )
    )

    assert first == second


def test_blank_source_line_is_preserved_exactly() -> None:
    value = observation(
        lines=(
            InvestigationSourceLine(
                line_number=10,
                content=b"",
            ),
            InvestigationSourceLine(
                line_number=11,
                content=b"next",
            ),
        )
    )

    record = (
        canonical_source_observation_evidence_record(
            value
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert (
        payload[
            "lines"
        ][0][
            "content_base64"
        ]
        == ""
    )


def test_wrong_observation_type_is_rejected() -> None:
    with pytest.raises(
        InvestigationEvidenceRecordError,
        match=(
            "InvestigationSourceObservation"
        ),
    ):
        canonical_source_observation_evidence_record(
            object()
        )


@pytest.mark.parametrize(
    (
        "field",
        "value",
    ),
    [
        (
            "observation_id",
            "",
        ),
        (
            "path",
            "",
        ),
        (
            "commit_sha",
            "",
        ),
        (
            "repository_observation_id",
            "",
        ),
        (
            "source_blob_evidence_id",
            "",
        ),
        (
            "source_object_id",
            "",
        ),
    ],
)
def test_required_textual_provenance_is_rejected_when_empty(
    field: str,
    value: str,
) -> None:
    item = replace(
        observation(),
        **{
            field: value,
        },
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
    ):
        canonical_source_observation_evidence_record(
            item
        )


@pytest.mark.parametrize(
    (
        "start_line",
        "end_line",
    ),
    [
        (
            0,
            11,
        ),
        (
            -1,
            11,
        ),
        (
            10,
            0,
        ),
        (
            12,
            11,
        ),
    ],
)
def test_invalid_read_window_is_rejected(
    start_line: int,
    end_line: int,
) -> None:
    item = replace(
        observation(),
        start_line=start_line,
        end_line=end_line,
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="line",
    ):
        canonical_source_observation_evidence_record(
            item
        )


def test_lines_must_be_a_tuple() -> None:
    item = replace(
        observation(),
        lines=[
            InvestigationSourceLine(
                line_number=10,
                content=b"alpha",
            ),
            InvestigationSourceLine(
                line_number=11,
                content=b"beta",
            ),
        ],
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="tuple",
    ):
        canonical_source_observation_evidence_record(
            item
        )


def test_read_window_requires_exact_number_of_lines() -> None:
    item = replace(
        observation(),
        lines=(
            InvestigationSourceLine(
                line_number=10,
                content=b"alpha",
            ),
        ),
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="line window",
    ):
        canonical_source_observation_evidence_record(
            item
        )


def test_read_lines_must_match_exact_requested_coordinates() -> None:
    item = replace(
        observation(),
        lines=(
            InvestigationSourceLine(
                line_number=10,
                content=b"alpha",
            ),
            InvestigationSourceLine(
                line_number=12,
                content=b"beta",
            ),
        ),
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="coordinates",
    ):
        canonical_source_observation_evidence_record(
            item
        )


def test_source_line_must_have_bytes_content() -> None:
    item = replace(
        observation(),
        lines=(
            InvestigationSourceLine(
                line_number=10,
                content="alpha",
            ),
            InvestigationSourceLine(
                line_number=11,
                content=b"beta",
            ),
        ),
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="bytes",
    ):
        canonical_source_observation_evidence_record(
            item
        )


def test_batch_preserves_all_source_observations() -> None:
    first = observation(
        identity=(
            "investigation-source-observation:first"
        )
    )

    second = replace(
        observation(
            identity=(
                "investigation-source-observation:second"
            )
        ),
        path="README.md",
        start_line=20,
        end_line=21,
        lines=(
            InvestigationSourceLine(
                line_number=20,
                content=b"one",
            ),
            InvestigationSourceLine(
                line_number=21,
                content=b"two",
            ),
        ),
    )

    records = (
        canonical_source_observation_evidence_records(
            (
                first,
                second,
            )
        )
    )

    assert tuple(
        record.evidence_id
        for record
        in records
    ) == (
        first.observation_id,
        second.observation_id,
    )

    assert all(
        record.evidence_kind
        == SOURCE_OBSERVATION_EVIDENCE_KIND
        for record
        in records
    )


def test_batch_requires_tuple() -> None:
    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="tuple",
    ):
        canonical_source_observation_evidence_records(
            []
        )


def test_batch_rejects_duplicate_observation_identity() -> None:
    first = observation()

    second = replace(
        first,
        path="README.md",
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="duplicate",
    ):
        canonical_source_observation_evidence_records(
            (
                first,
                second,
            )
        )
