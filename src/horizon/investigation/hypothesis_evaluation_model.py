"""Provider-neutral model boundary for hypothesis evidence evaluation.

The full InvestigationRequest remains Horizon's internal authority.
The model-facing view contains:

- exact semantic-gap and hypothesis identity;
- every evidence identity, kind, payload hash, and payload size;
- exact readable source lines only for first-class READ_SOURCE evidence.

Non-source canonical evidence bodies are deliberately omitted from the
provider input. They remain present in the immutable internal request.

This boundary cannot create claims, epistemic assessments, World Model
assertions, or semantic-gap closure.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import (
    Protocol,
    runtime_checkable,
)

from horizon.investigation.hypothesis_evaluation import (
    HypothesisEvidenceEvaluation,
    HypothesisEvaluationError,
    hypothesis_evaluation_schema,
    parse_hypothesis_evaluation,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
)


class HypothesisEvaluationModelError(
    ValueError
):
    """A hypothesis-evaluation model invocation is invalid."""


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationSourceLineView:
    line_number: int
    text: str


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationSourceExcerptView:
    path: str
    start_line: int
    end_line: int

    lines: tuple[
        HypothesisEvaluationSourceLineView,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationEvidenceView:
    evidence_id: str
    evidence_kind: str

    canonical_payload_sha256: str
    canonical_payload_bytes: int

    source_excerpt: (
        HypothesisEvaluationSourceExcerptView
        | None
    )


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationRequestView:
    request_id: str

    question_id: str
    question: str

    semantic_gap_id: str
    semantic_gap_section: str

    source_proposal_id: str
    hypothesis: str
    test_questions: tuple[
        str,
        ...,
    ]

    evidence_records: tuple[
        HypothesisEvaluationEvidenceView,
        ...,
    ]

    view_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationModelInvocation:
    request: InvestigationRequest
    source_proposal: InvestigationProposal

    request_view: (
        HypothesisEvaluationRequestView
    )

    instruction: bytes
    temperature: float | None
    cost_cap_usd: Decimal

    instruction_hash: str
    schema_hash: str
    canonical_input_hash: str

    invocation_id: str


SOURCE_OBSERVATION_EVIDENCE_KIND = (
    "INVESTIGATION_SOURCE_OBSERVATION"
)


def _canonical_bytes(
    value: object,
) -> bytes:
    return json.dumps(
        value,
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
    value: object,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            _canonical_bytes(
                value
            )
        ).hexdigest()
    )


def _proposal_kind(
    proposal: InvestigationProposal,
) -> str:
    value = getattr(
        proposal.kind,
        "value",
        proposal.kind,
    )

    if not isinstance(
        value,
        str,
    ):
        raise HypothesisEvaluationModelError(
            "source proposal kind is invalid"
        )

    return value


def _require_nonempty_text(
    value: object,
    *,
    field: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise HypothesisEvaluationModelError(
            field
            + " must be nonempty text"
        )

    return value


def _validate_context(
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
) -> tuple[
    str,
    tuple[
        str,
        ...,
    ],
]:
    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise HypothesisEvaluationModelError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not InvestigationRequestOrigin
        .REPOSITORY_SEMANTIC_GAP
    ):
        raise HypothesisEvaluationModelError(
            "request must be a repository semantic-gap request"
        )

    if (
        request.relationship_id
        is not None
    ):
        raise HypothesisEvaluationModelError(
            "semantic-gap evaluation request may not carry a relationship"
        )

    _require_nonempty_text(
        request.request_id,
        field="request id",
    )

    _require_nonempty_text(
        request.question_id,
        field="question id",
    )

    _require_nonempty_text(
        request.question,
        field="question",
    )

    semantic_gap_id = _require_nonempty_text(
        request.semantic_gap_id,
        field="semantic gap id",
    )

    semantic_gap_section = (
        _require_nonempty_text(
            request.semantic_gap_section,
            field="semantic gap section",
        )
    )

    if not isinstance(
        source_proposal,
        InvestigationProposal,
    ):
        raise HypothesisEvaluationModelError(
            "source proposal must be an InvestigationProposal"
        )

    if (
        _proposal_kind(
            source_proposal
        )
        != "PROPOSE_HYPOTHESIS"
    ):
        raise HypothesisEvaluationModelError(
            "source proposal must be PROPOSE_HYPOTHESIS"
        )

    if (
        source_proposal.question_id
        != request.question_id
    ):
        raise HypothesisEvaluationModelError(
            "source proposal question does not match request"
        )

    if (
        source_proposal.relationship_id
        != request.relationship_id
    ):
        raise HypothesisEvaluationModelError(
            "source proposal relationship does not match request"
        )

    for selected, allowed in (
        (
            source_proposal.assertion_ids,
            request.assertion_ids,
        ),
        (
            source_proposal.claim_ids,
            request.claim_ids,
        ),
        (
            source_proposal.assessment_ids,
            request.assessment_ids,
        ),
        (
            source_proposal.evidence_reference_ids,
            request.evidence_reference_ids,
        ),
    ):
        if not set(
            selected
        ).issubset(
            set(
                allowed
            )
        ):
            raise HypothesisEvaluationModelError(
                "source proposal context is outside the current request"
            )

    hypothesis = _require_nonempty_text(
        source_proposal.hypothesis,
        field="source hypothesis",
    )

    if (
        not isinstance(
            source_proposal.test_questions,
            tuple,
        )
        or not source_proposal.test_questions
    ):
        raise HypothesisEvaluationModelError(
            "source hypothesis must carry test questions"
        )

    test_questions = tuple(
        _require_nonempty_text(
            question,
            field="test question",
        )
        for question
        in source_proposal.test_questions
    )

    if (
        len(
            test_questions
        )
        != len(
            set(
                test_questions
            )
        )
    ):
        raise HypothesisEvaluationModelError(
            "source hypothesis contains duplicate test questions"
        )

    return (
        hypothesis,
        test_questions,
    )


def _source_excerpt(
    record: CanonicalEvidenceRecord,
) -> HypothesisEvaluationSourceExcerptView:
    try:
        payload = json.loads(
            record.canonical_payload
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise HypothesisEvaluationModelError(
            "READ_SOURCE canonical evidence must contain valid JSON"
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise HypothesisEvaluationModelError(
            "READ_SOURCE canonical evidence JSON must be an object"
        )

    if (
        payload.get(
            "operation_kind"
        )
        != "READ_SOURCE"
    ):
        raise HypothesisEvaluationModelError(
            "source observation evidence must represent READ_SOURCE"
        )

    if (
        payload.get(
            "observation_id"
        )
        != record.evidence_id
    ):
        raise HypothesisEvaluationModelError(
            "source observation identity does not match evidence identity"
        )

    path = _require_nonempty_text(
        payload.get(
            "path"
        ),
        field="source path",
    )

    start_line = payload.get(
        "start_line"
    )

    end_line = payload.get(
        "end_line"
    )

    line_count = payload.get(
        "line_count"
    )

    for name, value in (
        (
            "start line",
            start_line,
        ),
        (
            "end line",
            end_line,
        ),
        (
            "line count",
            line_count,
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
            or value <= 0
        ):
            raise HypothesisEvaluationModelError(
                name
                + " must be a positive integer"
            )

    if (
        end_line
        < start_line
    ):
        raise HypothesisEvaluationModelError(
            "source end line precedes start line"
        )

    lines = payload.get(
        "lines"
    )

    if not isinstance(
        lines,
        list,
    ):
        raise HypothesisEvaluationModelError(
            "source lines must be an array"
        )

    expected_numbers = tuple(
        range(
            start_line,
            end_line + 1,
        )
    )

    if (
        len(
            lines
        )
        != line_count
        or line_count
        != len(
            expected_numbers
        )
    ):
        raise HypothesisEvaluationModelError(
            "source line count does not match requested coordinates"
        )

    rendered = []

    for raw_line, expected_number in zip(
        lines,
        expected_numbers,
        strict=True,
    ):
        if not isinstance(
            raw_line,
            dict,
        ):
            raise HypothesisEvaluationModelError(
                "source line must be an object"
            )

        if (
            raw_line.get(
                "line_number"
            )
            != expected_number
        ):
            raise HypothesisEvaluationModelError(
                "source line coordinates are not contiguous"
            )

        encoded = raw_line.get(
            "content_base64"
        )

        if not isinstance(
            encoded,
            str,
        ):
            raise HypothesisEvaluationModelError(
                "source content base64 must be text"
            )

        try:
            content = base64.b64decode(
                encoded,
                validate=True,
            )
        except Exception as exc:
            raise HypothesisEvaluationModelError(
                "source content contains invalid base64"
            ) from exc

        try:
            text = content.decode(
                "utf-8"
            )
        except UnicodeDecodeError as exc:
            raise HypothesisEvaluationModelError(
                "source evidence is not valid UTF-8"
            ) from exc

        rendered.append(
            HypothesisEvaluationSourceLineView(
                line_number=(
                    expected_number
                ),
                text=text,
            )
        )

    return (
        HypothesisEvaluationSourceExcerptView(
            path=path,
            start_line=start_line,
            end_line=end_line,
            lines=tuple(
                rendered
            ),
        )
    )


def _evidence_view(
    record: CanonicalEvidenceRecord,
) -> HypothesisEvaluationEvidenceView:
    if not isinstance(
        record,
        CanonicalEvidenceRecord,
    ):
        raise HypothesisEvaluationModelError(
            "request evidence must contain CanonicalEvidenceRecord values"
        )

    _require_nonempty_text(
        record.evidence_id,
        field="evidence id",
    )

    _require_nonempty_text(
        record.evidence_kind,
        field="evidence kind",
    )

    if (
        not isinstance(
            record.canonical_payload,
            str,
        )
        or not record.canonical_payload
    ):
        raise HypothesisEvaluationModelError(
            "canonical evidence payload must be nonempty text"
        )

    encoded = (
        record.canonical_payload.encode(
            "utf-8"
        )
    )

    excerpt = None

    if (
        record.evidence_kind
        == SOURCE_OBSERVATION_EVIDENCE_KIND
    ):
        excerpt = _source_excerpt(
            record
        )

    return HypothesisEvaluationEvidenceView(
        evidence_id=(
            record.evidence_id
        ),
        evidence_kind=(
            record.evidence_kind
        ),
        canonical_payload_sha256=(
            _sha256(
                encoded
            )
        ),
        canonical_payload_bytes=(
            len(
                encoded
            )
        ),
        source_excerpt=excerpt,
    )


def _source_line_payload(
    value: HypothesisEvaluationSourceLineView,
) -> dict[
    str,
    object,
]:
    return {
        "line_number": (
            value.line_number
        ),
        "text": (
            value.text
        ),
    }


def _source_excerpt_payload(
    value: HypothesisEvaluationSourceExcerptView
    | None,
) -> dict[
    str,
    object,
] | None:
    if value is None:
        return None

    return {
        "path": (
            value.path
        ),
        "start_line": (
            value.start_line
        ),
        "end_line": (
            value.end_line
        ),
        "lines": [
            _source_line_payload(
                line
            )
            for line
            in value.lines
        ],
    }


def _evidence_payload(
    value: HypothesisEvaluationEvidenceView,
) -> dict[
    str,
    object,
]:
    return {
        "evidence_id": (
            value.evidence_id
        ),
        "evidence_kind": (
            value.evidence_kind
        ),
        "canonical_payload_sha256": (
            value.canonical_payload_sha256
        ),
        "canonical_payload_bytes": (
            value.canonical_payload_bytes
        ),
        "source_excerpt": (
            _source_excerpt_payload(
                value.source_excerpt
            )
        ),
    }


def _request_view_payload(
    view: HypothesisEvaluationRequestView,
) -> dict[
    str,
    object,
]:
    return {
        "request_id": (
            view.request_id
        ),
        "question_id": (
            view.question_id
        ),
        "question": (
            view.question
        ),
        "semantic_gap_id": (
            view.semantic_gap_id
        ),
        "semantic_gap_section": (
            view.semantic_gap_section
        ),
        "source_proposal_id": (
            view.source_proposal_id
        ),
        "hypothesis": (
            view.hypothesis
        ),
        "test_questions": list(
            view.test_questions
        ),
        "evidence_records": [
            _evidence_payload(
                record
            )
            for record
            in view.evidence_records
        ],
        "view_id": (
            view.view_id
        ),
    }


def make_hypothesis_evaluation_request_view(
    *,
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
) -> HypothesisEvaluationRequestView:
    """Create the bounded model-facing evidence evaluation view."""

    (
        hypothesis,
        test_questions,
    ) = _validate_context(
        request,
        source_proposal,
    )

    evidence_records = tuple(
        _evidence_view(
            record
        )
        for record
        in request.evidence_records
    )

    evidence_ids = tuple(
        record.evidence_id
        for record
        in evidence_records
    )

    if (
        len(
            evidence_ids
        )
        != len(
            set(
                evidence_ids
            )
        )
    ):
        raise HypothesisEvaluationModelError(
            "request contains duplicate evidence identities"
        )

    identity_payload = {
        "request_id": (
            request.request_id
        ),
        "question_id": (
            request.question_id
        ),
        "question": (
            request.question
        ),
        "semantic_gap_id": (
            request.semantic_gap_id
        ),
        "semantic_gap_section": (
            request.semantic_gap_section
        ),
        "source_proposal_id": (
            source_proposal.proposal_id
        ),
        "hypothesis": (
            hypothesis
        ),
        "test_questions": list(
            test_questions
        ),
        "evidence_records": [
            _evidence_payload(
                record
            )
            for record
            in evidence_records
        ],
    }

    view_id = _identity(
        "hypothesis-evaluation-request-view:",
        identity_payload,
    )

    return HypothesisEvaluationRequestView(
        request_id=(
            request.request_id
        ),
        question_id=(
            request.question_id
        ),
        question=(
            request.question
        ),
        semantic_gap_id=(
            request.semantic_gap_id
        ),
        semantic_gap_section=(
            request.semantic_gap_section
        ),
        source_proposal_id=(
            source_proposal.proposal_id
        ),
        hypothesis=hypothesis,
        test_questions=(
            test_questions
        ),
        evidence_records=(
            evidence_records
        ),
        view_id=view_id,
    )


def _validate_instruction(
    instruction: bytes,
) -> None:
    if (
        not isinstance(
            instruction,
            bytes,
        )
        or not instruction.strip()
    ):
        raise HypothesisEvaluationModelError(
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
        or not math.isfinite(
            float(
                temperature
            )
        )
        or float(
            temperature
        )
        < 0.0
        or float(
            temperature
        )
        > 2.0
    ):
        raise HypothesisEvaluationModelError(
            "temperature must be None or a finite value from 0 through 2"
        )


def _validate_cost_cap(
    cost_cap_usd: Decimal,
) -> None:
    if (
        not isinstance(
            cost_cap_usd,
            Decimal,
        )
        or not cost_cap_usd.is_finite()
        or cost_cap_usd <= 0
    ):
        raise HypothesisEvaluationModelError(
            "cost cap must be a finite positive Decimal"
        )


def canonical_hypothesis_evaluation_model_input(
    invocation: HypothesisEvaluationModelInvocation,
) -> dict[
    str,
    object,
]:
    """Return the exact semantic provider input bound by the invocation."""

    if not isinstance(
        invocation,
        HypothesisEvaluationModelInvocation,
    ):
        raise HypothesisEvaluationModelError(
            "invocation must be a HypothesisEvaluationModelInvocation"
        )

    return {
        "request": (
            _request_view_payload(
                invocation.request_view
            )
        ),
        "instruction_hash": (
            invocation.instruction_hash
        ),
        "schema_hash": (
            invocation.schema_hash
        ),
        "temperature": (
            invocation.temperature
        ),
        "cost_cap_usd": str(
            invocation.cost_cap_usd
        ),
    }


def make_hypothesis_evaluation_model_invocation(
    *,
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
    instruction: bytes,
    temperature: float | None,
    cost_cap_usd: Decimal,
) -> HypothesisEvaluationModelInvocation:
    """Seal one immutable model evaluation invocation."""

    request_view = (
        make_hypothesis_evaluation_request_view(
            request=request,
            source_proposal=source_proposal,
        )
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

    schema_hash = _sha256(
        _canonical_bytes(
            hypothesis_evaluation_schema()
        )
    )

    provisional = (
        HypothesisEvaluationModelInvocation(
            request=request,
            source_proposal=(
                source_proposal
            ),
            request_view=(
                request_view
            ),
            instruction=instruction,
            temperature=(
                normalized_temperature
            ),
            cost_cap_usd=(
                cost_cap_usd
            ),
            instruction_hash=(
                instruction_hash
            ),
            schema_hash=(
                schema_hash
            ),
            canonical_input_hash="",
            invocation_id="",
        )
    )

    canonical_input = (
        canonical_hypothesis_evaluation_model_input(
            provisional
        )
    )

    canonical_input_hash = _sha256(
        _canonical_bytes(
            canonical_input
        )
    )

    invocation_id = _identity(
        "hypothesis-evaluation-model-invocation:",
        {
            "request_id": (
                request.request_id
            ),
            "request_view_id": (
                request_view.view_id
            ),
            "source_proposal_id": (
                source_proposal.proposal_id
            ),
            "instruction_hash": (
                instruction_hash
            ),
            "schema_hash": (
                schema_hash
            ),
            "canonical_input_hash": (
                canonical_input_hash
            ),
            "temperature": (
                normalized_temperature
            ),
            "cost_cap_usd": str(
                cost_cap_usd
            ),
        },
    )

    return (
        HypothesisEvaluationModelInvocation(
            request=request,
            source_proposal=(
                source_proposal
            ),
            request_view=(
                request_view
            ),
            instruction=instruction,
            temperature=(
                normalized_temperature
            ),
            cost_cap_usd=(
                cost_cap_usd
            ),
            instruction_hash=(
                instruction_hash
            ),
            schema_hash=(
                schema_hash
            ),
            canonical_input_hash=(
                canonical_input_hash
            ),
            invocation_id=(
                invocation_id
            ),
        )
    )


class HypothesisEvaluationModelValidationResult(
    str,
    Enum,
):
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationModelResult:
    provider: str
    model_id: str

    output: Mapping[
        str,
        object,
    ]

    input_tokens: int
    output_tokens: int

    cost_usd: Decimal
    api_request_id: str | None


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationModelRun:
    cost_usd: Decimal
    cost_cap_usd: Decimal

    provider: str
    model_id: str
    temperature: float | None

    instruction_hash: str
    schema_hash: str

    canonical_input_hash: str
    canonical_output_hash: str

    input_tokens: int
    output_tokens: int

    api_request_id: str | None

    validation_result: (
        HypothesisEvaluationModelValidationResult
    )

    rejection_reason: str | None

    invocation_id: str
    run_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisEvaluationModelExecution:
    invocation: (
        HypothesisEvaluationModelInvocation
    )

    result: (
        HypothesisEvaluationModelResult
    )

    evaluation: (
        HypothesisEvidenceEvaluation
        | None
    )

    run: (
        HypothesisEvaluationModelRun
    )


@runtime_checkable
class HypothesisEvaluationModel(
    Protocol,
):
    def invoke(
        self,
        invocation: (
            HypothesisEvaluationModelInvocation
        ),
    ) -> HypothesisEvaluationModelResult:
        ...


def _validate_model_result(
    result: HypothesisEvaluationModelResult,
) -> None:
    if not isinstance(
        result,
        HypothesisEvaluationModelResult,
    ):
        raise HypothesisEvaluationModelError(
            "model result must be a "
            "HypothesisEvaluationModelResult"
        )

    _require_nonempty_text(
        result.provider,
        field="provider",
    )

    _require_nonempty_text(
        result.model_id,
        field="model id",
    )

    if not isinstance(
        result.output,
        Mapping,
    ):
        raise HypothesisEvaluationModelError(
            "model output must be an object"
        )

    try:
        _canonical_bytes(
            dict(
                result.output
            )
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise HypothesisEvaluationModelError(
            "model output is not canonical JSON"
        ) from exc

    for name, value in (
        (
            "input tokens",
            result.input_tokens,
        ),
        (
            "output tokens",
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
            raise HypothesisEvaluationModelError(
                name
                + " must be a nonnegative integer"
            )

    if (
        not isinstance(
            result.cost_usd,
            Decimal,
        )
        or not result.cost_usd.is_finite()
        or result.cost_usd < 0
    ):
        raise HypothesisEvaluationModelError(
            "model cost must be a finite "
            "nonnegative Decimal"
        )

    if (
        result.api_request_id
        is not None
    ):
        _require_nonempty_text(
            result.api_request_id,
            field="api request id",
        )


def _make_evaluation_run(
    *,
    invocation: HypothesisEvaluationModelInvocation,
    result: HypothesisEvaluationModelResult,
    validation_result: (
        HypothesisEvaluationModelValidationResult
    ),
    rejection_reason: str | None,
) -> HypothesisEvaluationModelRun:
    canonical_output_hash = _sha256(
        _canonical_bytes(
            dict(
                result.output
            )
        )
    )

    run_id = _identity(
        "hypothesis-evaluation-model-run:",
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
            "canonical_output_hash": (
                canonical_output_hash
            ),
            "input_tokens": (
                result.input_tokens
            ),
            "output_tokens": (
                result.output_tokens
            ),
            "cost_usd": str(
                result.cost_usd
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

    return HypothesisEvaluationModelRun(
        cost_usd=(
            result.cost_usd
        ),
        cost_cap_usd=(
            invocation.cost_cap_usd
        ),
        provider=(
            result.provider
        ),
        model_id=(
            result.model_id
        ),
        temperature=(
            invocation.temperature
        ),
        instruction_hash=(
            invocation.instruction_hash
        ),
        schema_hash=(
            invocation.schema_hash
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


def execute_hypothesis_evaluation_model(
    *,
    model: HypothesisEvaluationModel,
    request: InvestigationRequest,
    source_proposal: InvestigationProposal,
    instruction: bytes,
    temperature: float | None,
    cost_cap_usd: Decimal,
) -> HypothesisEvaluationModelExecution:
    """Execute one model call and validate only a typed evidence evaluation."""

    invocation = (
        make_hypothesis_evaluation_model_invocation(
            request=request,
            source_proposal=(
                source_proposal
            ),
            instruction=instruction,
            temperature=temperature,
            cost_cap_usd=(
                cost_cap_usd
            ),
        )
    )

    if not isinstance(
        model,
        HypothesisEvaluationModel,
    ):
        raise HypothesisEvaluationModelError(
            "model must implement "
            "HypothesisEvaluationModel"
        )

    result = model.invoke(
        invocation
    )

    _validate_model_result(
        result
    )

    if (
        result.cost_usd
        > invocation.cost_cap_usd
    ):
        run = _make_evaluation_run(
            invocation=invocation,
            result=result,
            validation_result=(
                HypothesisEvaluationModelValidationResult
                .INVALID
            ),
            rejection_reason=(
                "actual model cost exceeded "
                "pre-registered cost cap"
            ),
        )

        return (
            HypothesisEvaluationModelExecution(
                invocation=invocation,
                result=result,
                evaluation=None,
                run=run,
            )
        )

    try:
        evaluation = (
            parse_hypothesis_evaluation(
                request=request,
                source_proposal=(
                    source_proposal
                ),
                raw=result.output,
            )
        )
    except HypothesisEvaluationError as exc:
        run = _make_evaluation_run(
            invocation=invocation,
            result=result,
            validation_result=(
                HypothesisEvaluationModelValidationResult
                .INVALID
            ),
            rejection_reason=(
                "hypothesis evaluation validation "
                "failed: "
                + str(
                    exc
                )
            ),
        )

        return (
            HypothesisEvaluationModelExecution(
                invocation=invocation,
                result=result,
                evaluation=None,
                run=run,
            )
        )

    run = _make_evaluation_run(
        invocation=invocation,
        result=result,
        validation_result=(
            HypothesisEvaluationModelValidationResult
            .VALID
        ),
        rejection_reason=None,
    )

    return HypothesisEvaluationModelExecution(
        invocation=invocation,
        result=result,
        evaluation=evaluation,
        run=run,
    )
