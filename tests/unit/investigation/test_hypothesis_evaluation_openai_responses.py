from __future__ import annotations

import base64
import json

from decimal import Decimal
from types import SimpleNamespace

import pytest

from horizon.investigation.hypothesis_evaluation import (
    HypothesisEvaluationVerdict,
)
from horizon.investigation.hypothesis_evaluation_model import (
    HypothesisEvaluationModelValidationResult,
    execute_hypothesis_evaluation_model,
    make_hypothesis_evaluation_model_invocation,
)
from horizon.investigation.providers.openai_hypothesis_evaluation import (
    OpenAIHypothesisEvaluationResponsesError,
    OpenAIHypothesisEvaluationTokenPricing,
    OpenAIResponsesHypothesisEvaluationModel,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
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
        self.calls = []

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


def source_record() -> CanonicalEvidenceRecord:
    identity = (
        "investigation-source-observation:test"
    )

    payload = {
        "commit_sha": (
            "a" * 40
        ),
        "end_line": 2,
        "line_count": 2,
        "lines": [
            {
                "content_base64": (
                    base64.b64encode(
                        b"Prefect is a workflow "
                        b"orchestration framework."
                    ).decode(
                        "ascii"
                    )
                ),
                "line_number": 1,
            },
            {
                "content_base64": (
                    base64.b64encode(
                        b"Use @flow and @task."
                    ).decode(
                        "ascii"
                    )
                ),
                "line_number": 2,
            },
        ],
        "observation_id": identity,
        "operation_kind": "READ_SOURCE",
        "path": "README.md",
        "repository_observation_id": (
            "git-observation:test"
        ),
        "source_blob_evidence_id": (
            "git-blob-evidence:test"
        ),
        "source_object_id": (
            "b" * 40
        ),
        "start_line": 1,
    }

    return CanonicalEvidenceRecord(
        evidence_id=identity,
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload=json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )


def metadata_record() -> CanonicalEvidenceRecord:
    return CanonicalEvidenceRecord(
        evidence_id="evidence:metadata",
        evidence_kind="GIT_BLOB_EVIDENCE",
        canonical_payload=(
            '{"hidden":"body"}'
        ),
    )


def request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary "
            "software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(
            metadata_record(),
            source_record(),
        ),
        request_id=(
            "semantic-gap-followup-investigation-request:test"
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


def proposal(
    value: InvestigationRequest,
):
    return parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_HYPOTHESIS",
            "question_id": (
                value.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "hypothesis": (
                "The repository primarily implements "
                "workflow orchestration software."
            ),
            "test_questions": [
                (
                    "Does the declared purpose support "
                    "workflow orchestration?"
                ),
            ],
        },
    )


def invocation(
    *,
    temperature=None,
    cost_cap=Decimal(
        "0.200000"
    ),
):
    value = request()

    return (
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=proposal(
                value
            ),
            instruction=(
                b"Evaluate only against the visible "
                b"evidence and return structured output."
            ),
            temperature=temperature,
            cost_cap_usd=cost_cap,
        )
    )


def evaluation_output():
    value = request()
    proposed = proposal(
        value
    )

    return {
        "request_id": (
            value.request_id
        ),
        "question_id": (
            value.question_id
        ),
        "source_proposal_id": (
            proposed.proposal_id
        ),
        "verdict": "SUPPORTED",
        "supporting_evidence_ids": [
            (
                "investigation-source-observation:test"
            ),
        ],
        "contradicting_evidence_ids": [],
        "missing_evidence_questions": [],
    }


def usage(
    *,
    input_tokens=1000,
    cached_tokens=100,
    cache_write_tokens=50,
    output_tokens=100,
):
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_tokens_details=(
            SimpleNamespace(
                cached_tokens=cached_tokens,
                cache_write_tokens=(
                    cache_write_tokens
                ),
            )
        ),
    )


def completed_response(
    *,
    output=None,
    model="gpt-6-astra",
    request_id="req-eval-test",
    usage_value=None,
):
    if output is None:
        output = evaluation_output()

    if usage_value is None:
        usage_value = usage()

    return SimpleNamespace(
        status="completed",
        model=model,
        _request_id=request_id,
        output_text=json.dumps(
            output,
            sort_keys=True,
        ),
        usage=usage_value,
    )


def pricing():
    return (
        OpenAIHypothesisEvaluationTokenPricing(
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


def adapter(
    client,
    *,
    reasoning_effort="high",
):
    return (
        OpenAIResponsesHypothesisEvaluationModel(
            client=client,
            model_id="gpt-6-astra",
            reasoning_effort=(
                reasoning_effort
            ),
            max_output_tokens=4096,
            pricing=pricing(),
        )
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

    assert (
        call["model"]
        == "gpt-6-astra"
    )

    assert (
        call["reasoning"]
        == {
            "effort": "high",
        }
    )

    assert (
        call[
            "max_output_tokens"
        ]
        == 4096
    )

    assert (
        call["store"]
        is False
    )


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


def test_adapter_sends_compact_evaluation_input() -> None:
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
            "request"
        ][
            "source_proposal_id"
        ]
        == value.source_proposal.proposal_id
    )

    encoded = json.dumps(
        payload,
        sort_keys=True,
    )

    assert (
        '"canonical_payload"'
        not in encoded
    )

    assert (
        '"hidden":"body"'
        not in encoded
    )

    source = next(
        item
        for item
        in payload[
            "request"
        ][
            "evidence_records"
        ]
        if item[
            "evidence_kind"
        ]
        == (
            "INVESTIGATION_SOURCE_OBSERVATION"
        )
    )

    assert (
        source[
            "source_excerpt"
        ][
            "lines"
        ][0][
            "text"
        ]
        == (
            "Prefect is a workflow "
            "orchestration framework."
        )
    )


def test_adapter_uses_strict_evaluation_schema() -> None:
    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        invocation()
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
        == (
            "horizon_hypothesis_evidence_evaluation"
        )
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

    assert (
        schema[
            "properties"
        ][
            "verdict"
        ][
            "enum"
        ]
        == [
            "SUPPORTED",
            "CONTRADICTED",
            "STILL_INCOMPLETE",
        ]
    )


def test_reasoning_model_omits_temperature() -> None:
    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        invocation(
            temperature=None
        )
    )

    assert (
        "temperature"
        not in client.responses.calls[
            0
        ]
    )


def test_reasoning_model_rejects_temperature() -> None:
    client = FakeClient(
        completed_response()
    )

    with pytest.raises(
        OpenAIHypothesisEvaluationResponsesError,
        match="temperature",
    ):
        adapter(
            client
        ).invoke(
            invocation(
                temperature=0.1
            )
        )


def test_adapter_returns_provider_result_and_usage() -> None:
    client = FakeClient(
        completed_response()
    )

    result = adapter(
        client
    ).invoke(
        invocation()
    )

    assert (
        result.provider
        == "OPENAI"
    )

    assert (
        result.model_id
        == "gpt-6-astra"
    )

    assert (
        result.api_request_id
        == "req-eval-test"
    )

    assert (
        result.input_tokens
        == 1000
    )

    assert (
        result.output_tokens
        == 100
    )

    assert (
        result.cost_usd
        == Decimal(
            "0.014225"
        )
    )

    assert (
        dict(
            result.output
        )
        == evaluation_output()
    )


def test_execute_returns_valid_typed_non_authoritative_evaluation() -> None:
    value = request()
    proposed = proposal(
        value
    )

    client = FakeClient(
        completed_response()
    )

    execution = (
        execute_hypothesis_evaluation_model(
            model=adapter(
                client
            ),
            request=value,
            source_proposal=proposed,
            instruction=(
                b"Evaluate only against the visible "
                b"evidence and return structured output."
            ),
            temperature=None,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )
    )

    assert (
        execution.run.validation_result
        is HypothesisEvaluationModelValidationResult
        .VALID
    )

    assert (
        execution.run.rejection_reason
        is None
    )

    assert (
        execution.evaluation
        is not None
    )

    assert (
        execution.evaluation.verdict
        is HypothesisEvaluationVerdict
        .SUPPORTED
    )

    assert not hasattr(
        execution.evaluation,
        "claim_id",
    )

    assert not hasattr(
        execution.evaluation,
        "assessment_id",
    )

    assert not hasattr(
        execution.evaluation,
        "world_model_assertion_id",
    )


def test_invalid_evaluation_output_fails_closed() -> None:
    output = evaluation_output()

    output[
        "supporting_evidence_ids"
    ] = [
        "evidence:not-in-request",
    ]

    client = FakeClient(
        completed_response(
            output=output
        )
    )

    value = request()

    execution = (
        execute_hypothesis_evaluation_model(
            model=adapter(
                client
            ),
            request=value,
            source_proposal=proposal(
                value
            ),
            instruction=b"Evaluate.",
            temperature=None,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )
    )

    assert (
        execution.run.validation_result
        is HypothesisEvaluationModelValidationResult
        .INVALID
    )

    assert (
        execution.evaluation
        is None
    )

    assert (
        "validation failed"
        in execution.run.rejection_reason
    )


def test_actual_cost_above_cap_fails_closed() -> None:
    client = FakeClient(
        completed_response(
            usage_value=usage(
                input_tokens=100_000,
                cached_tokens=0,
                cache_write_tokens=0,
                output_tokens=10_000,
            )
        )
    )

    value = request()

    execution = (
        execute_hypothesis_evaluation_model(
            model=adapter(
                client
            ),
            request=value,
            source_proposal=proposal(
                value
            ),
            instruction=b"Evaluate.",
            temperature=None,
            cost_cap_usd=Decimal(
                "0.010000"
            ),
        )
    )

    assert (
        execution.run.validation_result
        is HypothesisEvaluationModelValidationResult
        .INVALID
    )

    assert (
        execution.evaluation
        is None
    )

    assert (
        "cost exceeded"
        in execution.run.rejection_reason
    )


def test_non_completed_response_is_rejected() -> None:
    response = completed_response()

    response.status = "incomplete"

    with pytest.raises(
        OpenAIHypothesisEvaluationResponsesError,
        match="status",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            invocation()
        )


def test_missing_request_id_is_rejected() -> None:
    response = completed_response(
        request_id="",
    )

    with pytest.raises(
        OpenAIHypothesisEvaluationResponsesError,
        match="request id",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            invocation()
        )


def test_non_json_output_is_rejected() -> None:
    response = completed_response()

    response.output_text = "not-json"

    with pytest.raises(
        OpenAIHypothesisEvaluationResponsesError,
        match="JSON",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            invocation()
        )


def test_non_object_output_is_rejected() -> None:
    response = completed_response()

    response.output_text = "[]"

    with pytest.raises(
        OpenAIHypothesisEvaluationResponsesError,
        match="object",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            invocation()
        )


def test_cached_and_cache_write_tokens_cannot_exceed_input() -> None:
    response = completed_response(
        usage_value=usage(
            input_tokens=10,
            cached_tokens=8,
            cache_write_tokens=5,
            output_tokens=1,
        )
    )

    with pytest.raises(
        OpenAIHypothesisEvaluationResponsesError,
        match="input tokens",
    ):
        adapter(
            FakeClient(
                response
            )
        ).invoke(
            invocation()
        )


def test_provider_schema_does_not_delegate_duplicate_enforcement() -> None:
    client = FakeClient(
        completed_response()
    )

    adapter(
        client
    ).invoke(
        invocation()
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
        value,
    ):
        if isinstance(
            value,
            dict,
        ):
            yield value

            for child in value.values():
                yield from walk(
                    child
                )

        elif isinstance(
            value,
            list,
        ):
            for child in value:
                yield from walk(
                    child
                )

    objects = tuple(
        walk(
            schema
        )
    )

    assert all(
        "uniqueItems"
        not in value
        for value
        in objects
    )
