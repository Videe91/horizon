"""OpenAI Responses adapter for Horizon semantic-gap typed planning.

This is a mechanical provider adapter.

It translates one immutable
SemanticGapTypedPlannerModelInvocation into exactly one OpenAI
Responses-compatible request and translates the completed response into
SemanticGapTypedPlannerModelResult.

It does not:

- read environment variables;
- construct credentials or SDK clients;
- select a model;
- retry;
- fall back to another provider;
- validate semantic authority;
- compile an InvestigationPlan;
- execute investigation operations;
- mutate Horizon truth.

The provider-neutral planner schema is preserved semantically.

Provider compatibility normalization is mechanical only:

- JSON Schema ``const`` becomes a singleton string ``enum``;
- JSON Schema ``oneOf`` becomes ``anyOf``.

No operation or field is added by that normalization.
"""

from __future__ import annotations

from horizon.investigation.typed_planner_request_view import (
    make_typed_planner_request_view,
)

import json
import math

from collections.abc import Mapping
from dataclasses import (
    dataclass,
    fields,
    is_dataclass,
)
from decimal import (
    Decimal,
    InvalidOperation,
)
from enum import Enum
from typing import Any

from horizon.investigation.typed_planner import (
    semantic_gap_typed_planner_schema,
)
from horizon.investigation.typed_planner_model import (
    SemanticGapTypedPlannerModelInvocation,
    SemanticGapTypedPlannerModelResult,
)


class OpenAITypedPlannerResponsesError(
    ValueError
):
    """OpenAI typed-planner Responses boundary failed closed."""


@dataclass(
    frozen=True,
    slots=True,
)
class OpenAITypedPlannerTokenPricing:
    """Per-million-token prices supplied by Horizon configuration."""

    input_per_million: Decimal
    cached_input_per_million: Decimal
    cache_write_per_million: Decimal
    output_per_million: Decimal

    def __post_init__(
        self,
    ) -> None:
        for name, value in (
            (
                "input_per_million",
                self.input_per_million,
            ),
            (
                "cached_input_per_million",
                self.cached_input_per_million,
            ),
            (
                "cache_write_per_million",
                self.cache_write_per_million,
            ),
            (
                "output_per_million",
                self.output_per_million,
            ),
        ):
            if not isinstance(
                value,
                Decimal,
            ):
                raise OpenAITypedPlannerResponsesError(
                    f"{name} must be Decimal"
                )

            if (
                not value.is_finite()
                or value < 0
            ):
                raise OpenAITypedPlannerResponsesError(
                    f"{name} must be nonnegative and finite"
                )


def _json_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        Decimal,
    ):
        if not value.is_finite():
            raise OpenAITypedPlannerResponsesError(
                "canonical input contains a non-finite decimal"
            )

        return str(
            value
        )

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
            field.name: _json_value(
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
                raise OpenAITypedPlannerResponsesError(
                    "canonical input mappings require string keys"
                )

            result[
                key
            ] = _json_value(
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
            _json_value(
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

    if isinstance(
        value,
        float,
    ):
        if not math.isfinite(
            value
        ):
            raise OpenAITypedPlannerResponsesError(
                "canonical input contains a non-finite float"
            )

        return value

    raise OpenAITypedPlannerResponsesError(
        "canonical input contains an unsupported value"
    )


def _canonical_input_json(
    invocation: SemanticGapTypedPlannerModelInvocation,
) -> str:
    payload = {
        "proposal": (
            invocation.proposal
        ),
        "plan_budget": {
            "max_total_seconds": (
                invocation
                .max_plan_total_seconds
            ),
        },
        "request": (
            make_typed_planner_request_view(
                invocation.request
            )
        ),
        "schema_hash": (
            invocation.schema_hash
        ),
        "operation_semantics": (
            invocation.operation_semantics
        ),
        "operation_semantics_id": (
            invocation.operation_semantics_id
        ),
    }

    try:
        return json.dumps(
            _json_value(
                payload
            ),
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise OpenAITypedPlannerResponsesError(
            "typed-planner input cannot be encoded canonically"
        ) from exc


def _normalize_schema_for_openai(
    value: object,
) -> object:
    """Mechanically normalize supported schema syntax for Responses."""

    if isinstance(
        value,
        list,
    ):
        return [
            _normalize_schema_for_openai(
                item
            )
            for item
            in value
        ]

    if not isinstance(
        value,
        dict,
    ):
        return value

    if set(
        value
    ) == {
        "const",
    }:
        constant = value[
            "const"
        ]

        if not isinstance(
            constant,
            str,
        ):
            raise OpenAITypedPlannerResponsesError(
                "typed-planner const discriminator must be a string"
            )

        return {
            "type": "string",
            "enum": [
                constant,
            ],
        }

    result: dict[
        str,
        object,
    ] = {}

    for key, item in value.items():
        normalized_key = (
            "anyOf"
            if key == "oneOf"
            else key
        )

        result[
            normalized_key
        ] = _normalize_schema_for_openai(
            item
        )

    return result


def _structured_output_format() -> dict[
    str,
    object,
]:
    normalized = (
        _normalize_schema_for_openai(
            semantic_gap_typed_planner_schema()
        )
    )

    if not isinstance(
        normalized,
        dict,
    ):
        raise OpenAITypedPlannerResponsesError(
            "normalized typed-planner schema must be an object"
        )

    return {
        "type": "json_schema",
        "name": (
            "horizon_semantic_gap_typed_planner"
        ),
        "strict": True,
        "schema": normalized,
    }


def _require_nonempty_text(
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
        raise OpenAITypedPlannerResponsesError(
            f"{field} must be a nonempty string"
        )

    return value


def _require_token_count(
    value: object,
    *,
    field: str,
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
        raise OpenAITypedPlannerResponsesError(
            f"{field} must be a nonnegative integer"
        )

    return value


def _usage_value(
    usage: object,
    field: str,
) -> object:
    if usage is None:
        raise OpenAITypedPlannerResponsesError(
            "response usage is missing"
        )

    if not hasattr(
        usage,
        field,
    ):
        raise OpenAITypedPlannerResponsesError(
            f"response usage is missing {field}"
        )

    return getattr(
        usage,
        field,
    )


def _input_detail(
    usage: object,
    field: str,
) -> int:
    details = getattr(
        usage,
        "input_tokens_details",
        None,
    )

    if details is None:
        return 0

    value = getattr(
        details,
        field,
        0,
    )

    if value is None:
        value = 0

    return _require_token_count(
        value,
        field=field,
    )


def _calculate_cost(
    *,
    usage: object,
    pricing: OpenAITypedPlannerTokenPricing,
) -> tuple[
    int,
    int,
    Decimal,
]:
    input_tokens = _require_token_count(
        _usage_value(
            usage,
            "input_tokens",
        ),
        field="input_tokens",
    )

    output_tokens = _require_token_count(
        _usage_value(
            usage,
            "output_tokens",
        ),
        field="output_tokens",
    )

    cached_tokens = _input_detail(
        usage,
        "cached_tokens",
    )

    cache_write_tokens = _input_detail(
        usage,
        "cache_write_tokens",
    )

    ordinary_input_tokens = (
        input_tokens
        - cached_tokens
        - cache_write_tokens
    )

    if ordinary_input_tokens < 0:
        raise OpenAITypedPlannerResponsesError(
            "input token accounting is inconsistent"
        )

    million = Decimal(
        "1000000"
    )

    try:
        cost = (
            Decimal(
                ordinary_input_tokens
            )
            * pricing.input_per_million
            / million
            + Decimal(
                cached_tokens
            )
            * pricing.cached_input_per_million
            / million
            + Decimal(
                cache_write_tokens
            )
            * pricing.cache_write_per_million
            / million
            + Decimal(
                output_tokens
            )
            * pricing.output_per_million
            / million
        )
    except (
        InvalidOperation,
        ArithmeticError,
    ) as exc:
        raise OpenAITypedPlannerResponsesError(
            "token cost calculation failed"
        ) from exc

    if (
        not cost.is_finite()
        or cost < 0
    ):
        raise OpenAITypedPlannerResponsesError(
            "calculated model cost is invalid"
        )

    return (
        input_tokens,
        output_tokens,
        cost.quantize(
            Decimal(
                "0.000001"
            )
        ),
    )


def _parse_output(
    output_text: object,
) -> Mapping[
    str,
    Any,
]:
    if (
        not isinstance(
            output_text,
            str,
        )
        or not output_text
    ):
        raise OpenAITypedPlannerResponsesError(
            "structured output text is missing"
        )

    try:
        decoded = json.loads(
            output_text
        )
    except json.JSONDecodeError as exc:
        raise OpenAITypedPlannerResponsesError(
            "structured output is not valid JSON"
        ) from exc

    if not isinstance(
        decoded,
        dict,
    ):
        raise OpenAITypedPlannerResponsesError(
            "structured output root must be an object"
        )

    return decoded


class OpenAIResponsesTypedPlannerModel:
    """One caller-configured OpenAI Responses typed planner."""

    def __init__(
        self,
        *,
        client: object,
        model_id: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
        pricing: OpenAITypedPlannerTokenPricing,
    ) -> None:
        if client is None:
            raise OpenAITypedPlannerResponsesError(
                "client is required"
            )

        self._model_id = _require_nonempty_text(
            model_id,
            field="model_id",
        )

        if reasoning_effort is None:
            self._reasoning_effort = None
        else:
            self._reasoning_effort = (
                _require_nonempty_text(
                    reasoning_effort,
                    field="reasoning_effort",
                )
            )

        if (
            isinstance(
                max_output_tokens,
                bool,
            )
            or not isinstance(
                max_output_tokens,
                int,
            )
            or max_output_tokens <= 0
        ):
            raise OpenAITypedPlannerResponsesError(
                "max_output_tokens must be a positive integer"
            )

        if not isinstance(
            pricing,
            OpenAITypedPlannerTokenPricing,
        ):
            raise OpenAITypedPlannerResponsesError(
                "pricing must be OpenAITypedPlannerTokenPricing"
            )

        responses = getattr(
            client,
            "responses",
            None,
        )

        if (
            responses is None
            or not callable(
                getattr(
                    responses,
                    "create",
                    None,
                )
            )
        ):
            raise OpenAITypedPlannerResponsesError(
                "client must expose responses.create"
            )

        self._client = client

        self._max_output_tokens = (
            max_output_tokens
        )

        self._pricing = pricing

    def invoke(
        self,
        invocation: (
            SemanticGapTypedPlannerModelInvocation
        ),
    ) -> SemanticGapTypedPlannerModelResult:
        if not isinstance(
            invocation,
            SemanticGapTypedPlannerModelInvocation,
        ):
            raise OpenAITypedPlannerResponsesError(
                "invocation must be "
                "SemanticGapTypedPlannerModelInvocation"
            )

        if (
            self._reasoning_effort is not None
            and invocation.temperature is not None
        ):
            raise OpenAITypedPlannerResponsesError(
                "temperature must be omitted "
                "when reasoning effort is configured"
            )

        try:
            instruction = (
                invocation.instruction.decode(
                    "utf-8"
                )
            )
        except UnicodeDecodeError as exc:
            raise OpenAITypedPlannerResponsesError(
                "sealed instruction must be UTF-8"
            ) from exc

        call: dict[
            str,
            object,
        ] = {
            "model": self._model_id,
            "instructions": instruction,
            "input": (
                _canonical_input_json(
                    invocation
                )
            ),
            "text": {
                "format": (
                    _structured_output_format()
                ),
            },
            "max_output_tokens": (
                self._max_output_tokens
            ),
            "store": False,
        }

        if (
            self._reasoning_effort
            is not None
        ):
            call[
                "reasoning"
            ] = {
                "effort": (
                    self._reasoning_effort
                ),
            }

        if (
            invocation.temperature
            is not None
        ):
            call[
                "temperature"
            ] = (
                invocation.temperature
            )

        response = (
            self._client.responses.create(
                **call
            )
        )

        status = getattr(
            response,
            "status",
            None,
        )

        if status != "completed":
            raise OpenAITypedPlannerResponsesError(
                "response status is not completed"
            )

        returned_model_id = (
            _require_nonempty_text(
                getattr(
                    response,
                    "model",
                    None,
                ),
                field="returned model id",
            )
        )

        request_id = getattr(
            response,
            "_request_id",
            None,
        )

        if (
            not isinstance(
                request_id,
                str,
            )
            or not request_id.strip()
        ):
            raise OpenAITypedPlannerResponsesError(
                "OpenAI HTTP request id is missing"
            )

        output = _parse_output(
            getattr(
                response,
                "output_text",
                None,
            )
        )

        (
            input_tokens,
            output_tokens,
            cost_usd,
        ) = _calculate_cost(
            usage=getattr(
                response,
                "usage",
                None,
            ),
            pricing=self._pricing,
        )

        return (
            SemanticGapTypedPlannerModelResult(
                provider="OPENAI",
                model_id=(
                    returned_model_id
                ),
                output=output,
                input_tokens=(
                    input_tokens
                ),
                output_tokens=(
                    output_tokens
                ),
                cost_usd=cost_usd,
                api_request_id=(
                    request_id
                ),
            )
        )
