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
    MAX_VISIBLE_DIRECT_DEFINITIONS,
    MAX_VISIBLE_SEARCH_MATCHES,
    TypedPlannerOperationalEvidenceError,
    TypedPlannerSearchObservationView,
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
