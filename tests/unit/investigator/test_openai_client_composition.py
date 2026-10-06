from __future__ import annotations

from decimal import Decimal

import pytest

import horizon.investigator.providers.openai_client as openai_client

from horizon.investigator.providers.openai_responses import (
    OpenAIResponsesInvestigatorModel,
    OpenAITokenPricing,
)


class FakeResponses:
    def create(
        self,
        **kwargs,
    ):
        raise AssertionError(
            "composition must not call responses.create"
        )


class FakeOpenAIClient:
    def __init__(
        self,
    ) -> None:
        self.responses = FakeResponses()


class FakeOpenAIConstructor:
    def __init__(
        self,
    ) -> None:
        self.calls: list[
            dict[str, object]
        ] = []

        self.client = FakeOpenAIClient()

    def __call__(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.client


def _pricing() -> OpenAITokenPricing:
    return OpenAITokenPricing(
        input_per_million=Decimal("10.00"),
        cached_input_per_million=Decimal("1.00"),
        cache_write_per_million=Decimal("12.50"),
        output_per_million=Decimal("50.00"),
    )


def test_live_composition_constructs_openai_client_once(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    openai_client.build_openai_investigator_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
        timeout_seconds=60.0,
    )

    assert len(
        constructor.calls
    ) == 1


def test_sdk_automatic_retries_are_explicitly_disabled(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    openai_client.build_openai_investigator_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
        timeout_seconds=60.0,
    )

    call = constructor.calls[0]

    assert call[
        "max_retries"
    ] == 0


def test_client_timeout_is_explicit_and_bounded(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    openai_client.build_openai_investigator_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
        timeout_seconds=45.0,
    )

    call = constructor.calls[0]

    assert call[
        "timeout"
    ] == 45.0


def test_exact_api_key_is_passed_only_to_sdk_constructor(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    openai_client.build_openai_investigator_model(
        api_key="sk-exact-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
        timeout_seconds=60.0,
    )

    call = constructor.calls[0]

    assert call[
        "api_key"
    ] == "sk-exact-test-secret"


def test_composition_returns_existing_responses_adapter(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = openai_client.build_openai_investigator_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
        timeout_seconds=60.0,
    )

    assert isinstance(
        model,
        OpenAIResponsesInvestigatorModel,
    )


def test_model_configuration_is_forwarded_without_hardcoding(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = openai_client.build_openai_investigator_model(
        api_key="sk-test-secret",
        model_id="gpt-6.1-sol",
        reasoning_effort="medium",
        max_output_tokens=2048,
        pricing=OpenAITokenPricing(
            input_per_million=Decimal("2.00"),
            cached_input_per_million=Decimal("0.10"),
            cache_write_per_million=Decimal("2.50"),
            output_per_million=Decimal("10.00"),
        ),
        timeout_seconds=30.0,
    )

    assert isinstance(
        model,
        OpenAIResponsesInvestigatorModel,
    )

    assert model._model_id == (
        "gpt-6.1-sol"
    )

    assert model._reasoning_effort == (
        "medium"
    )

    assert model._max_output_tokens == 2048


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
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    with pytest.raises(
        openai_client.OpenAIClientCompositionError,
        match="api_key",
    ):
        openai_client.build_openai_investigator_model(
            api_key=api_key,
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=_pricing(),
            timeout_seconds=60.0,
        )

    assert constructor.calls == []


@pytest.mark.parametrize(
    "timeout_seconds",
    (
        0.0,
        -1.0,
    ),
)
def test_nonpositive_timeout_fails_before_client_construction(
    monkeypatch,
    timeout_seconds: float,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    with pytest.raises(
        openai_client.OpenAIClientCompositionError,
        match="timeout",
    ):
        openai_client.build_openai_investigator_model(
            api_key="sk-test-secret",
            model_id="gpt-6-astra",
            reasoning_effort="high",
            max_output_tokens=4096,
            pricing=_pricing(),
            timeout_seconds=timeout_seconds,
        )

    assert constructor.calls == []


def test_composition_does_not_read_environment(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "sk-wrong-environment-secret",
    )

    openai_client.build_openai_investigator_model(
        api_key="sk-explicit-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
        timeout_seconds=60.0,
    )

    assert constructor.calls[0][
        "api_key"
    ] == "sk-explicit-secret"


def test_no_network_call_occurs_during_composition(
    monkeypatch,
) -> None:
    constructor = FakeOpenAIConstructor()

    monkeypatch.setattr(
        openai_client,
        "OpenAI",
        constructor,
    )

    model = openai_client.build_openai_investigator_model(
        api_key="sk-test-secret",
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
        timeout_seconds=60.0,
    )

    assert isinstance(
        model,
        OpenAIResponsesInvestigatorModel,
    )

    assert constructor.client.responses is not None
