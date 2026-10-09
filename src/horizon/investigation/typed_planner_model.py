"""Provider-neutral model boundary for semantic-gap typed planning.

This module allows exactly one caller-selected model invocation to propose
typed investigation bindings for an already-accepted semantic-gap
investigation proposal.

The boundary records:

- exact sealed instruction bytes;
- strict typed-planner schema hash;
- canonical input identity;
- exact provider-returned model identity;
- token usage;
- monetary cost;
- provider API request identity;
- canonical raw-output identity;
- validation result and rejection reason.

A model result is never Horizon truth.

This module does not:

- select a provider;
- construct provider clients;
- retry;
- fall back to another provider;
- compile an InvestigationPlan;
- execute investigation operations;
- mutate the World Model.
"""

from __future__ import annotations

from horizon.investigation.typed_planner_request_view import (
    make_typed_planner_request_view,
)

import hashlib
import json
import math

from collections.abc import Mapping
from dataclasses import (
    dataclass,
    fields,
    is_dataclass,
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    Protocol,
    runtime_checkable,
)

from horizon.investigation.typed_planner import (
    SemanticGapTypedPlannerError,
    SemanticGapTypedPlannerOutput,
    parse_semantic_gap_typed_planner_output,
    semantic_gap_typed_planner_schema,
)
from horizon.investigation.typed_planner_semantics import (
    TypedPlannerOperationSemanticsContract,
    semantic_gap_typed_planner_operation_semantics,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    InvestigationProposalKind,
)


class SemanticGapTypedPlannerModelError(
    ValueError
):
    """Typed-planner model invocation or run is invalid."""


class SemanticGapTypedPlannerValidationResult(
    str,
    Enum,
):
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(
    frozen=True,
    slots=True,
)
class SemanticGapTypedPlannerModelInvocation:
    request: InvestigationRequest
    proposal: InvestigationProposal

    instruction: bytes
    temperature: float | None
    max_plan_total_seconds: int
    cost_cap_usd: Decimal

    instruction_hash: str
    schema_hash: str

    operation_semantics: (
        TypedPlannerOperationSemanticsContract
    )
    operation_semantics_id: str

    canonical_input_hash: str

    invocation_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class SemanticGapTypedPlannerModelResult:
    provider: str
    model_id: str

    output: Mapping[
        str,
        Any,
    ]

    input_tokens: int
    output_tokens: int

    cost_usd: Decimal
    api_request_id: str | None


@dataclass(
    frozen=True,
    slots=True,
)
class SemanticGapTypedPlannerModelRun:
    cost_usd: Decimal
    cost_cap_usd: Decimal

    provider: str
    model_id: str
    temperature: float | None

    instruction_hash: str
    schema_hash: str
    operation_semantics_id: str

    canonical_input_hash: str
    canonical_output_hash: str

    input_tokens: int
    output_tokens: int

    api_request_id: str | None

    validation_result: (
        SemanticGapTypedPlannerValidationResult
    )

    rejection_reason: str | None

    invocation_id: str
    run_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class SemanticGapTypedPlannerExecution:
    invocation: (
        SemanticGapTypedPlannerModelInvocation
    )

    result: SemanticGapTypedPlannerModelResult

    planner_output: (
        SemanticGapTypedPlannerOutput
        | None
    )

    run: SemanticGapTypedPlannerModelRun


@runtime_checkable
class SemanticGapTypedPlannerModel(
    Protocol,
):
    """One provider-neutral semantic-gap typed planner."""

    def invoke(
        self,
        invocation: (
            SemanticGapTypedPlannerModelInvocation
        ),
    ) -> SemanticGapTypedPlannerModelResult:
        ...


def _canonicalize(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        Decimal,
    ):
        if not value.is_finite():
            raise SemanticGapTypedPlannerModelError(
                "decimal values must be finite"
            )

        return str(
            value
        )

    if (
        is_dataclass(
            value
        )
        and not isinstance(
            value,
            type,
        )
    ):
        return {
            field.name: _canonicalize(
                getattr(
                    value,
                    field.name,
                )
            )
            for field
            in fields(
                value
            )
        }

    if isinstance(
        value,
        Mapping,
    ):
        result: dict[
            str,
            Any,
        ] = {}

        for key, item in value.items():
            if not isinstance(
                key,
                str,
            ):
                raise SemanticGapTypedPlannerModelError(
                    "canonical mappings require string keys"
                )

            result[
                key
            ] = _canonicalize(
                item
            )

        return result

    if isinstance(
        value,
        (
            tuple,
            list,
        ),
    ):
        return [
            _canonicalize(
                item
            )
            for item
            in value
        ]

    if value is None or isinstance(
        value,
        (
            str,
            int,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        float,
    ):
        if not math.isfinite(
            value
        ):
            raise SemanticGapTypedPlannerModelError(
                "floating-point values must be finite"
            )

        return value

    raise SemanticGapTypedPlannerModelError(
        "value cannot be represented canonically"
    )


def _canonical_bytes(
    value: Any,
) -> bytes:
    try:
        return json.dumps(
            _canonicalize(
                value
            ),
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=True,
            allow_nan=False,
        ).encode(
            "utf-8"
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise SemanticGapTypedPlannerModelError(
            "value cannot be encoded canonically"
        ) from exc


def _sha256(
    value: bytes,
) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            value
        ).hexdigest()
    )


def _identity(
    prefix: str,
    value: Any,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            _canonical_bytes(
                value
            )
        ).hexdigest()
    )


def _validate_context(
    request: InvestigationRequest,
    proposal: InvestigationProposal,
) -> None:
    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise SemanticGapTypedPlannerModelError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not InvestigationRequestOrigin
        .REPOSITORY_SEMANTIC_GAP
    ):
        raise SemanticGapTypedPlannerModelError(
            "request must be a repository semantic-gap request"
        )

    if request.relationship_id is not None:
        raise SemanticGapTypedPlannerModelError(
            "semantic-gap request may not carry a relationship"
        )

    if not isinstance(
        proposal,
        InvestigationProposal,
    ):
        raise SemanticGapTypedPlannerModelError(
            "proposal must be an InvestigationProposal"
        )

    if (
        proposal.kind
        is not InvestigationProposalKind
        .PROPOSE_INVESTIGATION
    ):
        raise SemanticGapTypedPlannerModelError(
            "typed planner requires PROPOSE_INVESTIGATION"
        )

    if (
        proposal.question_id
        != request.question_id
    ):
        raise SemanticGapTypedPlannerModelError(
            "proposal question does not match request"
        )

    if (
        proposal.relationship_id
        != request.relationship_id
    ):
        raise SemanticGapTypedPlannerModelError(
            "proposal relationship does not match request"
        )


def _validate_instruction(
    instruction: bytes,
) -> None:
    if (
        not isinstance(
            instruction,
            bytes,
        )
        or not instruction
    ):
        raise SemanticGapTypedPlannerModelError(
            "instruction must be nonempty bytes"
        )


def _validate_temperature(
    temperature: float | None,
) -> None:
    if temperature is None:
        return

    if (
        isinstance(
            temperature,
            bool,
        )
        or not isinstance(
            temperature,
            (
                int,
                float,
            ),
        )
    ):
        raise SemanticGapTypedPlannerModelError(
            "temperature must be numeric or None"
        )

    if not math.isfinite(
        float(
            temperature
        )
    ):
        raise SemanticGapTypedPlannerModelError(
            "temperature must be finite"
        )

    if float(
        temperature
    ) < 0:
        raise SemanticGapTypedPlannerModelError(
            "temperature must be nonnegative"
        )


def _validate_cost_cap(
    cost_cap_usd: Decimal,
) -> None:
    if not isinstance(
        cost_cap_usd,
        Decimal,
    ):
        raise SemanticGapTypedPlannerModelError(
            "cost cap must be Decimal"
        )

    if (
        not cost_cap_usd.is_finite()
        or cost_cap_usd <= 0
    ):
        raise SemanticGapTypedPlannerModelError(
            "cost cap must be positive and finite"
        )


def _validate_max_plan_total_seconds(
    max_plan_total_seconds: int,
) -> None:
    if (
        isinstance(
            max_plan_total_seconds,
            bool,
        )
        or not isinstance(
            max_plan_total_seconds,
            int,
        )
        or max_plan_total_seconds <= 0
    ):
        raise SemanticGapTypedPlannerModelError(
            "max plan total seconds must be "
            "a positive integer"
        )


def make_semantic_gap_typed_planner_invocation(
    *,
    request: InvestigationRequest,
    proposal: InvestigationProposal,
    instruction: bytes,
    temperature: float | None,
    max_plan_total_seconds: int,
    cost_cap_usd: Decimal,
) -> SemanticGapTypedPlannerModelInvocation:
    """Create one immutable pre-registered typed-planner invocation."""

    _validate_context(
        request,
        proposal,
    )

    request_view = (
        make_typed_planner_request_view(
            request
        )
    )

    _validate_instruction(
        instruction
    )

    _validate_temperature(
        temperature
    )

    _validate_max_plan_total_seconds(
        max_plan_total_seconds
    )

    _validate_cost_cap(
        cost_cap_usd
    )

    normalized_temperature = (
        None
        if temperature is None
        else float(
            temperature
        )
    )

    instruction_hash = _sha256(
        instruction
    )

    schema = (
        semantic_gap_typed_planner_schema()
    )

    schema_hash = _sha256(
        _canonical_bytes(
            schema
        )
    )

    operation_semantics = (
        semantic_gap_typed_planner_operation_semantics()
    )

    operation_semantics_id = (
        operation_semantics.contract_id
    )

    canonical_input_hash = _sha256(
        _canonical_bytes(
            {
                "request": request_view,
                "proposal": proposal,
                "instruction_hash": (
                    instruction_hash
                ),
                "schema_hash": (
                    schema_hash
                ),
                "operation_semantics": (
                    operation_semantics
                ),
                "operation_semantics_id": (
                    operation_semantics_id
                ),
                "temperature": (
                    normalized_temperature
                ),
                "max_plan_total_seconds": (
                    max_plan_total_seconds
                ),
                "cost_cap_usd": (
                    str(
                        cost_cap_usd
                    )
                ),
            }
        )
    )

    invocation_id = _identity(
        "semantic-gap-typed-planner-invocation:",
        {
            "request_id": (
                request.request_id
            ),
            "request_view_id": (
                request_view.view_id
            ),
            "proposal_id": (
                proposal.proposal_id
            ),
            "instruction_hash": (
                instruction_hash
            ),
            "schema_hash": (
                schema_hash
            ),
            "operation_semantics_id": (
                operation_semantics_id
            ),
            "canonical_input_hash": (
                canonical_input_hash
            ),
            "temperature": (
                normalized_temperature
            ),
            "max_plan_total_seconds": (
                max_plan_total_seconds
            ),
            "cost_cap_usd": (
                str(
                    cost_cap_usd
                )
            ),
        },
    )

    return (
        SemanticGapTypedPlannerModelInvocation(
            request=request,
            proposal=proposal,
            instruction=instruction,
            temperature=(
                normalized_temperature
            ),
            max_plan_total_seconds=(
                max_plan_total_seconds
            ),
            cost_cap_usd=(
                cost_cap_usd
            ),
            instruction_hash=(
                instruction_hash
            ),
            schema_hash=schema_hash,
            operation_semantics=(
                operation_semantics
            ),
            operation_semantics_id=(
                operation_semantics_id
            ),
            canonical_input_hash=(
                canonical_input_hash
            ),
            invocation_id=(
                invocation_id
            ),
        )
    )


def _validate_result(
    result: SemanticGapTypedPlannerModelResult,
) -> None:
    if not isinstance(
        result,
        SemanticGapTypedPlannerModelResult,
    ):
        raise SemanticGapTypedPlannerModelError(
            "result must be SemanticGapTypedPlannerModelResult"
        )

    if (
        not isinstance(
            result.provider,
            str,
        )
        or not result.provider.strip()
    ):
        raise SemanticGapTypedPlannerModelError(
            "provider must be nonempty"
        )

    if (
        not isinstance(
            result.model_id,
            str,
        )
        or not result.model_id.strip()
    ):
        raise SemanticGapTypedPlannerModelError(
            "model id must be nonempty"
        )

    if not isinstance(
        result.output,
        Mapping,
    ):
        raise SemanticGapTypedPlannerModelError(
            "model output must be an object"
        )

    _canonical_bytes(
        result.output
    )

    for name, value in (
        (
            "input_tokens",
            result.input_tokens,
        ),
        (
            "output_tokens",
            result.output_tokens,
        ),
    ):
        if (
            isinstance(
                value,
                bool,
            )
            or not isinstance(
                value,
                int,
            )
            or value < 0
        ):
            raise SemanticGapTypedPlannerModelError(
                f"{name} must be a nonnegative integer"
            )

    if not isinstance(
        result.cost_usd,
        Decimal,
    ):
        raise SemanticGapTypedPlannerModelError(
            "model cost must be Decimal"
        )

    if (
        not result.cost_usd.is_finite()
        or result.cost_usd < 0
    ):
        raise SemanticGapTypedPlannerModelError(
            "model cost must be nonnegative and finite"
        )

    if (
        result.api_request_id is not None
        and (
            not isinstance(
                result.api_request_id,
                str,
            )
            or not result.api_request_id.strip()
        )
    ):
        raise SemanticGapTypedPlannerModelError(
            "API request id must be nonempty when present"
        )


def _make_run(
    *,
    invocation: (
        SemanticGapTypedPlannerModelInvocation
    ),
    result: SemanticGapTypedPlannerModelResult,
    validation_result: (
        SemanticGapTypedPlannerValidationResult
    ),
    rejection_reason: str | None,
) -> SemanticGapTypedPlannerModelRun:
    _validate_result(
        result
    )

    if (
        validation_result
        is SemanticGapTypedPlannerValidationResult
        .VALID
    ):
        if rejection_reason is not None:
            raise SemanticGapTypedPlannerModelError(
                "valid run may not have rejection reason"
            )
    else:
        if (
            not isinstance(
                rejection_reason,
                str,
            )
            or not rejection_reason.strip()
        ):
            raise SemanticGapTypedPlannerModelError(
                "invalid run requires rejection reason"
            )

    canonical_output_hash = _sha256(
        _canonical_bytes(
            result.output
        )
    )

    run_id = _identity(
        "semantic-gap-typed-planner-run:",
        {
            "invocation_id": (
                invocation.invocation_id
            ),
            "provider": (
                result.provider
            ),
            "model_id": (
                result.model_id
            ),
            "operation_semantics_id": (
                invocation.operation_semantics_id
            ),
            "canonical_output_hash": (
                canonical_output_hash
            ),
            "input_tokens": (
                result.input_tokens
            ),
            "output_tokens": (
                result.output_tokens
            ),
            "cost_usd": (
                str(
                    result.cost_usd
                )
            ),
            "api_request_id": (
                result.api_request_id
            ),
            "validation_result": (
                validation_result.value
            ),
            "rejection_reason": (
                rejection_reason
            ),
        },
    )

    return SemanticGapTypedPlannerModelRun(
        cost_usd=(
            result.cost_usd
        ),
        cost_cap_usd=(
            invocation.cost_cap_usd
        ),
        provider=result.provider,
        model_id=result.model_id,
        temperature=(
            invocation.temperature
        ),
        instruction_hash=(
            invocation.instruction_hash
        ),
        schema_hash=(
            invocation.schema_hash
        ),
        operation_semantics_id=(
            invocation.operation_semantics_id
        ),
        canonical_input_hash=(
            invocation.canonical_input_hash
        ),
        canonical_output_hash=(
            canonical_output_hash
        ),
        input_tokens=(
            result.input_tokens
        ),
        output_tokens=(
            result.output_tokens
        ),
        api_request_id=(
            result.api_request_id
        ),
        validation_result=(
            validation_result
        ),
        rejection_reason=(
            rejection_reason
        ),
        invocation_id=(
            invocation.invocation_id
        ),
        run_id=run_id,
    )


def execute_semantic_gap_typed_planner(
    *,
    model: SemanticGapTypedPlannerModel,
    request: InvestigationRequest,
    proposal: InvestigationProposal,
    instruction: bytes,
    temperature: float | None,
    max_plan_total_seconds: int,
    cost_cap_usd: Decimal,
) -> SemanticGapTypedPlannerExecution:
    """Execute exactly one caller-selected typed-planner model call."""

    invocation = (
        make_semantic_gap_typed_planner_invocation(
            request=request,
            proposal=proposal,
            instruction=instruction,
            temperature=temperature,
            max_plan_total_seconds=(
                max_plan_total_seconds
            ),
            cost_cap_usd=(
                cost_cap_usd
            ),
        )
    )

    result = model.invoke(
        invocation
    )

    _validate_result(
        result
    )

    if (
        result.cost_usd
        > invocation.cost_cap_usd
    ):
        run = _make_run(
            invocation=invocation,
            result=result,
            validation_result=(
                SemanticGapTypedPlannerValidationResult
                .INVALID
            ),
            rejection_reason=(
                "actual model cost exceeded "
                "pre-registered cost cap"
            ),
        )

        return (
            SemanticGapTypedPlannerExecution(
                invocation=invocation,
                result=result,
                planner_output=None,
                run=run,
            )
        )

    try:
        planner_output = (
            parse_semantic_gap_typed_planner_output(
                request=request,
                proposal=proposal,
                raw=result.output,
            )
        )
    except SemanticGapTypedPlannerError as exc:
        run = _make_run(
            invocation=invocation,
            result=result,
            validation_result=(
                SemanticGapTypedPlannerValidationResult
                .INVALID
            ),
            rejection_reason=(
                "planner output validation failed: "
                + str(
                    exc
                )
            ),
        )

        return (
            SemanticGapTypedPlannerExecution(
                invocation=invocation,
                result=result,
                planner_output=None,
                run=run,
            )
        )

    aggregate_max_seconds = sum(
        binding.draft.max_seconds
        for binding
        in planner_output.bindings
    )

    if (
        aggregate_max_seconds
        > invocation.max_plan_total_seconds
    ):
        run = _make_run(
            invocation=invocation,
            result=result,
            validation_result=(
                SemanticGapTypedPlannerValidationResult
                .INVALID
            ),
            rejection_reason=(
                "planner output aggregate max_seconds "
                "exceeds pre-registered plan time budget"
            ),
        )

        return (
            SemanticGapTypedPlannerExecution(
                invocation=invocation,
                result=result,
                planner_output=None,
                run=run,
            )
        )

    run = _make_run(
        invocation=invocation,
        result=result,
        validation_result=(
            SemanticGapTypedPlannerValidationResult
            .VALID
        ),
        rejection_reason=None,
    )

    return (
        SemanticGapTypedPlannerExecution(
            invocation=invocation,
            result=result,
            planner_output=(
                planner_output
            ),
            run=run,
        )
    )
