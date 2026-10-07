"""Bounded model-facing context from executed investigation evidence.

CanonicalEvidenceRecord bodies remain Horizon's internal authority. This
module exposes only deterministic operational coordinates useful for choosing
the next typed repository operation.
"""

from __future__ import annotations

import base64
import binascii
import json

from dataclasses import dataclass

from horizon.investigation.evidence_records import (
    SEARCH_OBSERVATION_EVIDENCE_KIND,
    SYMBOL_OBSERVATION_EVIDENCE_KIND,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
)


MAX_VISIBLE_SEARCH_MATCHES = 20
MAX_SEARCH_LINE_CHARACTERS = 240
MAX_VISIBLE_DIRECT_DEFINITIONS = 16


class TypedPlannerOperationalEvidenceError(
    ValueError
):
    """Canonical operation evidence cannot produce a safe planning view."""


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerSearchMatchView:
    path: str
    line_number: int
    line_text: str
    line_text_truncated: bool


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerSearchObservationView:
    operation_kind: str
    query: str
    path_prefix: str | None

    match_count: int
    visible_match_count: int
    omitted_match_count: int

    matches: tuple[
        TypedPlannerSearchMatchView,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerDirectDefinitionView:
    kind: str
    name: str
    line_start: int
    line_end: int


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerSymbolObservationView:
    operation_kind: str
    path: str
    symbol: str

    definition_line_start: int
    definition_line_end: int

    direct_definition_count: int
    visible_direct_definition_count: int
    omitted_direct_definition_count: int

    direct_definitions: tuple[
        TypedPlannerDirectDefinitionView,
        ...,
    ]


TypedPlannerOperationalEvidenceView = (
    TypedPlannerSearchObservationView
    | TypedPlannerSymbolObservationView
)


def _require_dict(
    value: object,
    *,
    name: str,
) -> dict[str, object]:
    if not isinstance(
        value,
        dict,
    ):
        raise TypedPlannerOperationalEvidenceError(
            f"{name} must be an object"
        )

    return value


def _require_list(
    value: object,
    *,
    name: str,
) -> list[object]:
    if not isinstance(
        value,
        list,
    ):
        raise TypedPlannerOperationalEvidenceError(
            f"{name} must be a list"
        )

    return value


def _require_nonempty_text(
    value: object,
    *,
    name: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise TypedPlannerOperationalEvidenceError(
            f"{name} must be nonempty text"
        )

    return value


def _require_nonnegative_int(
    value: object,
    *,
    name: str,
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
        raise TypedPlannerOperationalEvidenceError(
            f"{name} must be a nonnegative integer"
        )

    return value


def _require_positive_int(
    value: object,
    *,
    name: str,
) -> int:
    result = _require_nonnegative_int(
        value,
        name=name,
    )

    if result == 0:
        raise TypedPlannerOperationalEvidenceError(
            f"{name} must be positive"
        )

    return result


def _payload(
    record: CanonicalEvidenceRecord,
) -> dict[str, object]:
    try:
        value = json.loads(
            record.canonical_payload
        )
    except (
        json.JSONDecodeError,
        TypeError,
    ) as exc:
        raise TypedPlannerOperationalEvidenceError(
            "recognized operation evidence payload must be valid JSON"
        ) from exc

    return _require_dict(
        value,
        name="operation evidence payload",
    )


def _search_view(
    record: CanonicalEvidenceRecord,
) -> TypedPlannerSearchObservationView:
    payload = _payload(
        record
    )

    if (
        payload.get(
            "operation_kind"
        )
        != "SEARCH_SOURCE"
    ):
        raise TypedPlannerOperationalEvidenceError(
            "search evidence operation kind is inconsistent"
        )

    query = _require_nonempty_text(
        payload.get(
            "query"
        ),
        name="search query",
    )

    path_prefix_value = (
        payload.get(
            "path_prefix"
        )
    )

    path_prefix = (
        None
        if path_prefix_value is None
        else _require_nonempty_text(
            path_prefix_value,
            name="search path prefix",
        )
    )

    match_count = _require_nonnegative_int(
        payload.get(
            "match_count"
        ),
        name="search match count",
    )

    matches = _require_list(
        payload.get(
            "matches"
        ),
        name="search matches",
    )

    if len(matches) != match_count:
        raise TypedPlannerOperationalEvidenceError(
            "search match count does not match payload"
        )

    visible = []

    for raw_match in matches[
        :MAX_VISIBLE_SEARCH_MATCHES
    ]:
        match = _require_dict(
            raw_match,
            name="search match",
        )

        path = _require_nonempty_text(
            match.get(
                "path"
            ),
            name="search match path",
        )

        line_number = _require_positive_int(
            match.get(
                "line_number"
            ),
            name="search match line number",
        )

        line_base64 = _require_nonempty_text(
            match.get(
                "line_base64"
            ),
            name="search match line bytes",
        )

        try:
            line_bytes = base64.b64decode(
                line_base64,
                validate=True,
            )
        except (
            binascii.Error,
            ValueError,
        ) as exc:
            raise TypedPlannerOperationalEvidenceError(
                "search match line bytes are not valid base64"
            ) from exc

        line_text = line_bytes.decode(
            "utf-8",
            errors="replace",
        )

        truncated = (
            len(line_text)
            > MAX_SEARCH_LINE_CHARACTERS
        )

        if truncated:
            line_text = line_text[
                :MAX_SEARCH_LINE_CHARACTERS
            ]

        visible.append(
            TypedPlannerSearchMatchView(
                path=path,
                line_number=line_number,
                line_text=line_text,
                line_text_truncated=truncated,
            )
        )

    visible_matches = tuple(
        visible
    )

    return TypedPlannerSearchObservationView(
        operation_kind="SEARCH_SOURCE",
        query=query,
        path_prefix=path_prefix,
        match_count=match_count,
        visible_match_count=len(
            visible_matches
        ),
        omitted_match_count=(
            match_count
            - len(
                visible_matches
            )
        ),
        matches=visible_matches,
    )


def _symbol_view(
    record: CanonicalEvidenceRecord,
) -> TypedPlannerSymbolObservationView:
    payload = _payload(
        record
    )

    if (
        payload.get(
            "operation_kind"
        )
        != "INSPECT_SYMBOL"
    ):
        raise TypedPlannerOperationalEvidenceError(
            "symbol evidence operation kind is inconsistent"
        )

    path = _require_nonempty_text(
        payload.get(
            "path"
        ),
        name="symbol path",
    )

    symbol = _require_nonempty_text(
        payload.get(
            "symbol"
        ),
        name="symbol name",
    )

    definition = _require_dict(
        payload.get(
            "definition"
        ),
        name="symbol definition",
    )

    definition_id = _require_nonempty_text(
        definition.get(
            "evidence_id"
        ),
        name="symbol definition evidence id",
    )

    definition_line_start = (
        _require_positive_int(
            definition.get(
                "line_start"
            ),
            name=(
                "symbol definition line start"
            ),
        )
    )

    definition_line_end = (
        _require_positive_int(
            definition.get(
                "line_end"
            ),
            name=(
                "symbol definition line end"
            ),
        )
    )

    if (
        definition_line_end
        < definition_line_start
    ):
        raise TypedPlannerOperationalEvidenceError(
            "symbol definition line end precedes line start"
        )

    fact_count = _require_nonnegative_int(
        payload.get(
            "fact_count"
        ),
        name="symbol fact count",
    )

    facts = _require_list(
        payload.get(
            "facts"
        ),
        name="symbol facts",
    )

    if len(facts) != fact_count:
        raise TypedPlannerOperationalEvidenceError(
            "symbol fact count does not match payload"
        )

    candidates = []

    for raw_fact in facts:
        fact = _require_dict(
            raw_fact,
            name="symbol structure fact",
        )

        if (
            fact.get(
                "structural_parent_id"
            )
            != definition_id
        ):
            continue

        kind = fact.get(
            "kind"
        )

        if kind not in {
            "FUNCTION_DEFINITION",
            "ASYNC_FUNCTION_DEFINITION",
            "CLASS_DEFINITION",
        }:
            continue

        assert isinstance(
            kind,
            str,
        )

        name = _require_nonempty_text(
            fact.get(
                "name"
            ),
            name="direct definition name",
        )

        line_start = _require_positive_int(
            fact.get(
                "line_start"
            ),
            name=(
                "direct definition line start"
            ),
        )

        line_end = _require_positive_int(
            fact.get(
                "line_end"
            ),
            name=(
                "direct definition line end"
            ),
        )

        if line_end < line_start:
            raise TypedPlannerOperationalEvidenceError(
                "direct definition line end precedes line start"
            )

        candidates.append(
            TypedPlannerDirectDefinitionView(
                kind=kind,
                name=name,
                line_start=line_start,
                line_end=line_end,
            )
        )

    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.line_start,
                item.line_end,
                item.kind,
                item.name,
            ),
        )
    )

    visible = ordered[
        :MAX_VISIBLE_DIRECT_DEFINITIONS
    ]

    return TypedPlannerSymbolObservationView(
        operation_kind="INSPECT_SYMBOL",
        path=path,
        symbol=symbol,
        definition_line_start=(
            definition_line_start
        ),
        definition_line_end=(
            definition_line_end
        ),
        direct_definition_count=len(
            ordered
        ),
        visible_direct_definition_count=(
            len(
                visible
            )
        ),
        omitted_direct_definition_count=(
            len(ordered)
            - len(visible)
        ),
        direct_definitions=visible,
    )


def project_typed_planner_operational_evidence(
    record: CanonicalEvidenceRecord,
) -> TypedPlannerOperationalEvidenceView | None:
    """Project bounded coordinates from recognized operation evidence."""

    if not isinstance(
        record,
        CanonicalEvidenceRecord,
    ):
        raise TypedPlannerOperationalEvidenceError(
            "record must be a CanonicalEvidenceRecord"
        )

    if (
        record.evidence_kind
        == SEARCH_OBSERVATION_EVIDENCE_KIND
    ):
        return _search_view(
            record
        )

    if (
        record.evidence_kind
        == SYMBOL_OBSERVATION_EVIDENCE_KIND
    ):
        return _symbol_view(
            record
        )

    return None
