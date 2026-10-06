"""OpenAI Responses adapter for Horizon investigation.

This adapter is deliberately narrow.

It receives an already-created Responses-capable client and translates
one immutable Horizon InvestigatorModelInvocation into exactly one
Responses API request.

It does not:

- read environment variables;
- construct credentials;
- select a model on Horizon's behalf;
- retry a failed or invalid model call;
- fall back to another provider;
- mutate Horizon truth;
- validate semantic authority itself.

The shared Horizon execution and proposal layers remain responsible for
model-run disposition and strict proposal validation.
"""

from __future__ import annotations

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

from horizon.investigator.model import (
    InvestigatorModelInvocation,
    InvestigatorModelResult,
)


class OpenAIResponsesAdapterError(
    ValueError
):
    """The OpenAI Responses boundary failed closed."""


@dataclass(
    frozen=True,
    slots=True,
)
class OpenAITokenPricing:
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
                raise OpenAIResponsesAdapterError(
                    f"{name} must be Decimal"
                )

            if (
                not value.is_finite()
                or value < 0
            ):
                raise OpenAIResponsesAdapterError(
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
            raise OpenAIResponsesAdapterError(
                "canonical request contains a non-finite decimal"
            )

        return str(
            value
        )

    if is_dataclass(
        value
    ) and not isinstance(
        value,
        type,
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
                raise OpenAIResponsesAdapterError(
                    "canonical request mappings require string keys"
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
            raise OpenAIResponsesAdapterError(
                "canonical request contains a non-finite float"
            )

        return value

    raise OpenAIResponsesAdapterError(
        "canonical request contains an unsupported value"
    )


def _canonical_request_json(
    invocation: InvestigatorModelInvocation,
) -> str:
    payload = _json_value(
        invocation.request
    )

    try:
        return json.dumps(
            payload,
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
        raise OpenAIResponsesAdapterError(
            "investigation request cannot be encoded canonically"
        ) from exc


_STRING = {
    "type": "string",
}


_STRING_ARRAY = {
    "type": "array",
    "items": {
        "type": "string",
    },
}


_COMMON_PROPERTIES = {
    "question_id": _STRING,
    "relationship_id": _STRING,
    "assertion_ids": _STRING_ARRAY,
    "claim_ids": _STRING_ARRAY,
    "assessment_ids": _STRING_ARRAY,
    "evidence_reference_ids": _STRING_ARRAY,
}


_COMMON_REQUIRED = [
    "type",
    "question_id",
    "relationship_id",
    "assertion_ids",
    "claim_ids",
    "assessment_ids",
    "evidence_reference_ids",
]


def _strict_object(
    *,
    properties: Mapping[
        str,
        object,
    ],
    required: list[str],
) -> dict[str, object]:
    return {
        "type": "object",
        "properties": dict(
            properties
        ),
        "required": required,
        "additionalProperties": False,
    }


def _proposal_schema() -> dict[str, object]:
    investigation = _strict_object(
        properties={
            **_COMMON_PROPERTIES,
            "type": {
                "type": "string",
                "enum": [
                    "PROPOSE_INVESTIGATION",
                ],
            },
            "investigation_questions": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "minItems": 1,
            },
        },
        required=[
            *_COMMON_REQUIRED,
            "investigation_questions",
        ],
    )

    hypothesis = _strict_object(
        properties={
            **_COMMON_PROPERTIES,
            "type": {
                "type": "string",
                "enum": [
                    "PROPOSE_HYPOTHESIS",
                ],
            },
            "hypothesis": {
                "type": "string",
            },
            "test_questions": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "minItems": 1,
            },
        },
        required=[
            *_COMMON_REQUIRED,
            "hypothesis",
            "test_questions",
        ],
    )

    candidate = _strict_object(
        properties={
            "label": {
                "type": "string",
            },
            "investigation_question": {
                "type": "string",
            },
        },
        required=[
            "label",
            "investigation_question",
        ],
    )

    refine = _strict_object(
        properties={
            **_COMMON_PROPERTIES,
            "type": {
                "type": "string",
                "enum": [
                    "REFINE_OBJECT",
                ],
            },
            "candidates": {
                "type": "array",
                "items": candidate,
                "minItems": 2,
            },
            "missing_evidence_questions": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "minItems": 1,
            },
        },
        required=[
            *_COMMON_REQUIRED,
            "candidates",
            "missing_evidence_questions",
        ],
    )

    insufficient = _strict_object(
        properties={
            **_COMMON_PROPERTIES,
            "type": {
                "type": "string",
                "enum": [
                    "DECLARE_INSUFFICIENT_EVIDENCE",
                ],
            },
            "missing_evidence_questions": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "minItems": 1,
            },
        },
        required=[
            *_COMMON_REQUIRED,
            "missing_evidence_questions",
        ],
    )

    return {
        "type": "object",
        "properties": {
            "proposal": {
                "anyOf": [
                    investigation,
                    hypothesis,
                    refine,
                    insufficient,
                ],
            },
        },
        "required": [
            "proposal",
        ],
        "additionalProperties": False,
    }


def _structured_output_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "name": "horizon_investigation_proposal",
        "strict": True,
        "schema": _proposal_schema(),
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
        raise OpenAIResponsesAdapterError(
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
        raise OpenAIResponsesAdapterError(
            f"{field} must be a nonnegative integer"
        )

    return value


def _usage_value(
    usage: object,
    field: str,
) -> object:
    if usage is None:
        raise OpenAIResponsesAdapterError(
            "response usage is missing"
        )

    if not hasattr(
        usage,
        field,
    ):
        raise OpenAIResponsesAdapterError(
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
    pricing: OpenAITokenPricing,
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
        raise OpenAIResponsesAdapterError(
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
        raise OpenAIResponsesAdapterError(
            "token cost calculation failed"
        ) from exc

    if (
        not cost.is_finite()
        or cost < 0
    ):
        raise OpenAIResponsesAdapterError(
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
) -> Mapping[str, Any]:
    if (
        not isinstance(
            output_text,
            str,
        )
        or not output_text
    ):
        raise OpenAIResponsesAdapterError(
            "structured output text is missing"
        )

    try:
        decoded = json.loads(
            output_text
        )
    except json.JSONDecodeError as exc:
        raise OpenAIResponsesAdapterError(
            "structured output is not valid JSON"
        ) from exc

    if not isinstance(
        decoded,
        dict,
    ):
        raise OpenAIResponsesAdapterError(
            "structured output root must be an object"
        )

    if set(
        decoded
    ) != {
        "proposal",
    }:
        raise OpenAIResponsesAdapterError(
            "structured output wrapper is invalid"
        )

    proposal = decoded[
        "proposal"
    ]

    if not isinstance(
        proposal,
        dict,
    ):
        raise OpenAIResponsesAdapterError(
            "structured output proposal must be an object"
        )

    return proposal


class OpenAIResponsesInvestigatorModel:
    """One caller-configured OpenAI Responses investigator model."""

    def __init__(
        self,
        *,
        client: object,
        model_id: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
        pricing: OpenAITokenPricing,
    ) -> None:
        if client is None:
            raise OpenAIResponsesAdapterError(
                "client is required"
            )

        self._model_id = _require_nonempty_text(
            model_id,
            field="model_id",
        )

        if reasoning_effort is not None:
            self._reasoning_effort = _require_nonempty_text(
                reasoning_effort,
                field="reasoning_effort",
            )
        else:
            self._reasoning_effort = None

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
            raise OpenAIResponsesAdapterError(
                "max_output_tokens must be a positive integer"
            )

        if not isinstance(
            pricing,
            OpenAITokenPricing,
        ):
            raise OpenAIResponsesAdapterError(
                "pricing must be OpenAITokenPricing"
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
            raise OpenAIResponsesAdapterError(
                "client must expose responses.create"
            )

        self._client = client
        self._max_output_tokens = (
            max_output_tokens
        )
        self._pricing = pricing

    def invoke(
        self,
        invocation: InvestigatorModelInvocation,
    ) -> InvestigatorModelResult:
        if not isinstance(
            invocation,
            InvestigatorModelInvocation,
        ):
            raise OpenAIResponsesAdapterError(
                "invocation must be an InvestigatorModelInvocation"
            )

        if (
            self._reasoning_effort is not None
            and invocation.temperature is not None
        ):
            raise OpenAIResponsesAdapterError(
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
            raise OpenAIResponsesAdapterError(
                "sealed instruction must be UTF-8"
            ) from exc

        call: dict[
            str,
            object,
        ] = {
            "model": self._model_id,
            "instructions": instruction,
            "input": _canonical_request_json(
                invocation
            ),
            "text": {
                "format": _structured_output_format(),
            },
            "max_output_tokens": (
                self._max_output_tokens
            ),
            "store": False,
        }

        if self._reasoning_effort is not None:
            call[
                "reasoning"
            ] = {
                "effort": self._reasoning_effort,
            }

        if invocation.temperature is not None:
            call[
                "temperature"
            ] = invocation.temperature

        response = self._client.responses.create(
            **call
        )

        status = getattr(
            response,
            "status",
            None,
        )

        if status != "completed":
            raise OpenAIResponsesAdapterError(
                "response status is not completed"
            )

        returned_model_id = _require_nonempty_text(
            getattr(
                response,
                "model",
                None,
            ),
            field="returned model id",
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
            raise OpenAIResponsesAdapterError(
                "OpenAI HTTP request id is missing"
            )

        proposal = _parse_output(
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

        return InvestigatorModelResult(
            provider="OPENAI",
            model_id=returned_model_id,
            output=proposal,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            api_request_id=request_id,
        )
