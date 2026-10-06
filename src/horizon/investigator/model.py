"""Provider-neutral model boundary for Horizon investigation.

This module defines the contract shared by every investigator provider.

It deliberately knows nothing about provider-specific APIs, HTTP clients,
provider SDKs, routing policy, retries, fallback, or world-model mutation.

The contract preserves:

- the exact bounded InvestigationRequest;
- the exact sealed instruction bytes;
- deterministic instruction and input identities;
- pre-registered monetary cost caps;
- exact provider-returned model identity;
- token usage;
- actual monetary cost;
- canonical model-output identity;
- API request identity when available;
- validation result and rejection reason.

A model result is never Horizon truth.
"""

from __future__ import annotations

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

from horizon.investigator.middleware import (
    InvestigationRequest,
)


class InvestigatorModelRunError(
    ValueError
):
    """An investigator model invocation or run is invalid."""


class ModelRunValidationResult(
    str,
    Enum,
):
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigatorModelInvocation:
    request: InvestigationRequest
    instruction: bytes
    temperature: float
    cost_cap_usd: Decimal

    instruction_hash: str
    canonical_input_hash: str
    invocation_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigatorModelResult:
    provider: str
    model_id: str
    output: Mapping[str, Any]

    input_tokens: int
    output_tokens: int

    cost_usd: Decimal
    api_request_id: str | None


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigatorModelRun:
    cost_usd: Decimal
    cost_cap_usd: Decimal

    provider: str
    model_id: str
    temperature: float

    instruction_hash: str
    canonical_input_hash: str
    canonical_output_hash: str

    input_tokens: int
    output_tokens: int

    api_request_id: str | None

    validation_result: ModelRunValidationResult
    rejection_reason: str | None

    invocation_id: str
    run_id: str


@runtime_checkable
class InvestigatorModel(
    Protocol,
):
    """One provider-neutral investigator model."""

    def invoke(
        self,
        invocation: InvestigatorModelInvocation,
    ) -> InvestigatorModelResult:
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
            raise InvestigatorModelRunError(
                "decimal values must be finite"
            )

        return str(
            value
        )

    if is_dataclass(
        value
    ) and not isinstance(
        value,
        type,
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
                raise InvestigatorModelRunError(
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
            float,
            bool,
        ),
    ):
        if (
            isinstance(
                value,
                float,
            )
            and not math.isfinite(
                value
            )
        ):
            raise InvestigatorModelRunError(
                "floating-point values must be finite"
            )

        return value

    raise InvestigatorModelRunError(
        "value cannot be represented canonically"
    )


def _canonical_bytes(
    value: Any,
) -> bytes:
    try:
        payload = _canonicalize(
            value
        )

        return json.dumps(
            payload,
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
        raise InvestigatorModelRunError(
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


def _validate_request(
    request: InvestigationRequest,
) -> None:
    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise InvestigatorModelRunError(
            "request must be an InvestigationRequest"
        )

    if (
        not isinstance(
            request.request_id,
            str,
        )
        or not request.request_id.strip()
    ):
        raise InvestigatorModelRunError(
            "request identity must be nonempty"
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
        raise InvestigatorModelRunError(
            "instruction must be nonempty bytes"
        )


def _validate_temperature(
    temperature: float,
) -> None:
    if isinstance(
        temperature,
        bool,
    ) or not isinstance(
        temperature,
        (
            int,
            float,
        ),
    ):
        raise InvestigatorModelRunError(
            "temperature must be numeric"
        )

    if not math.isfinite(
        float(
            temperature
        )
    ):
        raise InvestigatorModelRunError(
            "temperature must be finite"
        )

    if float(
        temperature
    ) < 0:
        raise InvestigatorModelRunError(
            "temperature must be nonnegative"
        )


def _validate_cost_cap(
    cost_cap_usd: Decimal,
) -> None:
    if not isinstance(
        cost_cap_usd,
        Decimal,
    ):
        raise InvestigatorModelRunError(
            "cost cap must be Decimal"
        )

    if (
        not cost_cap_usd.is_finite()
        or cost_cap_usd <= 0
    ):
        raise InvestigatorModelRunError(
            "cost cap must be positive and finite"
        )


def make_model_invocation(
    *,
    request: InvestigationRequest,
    instruction: bytes,
    temperature: float,
    cost_cap_usd: Decimal,
) -> InvestigatorModelInvocation:
    """Create one immutable pre-registered model invocation."""

    _validate_request(
        request
    )

    _validate_instruction(
        instruction
    )

    _validate_temperature(
        temperature
    )

    _validate_cost_cap(
        cost_cap_usd
    )

    normalized_temperature = float(
        temperature
    )

    instruction_hash = _sha256(
        instruction
    )

    input_payload = {
        "cost_cap_usd": (
            str(
                cost_cap_usd
            )
        ),
        "instruction_hash": (
            instruction_hash
        ),
        "request": request,
        "temperature": (
            normalized_temperature
        ),
    }

    canonical_input_hash = _sha256(
        _canonical_bytes(
            input_payload
        )
    )

    invocation_id = _identity(
        "investigator-model-invocation:",
        {
            "canonical_input_hash": (
                canonical_input_hash
            ),
            "cost_cap_usd": (
                str(
                    cost_cap_usd
                )
            ),
            "instruction_hash": (
                instruction_hash
            ),
            "request_id": (
                request.request_id
            ),
            "temperature": (
                normalized_temperature
            ),
        },
    )

    return InvestigatorModelInvocation(
        request=request,
        instruction=instruction,
        temperature=normalized_temperature,
        cost_cap_usd=cost_cap_usd,
        instruction_hash=instruction_hash,
        canonical_input_hash=(
            canonical_input_hash
        ),
        invocation_id=invocation_id,
    )


def _validate_invocation(
    invocation: InvestigatorModelInvocation,
) -> None:
    if not isinstance(
        invocation,
        InvestigatorModelInvocation,
    ):
        raise InvestigatorModelRunError(
            "invocation must be an InvestigatorModelInvocation"
        )

    canonical = make_model_invocation(
        request=invocation.request,
        instruction=invocation.instruction,
        temperature=invocation.temperature,
        cost_cap_usd=invocation.cost_cap_usd,
    )

    if canonical != invocation:
        raise InvestigatorModelRunError(
            "invocation identity is invalid"
        )


def _validate_result(
    result: InvestigatorModelResult,
) -> None:
    if not isinstance(
        result,
        InvestigatorModelResult,
    ):
        raise InvestigatorModelRunError(
            "result must be an InvestigatorModelResult"
        )

    if (
        not isinstance(
            result.provider,
            str,
        )
        or not result.provider.strip()
    ):
        raise InvestigatorModelRunError(
            "provider must be nonempty"
        )

    if (
        not isinstance(
            result.model_id,
            str,
        )
        or not result.model_id.strip()
    ):
        raise InvestigatorModelRunError(
            "model id must be nonempty"
        )

    if not isinstance(
        result.output,
        Mapping,
    ):
        raise InvestigatorModelRunError(
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
            raise InvestigatorModelRunError(
                f"{name} must be a nonnegative integer"
            )

    if not isinstance(
        result.cost_usd,
        Decimal,
    ):
        raise InvestigatorModelRunError(
            "model cost must be Decimal"
        )

    if (
        not result.cost_usd.is_finite()
        or result.cost_usd < 0
    ):
        raise InvestigatorModelRunError(
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
        raise InvestigatorModelRunError(
            "API request id must be nonempty when present"
        )


def _validate_run_disposition(
    *,
    validation_result: ModelRunValidationResult,
    rejection_reason: str | None,
) -> None:
    if not isinstance(
        validation_result,
        ModelRunValidationResult,
    ):
        raise InvestigatorModelRunError(
            "validation result must be a "
            "ModelRunValidationResult"
        )

    if (
        validation_result
        is ModelRunValidationResult.VALID
    ):
        if rejection_reason is not None:
            raise InvestigatorModelRunError(
                "valid model run cannot have a rejection reason"
            )

        return

    if (
        not isinstance(
            rejection_reason,
            str,
        )
        or not rejection_reason.strip()
    ):
        raise InvestigatorModelRunError(
            "invalid model run requires a rejection reason"
        )


def make_model_run(
    *,
    invocation: InvestigatorModelInvocation,
    result: InvestigatorModelResult,
    validation_result: ModelRunValidationResult,
    rejection_reason: str | None,
) -> InvestigatorModelRun:
    """Record one immutable model run without changing Horizon truth."""

    _validate_invocation(
        invocation
    )

    _validate_result(
        result
    )

    _validate_run_disposition(
        validation_result=validation_result,
        rejection_reason=rejection_reason,
    )

    if (
        result.cost_usd
        > invocation.cost_cap_usd
        and validation_result
        is ModelRunValidationResult.VALID
    ):
        raise InvestigatorModelRunError(
            "over-cap model result cannot be recorded as valid"
        )

    canonical_output_hash = _sha256(
        _canonical_bytes(
            result.output
        )
    )

    run_payload = {
        "api_request_id": (
            result.api_request_id
        ),
        "canonical_input_hash": (
            invocation.canonical_input_hash
        ),
        "canonical_output_hash": (
            canonical_output_hash
        ),
        "cost_cap_usd": (
            str(
                invocation.cost_cap_usd
            )
        ),
        "cost_usd": (
            str(
                result.cost_usd
            )
        ),
        "input_tokens": (
            result.input_tokens
        ),
        "instruction_hash": (
            invocation.instruction_hash
        ),
        "invocation_id": (
            invocation.invocation_id
        ),
        "model_id": (
            result.model_id
        ),
        "output_tokens": (
            result.output_tokens
        ),
        "provider": (
            result.provider
        ),
        "rejection_reason": (
            rejection_reason
        ),
        "temperature": (
            invocation.temperature
        ),
        "validation_result": (
            validation_result.value
        ),
    }

    run_id = _identity(
        "investigator-model-run:",
        run_payload,
    )

    return InvestigatorModelRun(
        cost_usd=result.cost_usd,
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
        canonical_input_hash=(
            invocation.canonical_input_hash
        ),
        canonical_output_hash=(
            canonical_output_hash
        ),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
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
