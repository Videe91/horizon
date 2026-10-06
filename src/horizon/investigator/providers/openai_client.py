"""Composition of the real OpenAI SDK client with Horizon's adapter.

This module performs dependency wiring only.

The caller supplies:

- the API key;
- the OpenAI model identifier;
- reasoning configuration;
- output-token bound;
- pricing;
- request timeout.

Horizon explicitly disables SDK automatic retries so one investigator
execution corresponds to one provider request attempt.

This module does not read environment variables and does not execute a
Responses request during composition.
"""

from __future__ import annotations

import math

from openai import OpenAI

from horizon.investigator.providers.openai_responses import (
    OpenAIResponsesInvestigatorModel,
    OpenAITokenPricing,
)


class OpenAIClientCompositionError(
    ValueError
):
    """OpenAI client composition configuration is invalid."""


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
        raise OpenAIClientCompositionError(
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
        raise OpenAIClientCompositionError(
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
        raise OpenAIClientCompositionError(
            "timeout must be positive and finite"
        )

    return timeout


def build_openai_investigator_model(
    *,
    api_key: str,
    model_id: str,
    reasoning_effort: str | None,
    max_output_tokens: int,
    pricing: OpenAITokenPricing,
    timeout_seconds: float,
) -> OpenAIResponsesInvestigatorModel:
    """Build one caller-configured OpenAI investigator model."""

    validated_api_key = _require_api_key(
        api_key
    )

    validated_timeout = _require_timeout(
        timeout_seconds
    )

    client = OpenAI(
        api_key=validated_api_key,
        max_retries=0,
        timeout=validated_timeout,
    )

    return OpenAIResponsesInvestigatorModel(
        client=client,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        pricing=pricing,
    )
