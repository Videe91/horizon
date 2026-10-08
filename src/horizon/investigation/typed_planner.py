"""Strict AI-authored typed planning contract for semantic investigation.

This module is the boundary where a future model may translate an
accepted natural-language PROPOSE_INVESTIGATION proposal into Horizon's
closed typed investigation operations.

The model may propose only operations Horizon can execute today:

- SEARCH_SOURCE
- READ_SOURCE
- INSPECT_SYMBOL
- RESOLVE_CALL

The model may not:

- emit shell commands;
- emit Python code;
- emit arbitrary commands or environments;
- author Horizon step IDs or plan IDs;
- control Horizon plan budgets;
- execute any operation;
- create evidence, claims, assessments, or World Model assertions.

Parsing produces only ProposedInvestigationStepDraft bindings.

Horizon still owns final InvestigationPlan compilation.
"""

from __future__ import annotations

import hashlib
import json

from collections.abc import (
    Mapping,
    Sequence,
)
from dataclasses import (
    dataclass,
    fields,
    is_dataclass,
)
from enum import Enum
from typing import Any

from horizon.investigation.plan import (
    InspectSymbolOperation,
    InvestigationStepDraft,
    ReadSourceOperation,
    ResolveCallOperation,
    SearchSourceOperation,
)
from horizon.investigation.proposal_plan import (
    ProposedInvestigationStepDraft,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    InvestigationProposalKind,
)


class SemanticGapTypedPlannerError(
    ValueError
):
    """AI typed-planner output failed the Horizon authority boundary."""


@dataclass(
    frozen=True,
    slots=True,
)
class SemanticGapTypedPlannerOutput:
    proposal_id: str
    question_id: str

    bindings: tuple[
        ProposedInvestigationStepDraft,
        ...,
    ]

    planner_output_id: str


def _canonicalize(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if (
        is_dataclass(
            value
        )
        and not isinstance(
            value,
            type,
        )
    ):
        return {
            field.name: _canonicalize(
                getattr(
                    value,
                    field.name,
                )
            )
            for field
            in fields(
                value
            )
        }

    if isinstance(
        value,
        Mapping,
    ):
        result: dict[
            str,
            Any,
        ] = {}

        for key, item in value.items():
            if not isinstance(
                key,
                str,
            ):
                raise SemanticGapTypedPlannerError(
                    "planner mappings require string keys"
                )

            result[
                key
            ] = _canonicalize(
                item
            )

        return result

    if isinstance(
        value,
        (
            tuple,
            list,
        ),
    ):
        return [
            _canonicalize(
                item
            )
            for item
            in value
        ]

    if value is None or isinstance(
        value,
        (
            str,
            int,
            bool,
        ),
    ):
        return value

    raise SemanticGapTypedPlannerError(
        "planner value cannot be represented canonically"
    )


def _identity(
    prefix: str,
    value: object,
) -> str:
    encoded = json.dumps(
        _canonicalize(
            value
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        allow_nan=False,
    ).encode(
        "utf-8"
    )

    return (
        prefix
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _require_text(
    value: object,
    *,
    field: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise SemanticGapTypedPlannerError(
            f"{field} must be a nonempty string"
        )

    return value


def _require_sequence(
    value: object,
    *,
    field: str,
    minimum: int = 0,
) -> tuple[
    object,
    ...,
]:
    if (
        isinstance(
            value,
            str,
        )
        or not isinstance(
            value,
            Sequence,
        )
    ):
        raise SemanticGapTypedPlannerError(
            f"{field} must be a sequence"
        )

    result = tuple(
        value
    )

    if len(
        result
    ) < minimum:
        raise SemanticGapTypedPlannerError(
            f"{field} requires at least {minimum} value(s)"
        )

    return result


def _require_text_sequence(
    value: object,
    *,
    field: str,
) -> tuple[
    str,
    ...,
]:
    values = _require_sequence(
        value,
        field=field,
    )

    result = tuple(
        _require_text(
            item,
            field=field,
        )
        for item
        in values
    )

    if len(
        result
    ) != len(
        set(
            result
        )
    ):
        raise SemanticGapTypedPlannerError(
            f"{field} contains duplicate values"
        )

    return result


def _exact_fields(
    raw: Mapping[
        str,
        Any,
    ],
    expected: set[
        str
    ],
    *,
    label: str,
) -> None:
    actual = set(
        raw
    )

    if actual != expected:
        missing = tuple(
            sorted(
                expected
                - actual
            )
        )

        extra = tuple(
            sorted(
                actual
                - expected
            )
        )

        details = []

        if missing:
            details.append(
                "missing="
                + ",".join(
                    missing
                )
            )

        if extra:
            details.append(
                "extra="
                + ",".join(
                    extra
                )
            )

        suffix = (
            ": "
            + "; ".join(
                details
            )
            if details
            else ""
        )

        raise SemanticGapTypedPlannerError(
            f"{label} fields do not match strict schema"
            + suffix
        )


def _parse_search_source(
    raw: Mapping[
        str,
        Any,
    ],
) -> SearchSourceOperation:
    _exact_fields(
        raw,
        {
            "type",
            "query",
            "path_prefix",
        },
        label="SEARCH_SOURCE operation",
    )

    query = _require_text(
        raw[
            "query"
        ],
        field="SEARCH_SOURCE query",
    )

    path_prefix = raw[
        "path_prefix"
    ]

    if path_prefix is not None:
        path_prefix = _require_text(
            path_prefix,
            field=(
                "SEARCH_SOURCE path_prefix"
            ),
        )

    try:
        return SearchSourceOperation(
            query=query,
            path_prefix=path_prefix,
        )
    except ValueError as exc:
        raise SemanticGapTypedPlannerError(
            f"invalid SEARCH_SOURCE operation: {exc}"
        ) from exc


def _parse_read_source(
    raw: Mapping[
        str,
        Any,
    ],
) -> ReadSourceOperation:
    _exact_fields(
        raw,
        {
            "type",
            "path",
            "start_line",
            "end_line",
        },
        label="READ_SOURCE operation",
    )

    try:
        return ReadSourceOperation(
            path=_require_text(
                raw[
                    "path"
                ],
                field="READ_SOURCE path",
            ),
            start_line=raw[
                "start_line"
            ],
            end_line=raw[
                "end_line"
            ],
        )
    except ValueError as exc:
        raise SemanticGapTypedPlannerError(
            f"invalid READ_SOURCE operation: {exc}"
        ) from exc


def _parse_inspect_symbol(
    raw: Mapping[
        str,
        Any,
    ],
) -> InspectSymbolOperation:
    _exact_fields(
        raw,
        {
            "type",
            "path",
            "symbol",
        },
        label="INSPECT_SYMBOL operation",
    )

    try:
        return InspectSymbolOperation(
            path=_require_text(
                raw[
                    "path"
                ],
                field="INSPECT_SYMBOL path",
            ),
            symbol=_require_text(
                raw[
                    "symbol"
                ],
                field="INSPECT_SYMBOL symbol",
            ),
        )
    except ValueError as exc:
        raise SemanticGapTypedPlannerError(
            f"invalid INSPECT_SYMBOL operation: {exc}"
        ) from exc


def _parse_resolve_call(
    raw: Mapping[
        str,
        Any,
    ],
) -> ResolveCallOperation:
    _exact_fields(
        raw,
        {
            "type",
            "path",
            "line",
            "character",
        },
        label="RESOLVE_CALL operation",
    )

    try:
        return ResolveCallOperation(
            path=_require_text(
                raw[
                    "path"
                ],
                field="RESOLVE_CALL path",
            ),
            line=raw[
                "line"
            ],
            character=raw[
                "character"
            ],
        )
    except ValueError as exc:
        raise SemanticGapTypedPlannerError(
            f"invalid RESOLVE_CALL operation: {exc}"
        ) from exc


def _parse_operation(
    raw: object,
):
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticGapTypedPlannerError(
            "operation must be an object"
        )

    raw_type = _require_text(
        raw.get(
            "type"
        ),
        field="operation type",
    )

    if raw_type == "SEARCH_SOURCE":
        return _parse_search_source(
            raw
        )

    if raw_type == "READ_SOURCE":
        return _parse_read_source(
            raw
        )

    if raw_type == "INSPECT_SYMBOL":
        return _parse_inspect_symbol(
            raw
        )

    if raw_type == "RESOLVE_CALL":
        return _parse_resolve_call(
            raw
        )

    if raw_type in {
        "RESOLVE_TYPE",
        "TRACE_HTTP_CONTRACT",
    }:
        raise SemanticGapTypedPlannerError(
            f"{raw_type} is typed but not executable "
            "through the current Horizon investigation executor"
        )

    raise SemanticGapTypedPlannerError(
        "unknown typed planner operation"
    )


def _parse_binding(
    raw: object,
    *,
    proposed_questions: set[
        str
    ],
) -> ProposedInvestigationStepDraft:
    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticGapTypedPlannerError(
            "planner binding must be an object"
        )

    _exact_fields(
        raw,
        {
            "investigation_question",
            "step_key",
            "purpose",
            "operation",
            "depends_on_keys",
            "expected_information",
            "max_seconds",
        },
        label="planner binding",
    )

    investigation_question = (
        _require_text(
            raw[
                "investigation_question"
            ],
            field=(
                "investigation_question"
            ),
        )
    )

    if (
        investigation_question
        not in proposed_questions
    ):
        raise SemanticGapTypedPlannerError(
            "binding does not reference an exact "
            "proposed investigation question"
        )

    step_key = _require_text(
        raw[
            "step_key"
        ],
        field="step_key",
    )

    purpose = _require_text(
        raw[
            "purpose"
        ],
        field="purpose",
    )

    depends_on_keys = (
        _require_text_sequence(
            raw[
                "depends_on_keys"
            ],
            field="depends_on_keys",
        )
    )

    expected_information = (
        _require_text(
            raw[
                "expected_information"
            ],
            field="expected_information",
        )
    )

    operation = _parse_operation(
        raw[
            "operation"
        ]
    )

    try:
        draft = InvestigationStepDraft(
            step_key=step_key,
            purpose=purpose,
            operation=operation,
            depends_on_keys=(
                depends_on_keys
            ),
            expected_information=(
                expected_information
            ),
            max_seconds=raw[
                "max_seconds"
            ],
        )
    except ValueError as exc:
        raise SemanticGapTypedPlannerError(
            f"invalid InvestigationStepDraft: {exc}"
        ) from exc

    try:
        return ProposedInvestigationStepDraft(
            investigation_question=(
                investigation_question
            ),
            draft=draft,
        )
    except ValueError as exc:
        raise SemanticGapTypedPlannerError(
            f"invalid proposal binding: {exc}"
        ) from exc


def _validate_context(
    request: InvestigationRequest,
    proposal: InvestigationProposal,
) -> None:
    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise SemanticGapTypedPlannerError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not InvestigationRequestOrigin
        .REPOSITORY_SEMANTIC_GAP
    ):
        raise SemanticGapTypedPlannerError(
            "request is not a repository semantic-gap request"
        )

    if request.relationship_id is not None:
        raise SemanticGapTypedPlannerError(
            "semantic-gap request may not carry a relationship"
        )

    if not isinstance(
        proposal,
        InvestigationProposal,
    ):
        raise SemanticGapTypedPlannerError(
            "proposal must be an InvestigationProposal"
        )

    if (
        proposal.kind
        is not InvestigationProposalKind
        .PROPOSE_INVESTIGATION
    ):
        raise SemanticGapTypedPlannerError(
            "typed planning requires PROPOSE_INVESTIGATION"
        )

    if (
        proposal.question_id
        != request.question_id
    ):
        raise SemanticGapTypedPlannerError(
            "proposal question does not match request question"
        )

    if proposal.relationship_id is not None:
        raise SemanticGapTypedPlannerError(
            "semantic-gap proposal may not carry a relationship"
        )

    if not proposal.investigation_questions:
        raise SemanticGapTypedPlannerError(
            "proposal contains no investigation questions"
        )


def parse_semantic_gap_typed_planner_output(
    *,
    request: InvestigationRequest,
    proposal: InvestigationProposal,
    raw: Mapping[
        str,
        Any,
    ],
) -> SemanticGapTypedPlannerOutput:
    """Parse one strict AI-authored typed planning proposal."""

    _validate_context(
        request,
        proposal,
    )

    if not isinstance(
        raw,
        Mapping,
    ):
        raise SemanticGapTypedPlannerError(
            "typed planner output must be an object"
        )

    _exact_fields(
        raw,
        {
            "proposal_id",
            "question_id",
            "bindings",
        },
        label="typed planner output",
    )

    proposal_id = _require_text(
        raw[
            "proposal_id"
        ],
        field="proposal_id",
    )

    if (
        proposal_id
        != proposal.proposal_id
    ):
        raise SemanticGapTypedPlannerError(
            "planner proposal identity does not match "
            "the accepted investigation proposal"
        )

    question_id = _require_text(
        raw[
            "question_id"
        ],
        field="question_id",
    )

    if (
        question_id
        != request.question_id
    ):
        raise SemanticGapTypedPlannerError(
            "planner question identity does not match "
            "the semantic-gap request"
        )

    raw_bindings = _require_sequence(
        raw[
            "bindings"
        ],
        field="bindings",
        minimum=1,
    )

    proposed_questions = set(
        proposal.investigation_questions
    )

    bindings = tuple(
        _parse_binding(
            item,
            proposed_questions=(
                proposed_questions
            ),
        )
        for item
        in raw_bindings
    )

    bound_questions = {
        binding.investigation_question
        for binding
        in bindings
    }

    if (
        bound_questions
        != proposed_questions
    ):
        raise SemanticGapTypedPlannerError(
            "planner binding coverage does not include "
            "every proposed investigation question"
        )

    planner_output_id = _identity(
        "semantic-gap-typed-planner-output:",
        {
            "schema_version": 1,
            "proposal_id": (
                proposal_id
            ),
            "question_id": (
                question_id
            ),
            "bindings": bindings,
        },
    )

    return SemanticGapTypedPlannerOutput(
        proposal_id=proposal_id,
        question_id=question_id,
        bindings=bindings,
        planner_output_id=(
            planner_output_id
        ),
    )


def _strict_object(
    properties: Mapping[
        str,
        object,
    ],
    required: tuple[
        str,
        ...,
    ],
) -> dict[
    str,
    object,
]:
    return {
        "type": "object",
        "properties": dict(
            properties
        ),
        "required": list(
            required
        ),
        "additionalProperties": False,
    }


def semantic_gap_typed_planner_schema() -> dict[
    str,
    object,
]:
    """Return the provider-neutral strict planner output schema."""

    string = {
        "type": "string",
    }

    string_array = {
        "type": "array",
        "items": {
            "type": "string",
        },
    }

    search_source = _strict_object(
        {
            "type": {
                "const": "SEARCH_SOURCE",
            },
            "query": string,
            "path_prefix": {
                "oneOf": [
                    {
                        "type": "string",
                    },
                    {
                        "type": "null",
                    },
                ],
            },
        },
        (
            "type",
            "query",
            "path_prefix",
        ),
    )

    read_source = _strict_object(
        {
            "type": {
                "const": "READ_SOURCE",
            },
            "path": string,
            "start_line": {
                "type": "integer",
                "minimum": 1,
            },
            "end_line": {
                "oneOf": [
                    {
                        "type": "integer",
                        "minimum": 1,
                    },
                    {
                        "type": "null",
                    },
                ],
            },
        },
        (
            "type",
            "path",
            "start_line",
            "end_line",
        ),
    )

    inspect_symbol = _strict_object(
        {
            "type": {
                "const": "INSPECT_SYMBOL",
            },
            "path": string,
            "symbol": string,
        },
        (
            "type",
            "path",
            "symbol",
        ),
    )

    resolve_call = _strict_object(
        {
            "type": {
                "const": "RESOLVE_CALL",
            },
            "path": string,
            "line": {
                "type": "integer",
                "minimum": 1,
            },
            "character": {
                "type": "integer",
                "minimum": 0,
            },
        },
        (
            "type",
            "path",
            "line",
            "character",
        ),
    )

    operation = {
        "oneOf": [
            search_source,
            read_source,
            inspect_symbol,
            resolve_call,
        ],
    }

    binding = _strict_object(
        {
            "investigation_question": string,
            "step_key": string,
            "purpose": string,
            "operation": operation,
            "depends_on_keys": (
                string_array
            ),
            "expected_information": string,
            "max_seconds": {
                "type": "integer",
                "minimum": 1,
            },
        },
        (
            "investigation_question",
            "step_key",
            "purpose",
            "operation",
            "depends_on_keys",
            "expected_information",
            "max_seconds",
        ),
    )

    return _strict_object(
        {
            "proposal_id": string,
            "question_id": string,
            "bindings": {
                "type": "array",
                "items": binding,
                "minItems": 1,
            },
        },
        (
            "proposal_id",
            "question_id",
            "bindings",
        ),
    )
