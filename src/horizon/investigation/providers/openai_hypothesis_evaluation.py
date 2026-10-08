"""OpenAI Responses adapter for typed hypothesis evidence evaluation."""

from __future__ import annotations

import json

from dataclasses import dataclass
from decimal import Decimal

from horizon.investigation.hypothesis_evaluation import (
    hypothesis_evaluation_schema,
)
from horizon.investigation.hypothesis_evaluation_model import (
    HypothesisEvaluationModelInvocation,
    HypothesisEvaluationModelResult,
    canonical_hypothesis_evaluation_model_input,
)


class OpenAIHypothesisEvaluationResponsesError(
    ValueError
):
    """OpenAI hypothesis-evaluation adapter failure."""


@dataclass(
    frozen=True,
    slots=True,
)
class OpenAIHypothesisEvaluationTokenPricing:
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
            if (
                not isinstance(
                    value,
                    Decimal,
                )
                or not value.is_finite()
                or value < 0
            ):
                raise (
                    OpenAIHypothesisEvaluationResponsesError(
                        name
                        + " must be a finite "
                        "nonnegative Decimal"
                    )
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
        raise OpenAIHypothesisEvaluationResponsesError(
            field
            + " must be nonempty text"
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
        raise OpenAIHypothesisEvaluationResponsesError(
            field
            + " must be a nonnegative integer"
        )

    return value


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
    pricing: OpenAIHypothesisEvaluationTokenPricing,
) -> tuple[
    int,
    int,
    Decimal,
]:
    if usage is None:
        raise OpenAIHypothesisEvaluationResponsesError(
            "response usage is missing"
        )

    input_tokens = _require_token_count(
        getattr(
            usage,
            "input_tokens",
            None,
        ),
        field="input tokens",
    )

    output_tokens = _require_token_count(
        getattr(
            usage,
            "output_tokens",
            None,
        ),
        field="output tokens",
    )

    cached_tokens = _input_detail(
        usage,
        "cached_tokens",
    )

    cache_write_tokens = _input_detail(
        usage,
        "cache_write_tokens",
    )

    if (
        cached_tokens
        + cache_write_tokens
        > input_tokens
    ):
        raise OpenAIHypothesisEvaluationResponsesError(
            "cached and cache-write input tokens "
            "cannot exceed total input tokens"
        )

    uncached_tokens = (
        input_tokens
        - cached_tokens
        - cache_write_tokens
    )

    million = Decimal(
        "1000000"
    )

    cost = (
        (
            Decimal(
                uncached_tokens
            )
            * pricing.input_per_million
        )
        + (
            Decimal(
                cached_tokens
            )
            * pricing.cached_input_per_million
        )
        + (
            Decimal(
                cache_write_tokens
            )
            * pricing.cache_write_per_million
        )
        + (
            Decimal(
                output_tokens
            )
            * pricing.output_per_million
        )
    ) / million

    return (
        input_tokens,
        output_tokens,
        cost,
    )


def _parse_output(
    value: object,
) -> dict[
    str,
    object,
]:
    if not isinstance(
        value,
        str,
    ):
        raise OpenAIHypothesisEvaluationResponsesError(
            "response output_text must be JSON text"
        )

    try:
        parsed = json.loads(
            value
        )
    except json.JSONDecodeError as exc:
        raise OpenAIHypothesisEvaluationResponsesError(
            "response output_text is not valid JSON"
        ) from exc

    if not isinstance(
        parsed,
        dict,
    ):
        raise OpenAIHypothesisEvaluationResponsesError(
            "response JSON must be an object"
        )

    return parsed


def _provider_schema_value(
    value,
):
    if isinstance(
        value,
        dict,
    ):
        return {
            key: _provider_schema_value(
                child
            )
            for key, child
            in value.items()
            if key != "uniqueItems"
        }

    if isinstance(
        value,
        list,
    ):
        return [
            _provider_schema_value(
                child
            )
            for child
            in value
        ]

    return value


def _structured_output_format() -> dict[
    str,
    object,
]:
    return {
        "type": "json_schema",
        "name": (
            "horizon_hypothesis_evidence_evaluation"
        ),
        "strict": True,
        "schema": (
            _provider_schema_value(
                hypothesis_evaluation_schema()
            )
        ),
    }


def _canonical_input_json(
    invocation: HypothesisEvaluationModelInvocation,
) -> str:
    try:
        return json.dumps(
            canonical_hypothesis_evaluation_model_input(
                invocation
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
        raise OpenAIHypothesisEvaluationResponsesError(
            "hypothesis evaluation input "
            "cannot be encoded canonically"
        ) from exc


class OpenAIResponsesHypothesisEvaluationModel:
    """One caller-configured OpenAI Responses hypothesis evaluator."""

    def __init__(
        self,
        *,
        client: object,
        model_id: str,
        reasoning_effort: str | None,
        max_output_tokens: int,
        pricing: OpenAIHypothesisEvaluationTokenPricing,
    ) -> None:
        if client is None:
            raise OpenAIHypothesisEvaluationResponsesError(
                "client is required"
            )

        self._model_id = _require_text(
            model_id,
            field="model id",
        )

        if reasoning_effort is None:
            self._reasoning_effort = None
        else:
            self._reasoning_effort = (
                _require_text(
                    reasoning_effort,
                    field="reasoning effort",
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
            raise OpenAIHypothesisEvaluationResponsesError(
                "max_output_tokens must be "
                "a positive integer"
            )

        if not isinstance(
            pricing,
            OpenAIHypothesisEvaluationTokenPricing,
        ):
            raise OpenAIHypothesisEvaluationResponsesError(
                "pricing must be "
                "OpenAIHypothesisEvaluationTokenPricing"
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
            raise OpenAIHypothesisEvaluationResponsesError(
                "client must expose responses.create"
            )

        self._client = client
        self._max_output_tokens = (
            max_output_tokens
        )
        self._pricing = pricing

    def invoke(
        self,
        invocation: HypothesisEvaluationModelInvocation,
    ) -> HypothesisEvaluationModelResult:
        if not isinstance(
            invocation,
            HypothesisEvaluationModelInvocation,
        ):
            raise OpenAIHypothesisEvaluationResponsesError(
                "invocation must be "
                "HypothesisEvaluationModelInvocation"
            )

        if (
            self._reasoning_effort
            is not None
            and invocation.temperature
            is not None
        ):
            raise OpenAIHypothesisEvaluationResponsesError(
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
            raise OpenAIHypothesisEvaluationResponsesError(
                "sealed instruction must be UTF-8"
            ) from exc

        call: dict[
            str,
            object,
        ] = {
            "model": (
                self._model_id
            ),
            "instructions": (
                instruction
            ),
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
            raise OpenAIHypothesisEvaluationResponsesError(
                "response status is not completed"
            )

        returned_model_id = _require_text(
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
            raise OpenAIHypothesisEvaluationResponsesError(
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
            pricing=(
                self._pricing
            ),
        )

        return HypothesisEvaluationModelResult(
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
            cost_usd=(
                cost_usd
            ),
            api_request_id=(
                request_id
            ),
        )
