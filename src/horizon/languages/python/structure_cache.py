"""Content-addressed reuse for Python structural extraction.

The portable cache payload contains only computation that is safe to
reuse for identical source bytes.

It deliberately does not contain Horizon evidence identities.

On every materialization, evidence identities are rebuilt against the
current GitBlobEvidence so repository provenance remains exact.
"""

from __future__ import annotations

import json
import platform
import sys

from dataclasses import dataclass
from typing import Any

from horizon.cache.content import (
    ContentAddressedExtractionCache,
    ContentCacheKey,
    make_content_cache_key,
)
from horizon.languages.python.structure import (
    PythonStructureAnalysis,
    PythonStructureFact,
    PythonStructureKind,
    _analysis_identity,
    _callee_identity,
    _fact_identity,
    analyze_python_blob,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)


_EXTRACTOR = "python.structure"
_EXTRACTOR_VERSION = "1"
_PAYLOAD_SCHEMA_VERSION = 1


class PythonStructureCacheError(
    ValueError
):
    """Cached Python structure could not be trusted or materialized."""


@dataclass(
    frozen=True,
    slots=True,
)
class PythonStructureCacheResult:
    analysis: PythonStructureAnalysis
    cache_key: ContentCacheKey
    cache_hit: bool


def _canonical_json(
    value: Any,
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


def _extractor_parameters() -> bytes:
    return _canonical_json(
        {
            "python_implementation": (
                sys.implementation.name
            ),
            "python_version": (
                platform.python_version()
            ),
        }
    )


def make_python_structure_cache_key(
    content: bytes,
) -> ContentCacheKey:
    return make_content_cache_key(
        content=content,
        extractor=_EXTRACTOR,
        extractor_version=(
            _EXTRACTOR_VERSION
        ),
        parameters=(
            _extractor_parameters()
        ),
    )


def _parent_index(
    fact: PythonStructureFact,
    indexes: dict[
        str,
        int,
    ],
) -> int | None:
    if (
        fact.structural_parent_id
        is None
    ):
        return None

    try:
        return indexes[
            fact.structural_parent_id
        ]
    except KeyError as exc:
        raise PythonStructureCacheError(
            "structure fact parent was not materialized before its child"
        ) from exc


def _encode_analysis(
    analysis: PythonStructureAnalysis,
) -> bytes:
    indexes: dict[
        str,
        int,
    ] = {}

    records: list[
        dict[
            str,
            Any,
        ]
    ] = []

    for index, fact in enumerate(
        analysis.facts
    ):
        parent = _parent_index(
            fact,
            indexes,
        )

        records.append(
            {
                "kind": (
                    fact.kind.value
                ),
                "name": (
                    None
                    if fact.kind
                    is PythonStructureKind.MODULE
                    else fact.name
                ),
                "module": (
                    fact.module
                ),
                "alias": (
                    fact.alias
                ),
                "callee_expression": (
                    fact.callee_expression
                ),
                "callee_byte_start": (
                    fact.callee_byte_start
                ),
                "callee_byte_end": (
                    fact.callee_byte_end
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
                "parent_index": (
                    parent
                ),
            }
        )

        indexes[
            fact.evidence_id
        ] = index

    return _canonical_json(
        {
            "schema_version": (
                _PAYLOAD_SCHEMA_VERSION
            ),
            "facts": records,
        }
    )


def _require_dict(
    value: Any,
    *,
    message: str,
) -> dict[
    str,
    Any,
]:
    if not isinstance(
        value,
        dict,
    ):
        raise PythonStructureCacheError(
            message
        )

    return value


def _require_string(
    value: Any,
    *,
    field: str,
    nullable: bool = False,
) -> str | None:
    if (
        nullable
        and value is None
    ):
        return None

    if not isinstance(
        value,
        str,
    ):
        raise PythonStructureCacheError(
            f"cached structure field {field!r} must be a string"
        )

    return value


def _require_int(
    value: Any,
    *,
    field: str,
    nullable: bool = False,
) -> int | None:
    if (
        nullable
        and value is None
    ):
        return None

    if type(
        value
    ) is not int:
        raise PythonStructureCacheError(
            f"cached structure field {field!r} must be an integer"
        )

    return value


def _require_scope(
    value: Any,
) -> tuple[
    str,
    ...,
]:
    if not isinstance(
        value,
        list,
    ):
        raise PythonStructureCacheError(
            "cached structure scope must be an array"
        )

    if any(
        not isinstance(
            part,
            str,
        )
        for part in value
    ):
        raise PythonStructureCacheError(
            "cached structure scope members must be strings"
        )

    return tuple(
        value
    )


_RECORD_FIELDS = {
    "kind",
    "name",
    "module",
    "alias",
    "callee_expression",
    "callee_byte_start",
    "callee_byte_end",
    "scope",
    "line_start",
    "line_end",
    "byte_start",
    "byte_end",
    "parent_index",
}


def _decode_document(
    payload: bytes,
) -> tuple[
    dict[
        str,
        Any,
    ],
    ...,
]:
    try:
        decoded = json.loads(
            payload.decode(
                "utf-8"
            )
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise PythonStructureCacheError(
            "cached Python structure payload is not valid JSON"
        ) from exc

    document = _require_dict(
        decoded,
        message=(
            "cached Python structure payload root must be an object"
        ),
    )

    if set(
        document
    ) != {
        "schema_version",
        "facts",
    }:
        raise PythonStructureCacheError(
            "cached Python structure payload fields are invalid"
        )

    if (
        document[
            "schema_version"
        ]
        != _PAYLOAD_SCHEMA_VERSION
    ):
        raise PythonStructureCacheError(
            "cached Python structure schema version is unsupported"
        )

    records = document[
        "facts"
    ]

    if not isinstance(
        records,
        list,
    ):
        raise PythonStructureCacheError(
            "cached Python structure facts must be an array"
        )

    output: list[
        dict[
            str,
            Any,
        ]
    ] = []

    for record in records:
        item = _require_dict(
            record,
            message=(
                "cached Python structure fact must be an object"
            ),
        )

        if set(
            item
        ) != _RECORD_FIELDS:
            raise PythonStructureCacheError(
                "cached Python structure fact fields are invalid"
            )

        output.append(
            item
        )

    return tuple(
        output
    )


def _materialize(
    *,
    blob: GitBlobEvidence,
    payload: bytes,
) -> PythonStructureAnalysis:
    records = _decode_document(
        payload
    )

    if not records:
        raise PythonStructureCacheError(
            "cached Python structure contains no module fact"
        )

    facts: list[
        PythonStructureFact
    ] = []

    module_count = 0

    for index, record in enumerate(
        records
    ):
        kind_text = _require_string(
            record[
                "kind"
            ],
            field="kind",
        )

        assert kind_text is not None

        try:
            kind = PythonStructureKind(
                kind_text
            )
        except ValueError as exc:
            raise PythonStructureCacheError(
                "cached Python structure kind is unknown"
            ) from exc

        raw_name = record[
            "name"
        ]

        if (
            kind
            is PythonStructureKind.MODULE
        ):
            if raw_name is not None:
                raise PythonStructureCacheError(
                    "cached module fact must not preserve an old path"
                )

            name = blob.path
            module_count += 1

        else:
            name_value = _require_string(
                raw_name,
                field="name",
            )

            assert (
                name_value
                is not None
            )

            name = name_value

        module = _require_string(
            record[
                "module"
            ],
            field="module",
            nullable=True,
        )

        alias = _require_string(
            record[
                "alias"
            ],
            field="alias",
            nullable=True,
        )

        callee_expression = (
            _require_string(
                record[
                    "callee_expression"
                ],
                field=(
                    "callee_expression"
                ),
                nullable=True,
            )
        )

        callee_byte_start = (
            _require_int(
                record[
                    "callee_byte_start"
                ],
                field=(
                    "callee_byte_start"
                ),
                nullable=True,
            )
        )

        callee_byte_end = (
            _require_int(
                record[
                    "callee_byte_end"
                ],
                field=(
                    "callee_byte_end"
                ),
                nullable=True,
            )
        )

        scope = _require_scope(
            record[
                "scope"
            ]
        )

        line_start = _require_int(
            record[
                "line_start"
            ],
            field="line_start",
        )

        line_end = _require_int(
            record[
                "line_end"
            ],
            field="line_end",
        )

        byte_start = _require_int(
            record[
                "byte_start"
            ],
            field="byte_start",
        )

        byte_end = _require_int(
            record[
                "byte_end"
            ],
            field="byte_end",
        )

        assert line_start is not None
        assert line_end is not None
        assert byte_start is not None
        assert byte_end is not None

        parent_index = _require_int(
            record[
                "parent_index"
            ],
            field="parent_index",
            nullable=True,
        )

        if parent_index is None:
            structural_parent_id = None

        else:
            if (
                parent_index < 0
                or parent_index
                >= index
            ):
                raise PythonStructureCacheError(
                    "cached Python structure parent index is invalid"
                )

            structural_parent_id = (
                facts[
                    parent_index
                ].evidence_id
            )

        if (
            kind
            is PythonStructureKind.CALL
        ):
            if (
                callee_expression is None
                or callee_byte_start is None
                or callee_byte_end is None
            ):
                raise PythonStructureCacheError(
                    "cached CALL fact lacks callee evidence"
                )

        else:
            if (
                callee_expression is not None
                or callee_byte_start is not None
                or callee_byte_end is not None
            ):
                raise PythonStructureCacheError(
                    "cached non-CALL fact contains callee evidence"
                )

        evidence_id = _fact_identity(
            source_evidence_id=(
                blob.evidence_id
            ),
            kind=kind,
            name=name,
            module=module,
            alias=alias,
            scope=scope,
            structural_parent_id=(
                structural_parent_id
            ),
            line_start=(
                line_start
            ),
            line_end=(
                line_end
            ),
            byte_start=(
                byte_start
            ),
            byte_end=(
                byte_end
            ),
        )

        if (
            kind
            is PythonStructureKind.CALL
        ):
            assert (
                callee_expression
                is not None
            )
            assert (
                callee_byte_start
                is not None
            )
            assert (
                callee_byte_end
                is not None
            )

            callee_evidence_id = (
                _callee_identity(
                    source_evidence_id=(
                        blob.evidence_id
                    ),
                    call_evidence_id=(
                        evidence_id
                    ),
                    expression=(
                        callee_expression
                    ),
                    byte_start=(
                        callee_byte_start
                    ),
                    byte_end=(
                        callee_byte_end
                    ),
                )
            )

        else:
            callee_evidence_id = None

        facts.append(
            PythonStructureFact(
                kind=kind,
                name=name,
                module=module,
                alias=alias,
                callee_expression=(
                    callee_expression
                ),
                callee_byte_start=(
                    callee_byte_start
                ),
                callee_byte_end=(
                    callee_byte_end
                ),
                callee_evidence_id=(
                    callee_evidence_id
                ),
                scope=scope,
                line_start=(
                    line_start
                ),
                line_end=(
                    line_end
                ),
                byte_start=(
                    byte_start
                ),
                byte_end=(
                    byte_end
                ),
                structural_parent_id=(
                    structural_parent_id
                ),
                source_evidence_id=(
                    blob.evidence_id
                ),
                evidence_id=(
                    evidence_id
                ),
            )
        )

    if module_count != 1:
        raise PythonStructureCacheError(
            "cached Python structure must contain exactly one module fact"
        )

    if (
        facts[0].kind
        is not PythonStructureKind.MODULE
        or facts[0].structural_parent_id
        is not None
        or facts[0].scope
        != ()
    ):
        raise PythonStructureCacheError(
            "cached Python structure module root is invalid"
        )

    materialized_facts = tuple(
        facts
    )

    return PythonStructureAnalysis(
        path=blob.path,
        source_evidence_id=(
            blob.evidence_id
        ),
        facts=(
            materialized_facts
        ),
        analysis_id=(
            _analysis_identity(
                source_evidence_id=(
                    blob.evidence_id
                ),
                facts=(
                    materialized_facts
                ),
            )
        ),
    )


def analyze_python_blob_cached(
    blob: GitBlobEvidence,
    cache: ContentAddressedExtractionCache,
) -> PythonStructureCacheResult:
    """Analyze one Python blob with reusable content-addressed extraction."""

    if not isinstance(
        blob,
        GitBlobEvidence,
    ):
        raise PythonStructureCacheError(
            "blob must be GitBlobEvidence"
        )

    if not isinstance(
        cache,
        ContentAddressedExtractionCache,
    ):
        raise PythonStructureCacheError(
            "cache must be ContentAddressedExtractionCache"
        )

    key = (
        make_python_structure_cache_key(
            blob.content
        )
    )

    cached = cache.get(
        key
    )

    if cached is not None:
        return PythonStructureCacheResult(
            analysis=_materialize(
                blob=blob,
                payload=(
                    cached.payload
                ),
            ),
            cache_key=key,
            cache_hit=True,
        )

    analysis = analyze_python_blob(
        blob
    )

    payload = _encode_analysis(
        analysis
    )

    cache.put(
        key,
        payload,
    )

    return PythonStructureCacheResult(
        analysis=analysis,
        cache_key=key,
        cache_hit=False,
    )
