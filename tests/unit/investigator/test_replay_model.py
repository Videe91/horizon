from __future__ import annotations

from decimal import Decimal

import pytest

from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.model import (
    InvestigatorModelResult,
    make_model_invocation,
)
from horizon.investigator.replay_model import (
    InvestigatorReplayError,
    ReplayThenDelegateInvestigatorModel,
)


def request(
    *,
    request_id: str = "investigation-request:test",
) -> InvestigationRequest:
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
        request_id=request_id,
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )


def invocation(
    *,
    instruction: bytes = b"sealed investigator instruction",
):
    return make_model_invocation(
        request=request(),
        instruction=instruction,
        temperature=None,
        cost_cap_usd=Decimal(
            "0.300000"
        ),
    )


def result(
    *,
    api_request_id: str = "req-paid-one",
) -> InvestigatorModelResult:
    return InvestigatorModelResult(
        provider="OPENAI",
        model_id="gpt-6-astra",
        output={
            "type": "PROPOSE_HYPOTHESIS",
            "question_id": (
                "repository-semantic-gap-question:test"
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "hypothesis": (
                "The repository may maintain software understanding."
            ),
            "test_questions": [
                (
                    "Which frozen source passages "
                    "support that interpretation?"
                ),
            ],
        },
        input_tokens=100,
        output_tokens=50,
        cost_usd=Decimal(
            "0.010000"
        ),
        api_request_id=api_request_id,
    )


class Delegate:
    def __init__(
        self,
        value: InvestigatorModelResult,
    ) -> None:
        self.value = value
        self.calls = []

    def invoke(
        self,
        model_invocation,
    ) -> InvestigatorModelResult:
        self.calls.append(
            model_invocation
        )

        return self.value


def test_exact_first_invocation_replays_without_calling_delegate():
    first = invocation()

    preserved = result()

    delegate = Delegate(
        result(
            api_request_id="req-live-later"
        )
    )

    model = ReplayThenDelegateInvestigatorModel(
        replay_invocation_id=(
            first.invocation_id
        ),
        replay_result=preserved,
        delegate=delegate,
    )

    returned = model.invoke(
        first
    )

    assert returned == preserved
    assert delegate.calls == []
    assert model.replay_consumed is True
    assert model.replay_count == 1
    assert model.delegate_count == 0


def test_mismatched_first_invocation_fails_closed_without_delegate():
    expected = invocation(
        instruction=b"sealed instruction one",
    )

    different = invocation(
        instruction=b"sealed instruction two",
    )

    delegate = Delegate(
        result(
            api_request_id="req-must-not-run"
        )
    )

    model = ReplayThenDelegateInvestigatorModel(
        replay_invocation_id=(
            expected.invocation_id
        ),
        replay_result=result(),
        delegate=delegate,
    )

    with pytest.raises(
        InvestigatorReplayError,
        match=(
            "first investigator invocation "
            "does not match preserved replay authority"
        ),
    ):
        model.invoke(
            different
        )

    assert delegate.calls == []
    assert model.replay_consumed is False
    assert model.replay_count == 0
    assert model.delegate_count == 0


def test_second_invocation_delegates_after_exact_replay():
    first = invocation(
        instruction=b"first sealed instruction",
    )

    second = invocation(
        instruction=b"second sealed instruction",
    )

    preserved = result(
        api_request_id="req-preserved"
    )

    delegated = result(
        api_request_id="req-new-live"
    )

    delegate = Delegate(
        delegated
    )

    model = ReplayThenDelegateInvestigatorModel(
        replay_invocation_id=(
            first.invocation_id
        ),
        replay_result=preserved,
        delegate=delegate,
    )

    assert (
        model.invoke(
            first
        )
        == preserved
    )

    returned = model.invoke(
        second
    )

    assert returned == delegated

    assert delegate.calls == [
        second,
    ]

    assert model.replay_consumed is True
    assert model.replay_count == 1
    assert model.delegate_count == 1


def test_replay_cannot_be_consumed_twice_even_for_same_invocation():
    first = invocation()

    preserved = result(
        api_request_id="req-preserved"
    )

    delegated = result(
        api_request_id="req-delegated"
    )

    delegate = Delegate(
        delegated
    )

    model = ReplayThenDelegateInvestigatorModel(
        replay_invocation_id=(
            first.invocation_id
        ),
        replay_result=preserved,
        delegate=delegate,
    )

    assert (
        model.invoke(
            first
        )
        == preserved
    )

    assert (
        model.invoke(
            first
        )
        == delegated
    )

    assert model.replay_count == 1
    assert model.delegate_count == 1
    assert delegate.calls == [
        first,
    ]
