from __future__ import annotations

import base64
import copy
import json

from dataclasses import asdict

import pytest

from horizon.investigation.bounded_evidence import (
    BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND,
    bound_search_observation_evidence_record,
)
from horizon.investigation.typed_planner_operational_evidence import (
    MAX_SEARCH_LINE_CHARACTERS,
    MAX_SOURCE_LINE_CHARACTERS,
    MAX_VISIBLE_DIRECT_DEFINITIONS,
    MAX_VISIBLE_SEARCH_MATCHES,
    MAX_VISIBLE_SOURCE_LINES,
    TypedPlannerOperationalEvidenceError,
    TypedPlannerSearchObservationView,
    TypedPlannerSourceObservationView,
    TypedPlannerSymbolObservationView,
)
from horizon.investigation.typed_planner_request_view import (
    make_typed_planner_request_view,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)


SEARCH_KIND = (
    "INVESTIGATION_SEARCH_OBSERVATION"
)

SYMBOL_KIND = (
    "INVESTIGATION_SYMBOL_OBSERVATION"
)

SOURCE_KIND = (
    "INVESTIGATION_SOURCE_OBSERVATION"
)


def canonical(
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
        allow_nan=False,
    )


def record(
    *,
    identity: str,
    kind: str,
    payload: object,
) -> CanonicalEvidenceRecord:
    body = (
        payload
        if isinstance(
            payload,
            str,
        )
        else canonical(
            payload
        )
    )

    return CanonicalEvidenceRecord(
        evidence_id=identity,
        evidence_kind=kind,
        canonical_payload=body,
    )


def request(
    *records: CanonicalEvidenceRecord,
) -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary "
            "software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=tuple(
            item.evidence_id
            for item
            in records
        ),
        evidence_records=tuple(
            records
        ),
        request_id=(
            "semantic-gap-followup-investigation-request:test"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
        ),
        semantic_gap_section=(
            "WHAT_IT_IS"
        ),
    )


def search_payload(
    *,
    count: int,
) -> dict[str, object]:
    matches = []

    for index in range(
        count
    ):
        text = (
            "x" * 400
            if index == 0
            else (
                "source line "
                + str(index + 1)
            )
        )

        matches.append(
            {
                "evidence_id": (
                    "git-search-match:"
                    + str(index)
                ),
                "path": "README.md",
                "object_id": "a" * 40,
                "line_number": (
                    index + 1
                ),
                "line_base64": (
                    base64.b64encode(
                        text.encode(
                            "utf-8"
                        )
                    ).decode(
                        "ascii"
                    )
                ),
                "byte_start": index,
                "byte_end": (
                    index
                    + len(
                        text.encode(
                            "utf-8"
                        )
                    )
                ),
            }
        )

    return {
        "operation_kind": (
            "SEARCH_SOURCE"
        ),
        "observation_id": (
            "investigation-search-observation:test"
        ),
        "query": "workflow",
        "path_prefix": "README.md",
        "commit_sha": "b" * 40,
        "repository_observation_id": (
            "git-observation:test"
        ),
        "source_search_id": (
            "git-search:test"
        ),
        "match_count": count,
        "matches": matches,
    }


def fact(
    *,
    kind: str,
    name: str,
    identity: str,
    parent: str | None,
    line_start: int,
    line_end: int,
) -> dict[str, object]:
    return {
        "kind": kind,
        "name": name,
        "module": None,
        "alias": None,
        "callee_expression": (
            "target()"
            if kind == "CALL"
            else None
        ),
        "callee_byte_start": (
            0
            if kind == "CALL"
            else None
        ),
        "callee_byte_end": (
            8
            if kind == "CALL"
            else None
        ),
        "callee_evidence_id": (
            "python-callee-evidence:"
            + identity
            if kind == "CALL"
            else None
        ),
        "scope": [
            "Widget",
        ],
        "line_start": line_start,
        "line_end": line_end,
        "byte_start": (
            line_start * 10
        ),
        "byte_end": (
            line_end * 10
        ),
        "structural_parent_id": (
            parent
        ),
        "source_evidence_id": (
            "git-blob-evidence:test"
        ),
        "evidence_id": identity,
    }


def source_payload(
    *,
    count: int,
    identity: str = (
        "investigation-source-observation:test"
    ),
    start_line: int = 10,
    characters_per_line: int = 20,
    include_completeness: bool = True,
    reaches_eof: bool = True,
) -> dict[str, object]:
    end_line = (
        start_line
        + count
        - 1
    )

    lines = []

    for index in range(
        count
    ):
        line_number = (
            start_line
            + index
        )

        text = (
            "source line "
            + str(
                line_number
            )
            + " "
            + (
                "x"
                * characters_per_line
            )
        )

        lines.append(
            {
                "line_number": (
                    line_number
                ),
                "content_base64": (
                    base64.b64encode(
                        text.encode(
                            "utf-8"
                        )
                    ).decode(
                        "ascii"
                    )
                ),
            }
        )

    payload = {
        "operation_kind": (
            "READ_SOURCE"
        ),
        "observation_id": (
            identity
        ),
        "path": (
            "tests/test_repository_behavior.py"
        ),
        "start_line": (
            start_line
        ),
        "end_line": (
            end_line
        ),
        "commit_sha": (
            "b" * 40
        ),
        "repository_observation_id": (
            "git-observation:test"
        ),
        "source_blob_evidence_id": (
            "git-blob-evidence:test-source"
        ),
        "source_object_id": (
            "c" * 40
        ),
        "line_count": (
            count
        ),
        "lines": (
            lines
        ),
    }

    if include_completeness:
        observed_source_line_count = (
            end_line
            if reaches_eof
            else (
                end_line
                + 100
            )
        )

        payload[
            "observed_source_line_count"
        ] = (
            observed_source_line_count
        )

        payload[
            "ends_at_observed_eof"
        ] = (
            reaches_eof
        )

    return payload


def symbol_payload(
    *,
    direct_count: int,
    call_count: int,
) -> dict[str, object]:
    definition_id = (
        "python-structure-fact:class"
    )

    definition = fact(
        kind="CLASS_DEFINITION",
        name="Widget",
        identity=definition_id,
        parent=(
            "python-structure-fact:module"
        ),
        line_start=100,
        line_end=900,
    )

    definition[
        "scope"
    ] = []

    facts = [
        definition,
    ]

    for index in range(
        direct_count
    ):
        facts.append(
            fact(
                kind=(
                    "FUNCTION_DEFINITION"
                ),
                name=(
                    "method_"
                    + str(index)
                ),
                identity=(
                    "python-structure-fact:"
                    "method-"
                    + str(index)
                ),
                parent=definition_id,
                line_start=(
                    120
                    + index * 10
                ),
                line_end=(
                    125
                    + index * 10
                ),
            )
        )

    for index in range(
        call_count
    ):
        facts.append(
            fact(
                kind="CALL",
                name="call",
                identity=(
                    "python-structure-fact:"
                    "call-"
                    + str(index)
                ),
                parent=(
                    "python-structure-fact:"
                    "method-0"
                ),
                line_start=(
                    500
                    + index
                ),
                line_end=(
                    500
                    + index
                ),
            )
        )

    return {
        "operation_kind": (
            "INSPECT_SYMBOL"
        ),
        "observation_id": (
            "investigation-symbol-observation:test"
        ),
        "path": "src/widget.py",
        "symbol": "Widget",
        "commit_sha": "b" * 40,
        "repository_observation_id": (
            "git-observation:test"
        ),
        "source_blob_evidence_id": (
            "git-blob-evidence:test"
        ),
        "source_object_id": (
            "c" * 40
        ),
        "structure_analysis_id": (
            "python-structure-analysis:test"
        ),
        "definition": definition,
        "fact_count": len(
            facts
        ),
        "facts": facts,
    }


def test_search_evidence_exposes_bounded_operational_context() -> None:
    value = request(
        record(
            identity=(
                "investigation-search-observation:test"
            ),
            kind=SEARCH_KIND,
            payload=search_payload(
                count=25
            ),
        )
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    evidence = view.evidence_records[
        0
    ]

    context = (
        evidence.operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSearchObservationView,
    )

    assert context.query == "workflow"
    assert context.path_prefix == "README.md"
    assert context.match_count == 25

    assert (
        context.visible_match_count
        == MAX_VISIBLE_SEARCH_MATCHES
    )

    assert (
        context.omitted_match_count
        == 5
    )

    assert len(
        context.matches
    ) == MAX_VISIBLE_SEARCH_MATCHES

    assert (
        len(
            context.matches[
                0
            ].line_text
        )
        == MAX_SEARCH_LINE_CHARACTERS
    )

    assert (
        context.matches[
            0
        ].line_text_truncated
        is True
    )


def test_bounded_search_evidence_exposes_operational_context() -> None:
    complete = record(
        identity=(
            "investigation-search-observation:test"
        ),
        kind=SEARCH_KIND,
        payload=search_payload(
            count=25
        ),
    )

    bounded = (
        bound_search_observation_evidence_record(
            complete,
            max_payload_bytes=100_000,
        )
    )

    assert (
        bounded.evidence_kind
        == BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND
    )

    value = request(
        bounded
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    evidence = view.evidence_records[
        0
    ]

    context = (
        evidence.operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSearchObservationView,
    )

    assert context.query == "workflow"
    assert context.path_prefix == "README.md"

    assert (
        context.match_count
        == 25
    )

    assert (
        context.visible_match_count
        == MAX_VISIBLE_SEARCH_MATCHES
    )

    assert (
        context.omitted_match_count
        == 5
    )

    assert (
        len(
            context.matches
        )
        == MAX_VISIBLE_SEARCH_MATCHES
    )

    assert (
        context.matches[
            0
        ].path
        == "README.md"
    )

    assert (
        context.matches[
            0
        ].line_number
        == 1
    )



def test_source_evidence_exposes_bounded_semantic_context() -> None:
    count = 30

    value = request(
        record(
            identity=(
                "investigation-source-observation:test"
            ),
            kind=SOURCE_KIND,
            payload=source_payload(
                count=count,
            ),
        )
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    evidence = view.evidence_records[
        0
    ]

    context = (
        evidence.operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSourceObservationView,
    )

    assert (
        context.operation_kind
        == "READ_SOURCE"
    )

    assert (
        context.path
        == "tests/test_repository_behavior.py"
    )

    assert (
        context.start_line
        == 10
    )

    assert (
        context.end_line
        == 39
    )

    assert (
        context.line_count
        == count
    )

    assert (
        context.observed_source_line_count
        == 39
    )

    assert (
        context.ends_at_observed_eof
        is True
    )

    assert (
        context.selection_mode
        == "HEAD_TAIL"
    )

    assert (
        context.visible_line_count
        == MAX_VISIBLE_SOURCE_LINES
    )

    assert (
        context.omitted_line_count
        == (
            count
            - MAX_VISIBLE_SOURCE_LINES
        )
    )

    visible_numbers = tuple(
        line.line_number
        for line
        in context.lines
    )

    assert visible_numbers == (
        tuple(
            range(
                10,
                22,
            )
        )
        + tuple(
            range(
                28,
                40,
            )
        )
    )

    assert (
        context.lines[
            0
        ].line_text
        .startswith(
            "source line 10 "
        )
    )

    assert (
        context.lines[
            -1
        ].line_text
        .startswith(
            "source line 39 "
        )
    )


def test_small_source_read_exposes_all_lines() -> None:
    value = request(
        record(
            identity=(
                "investigation-source-observation:test"
            ),
            kind=SOURCE_KIND,
            payload=source_payload(
                count=5,
            ),
        )
    )

    context = (
        make_typed_planner_request_view(
            value
        )
        .evidence_records[
            0
        ]
        .operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSourceObservationView,
    )

    assert (
        context.selection_mode
        == "ALL"
    )

    assert (
        context.visible_line_count
        == 5
    )

    assert (
        context.omitted_line_count
        == 0
    )

    assert tuple(
        line.line_number
        for line
        in context.lines
    ) == (
        10,
        11,
        12,
        13,
        14,
    )


def test_source_semantic_lines_are_character_bounded() -> None:
    value = request(
        record(
            identity=(
                "investigation-source-observation:test"
            ),
            kind=SOURCE_KIND,
            payload=source_payload(
                count=2,
                characters_per_line=1000,
            ),
        )
    )

    context = (
        make_typed_planner_request_view(
            value
        )
        .evidence_records[
            0
        ]
        .operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSourceObservationView,
    )

    assert (
        len(
            context.lines[
                0
            ].line_text
        )
        == MAX_SOURCE_LINE_CHARACTERS
    )

    assert (
        context.lines[
            0
        ].line_text_truncated
        is True
    )


def test_legacy_source_evidence_without_eof_metadata_remains_visible() -> None:
    value = request(
        record(
            identity=(
                "investigation-source-observation:test"
            ),
            kind=SOURCE_KIND,
            payload=source_payload(
                count=3,
                include_completeness=False,
            ),
        )
    )

    context = (
        make_typed_planner_request_view(
            value
        )
        .evidence_records[
            0
        ]
        .operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSourceObservationView,
    )

    assert (
        context.observed_source_line_count
        is None
    )

    assert (
        context.ends_at_observed_eof
        is None
    )


def test_malformed_source_evidence_fails_closed() -> None:
    payload = source_payload(
        count=3,
    )

    payload[
        "lines"
    ][
        1
    ][
        "line_number"
    ] = 99

    value = request(
        record(
            identity=(
                "investigation-source-observation:test"
            ),
            kind=SOURCE_KIND,
            payload=payload,
        )
    )

    with pytest.raises(
        TypedPlannerOperationalEvidenceError,
        match="coordinates",
    ):
        make_typed_planner_request_view(
            value
        )


def test_large_source_body_does_not_scale_planner_view() -> None:
    large = record(
        identity=(
            "investigation-source-observation:test"
        ),
        kind=SOURCE_KIND,
        payload=source_payload(
            count=1000,
            characters_per_line=400,
        ),
    )

    value = request(
        large
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    model_view_bytes = len(
        canonical(
            asdict(
                view
            )
        ).encode(
            "utf-8"
        )
    )

    assert (
        len(
            large.canonical_payload
            .encode(
                "utf-8"
            )
        )
        > 400_000
    )

    assert (
        model_view_bytes
        < 15_000
    )

    context = (
        view.evidence_records[
            0
        ]
        .operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSourceObservationView,
    )

    assert (
        context.visible_line_count
        == MAX_VISIBLE_SOURCE_LINES
    )

    assert (
        context.omitted_line_count
        == (
            1000
            - MAX_VISIBLE_SOURCE_LINES
        )
    )


def test_source_operational_context_serializes_into_model_request_view() -> None:
    value = request(
        record(
            identity=(
                "investigation-source-observation:test"
            ),
            kind=SOURCE_KIND,
            payload=source_payload(
                count=4,
            ),
        )
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    payload = asdict(
        view
    )

    context = (
        payload[
            "evidence_records"
        ][
            0
        ][
            "operational_context"
        ]
    )

    assert (
        context[
            "operation_kind"
        ]
        == "READ_SOURCE"
    )

    assert (
        context[
            "path"
        ]
        == "tests/test_repository_behavior.py"
    )

    assert (
        context[
            "lines"
        ][
            0
        ][
            "line_text"
        ]
        .startswith(
            "source line 10 "
        )
    )

    assert (
        "canonical_payload"
        not in payload[
            "evidence_records"
        ][
            0
        ]
    )


def test_symbol_evidence_exposes_boundaries_not_bulk_facts() -> None:
    value = request(
        record(
            identity=(
                "investigation-symbol-observation:test"
            ),
            kind=SYMBOL_KIND,
            payload=symbol_payload(
                direct_count=20,
                call_count=100,
            ),
        )
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    evidence = view.evidence_records[
        0
    ]

    context = (
        evidence.operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSymbolObservationView,
    )

    assert context.path == "src/widget.py"
    assert context.symbol == "Widget"

    assert (
        context.definition_line_start
        == 100
    )

    assert (
        context.definition_line_end
        == 900
    )

    assert (
        context.direct_definition_count
        == 20
    )

    assert (
        context.visible_direct_definition_count
        == MAX_VISIBLE_DIRECT_DEFINITIONS
    )

    assert (
        context.omitted_direct_definition_count
        == 4
    )

    assert (
        context.direct_definitions[
            0
        ].name
        == "method_0"
    )

    assert not hasattr(
        evidence,
        "canonical_payload",
    )

    assert not hasattr(
        context,
        "facts",
    )


def test_unrecognized_evidence_remains_hash_and_size_only() -> None:
    value = request(
        record(
            identity="evidence:other",
            kind=(
                "GIT_BLOB_EVIDENCE"
            ),
            payload="x" * 100_000,
        )
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    evidence = view.evidence_records[
        0
    ]

    assert (
        evidence.operational_context
        is None
    )

    assert (
        evidence.canonical_payload_bytes
        == 100_000
    )


def test_recognized_malformed_operation_evidence_fails_closed() -> None:
    value = request(
        record(
            identity=(
                "investigation-search-observation:bad"
            ),
            kind=SEARCH_KIND,
            payload="not-json",
        )
    )

    with pytest.raises(
        TypedPlannerOperationalEvidenceError
    ):
        make_typed_planner_request_view(
            value
        )


def test_malformed_bounded_search_evidence_fails_closed() -> None:
    value = request(
        record(
            identity=(
                "bounded-investigation-search-evidence:bad"
            ),
            kind=(
                BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND
            ),
            payload="not-json",
        )
    )

    with pytest.raises(
        TypedPlannerOperationalEvidenceError
    ):
        make_typed_planner_request_view(
            value
        )



def test_hidden_symbol_body_change_changes_identity_but_not_projection() -> None:
    first_payload = symbol_payload(
        direct_count=2,
        call_count=2,
    )

    second_payload = copy.deepcopy(
        first_payload
    )

    second_payload[
        "facts"
    ][-1][
        "callee_expression"
    ] = "different_target()"

    first = make_typed_planner_request_view(
        request(
            record(
                identity=(
                    "investigation-symbol-observation:test"
                ),
                kind=SYMBOL_KIND,
                payload=first_payload,
            )
        )
    )

    second = make_typed_planner_request_view(
        request(
            record(
                identity=(
                    "investigation-symbol-observation:test"
                ),
                kind=SYMBOL_KIND,
                payload=second_payload,
            )
        )
    )

    assert (
        first.evidence_records[
            0
        ].operational_context
        == second.evidence_records[
            0
        ].operational_context
    )

    assert (
        first.evidence_records[
            0
        ].canonical_payload_sha256
        != second.evidence_records[
            0
        ].canonical_payload_sha256
    )

    assert (
        first.view_id
        != second.view_id
    )


def test_large_symbol_body_does_not_scale_model_view() -> None:
    large = record(
        identity=(
            "investigation-symbol-observation:large"
        ),
        kind=SYMBOL_KIND,
        payload=symbol_payload(
            direct_count=20,
            call_count=1500,
        ),
    )

    value = request(
        large
    )

    view = (
        make_typed_planner_request_view(
            value
        )
    )

    model_view_bytes = len(
        canonical(
            asdict(
                view
            )
        ).encode(
            "utf-8"
        )
    )

    assert (
        len(
            large.canonical_payload
            .encode(
                "utf-8"
            )
        )
        > model_view_bytes
    )

    assert (
        model_view_bytes
        < 25_000
    )

    context = (
        view.evidence_records[
            0
        ].operational_context
    )

    assert isinstance(
        context,
        TypedPlannerSymbolObservationView,
    )

    assert (
        context.visible_direct_definition_count
        == MAX_VISIBLE_DIRECT_DEFINITIONS
    )
