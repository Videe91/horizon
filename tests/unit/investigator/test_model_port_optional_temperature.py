from __future__ import annotations

from decimal import Decimal

from horizon.investigator.middleware import (
    InvestigationRequest,
)
from horizon.investigator.model import (
    InvestigatorModelResult,
    ModelRunValidationResult,
    make_model_invocation,
    make_model_run,
)


def _request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id="world-model-open-question:test",
        question="Who owns this responsibility?",
        relationship_id="world-model-relationship:test",
        relationship_kind="CONFLICT",
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id="investigation-request:test",
    )


def test_model_invocation_can_explicitly_omit_temperature() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed investigator instruction",
        temperature=None,
        cost_cap_usd=Decimal("1.000000"),
    )

    assert invocation.temperature is None

    assert invocation.invocation_id.startswith(
        "investigator-model-invocation:"
    )


def test_omitted_temperature_is_part_of_invocation_identity() -> None:
    request = _request()

    omitted = make_model_invocation(
        request=request,
        instruction=b"sealed investigator instruction",
        temperature=None,
        cost_cap_usd=Decimal("1.000000"),
    )

    explicit_zero = make_model_invocation(
        request=request,
        instruction=b"sealed investigator instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    assert (
        omitted.invocation_id
        != explicit_zero.invocation_id
    )

    assert (
        omitted.canonical_input_hash
        != explicit_zero.canonical_input_hash
    )


def test_completed_run_records_that_temperature_was_not_sent() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed investigator instruction",
        temperature=None,
        cost_cap_usd=Decimal("1.000000"),
    )

    result = InvestigatorModelResult(
        provider="TEST_PROVIDER",
        model_id="test-model",
        output={
            "type": "DECLARE_INSUFFICIENT_EVIDENCE",
        },
        input_tokens=100,
        output_tokens=20,
        cost_usd=Decimal("0.010000"),
        api_request_id="request-test",
    )

    run = make_model_run(
        invocation=invocation,
        result=result,
        validation_result=(
            ModelRunValidationResult.VALID
        ),
        rejection_reason=None,
    )

    assert run.temperature is None


def test_explicit_numeric_temperature_remains_supported() -> None:
    invocation = make_model_invocation(
        request=_request(),
        instruction=b"sealed investigator instruction",
        temperature=0.0,
        cost_cap_usd=Decimal("1.000000"),
    )

    assert invocation.temperature == 0.0
