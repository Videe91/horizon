from __future__ import annotations

import hashlib

from decimal import Decimal

import pytest

from horizon.investigator.middleware import (
    InvestigationRequest,
)
from horizon.investigator.model import (
    InvestigatorModel,
    InvestigatorModelInvocation,
    InvestigatorModelResult,
    InvestigatorModelRunError,
    ModelRunValidationResult,
    make_model_invocation,
    make_model_run,
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


class FakeInvestigatorModel:
    def __init__(
        self,
        result: InvestigatorModelResult,
    ) -> None:
        self.result = result
        self.calls: list[
            InvestigatorModelInvocation
        ] = []

    def invoke(
        self,
        invocation: InvestigatorModelInvocation,
    ) -> InvestigatorModelResult:
        self.calls.append(
            invocation
        )

        return self.result


def _anthropic_result() -> InvestigatorModelResult:
    return InvestigatorModelResult(
        provider="ANTHROPIC",
        model_id="claude-opus-5-5",
        output={
            "type": "REFINE_OBJECT",
            "question_id": (
                "world-model-open-question:test"
            ),
        },
        input_tokens=1200,
        output_tokens=240,
        cost_usd=Decimal("0.087500"),
        api_request_id="anthropic-request-1",
    )


def test_model_port_is_provider_neutral_and_structural() -> None:
    fake = FakeInvestigatorModel(
        _anthropic_result()
    )

    assert isinstance(
        fake,
        InvestigatorModel,
    )


def test_invocation_preserves_exact_instruction_request_and_cost_cap() -> None:
    request = _request()

    instruction = (
        b"AI proposes. Horizon verifies. "
        b"Evidence changes knowledge."
    )

    invocation = make_model_invocation(
        request=request,
        instruction=instruction,
        temperature=0.0,
        cost_cap_usd=Decimal("0.250000"),
    )

    assert invocation.request is request
    assert invocation.instruction == instruction
    assert invocation.temperature == 0.0

    assert invocation.cost_cap_usd == (
        Decimal("0.250000")
    )

    assert invocation.instruction_hash == (
        "sha256:"
        + hashlib.sha256(
            instruction
        ).hexdigest()
    )

    assert invocation.canonical_input_hash.startswith(
        "sha256:"
    )

    assert invocation.invocation_id.startswith(
        "investigator-model-invocation:"
    )


def test_same_invocation_is_content_addressed_deterministically() -> None:
    request = _request()

    kwargs = {
        "request": request,
        "instruction": b"sealed investigator instruction",
        "temperature": 0.0,
        "cost_cap_usd": Decimal("1.000000"),
    }

    first = make_model_invocation(
        **kwargs,
    )

    second = make_model_invocation(
        **kwargs,
    )

    assert first == second


def test_instruction_change_changes_instruction_and_invocation_identity() -> None:
    request = _request()

    first = make_model_invocation(
        request=request,
        instruction=b"instruction A",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    second = make_model_invocation(
        request=request,
        instruction=b"instruction B",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    assert (
        first.instruction_hash
        != second.instruction_hash
    )

    assert (
        first.invocation_id
        != second.invocation_id
    )


def test_fake_model_receives_exact_invocation() -> None:
    result = _anthropic_result()

    fake = FakeInvestigatorModel(
        result
    )

    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    returned = fake.invoke(
        invocation
    )

    assert fake.calls == [
        invocation,
    ]

    assert returned is result


def test_valid_model_run_records_full_provenance() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("0.250000"),
    )

    result = _anthropic_result()

    run = make_model_run(
        invocation=invocation,
        result=result,
        validation_result=(
            ModelRunValidationResult.VALID
        ),
        rejection_reason=None,
    )

    assert run.cost_usd == (
        Decimal("0.087500")
    )

    assert run.cost_cap_usd == (
        Decimal("0.250000")
    )

    assert run.provider == "ANTHROPIC"

    assert run.model_id == (
        "claude-opus-5-5"
    )

    assert run.temperature == 0.0

    assert run.instruction_hash == (
        invocation.instruction_hash
    )

    assert run.canonical_input_hash == (
        invocation.canonical_input_hash
    )

    assert run.canonical_output_hash.startswith(
        "sha256:"
    )

    assert run.input_tokens == 1200
    assert run.output_tokens == 240

    assert run.api_request_id == (
        "anthropic-request-1"
    )

    assert run.validation_result is (
        ModelRunValidationResult.VALID
    )

    assert run.rejection_reason is None

    assert run.run_id.startswith(
        "investigator-model-run:"
    )


def test_output_hash_is_independent_of_mapping_order() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    left = InvestigatorModelResult(
        provider="OPENAI",
        model_id="gpt-6-astra",
        output={
            "type": "PROPOSE_INVESTIGATION",
            "question_id": "question:test",
        },
        input_tokens=100,
        output_tokens=20,
        cost_usd=Decimal("0.010000"),
        api_request_id="openai-request-left",
    )

    right = InvestigatorModelResult(
        provider="OPENAI",
        model_id="gpt-6-astra",
        output={
            "question_id": "question:test",
            "type": "PROPOSE_INVESTIGATION",
        },
        input_tokens=100,
        output_tokens=20,
        cost_usd=Decimal("0.010000"),
        api_request_id="openai-request-right",
    )

    left_run = make_model_run(
        invocation=invocation,
        result=left,
        validation_result=(
            ModelRunValidationResult.VALID
        ),
        rejection_reason=None,
    )

    right_run = make_model_run(
        invocation=invocation,
        result=right,
        validation_result=(
            ModelRunValidationResult.VALID
        ),
        rejection_reason=None,
    )

    assert (
        left_run.canonical_output_hash
        == right_run.canonical_output_hash
    )


def test_invalid_run_requires_rejection_reason() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    with pytest.raises(
        InvestigatorModelRunError
    ):
        make_model_run(
            invocation=invocation,
            result=_anthropic_result(),
            validation_result=(
                ModelRunValidationResult.INVALID
            ),
            rejection_reason=None,
        )


def test_valid_run_rejects_rejection_reason() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    with pytest.raises(
        InvestigatorModelRunError
    ):
        make_model_run(
            invocation=invocation,
            result=_anthropic_result(),
            validation_result=(
                ModelRunValidationResult.VALID
            ),
            rejection_reason=(
                "should not exist"
            ),
        )


@pytest.mark.parametrize(
    "cost_cap",
    (
        Decimal("0"),
        Decimal("-0.01"),
    ),
)
def test_invocation_requires_positive_pre_registered_cost_cap(
    cost_cap: Decimal,
) -> None:
    with pytest.raises(
        InvestigatorModelRunError
    ):
        make_model_invocation(
            request=_request(),
            instruction=b"sealed instruction",
            temperature=0.0,
            cost_cap_usd=cost_cap,
        )


@pytest.mark.parametrize(
    (
        "input_tokens",
        "output_tokens",
    ),
    (
        (-1, 0),
        (0, -1),
    ),
)
def test_negative_token_usage_is_rejected(
    input_tokens: int,
    output_tokens: int,
) -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    result = InvestigatorModelResult(
        provider="ANTHROPIC",
        model_id="claude-opus-5-5",
        output={
            "type": "REFINE_OBJECT",
        },
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal("0.010000"),
        api_request_id=None,
    )

    with pytest.raises(
        InvestigatorModelRunError
    ):
        make_model_run(
            invocation=invocation,
            result=result,
            validation_result=(
                ModelRunValidationResult.VALID
            ),
            rejection_reason=None,
        )


def test_negative_monetary_cost_is_rejected() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    result = InvestigatorModelResult(
        provider="OPENAI",
        model_id="gpt-6-astra",
        output={
            "type": "REFINE_OBJECT",
        },
        input_tokens=100,
        output_tokens=20,
        cost_usd=Decimal("-0.01"),
        api_request_id=None,
    )

    with pytest.raises(
        InvestigatorModelRunError
    ):
        make_model_run(
            invocation=invocation,
            result=result,
            validation_result=(
                ModelRunValidationResult.VALID
            ),
            rejection_reason=None,
        )


def test_over_cap_result_is_recorded_not_hidden() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("0.050000"),
    )

    result = InvestigatorModelResult(
        provider="ANTHROPIC",
        model_id="claude-opus-5-5",
        output={
            "type": "REFINE_OBJECT",
        },
        input_tokens=1000,
        output_tokens=200,
        cost_usd=Decimal("0.060000"),
        api_request_id="request-over-cap",
    )

    run = make_model_run(
        invocation=invocation,
        result=result,
        validation_result=(
            ModelRunValidationResult.INVALID
        ),
        rejection_reason=(
            "actual model cost exceeded "
            "pre-registered cost cap"
        ),
    )

    assert run.cost_usd == (
        Decimal("0.060000")
    )

    assert run.cost_cap_usd == (
        Decimal("0.050000")
    )

    assert run.validation_result is (
        ModelRunValidationResult.INVALID
    )
