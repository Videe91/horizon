from __future__ import annotations

from decimal import Decimal

import pytest

import horizon.investigation.providers.openai_client as openai_client

from horizon.investigation.providers.openai_responses import (
    OpenAIResponsesTypedPlannerModel,
    OpenAITypedPlannerTokenPricing,
)


class FakeResponses:
    def __init__(
        self,
    ) -> None:
        self.calls: list[
            dict[
                str,
                object,
            ]
        ] = []

    def create(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        raise AssertionError(
            "composition must not call responses.create"
        )


class FakeOpenAIClient:
    def __init__(
        self,
    ) -> None:
        self.responses = (
            FakeResponses()
        )


class FakeOpenAIConstructor:
    def __init__(
        self,
    ) -> None:
        self.calls: list[
            dict[
                str,
                object,
            ]
        ] = []

        self.client = (
            FakeOpenAIClient()
        )

    def __call__(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.client


def pricing() -> OpenAITypedPlannerTokenPricing:
    return (
        OpenAITypedPlannerTokenPricing(
            input_per_million=Decimal(
                "10.00"
            ),
            cached_input_per_million=Decimal(
                "1.00"
            ),
            cache_write_per_million=Decimal(
                "12.50"
            ),
            output_per_million=Decimal(
                "50.00"
            ),
        )
    )


def test_composition_constructs_sdk_client_once(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    openai_client.build_openai_typed_planner_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=pricing(),
        timeout_seconds=60.0,
    )

    assert len(
        constructor.calls
    ) == 1


def test_sdk_automatic_retries_are_explicitly_disabled(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    openai_client.build_openai_typed_planner_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=pricing(),
        timeout_seconds=60.0,
    )

    call = constructor.calls[0]

    assert call[
        "max_retries"
    ] == 0


def test_timeout_is_explicit_and_bounded(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    openai_client.build_openai_typed_planner_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=pricing(),
        timeout_seconds=45.0,
    )

    assert (
        constructor.calls[
            0
        ][
            "timeout"
        ]
        == 45.0
    )


def test_exact_api_key_goes_only_to_sdk_constructor(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = (
        openai_client
        .build_openai_typed_planner_model(
            api_key=(
                "sk-exact-secret"
            ),
            model_id=(
                "gpt-6-astra"
            ),
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=pricing(),
            timeout_seconds=60.0,
        )
    )

    assert (
        constructor.calls[
            0
        ][
            "api_key"
        ]
        == "sk-exact-secret"
    )

    assert not hasattr(
        model,
        "_api_key",
    )


def test_composition_returns_025g_adapter(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = (
        openai_client
        .build_openai_typed_planner_model(
            api_key="sk-test-secret",
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=pricing(),
            timeout_seconds=60.0,
        )
    )

    assert isinstance(
        model,
        OpenAIResponsesTypedPlannerModel,
    )


def test_model_configuration_is_forwarded_without_hardcoding(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = (
        openai_client
        .build_openai_typed_planner_model(
            api_key="sk-test-secret",
            model_id="gpt-6.1-sol",
            reasoning_effort="medium",
            max_output_tokens=2048,
            pricing=(
                OpenAITypedPlannerTokenPricing(
                    input_per_million=(
                        Decimal(
                            "2.00"
                        )
                    ),
                    cached_input_per_million=(
                        Decimal(
                            "0.10"
                        )
                    ),
                    cache_write_per_million=(
                        Decimal(
                            "2.50"
                        )
                    ),
                    output_per_million=(
                        Decimal(
                            "10.00"
                        )
                    ),
                )
            ),
            timeout_seconds=30.0,
        )
    )

    assert (
        model._model_id
        == "gpt-6.1-sol"
    )

    assert (
        model._reasoning_effort
        == "medium"
    )

    assert (
        model._max_output_tokens
        == 2048
    )


@pytest.mark.parametrize(
    "api_key",
    (
        "",
        "   ",
    ),
)
def test_blank_api_key_fails_before_client_construction(
    monkeypatch,
    api_key: str,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    with pytest.raises(
        openai_client
        .OpenAITypedPlannerClientCompositionError,
        match="api_key",
    ):
        openai_client.build_openai_typed_planner_model(
            api_key=api_key,
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=pricing(),
            timeout_seconds=60.0,
        )

    assert (
        constructor.calls
        == []
    )


@pytest.mark.parametrize(
    "timeout_seconds",
    (
        0.0,
        -1.0,
        float(
            "inf"
        ),
    ),
)
def test_invalid_timeout_fails_before_client_construction(
    monkeypatch,
    timeout_seconds: float,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    with pytest.raises(
        openai_client
        .OpenAITypedPlannerClientCompositionError,
        match="timeout",
    ):
        openai_client.build_openai_typed_planner_model(
            api_key="sk-test-secret",
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=pricing(),
            timeout_seconds=(
                timeout_seconds
            ),
        )

    assert (
        constructor.calls
        == []
    )


def test_boolean_timeout_is_rejected(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    with pytest.raises(
        openai_client
        .OpenAITypedPlannerClientCompositionError,
        match="timeout",
    ):
        openai_client.build_openai_typed_planner_model(
            api_key="sk-test-secret",
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=pricing(),
            timeout_seconds=True,
        )

    assert (
        constructor.calls
        == []
    )


def test_composition_does_not_read_environment(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "sk-wrong-environment-secret",
    )

    openai_client.build_openai_typed_planner_model(
        api_key="sk-explicit-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=pricing(),
        timeout_seconds=60.0,
    )

    assert (
        constructor.calls[
            0
        ][
            "api_key"
        ]
        == "sk-explicit-secret"
    )


def test_no_network_call_occurs_during_composition(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = (
        openai_client
        .build_openai_typed_planner_model(
            api_key="sk-test-secret",
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=pricing(),
            timeout_seconds=60.0,
        )
    )

    assert isinstance(
        model,
        OpenAIResponsesTypedPlannerModel,
    )

    assert (
        constructor.client.responses.calls
        == []
    )


def test_adapter_and_sdk_client_share_exact_constructed_client(
    monkeypatch,
) -> None:
    constructor = (
        FakeOpenAIConstructor()
    )

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = (
        openai_client
        .build_openai_typed_planner_model(
            api_key="sk-test-secret",
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=pricing(),
            timeout_seconds=60.0,
        )
    )

    assert (
        model._client
        is constructor.client
    )
