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

from horizon.investigation.bounded_evidence import (
    BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND,
)
from horizon.investigation.evidence_records import (
    SEARCH_OBSERVATION_EVIDENCE_KIND,
    SOURCE_OBSERVATION_EVIDENCE_KIND,
    SYMBOL_OBSERVATION_EVIDENCE_KIND,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
)


MAX_VISIBLE_SEARCH_MATCHES = 20
MAX_SEARCH_LINE_CHARACTERS = 240

MAX_VISIBLE_SOURCE_LINES = 24
MAX_SOURCE_LINE_CHARACTERS = 240

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
class TypedPlannerSourceLineView:
    line_number: int
    line_text: str
    line_text_truncated: bool


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerSourceObservationView:
    operation_kind: str

    path: str
    start_line: int
    end_line: int
    line_count: int

    observed_source_line_count: int | None
    ends_at_observed_eof: bool | None

    selection_mode: str
    visible_line_count: int
    omitted_line_count: int

    lines: tuple[
        TypedPlannerSourceLineView,
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
    | TypedPlannerSourceObservationView
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


def _search_matches(
    record: CanonicalEvidenceRecord,
    payload: dict[str, object],
) -> tuple[
    int,
    list[object],
]:
    if (
        record.evidence_kind
        == SEARCH_OBSERVATION_EVIDENCE_KIND
    ):
        match_count = (
            _require_nonnegative_int(
                payload.get(
                    "match_count"
                ),
                name="search match count",
            )
        )

        matches = _require_list(
            payload.get(
                "matches"
            ),
            name="search matches",
        )

        if (
            len(
                matches
            )
            != match_count
        ):
            raise TypedPlannerOperationalEvidenceError(
                "search match count does not match payload"
            )

        return (
            match_count,
            matches,
        )

    if (
        record.evidence_kind
        == BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND
    ):
        if (
            payload.get(
                "source_evidence_kind"
            )
            != SEARCH_OBSERVATION_EVIDENCE_KIND
        ):
            raise TypedPlannerOperationalEvidenceError(
                "bounded search source evidence kind is inconsistent"
            )

        _require_nonempty_text(
            payload.get(
                "source_evidence_id"
            ),
            name="bounded search source evidence id",
        )

        total_match_count = (
            _require_nonnegative_int(
                payload.get(
                    "total_match_count"
                ),
                name="bounded search total match count",
            )
        )

        selected_match_count = (
            _require_nonnegative_int(
                payload.get(
                    "selected_match_count"
                ),
                name="bounded search selected match count",
            )
        )

        bounded_omitted_count = (
            _require_nonnegative_int(
                payload.get(
                    "omitted_match_count"
                ),
                name="bounded search omitted match count",
            )
        )

        matches = _require_list(
            payload.get(
                "selected_matches"
            ),
            name="bounded search selected matches",
        )

        if (
            len(
                matches
            )
            != selected_match_count
        ):
            raise TypedPlannerOperationalEvidenceError(
                "bounded search selected match count "
                "does not match payload"
            )

        if (
            selected_match_count
            + bounded_omitted_count
            != total_match_count
        ):
            raise TypedPlannerOperationalEvidenceError(
                "bounded search total match count "
                "does not match selected plus omitted"
            )

        return (
            total_match_count,
            matches,
        )

    raise TypedPlannerOperationalEvidenceError(
        "search evidence kind is not recognized"
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

    (
        match_count,
        matches,
    ) = _search_matches(
        record,
        payload,
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


def _source_view(
    record: CanonicalEvidenceRecord,
) -> TypedPlannerSourceObservationView:
    payload = _payload(
        record
    )

    if (
        payload.get(
            "operation_kind"
        )
        != "READ_SOURCE"
    ):
        raise TypedPlannerOperationalEvidenceError(
            "source evidence operation kind is inconsistent"
        )

    if (
        payload.get(
            "observation_id"
        )
        != record.evidence_id
    ):
        raise TypedPlannerOperationalEvidenceError(
            "source observation identity is inconsistent"
        )

    path = _require_nonempty_text(
        payload.get(
            "path"
        ),
        name="source path",
    )

    start_line = _require_positive_int(
        payload.get(
            "start_line"
        ),
        name="source start line",
    )

    end_line = _require_positive_int(
        payload.get(
            "end_line"
        ),
        name="source end line",
    )

    if (
        end_line
        < start_line
    ):
        raise TypedPlannerOperationalEvidenceError(
            "source end line precedes start line"
        )

    line_count = _require_positive_int(
        payload.get(
            "line_count"
        ),
        name="source line count",
    )

    expected_line_count = (
        end_line
        - start_line
        + 1
    )

    if (
        line_count
        != expected_line_count
    ):
        raise TypedPlannerOperationalEvidenceError(
            "source line count does not match coordinates"
        )

    observed_source_line_count = (
        payload.get(
            "observed_source_line_count"
        )
    )

    ends_at_observed_eof = (
        payload.get(
            "ends_at_observed_eof"
        )
    )

    if (
        observed_source_line_count
        is None
    ) != (
        ends_at_observed_eof
        is None
    ):
        raise TypedPlannerOperationalEvidenceError(
            "source completeness metadata must be "
            "present or absent as one unit"
        )

    if (
        observed_source_line_count
        is not None
    ):
        observed_source_line_count = (
            _require_positive_int(
                observed_source_line_count,
                name=(
                    "observed source line count"
                ),
            )
        )

        if (
            observed_source_line_count
            < end_line
        ):
            raise TypedPlannerOperationalEvidenceError(
                "observed source line count "
                "precedes source read end"
            )

        if not isinstance(
            ends_at_observed_eof,
            bool,
        ):
            raise TypedPlannerOperationalEvidenceError(
                "ends_at_observed_eof must be boolean"
            )

        if (
            ends_at_observed_eof
            != (
                end_line
                == observed_source_line_count
            )
        ):
            raise TypedPlannerOperationalEvidenceError(
                "source EOF metadata is inconsistent"
            )

    raw_lines = _require_list(
        payload.get(
            "lines"
        ),
        name="source lines",
    )

    if (
        len(
            raw_lines
        )
        != line_count
    ):
        raise TypedPlannerOperationalEvidenceError(
            "source line array does not match line count"
        )

    if (
        line_count
        <= MAX_VISIBLE_SOURCE_LINES
    ):
        selected_indexes = tuple(
            range(
                line_count
            )
        )

        selection_mode = "ALL"

    else:
        head_count = (
            MAX_VISIBLE_SOURCE_LINES
            // 2
        )

        tail_count = (
            MAX_VISIBLE_SOURCE_LINES
            - head_count
        )

        selected_indexes = (
            tuple(
                range(
                    head_count
                )
            )
            + tuple(
                range(
                    line_count
                    - tail_count,
                    line_count,
                )
            )
        )

        selection_mode = "HEAD_TAIL"

    selected_index_set = set(
        selected_indexes
    )

    visible = []

    for index, raw_line in enumerate(
        raw_lines
    ):
        line = _require_dict(
            raw_line,
            name="source line",
        )

        expected_line_number = (
            start_line
            + index
        )

        if (
            line.get(
                "line_number"
            )
            != expected_line_number
        ):
            raise TypedPlannerOperationalEvidenceError(
                "source line coordinates are not contiguous"
            )

        encoded = line.get(
            "content_base64"
        )

        if not isinstance(
            encoded,
            str,
        ):
            raise TypedPlannerOperationalEvidenceError(
                "source line bytes must be base64 text"
            )

        try:
            line_bytes = base64.b64decode(
                encoded,
                validate=True,
            )
        except (
            binascii.Error,
            ValueError,
        ) as exc:
            raise TypedPlannerOperationalEvidenceError(
                "source line bytes are not valid base64"
            ) from exc

        line_text = line_bytes.decode(
            "utf-8",
            errors="replace",
        )

        if (
            index
            not in selected_index_set
        ):
            continue

        truncated = (
            len(
                line_text
            )
            > MAX_SOURCE_LINE_CHARACTERS
        )

        if truncated:
            line_text = line_text[
                :MAX_SOURCE_LINE_CHARACTERS
            ]

        visible.append(
            TypedPlannerSourceLineView(
                line_number=(
                    expected_line_number
                ),
                line_text=(
                    line_text
                ),
                line_text_truncated=(
                    truncated
                ),
            )
        )

    visible_lines = tuple(
        visible
    )

    if (
        len(
            visible_lines
        )
        != len(
            selected_indexes
        )
    ):
        raise TypedPlannerOperationalEvidenceError(
            "source visibility projection is inconsistent"
        )

    return TypedPlannerSourceObservationView(
        operation_kind="READ_SOURCE",
        path=path,
        start_line=start_line,
        end_line=end_line,
        line_count=line_count,
        observed_source_line_count=(
            observed_source_line_count
        ),
        ends_at_observed_eof=(
            ends_at_observed_eof
        ),
        selection_mode=(
            selection_mode
        ),
        visible_line_count=(
            len(
                visible_lines
            )
        ),
        omitted_line_count=(
            line_count
            - len(
                visible_lines
            )
        ),
        lines=visible_lines,
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
        in {
            SEARCH_OBSERVATION_EVIDENCE_KIND,
            BOUNDED_SEARCH_OBSERVATION_EVIDENCE_KIND,
        }
    ):
        return _search_view(
            record
        )

    if (
        record.evidence_kind
        == SOURCE_OBSERVATION_EVIDENCE_KIND
    ):
        return _source_view(
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
