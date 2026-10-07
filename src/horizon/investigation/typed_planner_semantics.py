"""Authoritative execution semantics for AI-authored typed plans.

The typed planner schema defines which fields a model may emit.

This module defines what those fields actually mean to Horizon's
existing executors.

These semantics are supplied to the planner model as first-class,
content-addressed input. They are not documentation-only hints.

In particular, SEARCH_SOURCE is a literal byte-substring search.
It is not a regular-expression engine and it is not a glob engine.

Planning is static. Dependencies express execution ordering only;
outputs from one step are not substituted into arguments of another
step. If a path, symbol, line, or character position must first be
discovered, the planner must stop at discovery and Horizon must re-plan
after the new evidence exists.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerOperationSemantics:
    kind: str

    rules: tuple[
        tuple[
            str,
            str,
        ],
        ...,
    ]

    def __post_init__(
        self,
    ) -> None:
        if (
            not isinstance(
                self.kind,
                str,
            )
            or not self.kind.strip()
        ):
            raise ValueError(
                "operation semantics kind must be nonempty"
            )

        keys = tuple(
            key
            for key, _
            in self.rules
        )

        if len(
            keys
        ) != len(
            set(
                keys
            )
        ):
            raise ValueError(
                "operation semantics rule keys must be unique"
            )

        for key, value in self.rules:
            if (
                not isinstance(
                    key,
                    str,
                )
                or not key.strip()
                or not isinstance(
                    value,
                    str,
                )
                or not value.strip()
            ):
                raise ValueError(
                    "operation semantics rules must be nonempty strings"
                )


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerOperationSemanticsContract:
    schema_version: int

    planner_laws: tuple[
        tuple[
            str,
            str,
        ],
        ...,
    ]

    operations: tuple[
        TypedPlannerOperationSemantics,
        ...,
    ]

    contract_id: str


def _payload(
    *,
    schema_version: int,
    planner_laws: tuple[
        tuple[
            str,
            str,
        ],
        ...,
    ],
    operations: tuple[
        TypedPlannerOperationSemantics,
        ...,
    ],
) -> dict[
    str,
    object,
]:
    return {
        "schema_version": (
            schema_version
        ),
        "planner_laws": [
            [
                key,
                value,
            ]
            for key, value
            in planner_laws
        ],
        "operations": [
            {
                "kind": (
                    operation.kind
                ),
                "rules": [
                    [
                        key,
                        value,
                    ]
                    for key, value
                    in operation.rules
                ],
            }
            for operation
            in operations
        ],
    }


def _identity(
    payload: dict[
        str,
        object,
    ],
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        "typed-planner-operation-semantics:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def semantic_gap_typed_planner_operation_semantics(
) -> TypedPlannerOperationSemanticsContract:
    """Return the exact executor semantics exposed to planner models."""

    schema_version = 1

    planner_laws = (
        (
            "OPERATION_ARGUMENT_BINDING",
            "STATIC_AT_PLAN_COMPILE_TIME",
        ),
        (
            "DEPENDENCY_SEMANTICS",
            "ORDERING_ONLY_NO_OUTPUT_SUBSTITUTION",
        ),
        (
            "UNKNOWN_PATH_SYMBOL_OR_COORDINATE",
            "DO_NOT_INVENT_SEARCH_THEN_REPLAN",
        ),
        (
            "REPOSITORY_STATE",
            "READ_ONLY_FROZEN_OBSERVED_GIT_COMMIT",
        ),
        (
            "MODEL_AUTHORITY",
            "PROPOSES_OPERATIONS_ONLY_HORIZON_EXECUTES_AND_VERIFIES",
        ),
    )

    operations = (
        TypedPlannerOperationSemantics(
            kind="SEARCH_SOURCE",
            rules=(
                (
                    "QUERY_MODE",
                    "EXACT_CASE_SENSITIVE_LITERAL_UTF8_SUBSTRING",
                ),
                (
                    "REGEX_SUPPORTED",
                    "NO",
                ),
                (
                    "GLOB_SUPPORTED",
                    "NO",
                ),
                (
                    "REGEX_METACHARACTERS",
                    "HAVE_NO_SPECIAL_MEANING",
                ),
                (
                    "SOURCE",
                    "FROZEN_OBSERVED_GIT_BLOB_BYTES",
                ),
                (
                    "PATH_PREFIX",
                    "OPTIONAL_REPOSITORY_RELATIVE_LITERAL_PREFIX_FILTER",
                ),
                (
                    "MATCH_RESULT",
                    "ALL_LITERAL_MATCHES_WITH_OBSERVED_EVIDENCE_IDENTITIES",
                ),
            ),
        ),
        TypedPlannerOperationSemantics(
            kind="READ_SOURCE",
            rules=(
                (
                    "PATH",
                    "EXACT_REPOSITORY_RELATIVE_OBSERVED_GIT_BLOB_PATH",
                ),
                (
                    "START_LINE",
                    "ONE_BASED_INCLUSIVE",
                ),
                (
                    "END_LINE",
                    "ONE_BASED_INCLUSIVE",
                ),
                (
                    "END_LINE_REQUIREMENT",
                    "MUST_NOT_EXCEED_OBSERVED_SOURCE_LENGTH",
                ),
                (
                    "DISCOVERY",
                    "DOES_NOT_DISCOVER_OR_GUESS_PATHS",
                ),
            ),
        ),
        TypedPlannerOperationSemantics(
            kind="INSPECT_SYMBOL",
            rules=(
                (
                    "PATH",
                    "EXACT_REPOSITORY_RELATIVE_PYTHON_BLOB_PATH",
                ),
                (
                    "SYMBOL",
                    "EXACT_DOTTED_LEXICAL_DEFINITION_NAME",
                ),
                (
                    "FUZZY_LOOKUP",
                    "NO",
                ),
                (
                    "RESULT",
                    "OBSERVED_PYTHON_STRUCTURE_DEFINITION_AND_SUBTREE",
                ),
                (
                    "DISCOVERY",
                    "DOES_NOT_DISCOVER_OR_GUESS_PATHS_OR_SYMBOLS",
                ),
            ),
        ),
        TypedPlannerOperationSemantics(
            kind="RESOLVE_CALL",
            rules=(
                (
                    "PATH",
                    "EXACT_REPOSITORY_RELATIVE_PYTHON_BLOB_PATH",
                ),
                (
                    "LINE",
                    "ONE_BASED",
                ),
                (
                    "CHARACTER",
                    "ZERO_BASED_BYTE_OFFSET_WITHIN_SOURCE_LINE",
                ),
                (
                    "POSITION_REQUIREMENT",
                    "MUST_FALL_INSIDE_OBSERVED_CALLEE_EXPRESSION",
                ),
                (
                    "SEMANTIC_ENGINE",
                    "TRUSTED_PYRIGHT_CALLEE_TYPE_RESOLUTION",
                ),
                (
                    "DISCOVERY",
                    "DOES_NOT_DISCOVER_OR_GUESS_PATHS_OR_COORDINATES",
                ),
            ),
        ),
    )

    payload = _payload(
        schema_version=schema_version,
        planner_laws=(
            planner_laws
        ),
        operations=operations,
    )

    return (
        TypedPlannerOperationSemanticsContract(
            schema_version=(
                schema_version
            ),
            planner_laws=(
                planner_laws
            ),
            operations=operations,
            contract_id=(
                _identity(
                    payload
                )
            ),
        )
    )
