from __future__ import annotations

import json

import pytest

from horizon.investigation.evidence_records import (
    InvestigationEvidenceRecordError,
    SYMBOL_OBSERVATION_EVIDENCE_KIND,
    canonical_symbol_observation_evidence_record,
    canonical_symbol_observation_evidence_records,
)
from horizon.investigation.execution import (
    InvestigationSymbolObservation,
)
from horizon.languages.python.structure import (
    PythonStructureFact,
    PythonStructureKind,
)


def structure_fact(
    *,
    kind: str,
    name: str,
    scope: tuple[str, ...],
    line_start: int,
    line_end: int,
    byte_start: int,
    byte_end: int,
    evidence_id: str,
    structural_parent_id: str | None,
) -> PythonStructureFact:
    return PythonStructureFact(
        kind=PythonStructureKind(
            kind
        ),
        name=name,
        module=None,
        alias=None,
        callee_expression=None,
        callee_byte_start=None,
        callee_byte_end=None,
        callee_evidence_id=None,
        scope=scope,
        line_start=line_start,
        line_end=line_end,
        byte_start=byte_start,
        byte_end=byte_end,
        structural_parent_id=(
            structural_parent_id
        ),
        source_evidence_id=(
            "git-blob-evidence:test"
        ),
        evidence_id=evidence_id,
    )


def observation(
    *,
    observation_id: str = (
        "investigation-symbol-observation:test"
    ),
) -> InvestigationSymbolObservation:
    definition = structure_fact(
        kind="CLASS_DEFINITION",
        name="Widget",
        scope=(),
        line_start=10,
        line_end=40,
        byte_start=100,
        byte_end=500,
        evidence_id=(
            "python-structure-fact:class"
        ),
        structural_parent_id=(
            "python-structure-fact:module"
        ),
    )

    method = structure_fact(
        kind="FUNCTION_DEFINITION",
        name="run",
        scope=(
            "Widget",
        ),
        line_start=20,
        line_end=30,
        byte_start=200,
        byte_end=350,
        evidence_id=(
            "python-structure-fact:method"
        ),
        structural_parent_id=(
            definition.evidence_id
        ),
    )

    return InvestigationSymbolObservation(
        path="src/widget.py",
        symbol="Widget",
        commit_sha="a" * 40,
        repository_observation_id=(
            "git-commit-observation:test"
        ),
        source_blob_evidence_id=(
            "git-blob-evidence:test"
        ),
        source_object_id=(
            "b" * 40
        ),
        structure_analysis_id=(
            "python-structure-analysis:test"
        ),
        definition=definition,
        facts=(
            definition,
            method,
        ),
        observation_id=(
            observation_id
        ),
    )


def test_symbol_observation_becomes_canonical_evidence() -> None:
    value = observation()

    result = (
        canonical_symbol_observation_evidence_record(
            value
        )
    )

    assert (
        result.evidence_id
        == value.observation_id
    )

    assert (
        result.evidence_kind
        == SYMBOL_OBSERVATION_EVIDENCE_KIND
    )

    payload = json.loads(
        result.canonical_payload
    )

    assert payload[
        "operation_kind"
    ] == "INSPECT_SYMBOL"

    assert payload[
        "observation_id"
    ] == value.observation_id

    assert payload[
        "path"
    ] == "src/widget.py"

    assert payload[
        "symbol"
    ] == "Widget"

    assert payload[
        "commit_sha"
    ] == "a" * 40

    assert payload[
        "repository_observation_id"
    ] == "git-commit-observation:test"

    assert payload[
        "source_blob_evidence_id"
    ] == "git-blob-evidence:test"

    assert payload[
        "source_object_id"
    ] == "b" * 40

    assert payload[
        "structure_analysis_id"
    ] == "python-structure-analysis:test"


def test_definition_is_preserved_losslessly() -> None:
    result = (
        canonical_symbol_observation_evidence_record(
            observation()
        )
    )

    payload = json.loads(
        result.canonical_payload
    )

    definition = payload[
        "definition"
    ]

    assert definition == {
        "kind": "CLASS_DEFINITION",
        "name": "Widget",
        "module": None,
        "alias": None,
        "callee_expression": None,
        "callee_byte_start": None,
        "callee_byte_end": None,
        "callee_evidence_id": None,
        "scope": [],
        "line_start": 10,
        "line_end": 40,
        "byte_start": 100,
        "byte_end": 500,
        "structural_parent_id": (
            "python-structure-fact:module"
        ),
        "source_evidence_id": (
            "git-blob-evidence:test"
        ),
        "evidence_id": (
            "python-structure-fact:class"
        ),
    }


def test_all_structural_facts_are_preserved() -> None:
    result = (
        canonical_symbol_observation_evidence_record(
            observation()
        )
    )

    payload = json.loads(
        result.canonical_payload
    )

    assert payload[
        "fact_count"
    ] == 2

    assert len(
        payload[
            "facts"
        ]
    ) == 2

    assert payload[
        "facts"
    ][0][
        "evidence_id"
    ] == "python-structure-fact:class"

    assert payload[
        "facts"
    ][1] == {
        "kind": "FUNCTION_DEFINITION",
        "name": "run",
        "module": None,
        "alias": None,
        "callee_expression": None,
        "callee_byte_start": None,
        "callee_byte_end": None,
        "callee_evidence_id": None,
        "scope": [
            "Widget",
        ],
        "line_start": 20,
        "line_end": 30,
        "byte_start": 200,
        "byte_end": 350,
        "structural_parent_id": (
            "python-structure-fact:class"
        ),
        "source_evidence_id": (
            "git-blob-evidence:test"
        ),
        "evidence_id": (
            "python-structure-fact:method"
        ),
    }


def test_canonicalization_is_deterministic() -> None:
    value = observation()

    first = (
        canonical_symbol_observation_evidence_record(
            value
        )
    )

    second = (
        canonical_symbol_observation_evidence_record(
            value
        )
    )

    assert first == second


def test_plural_bridge_preserves_order() -> None:
    first = observation(
        observation_id=(
            "investigation-symbol-observation:first"
        )
    )

    second = observation(
        observation_id=(
            "investigation-symbol-observation:second"
        )
    )

    results = (
        canonical_symbol_observation_evidence_records(
            (
                first,
                second,
            )
        )
    )

    assert [
        item.evidence_id
        for item
        in results
    ] == [
        first.observation_id,
        second.observation_id,
    ]


def test_plural_bridge_rejects_duplicate_observations() -> None:
    value = observation()

    with pytest.raises(
        InvestigationEvidenceRecordError
    ):
        canonical_symbol_observation_evidence_records(
            (
                value,
                value,
            )
        )


def test_plural_bridge_requires_tuple() -> None:
    value = observation()

    with pytest.raises(
        InvestigationEvidenceRecordError
    ):
        canonical_symbol_observation_evidence_records(
            [value]  # type: ignore[arg-type]
        )


def test_single_bridge_rejects_wrong_type() -> None:
    with pytest.raises(
        InvestigationEvidenceRecordError
    ):
        canonical_symbol_observation_evidence_record(
            object()  # type: ignore[arg-type]
        )
