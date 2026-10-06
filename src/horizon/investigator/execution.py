"""Execution orchestration for one Horizon investigation model call.

This module composes already-sealed boundaries:

    InvestigationRequest
        -> InvestigatorModelInvocation
        -> InvestigatorModel
        -> InvestigatorModelResult
        -> strict proposal validation
        -> immutable InvestigatorModelRun

It coordinates exactly one caller-selected model invocation and introduces
no provider selection, repeated provider calls, investigation scheduling,
provider-specific semantics, or Horizon world-model mutation.

A completed model call is always retained as a run record.

A valid proposal may be returned to the caller.

An invalid proposal is recorded and never promoted into a Horizon
proposal object.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from horizon.investigator.middleware import (
    InvestigationRequest,
)
from horizon.investigator.model import (
    InvestigatorModel,
    InvestigatorModelInvocation,
    InvestigatorModelResult,
    InvestigatorModelRun,
    ModelRunValidationResult,
    make_model_invocation,
    make_model_run,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    InvestigationProposalError,
    parse_investigation_proposal,
)


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationExecution:
    invocation: InvestigatorModelInvocation
    result: InvestigatorModelResult
    proposal: InvestigationProposal | None
    run: InvestigatorModelRun


def execute_investigation(
    *,
    model: InvestigatorModel,
    request: InvestigationRequest,
    instruction: bytes,
    temperature: float,
    cost_cap_usd: Decimal,
) -> InvestigationExecution:
    """Execute exactly one investigator call and record its disposition."""

    invocation = make_model_invocation(
        request=request,
        instruction=instruction,
        temperature=temperature,
        cost_cap_usd=cost_cap_usd,
    )

    result = model.invoke(
        invocation
    )

    if (
        result.cost_usd
        > invocation.cost_cap_usd
    ):
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

        return InvestigationExecution(
            invocation=invocation,
            result=result,
            proposal=None,
            run=run,
        )

    try:
        proposal = parse_investigation_proposal(
            request,
            result.output,
        )
    except InvestigationProposalError as exc:
        run = make_model_run(
            invocation=invocation,
            result=result,
            validation_result=(
                ModelRunValidationResult.INVALID
            ),
            rejection_reason=(
                "proposal validation failed: "
                f"{exc}"
            ),
        )

        return InvestigationExecution(
            invocation=invocation,
            result=result,
            proposal=None,
            run=run,
        )

    run = make_model_run(
        invocation=invocation,
        result=result,
        validation_result=(
            ModelRunValidationResult.VALID
        ),
        rejection_reason=None,
    )

    return InvestigationExecution(
        invocation=invocation,
        result=result,
        proposal=proposal,
        run=run,
    )
