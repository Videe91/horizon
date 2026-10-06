from __future__ import annotations

import json

from decimal import Decimal
from types import SimpleNamespace

import pytest

from horizon.investigator.middleware import (
    InvestigationRequest,
)
from horizon.investigator.model import (
    InvestigatorModel,
    InvestigatorModelInvocation,
    make_model_invocation,
)
from horizon.investigator.providers.openai_responses import (
    OpenAIResponsesAdapterError,
    OpenAIResponsesInvestigatorModel,
    OpenAITokenPricing,
)


def _request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "world-model-open-question:test"
        ),
        question=(
            "Who owns responsibility for "
            "the retry eligibility decision?"
        ),
        relationship_id=(
            "world-model-relationship:test"
        ),
        relationship_kind="CONFLICT",
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:test"
        ),
    )


def _invocation(
    *,
    temperature: float | None = None,
    cost_cap_usd: Decimal = Decimal("1.000000"),
) -> InvestigatorModelInvocation:
    return make_model_invocation(
        request=_request(),
        instruction=(
            b"AI proposes. Horizon verifies. "
            b"Evidence changes knowledge."
        ),
        temperature=temperature,
        cost_cap_usd=cost_cap_usd,
    )


def _proposal(
    request: InvestigationRequest,
) -> dict[str, object]:
    return {
        "type": "DECLARE_INSUFFICIENT_EVIDENCE",
        "question_id": request.question_id,
        "relationship_id": (
            request.relationship_id
        ),
        "assertion_ids": list(
            request.assertion_ids
        ),
        "claim_ids": list(
            request.claim_ids
        ),
        "assessment_ids": list(
            request.assessment_ids
        ),
        "evidence_reference_ids": list(
            request.evidence_reference_ids
        ),
        "missing_evidence_questions": [
            "Which component owns the decision?",
        ],
    }


def _usage(
    *,
    input_tokens: int = 1000,
    cached_tokens: int = 100,
    cache_write_tokens: int = 200,
    output_tokens: int = 100,
):
    return SimpleNamespace(
        input_tokens=input_tokens,
        input_tokens_details=SimpleNamespace(
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        ),
        output_tokens=output_tokens,
    )


def _completed_response(
    *,
    request: InvestigationRequest,
    model: str = "gpt-6-astra",
    request_id: str = "req_openai_test",
    response_id: str = "resp_openai_test",
):
    return SimpleNamespace(
        id=response_id,
        _request_id=request_id,
        model=model,
        status="completed",
        output_text=json.dumps(
            {
                "proposal": _proposal(
                    request
                ),
            },
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
        usage=_usage(),
    )


class FakeResponses:
    def __init__(
        self,
        response,
    ) -> None:
        self.response = response
        self.calls: list[
            dict[str, object]
        ] = []

    def create(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.response


class FakeOpenAIClient:
    def __init__(
        self,
        response,
    ) -> None:
        self.responses = FakeResponses(
            response
        )


def _pricing() -> OpenAITokenPricing:
    return OpenAITokenPricing(
        input_per_million=Decimal("10.00"),
        cached_input_per_million=Decimal("1.00"),
        cache_write_per_million=Decimal("12.50"),
        output_per_million=Decimal("50.00"),
    )


def _adapter(
    client,
) -> OpenAIResponsesInvestigatorModel:
    return OpenAIResponsesInvestigatorModel(
        client=client,
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=_pricing(),
    )


def test_adapter_satisfies_shared_investigator_model_port() -> None:
    request = _request()

    client = FakeOpenAIClient(
        _completed_response(
            request=request
        )
    )

    adapter = _adapter(
        client
    )

    assert isinstance(
        adapter,
        InvestigatorModel,
    )


def test_adapter_makes_exactly_one_responses_api_call() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    assert len(
        client.responses.calls
    ) == 1


def test_adapter_sends_configured_model_and_reasoning_effort() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    call = client.responses.calls[0]

    assert call["model"] == (
        "gpt-6-astra"
    )

    assert call["reasoning"] == {
        "effort": "high",
    }

    assert call["max_output_tokens"] == 4096


def test_adapter_sends_exact_sealed_instruction() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    call = client.responses.calls[0]

    assert call["instructions"] == (
        invocation.instruction.decode(
            "utf-8"
        )
    )


def test_adapter_sends_canonical_bounded_request_as_input() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    call = client.responses.calls[0]

    assert isinstance(
        call["input"],
        str,
    )

    payload = json.loads(
        call["input"]
    )

    assert payload[
        "request_id"
    ] == invocation.request.request_id

    assert payload[
        "question_id"
    ] == invocation.request.question_id

    assert payload[
        "relationship_id"
    ] == invocation.request.relationship_id

    assert payload[
        "assertions"
    ] == []

    assert payload[
        "claims"
    ] == []

    assert payload[
        "assessments"
    ] == []

    assert payload[
        "evidence_records"
    ] == []


def test_adapter_uses_strict_structured_output_wrapper() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    call = client.responses.calls[0]

    assert "text" in call

    format_spec = (
        call[
            "text"
        ][
            "format"
        ]
    )

    assert format_spec[
        "type"
    ] == "json_schema"

    assert format_spec[
        "strict"
    ] is True

    assert format_spec[
        "name"
    ] == "horizon_investigation_proposal"

    schema = format_spec[
        "schema"
    ]

    assert schema[
        "type"
    ] == "object"

    assert schema[
        "required"
    ] == [
        "proposal",
    ]

    assert schema[
        "additionalProperties"
    ] is False

    proposal_schema = (
        schema[
            "properties"
        ][
            "proposal"
        ]
    )

    assert len(
        proposal_schema[
            "anyOf"
        ]
    ) == 4

    proposal_types = {
        variant[
            "properties"
        ][
            "type"
        ][
            "const"
        ]
        for variant
        in proposal_schema[
            "anyOf"
        ]
    }

    assert proposal_types == {
        "PROPOSE_INVESTIGATION",
        "PROPOSE_HYPOTHESIS",
        "REFINE_OBJECT",
        "DECLARE_INSUFFICIENT_EVIDENCE",
    }


def test_reasoning_request_omits_temperature_when_invocation_omits_it() -> None:
    invocation = _invocation(
        temperature=None
    )

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    call = client.responses.calls[0]

    assert "temperature" not in call


def test_reasoning_request_rejects_numeric_temperature_before_api_call() -> None:
    invocation = _invocation(
        temperature=0.0
    )

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    with pytest.raises(
        OpenAIResponsesAdapterError,
        match=(
            "temperature must be omitted "
            "when reasoning effort is configured"
        ),
    ):
        adapter.invoke(
            invocation
        )

    assert client.responses.calls == []


def test_adapter_disables_response_storage_explicitly() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    call = client.responses.calls[0]

    assert call["store"] is False


def test_adapter_returns_exact_response_model_and_http_request_id() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request,
            model="gpt-6-astra-returned-id",
            request_id="req_exact_123",
        )
    )

    adapter = _adapter(
        client
    )

    result = adapter.invoke(
        invocation
    )

    assert result.provider == "OPENAI"

    assert result.model_id == (
        "gpt-6-astra-returned-id"
    )

    assert result.api_request_id == (
        "req_exact_123"
    )


def test_adapter_unwraps_only_the_proposal_object() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    result = adapter.invoke(
        invocation
    )

    assert result.output == _proposal(
        invocation.request
    )


def test_adapter_records_provider_token_usage() -> None:
    invocation = _invocation()

    response = _completed_response(
        request=invocation.request
    )

    response.usage = _usage(
        input_tokens=1234,
        cached_tokens=234,
        cache_write_tokens=100,
        output_tokens=321,
    )

    client = FakeOpenAIClient(
        response
    )

    result = _adapter(
        client
    ).invoke(
        invocation
    )

    assert result.input_tokens == 1234
    assert result.output_tokens == 321


def test_adapter_costs_ordinary_cached_write_and_output_tokens_separately() -> None:
    invocation = _invocation()

    response = _completed_response(
        request=invocation.request
    )

    response.usage = _usage(
        input_tokens=1000,
        cached_tokens=100,
        cache_write_tokens=200,
        output_tokens=100,
    )

    client = FakeOpenAIClient(
        response
    )

    result = _adapter(
        client
    ).invoke(
        invocation
    )

    # ordinary input:
    #   1000 - 100 cached - 200 cache-write
    #   = 700 tokens
    #
    # 700 * $10 / 1M       = $0.0070
    # 100 * $1 / 1M        = $0.0001
    # 200 * $12.50 / 1M    = $0.0025
    # 100 * $50 / 1M       = $0.0050
    #
    # total                 = $0.0146

    assert result.cost_usd == (
        Decimal("0.014600")
    )


def test_negative_ordinary_input_token_count_fails_closed() -> None:
    invocation = _invocation()

    response = _completed_response(
        request=invocation.request
    )

    response.usage = _usage(
        input_tokens=100,
        cached_tokens=80,
        cache_write_tokens=30,
        output_tokens=10,
    )

    client = FakeOpenAIClient(
        response
    )

    with pytest.raises(
        OpenAIResponsesAdapterError,
        match="input token accounting is inconsistent",
    ):
        _adapter(
            client
        ).invoke(
            invocation
        )


def test_non_completed_response_fails_closed() -> None:
    invocation = _invocation()

    response = _completed_response(
        request=invocation.request
    )

    response.status = "incomplete"

    client = FakeOpenAIClient(
        response
    )

    with pytest.raises(
        OpenAIResponsesAdapterError,
        match="response status is not completed",
    ):
        _adapter(
            client
        ).invoke(
            invocation
        )


@pytest.mark.parametrize(
    "output_text",
    (
        "",
        "not-json",
        "[]",
        '{"proposal": null}',
        '{"wrong": {}}',
        '{"proposal": {}, "extra": true}',
    ),
)
def test_malformed_structured_output_fails_closed(
    output_text: str,
) -> None:
    invocation = _invocation()

    response = _completed_response(
        request=invocation.request
    )

    response.output_text = output_text

    client = FakeOpenAIClient(
        response
    )

    with pytest.raises(
        OpenAIResponsesAdapterError
    ):
        _adapter(
            client
        ).invoke(
            invocation
        )


def test_missing_http_request_id_fails_closed() -> None:
    invocation = _invocation()

    response = _completed_response(
        request=invocation.request
    )

    response._request_id = None

    client = FakeOpenAIClient(
        response
    )

    with pytest.raises(
        OpenAIResponsesAdapterError,
        match="HTTP request id",
    ):
        _adapter(
            client
        ).invoke(
            invocation
        )


def test_adapter_is_model_configurable_not_astra_hardwired() -> None:
    invocation = _invocation()

    response = _completed_response(
        request=invocation.request,
        model="gpt-6.1-sol",
    )

    client = FakeOpenAIClient(
        response
    )

    adapter = OpenAIResponsesInvestigatorModel(
        client=client,
        model_id="gpt-6.1-sol",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=OpenAITokenPricing(
            input_per_million=Decimal("2.00"),
            cached_input_per_million=Decimal("0.10"),
            cache_write_per_million=Decimal("2.50"),
            output_per_million=Decimal("10.00"),
        ),
    )

    result = adapter.invoke(
        invocation
    )

    call = client.responses.calls[0]

    assert call["model"] == (
        "gpt-6.1-sol"
    )

    assert result.model_id == (
        "gpt-6.1-sol"
    )


def test_strict_output_schema_contains_no_unsupported_unique_items() -> None:
    invocation = _invocation()

    client = FakeOpenAIClient(
        _completed_response(
            request=invocation.request
        )
    )

    adapter = _adapter(
        client
    )

    adapter.invoke(
        invocation
    )

    schema = (
        client.responses.calls[0]
        ["text"]
        ["format"]
        ["schema"]
    )

    def walk(
        value,
    ):
        if isinstance(
            value,
            dict,
        ):
            for key, item in value.items():
                yield key
                yield from walk(
                    item
                )

        elif isinstance(
            value,
            list,
        ):
            for item in value:
                yield from walk(
                    item
                )

    keys = tuple(
        walk(
            schema
        )
    )

    assert "uniqueItems" not in keys
