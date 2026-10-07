"""Composition of OpenAI SDK client with Horizon typed-planner adapter.

This module performs dependency wiring only.

The caller explicitly supplies:

- API key;
- model identifier;
- reasoning configuration;
- output-token bound;
- pricing;
- request timeout.

SDK automatic retries are disabled so one Horizon typed-planner
execution corresponds to one provider request attempt.

This module does not:

- read environment variables;
- make a Responses request during composition;
- choose a model;
- retry;
- fall back between providers;
- compile an InvestigationPlan;
- execute investigation operations;
- mutate Horizon truth.
"""

from __future__ import annotations

import math

from openai import OpenAI

from horizon.investigation.providers.openai_responses import (
    OpenAIResponsesTypedPlannerModel,
    OpenAITypedPlannerTokenPricing,
)


class OpenAITypedPlannerClientCompositionError(
    ValueError
):
    """OpenAI typed-planner client composition is invalid."""


def _require_api_key(
    api_key: object,
) -> str:
    if (
        not isinstance(
            api_key,
            str,
        )
        or not api_key.strip()
    ):
        raise OpenAITypedPlannerClientCompositionError(
            "api_key must be a nonempty string"
        )

    return api_key


def _require_timeout(
    timeout_seconds: object,
) -> float:
    if (
        isinstance(
            timeout_seconds,
            bool,
        )
        or not isinstance(
            timeout_seconds,
            (
                int,
                float,
            ),
        )
    ):
        raise OpenAITypedPlannerClientCompositionError(
            "timeout must be numeric"
        )

    timeout = float(
        timeout_seconds
    )

    if (
        not math.isfinite(
            timeout
        )
        or timeout <= 0
    ):
        raise OpenAITypedPlannerClientCompositionError(
            "timeout must be positive and finite"
        )

    return timeout


def build_openai_typed_planner_model(
    *,
    api_key: str,
    model_id: str,
    reasoning_effort: str | None,
    max_output_tokens: int,
    pricing: OpenAITypedPlannerTokenPricing,
    timeout_seconds: float,
) -> OpenAIResponsesTypedPlannerModel:
    """Build one explicitly configured OpenAI typed-planner model."""

    validated_api_key = (
        _require_api_key(
            api_key
        )
    )

    validated_timeout = (
        _require_timeout(
            timeout_seconds
        )
    )

    client = OpenAI(
        api_key=validated_api_key,
        max_retries=0,
        timeout=validated_timeout,
    )

    return (
        OpenAIResponsesTypedPlannerModel(
            client=client,
            model_id=model_id,
            reasoning_effort=(
                reasoning_effort
            ),
            max_output_tokens=(
                max_output_tokens
            ),
            pricing=pricing,
        )
    )
