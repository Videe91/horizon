"""Canonical investigator evidence records from executed operations.

Typed investigation execution produces observations, not Horizon truth.

This module bridges those immutable observations back into the
investigator evidence vocabulary so a later investigation round can
reason from evidence gathered by an earlier round.

No claim, epistemic assessment, or world-model assertion is created here.
"""

from __future__ import annotations

import base64
import json

from horizon.investigation.execution import (
    InvestigationSearchObservation,
    InvestigationSymbolObservation,
)
from horizon.languages.python.structure import (
    PythonStructureFact,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
)
from horizon.repository.git_search import (
    GitTextMatch,
)


class InvestigationEvidenceRecordError(
    ValueError
):
    """Executed investigation evidence cannot be represented faithfully."""


SEARCH_OBSERVATION_EVIDENCE_KIND = (
    "INVESTIGATION_SEARCH_OBSERVATION"
)

SYMBOL_OBSERVATION_EVIDENCE_KIND = (
    "INVESTIGATION_SYMBOL_OBSERVATION"
)


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
        raise InvestigationEvidenceRecordError(
            f"{name} must be nonempty"
        )

    return value


def _match_payload(
    match: GitTextMatch,
) -> dict[
    str,
    object,
]:
    if not isinstance(
        match,
        GitTextMatch,
    ):
        raise InvestigationEvidenceRecordError(
            "search observation matches must be GitTextMatch values"
        )

    _require_nonempty_text(
        match.evidence_id,
        name="match evidence id",
    )

    _require_nonempty_text(
        match.path,
        name="match path",
    )

    _require_nonempty_text(
        match.object_id,
        name="match object id",
    )

    if (
        isinstance(
            match.line_number,
            bool,
        )
        or not isinstance(
            match.line_number,
            int,
        )
        or match.line_number <= 0
    ):
        raise InvestigationEvidenceRecordError(
            "match line number must be positive"
        )

    if not isinstance(
        match.line,
        bytes,
    ):
        raise InvestigationEvidenceRecordError(
            "match line must be bytes"
        )

    for name, value in (
        (
            "match byte start",
            match.byte_start,
        ),
        (
            "match byte end",
            match.byte_end,
        ),
    ):
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
            raise InvestigationEvidenceRecordError(
                f"{name} must be nonnegative"
            )

    if (
        match.byte_end
        < match.byte_start
    ):
        raise InvestigationEvidenceRecordError(
            "match byte end must not precede byte start"
        )

    return {
        "evidence_id": (
            match.evidence_id
        ),
        "path": match.path,
        "object_id": (
            match.object_id
        ),
        "line_number": (
            match.line_number
        ),
        "line_base64": (
            base64.b64encode(
                match.line
            ).decode(
                "ascii"
            )
        ),
        "byte_start": (
            match.byte_start
        ),
        "byte_end": (
            match.byte_end
        ),
    }


def canonical_search_observation_evidence_record(
    observation: InvestigationSearchObservation,
) -> CanonicalEvidenceRecord:
    """Represent one exact SEARCH_SOURCE observation as canonical evidence."""

    if not isinstance(
        observation,
        InvestigationSearchObservation,
    ):
        raise InvestigationEvidenceRecordError(
            "observation must be an InvestigationSearchObservation"
        )

    _require_nonempty_text(
        observation.observation_id,
        name="observation id",
    )

    _require_nonempty_text(
        observation.query,
        name="search query",
    )

    if (
        observation.path_prefix
        is not None
    ):
        _require_nonempty_text(
            observation.path_prefix,
            name="search path prefix",
        )

    _require_nonempty_text(
        observation.commit_sha,
        name="commit sha",
    )

    _require_nonempty_text(
        observation.repository_observation_id,
        name="repository observation id",
    )

    _require_nonempty_text(
        observation.source_search_id,
        name="source search id",
    )

    match_ids = tuple(
        match.evidence_id
        for match
        in observation.matches
    )

    if (
        len(
            match_ids
        )
        != len(
            set(
                match_ids
            )
        )
    ):
        raise InvestigationEvidenceRecordError(
            "search observation contains duplicate match evidence ids"
        )

    payload = {
        "operation_kind": (
            "SEARCH_SOURCE"
        ),
        "observation_id": (
            observation.observation_id
        ),
        "query": (
            observation.query
        ),
        "path_prefix": (
            observation.path_prefix
        ),
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.repository_observation_id
        ),
        "source_search_id": (
            observation.source_search_id
        ),
        "match_count": len(
            observation.matches
        ),
        "matches": [
            _match_payload(
                match
            )
            for match
            in observation.matches
        ],
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
            observation.observation_id
        ),
        evidence_kind=(
            SEARCH_OBSERVATION_EVIDENCE_KIND
        ),
        canonical_payload=(
            canonical_payload
        ),
    )


def canonical_search_observation_evidence_records(
    observations: tuple[
        InvestigationSearchObservation,
        ...,
    ],
) -> tuple[
    CanonicalEvidenceRecord,
    ...,
]:
    """Represent several exact search observations without collapsing them."""

    if not isinstance(
        observations,
        tuple,
    ):
        raise InvestigationEvidenceRecordError(
            "observations must be a tuple"
        )

    observation_ids = tuple(
        observation.observation_id
        if isinstance(
            observation,
            InvestigationSearchObservation,
        )
        else None
        for observation
        in observations
    )

    if (
        len(
            observation_ids
        )
        != len(
            set(
                observation_ids
            )
        )
    ):
        raise InvestigationEvidenceRecordError(
            "observations contain duplicate identities"
        )

    return tuple(
        canonical_search_observation_evidence_record(
            observation
        )
        for observation
        in observations
    )


def _structure_fact_payload(
    fact: PythonStructureFact,
) -> dict[
    str,
    object,
]:
    if not isinstance(
        fact,
        PythonStructureFact,
    ):
        raise InvestigationEvidenceRecordError(
            "symbol observation facts must be PythonStructureFact values"
        )

    _require_nonempty_text(
        fact.evidence_id,
        name="structure fact evidence id",
    )

    _require_nonempty_text(
        fact.source_evidence_id,
        name="structure fact source evidence id",
    )

    _require_nonempty_text(
        fact.name,
        name="structure fact name",
    )

    kind_value = getattr(
        fact.kind,
        "value",
        None,
    )

    if (
        not isinstance(
            kind_value,
            str,
        )
        or not kind_value
    ):
        raise InvestigationEvidenceRecordError(
            "structure fact kind must expose nonempty text"
        )

    for name, value in (
        (
            "structure fact line start",
            fact.line_start,
        ),
        (
            "structure fact line end",
            fact.line_end,
        ),
        (
            "structure fact byte start",
            fact.byte_start,
        ),
        (
            "structure fact byte end",
            fact.byte_end,
        ),
    ):
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
            raise InvestigationEvidenceRecordError(
                f"{name} must be a nonnegative integer"
            )

    if fact.line_start <= 0:
        raise InvestigationEvidenceRecordError(
            "structure fact line start must be positive"
        )

    if fact.line_end < fact.line_start:
        raise InvestigationEvidenceRecordError(
            "structure fact line end must not precede line start"
        )

    if fact.byte_end < fact.byte_start:
        raise InvestigationEvidenceRecordError(
            "structure fact byte end must not precede byte start"
        )

    return {
        "kind": kind_value,
        "name": fact.name,
        "module": fact.module,
        "alias": fact.alias,
        "callee_expression": (
            fact.callee_expression
        ),
        "callee_byte_start": (
            fact.callee_byte_start
        ),
        "callee_byte_end": (
            fact.callee_byte_end
        ),
        "callee_evidence_id": (
            fact.callee_evidence_id
        ),
        "scope": list(
            fact.scope
        ),
        "line_start": (
            fact.line_start
        ),
        "line_end": (
            fact.line_end
        ),
        "byte_start": (
            fact.byte_start
        ),
        "byte_end": (
            fact.byte_end
        ),
        "structural_parent_id": (
            fact.structural_parent_id
        ),
        "source_evidence_id": (
            fact.source_evidence_id
        ),
        "evidence_id": (
            fact.evidence_id
        ),
    }


def canonical_symbol_observation_evidence_record(
    observation: InvestigationSymbolObservation,
) -> CanonicalEvidenceRecord:
    """Represent one exact INSPECT_SYMBOL observation as canonical evidence."""

    if not isinstance(
        observation,
        InvestigationSymbolObservation,
    ):
        raise InvestigationEvidenceRecordError(
            "observation must be an InvestigationSymbolObservation"
        )

    for name, value in (
        (
            "observation id",
            observation.observation_id,
        ),
        (
            "symbol path",
            observation.path,
        ),
        (
            "symbol name",
            observation.symbol,
        ),
        (
            "commit sha",
            observation.commit_sha,
        ),
        (
            "repository observation id",
            observation.repository_observation_id,
        ),
        (
            "source blob evidence id",
            observation.source_blob_evidence_id,
        ),
        (
            "source object id",
            observation.source_object_id,
        ),
        (
            "structure analysis id",
            observation.structure_analysis_id,
        ),
    ):
        _require_nonempty_text(
            value,
            name=name,
        )

    if not isinstance(
        observation.definition,
        PythonStructureFact,
    ):
        raise InvestigationEvidenceRecordError(
            "symbol observation definition must be a PythonStructureFact"
        )

    if not isinstance(
        observation.facts,
        tuple,
    ):
        raise InvestigationEvidenceRecordError(
            "symbol observation facts must be a tuple"
        )

    if not observation.facts:
        raise InvestigationEvidenceRecordError(
            "symbol observation facts must not be empty"
        )

    fact_ids = tuple(
        fact.evidence_id
        if isinstance(
            fact,
            PythonStructureFact,
        )
        else None
        for fact
        in observation.facts
    )

    if len(
        fact_ids
    ) != len(
        set(
            fact_ids
        )
    ):
        raise InvestigationEvidenceRecordError(
            "symbol observation contains duplicate structure fact identities"
        )

    if (
        observation.definition.evidence_id
        not in fact_ids
    ):
        raise InvestigationEvidenceRecordError(
            "symbol observation facts do not contain its definition"
        )

    payload = {
        "operation_kind": (
            "INSPECT_SYMBOL"
        ),
        "observation_id": (
            observation.observation_id
        ),
        "path": observation.path,
        "symbol": observation.symbol,
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.repository_observation_id
        ),
        "source_blob_evidence_id": (
            observation.source_blob_evidence_id
        ),
        "source_object_id": (
            observation.source_object_id
        ),
        "structure_analysis_id": (
            observation.structure_analysis_id
        ),
        "definition": (
            _structure_fact_payload(
                observation.definition
            )
        ),
        "fact_count": len(
            observation.facts
        ),
        "facts": [
            _structure_fact_payload(
                fact
            )
            for fact
            in observation.facts
        ],
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
            observation.observation_id
        ),
        evidence_kind=(
            SYMBOL_OBSERVATION_EVIDENCE_KIND
        ),
        canonical_payload=(
            canonical_payload
        ),
    )


def canonical_symbol_observation_evidence_records(
    observations: tuple[
        InvestigationSymbolObservation,
        ...,
    ],
) -> tuple[
    CanonicalEvidenceRecord,
    ...,
]:
    """Represent several exact symbol observations without collapsing them."""

    if not isinstance(
        observations,
        tuple,
    ):
        raise InvestigationEvidenceRecordError(
            "observations must be a tuple"
        )

    observation_ids = tuple(
        observation.observation_id
        if isinstance(
            observation,
            InvestigationSymbolObservation,
        )
        else None
        for observation
        in observations
    )

    if len(
        observation_ids
    ) != len(
        set(
            observation_ids
        )
    ):
        raise InvestigationEvidenceRecordError(
            "observations contain duplicate identities"
        )

    return tuple(
        canonical_symbol_observation_evidence_record(
            observation
        )
        for observation
        in observations
    )
