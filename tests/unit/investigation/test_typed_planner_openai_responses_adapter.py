from __future__ import annotations

import json

from decimal import Decimal
from types import SimpleNamespace

import pytest

from horizon.investigation.providers.openai_responses import (
    OpenAIResponsesTypedPlannerModel,
    OpenAITypedPlannerTokenPricing,
    OpenAITypedPlannerResponsesError,
)
from horizon.investigation.typed_planner_model import (
    make_semantic_gap_typed_planner_invocation,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)


class FakeResponses:
    def __init__(
        self,
        response,
    ) -> None:
        self.response = response
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

        return self.response


class FakeClient:
    def __init__(
        self,
        response,
    ) -> None:
        self.responses = FakeResponses(
            response
        )


def request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:test"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )


def proposal():
    value = request()

    return parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_INVESTIGATION",
            "question_id": (
                value.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": [
                (
                    "Which source locations provide "
                    "evidence for repository purpose?"
                ),
            ],
        },
    )


def planner_output() -> dict[str, object]:
    value = request()
    proposed = proposal()

    return {
        "proposal_id": (
            proposed.proposal_id
        ),
        "question_id": (
            value.question_id
        ),
        "bindings": [
            {
                "investigation_question": (
                    "Which source locations provide "
                    "evidence for repository purpose?"
                ),
                "step_key": (
                    "find-purpose"
                ),
                "purpose": (
                    "Locate source relevant to repository purpose."
                ),
                "operation": {
                    "type": "SEARCH_SOURCE",
                    "query": "flow",
                    "path_prefix": "src/acme",
                },
                "depends_on_keys": [],
                "expected_information": (
                    "Observed frozen source locations."
                ),
                "max_seconds": 20,
            },
        ],
    }


def invocation(
    *,
    temperature=None,
):
    return (
        make_semantic_gap_typed_planner_invocation(
            request=request(),
            proposal=proposal(),
            instruction=(
                b"Translate only into legal typed "
                b"Horizon investigation operations."
            ),
            temperature=temperature,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )


def usage(
    *,
    input_tokens: int = 1000,
    cached_tokens: int = 100,
    cache_write_tokens: int = 50,
    output_tokens: int = 100,
):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=(
            SimpleNamespace(
                cached_tokens=(
                    cached_tokens
                ),
                cache_write_tokens=(
                    cache_write_tokens
                ),
            )
        ),
    )


def completed_response(
    *,
    output=None,
    model: str = "gpt-6-astra",
    request_id: str = "req-test-1",
):
    if output is None:
        output = planner_output()

    return SimpleNamespace(
        status="completed",
        model=model,
        _request_id=(
            request_id
        ),
        output_text=json.dumps(
            output,
            sort_keys=True,
        ),
        usage=usage(),
    )


def pricing():
    return OpenAITypedPlannerTokenPricing(
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


def adapter(
    client,
    *,
    reasoning_effort="high",
):
    return OpenAIResponsesTypedPlannerModel(
        client=client,
        model_id="gpt-6-astra",
        reasoning_effort=(
            reasoning_effort
        ),
        max_output_tokens=4096,
        pricing=pricing(),
    )


def test_adapter_sends_exact_model_configuration() -> None:
    value = invocation()

    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        value
    )

    call = client.responses.calls[0]

    assert call[
        "model"
    ] == "gpt-6-astra"

    assert call[
        "reasoning"
    ] == {
        "effort": "high",
    }

    assert call[
        "max_output_tokens"
    ] == 4096


def test_adapter_sends_exact_sealed_instruction() -> None:
    value = invocation()

    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        value
    )

    assert (
        client.responses.calls[
            0
        ][
            "instructions"
        ]
        == value.instruction.decode(
            "utf-8"
        )
    )


def test_adapter_sends_bounded_request_and_proposal_as_input() -> None:
    value = invocation()

    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        value
    )

    payload = json.loads(
        client.responses.calls[
            0
        ][
            "input"
        ]
    )

    assert set(
        payload
    ) == {
        "proposal",
        "plan_budget",
        "request",
        "schema_hash",
        "operation_semantics",
        "operation_semantics_id",
    }

    assert (
        payload[
            "plan_budget"
        ]
        == {
            "max_total_seconds": 120,
        }
    )

    assert (
        payload[
            "request"
        ][
            "request_id"
        ]
        == value.request.request_id
    )

    assert (
        payload[
            "proposal"
        ][
            "proposal_id"
        ]
        == value.proposal.proposal_id
    )

    assert (
        payload[
            "schema_hash"
        ]
        == value.schema_hash
    )

    assert (
        payload[
            "operation_semantics_id"
        ]
        == value.operation_semantics_id
    )

    assert (
        payload[
            "operation_semantics"
        ][
            "contract_id"
        ]
        == value.operation_semantics_id
    )


def test_adapter_uses_strict_typed_planner_schema() -> None:
    value = invocation()

    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        value
    )

    format_spec = (
        client.responses.calls[
            0
        ][
            "text"
        ][
            "format"
        ]
    )

    assert (
        format_spec[
            "type"
        ]
        == "json_schema"
    )

    assert (
        format_spec[
            "name"
        ]
        == "horizon_semantic_gap_typed_planner"
    )

    assert (
        format_spec[
            "strict"
        ]
        is True
    )

    schema = format_spec[
        "schema"
    ]

    assert (
        schema[
            "additionalProperties"
        ]
        is False
    )


def test_provider_schema_mechanically_normalizes_const_and_oneof() -> None:
    value = invocation()

    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        value
    )

    schema = (
        client.responses.calls[
            0
        ][
            "text"
        ][
            "format"
        ][
            "schema"
        ]
    )

    def walk(
        item,
    ):
        if isinstance(
            item,
            dict,
        ):
            yield item

            for child in (
                item.values()
            ):
                yield from walk(
                    child
                )

        elif isinstance(
            item,
            list,
        ):
            for child in item:
                yield from walk(
                    child
                )

    objects = tuple(
        walk(
            schema
        )
    )

    assert all(
        "const"
        not in item
        for item
        in objects
    )

    assert all(
        "oneOf"
        not in item
        for item
        in objects
    )


def test_provider_schema_preserves_exact_operation_vocabulary() -> None:
    value = invocation()

    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        value
    )

    schema = (
        client.responses.calls[
            0
        ][
            "text"
        ][
            "format"
        ][
            "schema"
        ]
    )

    alternatives = (
        schema[
            "properties"
        ][
            "bindings"
        ][
            "items"
        ][
            "properties"
        ][
            "operation"
        ][
            "anyOf"
        ]
    )

    operations = {
        alternative[
            "properties"
        ][
            "type"
        ][
            "enum"
        ][
            0
        ]
        for alternative
        in alternatives
    }

    assert operations == {
        "SEARCH_SOURCE",
        "READ_SOURCE",
        "INSPECT_SYMBOL",
        "RESOLVE_CALL",
    }


def test_response_storage_is_explicitly_disabled() -> None:
    value = invocation()

    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        value
    )

    assert (
        client.responses.calls[
            0
        ][
            "store"
        ]
        is False
    )


def test_reasoning_configuration_requires_temperature_omission() -> None:
    value = invocation(
        temperature=0.0
    )

    client = FakeClient(
        completed_response()
    )

    with pytest.raises(
        OpenAITypedPlannerResponsesError,
        match="temperature must be omitted",
    ):
        adapter(
            client
        ).invoke(
            value
        )

    assert (
        client.responses.calls
        == []
    )


def test_non_reasoning_configuration_forwards_temperature() -> None:
    value = invocation(
        temperature=0.0
    )

    client = FakeClient(
        completed_response()
    )

    adapter(
        client,
        reasoning_effort=None,
    ).invoke(
        value
    )

    assert (
        client.responses.calls[
            0
        ][
            "temperature"
        ]
        == 0.0
    )


def test_adapter_returns_exact_provider_model_and_request_id() -> None:
    value = invocation()

    client = FakeClient(
        completed_response(
            model=(
                "gpt-6-astra-returned"
            ),
            request_id=(
                "req-exact-025g"
            ),
        )
    )

    result = adapter(
        client
    ).invoke(
        value
    )

    assert (
        result.provider
        == "OPENAI"
    )

    assert (
        result.model_id
        == "gpt-6-astra-returned"
    )

    assert (
        result.api_request_id
        == "req-exact-025g"
    )


def test_adapter_returns_raw_typed_planner_output() -> None:
    value = invocation()

    output = planner_output()

    client = FakeClient(
        completed_response(
            output=output
        )
    )

    result = adapter(
        client
    ).invoke(
        value
    )

    assert (
        result.output
        == output
    )


def test_adapter_records_exact_token_usage() -> None:
    value = invocation()

    response = (
        completed_response()
    )

    response.usage = usage(
        input_tokens=1234,
        cached_tokens=234,
        cache_write_tokens=100,
        output_tokens=321,
    )

    result = adapter(
        FakeClient(
            response
        )
    ).invoke(
        value
    )

    assert (
        result.input_tokens
        == 1234
    )

    assert (
        result.output_tokens
        == 321
    )


def test_adapter_calculates_token_cost_by_category() -> None:
    value = invocation()

    response = (
        completed_response()
    )

    response.usage = usage(
        input_tokens=1000,
        cached_tokens=100,
        cache_write_tokens=200,
        output_tokens=100,
    )

    result = adapter(
        FakeClient(
            response
        )
    ).invoke(
        value
    )

    assert result.cost_usd == (
        Decimal(
            "0.014600"
        )
    )


def test_inconsistent_token_accounting_fails_closed() -> None:
    value = invocation()

    response = (
        completed_response()
    )

    response.usage = usage(
        input_tokens=100,
        cached_tokens=80,
        cache_write_tokens=30,
        output_tokens=10,
    )

    with pytest.raises(
        OpenAITypedPlannerResponsesError,
        match="token accounting",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            value
        )


def test_non_completed_response_fails_closed() -> None:
    value = invocation()

    response = (
        completed_response()
    )

    response.status = (
        "incomplete"
    )

    with pytest.raises(
        OpenAITypedPlannerResponsesError,
        match="not completed",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            value
        )


@pytest.mark.parametrize(
    "output_text",
    (
        "",
        "not-json",
        "[]",
        "null",
    ),
)
def test_malformed_output_fails_closed(
    output_text: str,
) -> None:
    value = invocation()

    response = (
        completed_response()
    )

    response.output_text = (
        output_text
    )

    with pytest.raises(
        OpenAITypedPlannerResponsesError
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            value
        )


def test_missing_http_request_id_fails_closed() -> None:
    value = invocation()

    response = (
        completed_response()
    )

    response._request_id = None

    with pytest.raises(
        OpenAITypedPlannerResponsesError,
        match="HTTP request id",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            value
        )


def test_adapter_is_model_configurable_not_hardwired() -> None:
    value = invocation()

    client = FakeClient(
        completed_response(
            model="gpt-6.1-sol",
        )
    )

    model = (
        OpenAIResponsesTypedPlannerModel(
            client=client,
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
        )
    )

    result = model.invoke(
        value
    )

    assert (
        client.responses.calls[
            0
        ][
            "model"
        ]
        == "gpt-6.1-sol"
    )

    assert (
        result.model_id
        == "gpt-6.1-sol"
    )
