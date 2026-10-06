"""Typed autonomous-investigation plans.

The AI may design an investigation.

Horizon owns the execution boundary.

A plan is not evidence, a claim, an epistemic assessment, or world-model
truth. It contains only typed requests for operations Horizon explicitly
supports.

There is deliberately no arbitrary command, shell, script, Python-code,
environment, or generic argument escape hatch in this contract.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import (
    dataclass,
    fields,
    is_dataclass,
)
from enum import Enum
from pathlib import PurePosixPath
from typing import (
    TypeAlias,
)


class InvestigationPlanError(
    ValueError
):
    """An autonomous investigation plan is structurally invalid."""


class InvestigationOperationKind(
    str,
    Enum,
):
    SEARCH_SOURCE = "SEARCH_SOURCE"
    READ_SOURCE = "READ_SOURCE"
    INSPECT_SYMBOL = "INSPECT_SYMBOL"
    RESOLVE_CALL = "RESOLVE_CALL"
    RESOLVE_TYPE = "RESOLVE_TYPE"
    TRACE_HTTP_CONTRACT = "TRACE_HTTP_CONTRACT"


def _require_nonempty(
    value: str,
    *,
    name: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise InvestigationPlanError(
            f"{name} must be nonempty"
        )

    return value


def _require_positive_integer(
    value: int,
    *,
    name: str,
) -> int:
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
        raise InvestigationPlanError(
            f"{name} must be a positive integer"
        )

    return value


def _require_nonnegative_integer(
    value: int,
    *,
    name: str,
) -> int:
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
        raise InvestigationPlanError(
            f"{name} must be a nonnegative integer"
        )

    return value


def _validate_repository_path(
    value: str,
    *,
    name: str,
) -> str:
    _require_nonempty(
        value,
        name=name,
    )

    path = PurePosixPath(
        value
    )

    if path.is_absolute():
        raise InvestigationPlanError(
            f"{name} must be repository-relative"
        )

    if ".." in path.parts:
        raise InvestigationPlanError(
            f"{name} may not escape the repository"
        )

    normalized = str(
        path
    )

    if normalized in {
        "",
        ".",
    }:
        raise InvestigationPlanError(
            f"{name} must identify a repository path"
        )

    return normalized


@dataclass(
    frozen=True,
    slots=True,
)
class SearchSourceOperation:
    query: str
    path_prefix: str | None = None

    @property
    def kind(
        self,
    ) -> InvestigationOperationKind:
        return InvestigationOperationKind.SEARCH_SOURCE

    def __post_init__(
        self,
    ) -> None:
        _require_nonempty(
            self.query,
            name="search query",
        )

        if self.path_prefix is not None:
            _validate_repository_path(
                self.path_prefix,
                name="search path prefix",
            )


@dataclass(
    frozen=True,
    slots=True,
)
class ReadSourceOperation:
    path: str
    start_line: int
    end_line: int

    @property
    def kind(
        self,
    ) -> InvestigationOperationKind:
        return InvestigationOperationKind.READ_SOURCE

    def __post_init__(
        self,
    ) -> None:
        _validate_repository_path(
            self.path,
            name="read path",
        )

        _require_positive_integer(
            self.start_line,
            name="start line",
        )

        _require_positive_integer(
            self.end_line,
            name="end line",
        )

        if (
            self.end_line
            < self.start_line
        ):
            raise InvestigationPlanError(
                "end line must be greater than or equal to start line"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class InspectSymbolOperation:
    path: str
    symbol: str

    @property
    def kind(
        self,
    ) -> InvestigationOperationKind:
        return InvestigationOperationKind.INSPECT_SYMBOL

    def __post_init__(
        self,
    ) -> None:
        _validate_repository_path(
            self.path,
            name="symbol path",
        )

        _require_nonempty(
            self.symbol,
            name="symbol",
        )


@dataclass(
    frozen=True,
    slots=True,
)
class ResolveCallOperation:
    path: str
    line: int
    character: int

    @property
    def kind(
        self,
    ) -> InvestigationOperationKind:
        return InvestigationOperationKind.RESOLVE_CALL

    def __post_init__(
        self,
    ) -> None:
        _validate_repository_path(
            self.path,
            name="call path",
        )

        _require_positive_integer(
            self.line,
            name="line",
        )

        _require_nonnegative_integer(
            self.character,
            name="character",
        )


@dataclass(
    frozen=True,
    slots=True,
)
class ResolveTypeOperation:
    path: str
    line: int
    character: int

    @property
    def kind(
        self,
    ) -> InvestigationOperationKind:
        return InvestigationOperationKind.RESOLVE_TYPE

    def __post_init__(
        self,
    ) -> None:
        _validate_repository_path(
            self.path,
            name="type path",
        )

        _require_positive_integer(
            self.line,
            name="line",
        )

        _require_nonnegative_integer(
            self.character,
            name="character",
        )


@dataclass(
    frozen=True,
    slots=True,
)
class TraceHttpContractOperation:
    client_path: str
    server_path: str
    route_hint: str

    @property
    def kind(
        self,
    ) -> InvestigationOperationKind:
        return InvestigationOperationKind.TRACE_HTTP_CONTRACT

    def __post_init__(
        self,
    ) -> None:
        _validate_repository_path(
            self.client_path,
            name="HTTP client path",
        )

        _validate_repository_path(
            self.server_path,
            name="HTTP server path",
        )

        _require_nonempty(
            self.route_hint,
            name="HTTP route hint",
        )


InvestigationOperation: TypeAlias = (
    SearchSourceOperation
    | ReadSourceOperation
    | InspectSymbolOperation
    | ResolveCallOperation
    | ResolveTypeOperation
    | TraceHttpContractOperation
)


_OPERATION_TYPES = (
    SearchSourceOperation,
    ReadSourceOperation,
    InspectSymbolOperation,
    ResolveCallOperation,
    ResolveTypeOperation,
    TraceHttpContractOperation,
)


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationStepDraft:
    """Model-authored planning data.

    ``step_key`` and ``depends_on_keys`` are local plan labels only.
    They are never Horizon evidence or world-model identifiers.
    """

    step_key: str
    purpose: str
    operation: InvestigationOperation
    depends_on_keys: tuple[
        str,
        ...,
    ]
    expected_information: str
    max_seconds: int

    def __post_init__(
        self,
    ) -> None:
        _require_nonempty(
            self.step_key,
            name="step key",
        )

        _require_nonempty(
            self.purpose,
            name="step purpose",
        )

        if not isinstance(
            self.operation,
            _OPERATION_TYPES,
        ):
            raise InvestigationPlanError(
                "step operation must be a supported typed operation"
            )

        if not isinstance(
            self.depends_on_keys,
            tuple,
        ):
            raise InvestigationPlanError(
                "step dependencies must be a tuple"
            )

        for dependency in self.depends_on_keys:
            _require_nonempty(
                dependency,
                name="dependency step key",
            )

        if (
            len(
                self.depends_on_keys
            )
            != len(
                set(
                    self.depends_on_keys
                )
            )
        ):
            raise InvestigationPlanError(
                "step contains duplicate dependencies"
            )

        if (
            self.step_key
            in self.depends_on_keys
        ):
            raise InvestigationPlanError(
                "step may not depend on itself"
            )

        _require_nonempty(
            self.expected_information,
            name="expected information",
        )

        _require_positive_integer(
            self.max_seconds,
            name="step max seconds",
        )


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationStep:
    source_step_key: str
    purpose: str
    operation: InvestigationOperation
    depends_on_step_ids: tuple[
        str,
        ...,
    ]
    expected_information: str
    max_seconds: int
    step_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationPlan:
    proposal_id: str
    question_id: str
    steps: tuple[
        InvestigationStep,
        ...,
    ]
    max_steps: int
    max_total_seconds: int
    plan_id: str


def _canonicalize(
    value,
):
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if (
        is_dataclass(
            value
        )
        and not isinstance(
            value,
            type,
        )
    ):
        payload = {
            field.name: _canonicalize(
                getattr(
                    value,
                    field.name,
                )
            )
            for field in fields(
                value
            )
        }

        if hasattr(
            value,
            "kind",
        ):
            payload[
                "kind"
            ] = value.kind.value

        return payload

    if isinstance(
        value,
        tuple,
    ):
        return [
            _canonicalize(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        list,
    ):
        return [
            _canonicalize(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        dict,
    ):
        result = {}

        for key, item in value.items():
            if not isinstance(
                key,
                str,
            ):
                raise InvestigationPlanError(
                    "canonical mappings require string keys"
                )

            result[
                key
            ] = _canonicalize(
                item
            )

        return result

    if value is None or isinstance(
        value,
        (
            str,
            int,
            bool,
        ),
    ):
        return value

    raise InvestigationPlanError(
        "plan value cannot be represented canonically"
    )


def _identity(
    prefix: str,
    payload,
) -> str:
    encoded = json.dumps(
        _canonicalize(
            payload
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

    return (
        prefix
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _topological_keys(
    drafts_by_key: dict[
        str,
        InvestigationStepDraft,
    ],
) -> tuple[
    str,
    ...,
]:
    state: dict[
        str,
        int,
    ] = {}

    ordered: list[
        str
    ] = []

    def visit(
        key: str,
    ) -> None:
        marker = state.get(
            key,
            0,
        )

        if marker == 1:
            raise InvestigationPlanError(
                "investigation plan contains a dependency cycle"
            )

        if marker == 2:
            return

        state[
            key
        ] = 1

        draft = drafts_by_key[
            key
        ]

        for dependency in sorted(
            draft.depends_on_keys
        ):
            visit(
                dependency
            )

        state[
            key
        ] = 2

        ordered.append(
            key
        )

    for key in sorted(
        drafts_by_key
    ):
        visit(
            key
        )

    return tuple(
        ordered
    )


def compile_investigation_plan(
    *,
    proposal_id: str,
    question_id: str,
    drafts: tuple[
        InvestigationStepDraft,
        ...,
    ],
    max_steps: int,
    max_total_seconds: int,
) -> InvestigationPlan:
    """Compile model-local plan labels into Horizon-owned identities."""

    _require_nonempty(
        proposal_id,
        name="proposal id",
    )

    _require_nonempty(
        question_id,
        name="question id",
    )

    _require_positive_integer(
        max_steps,
        name="max steps",
    )

    _require_positive_integer(
        max_total_seconds,
        name="max total seconds",
    )

    if not isinstance(
        drafts,
        tuple,
    ):
        raise InvestigationPlanError(
            "drafts must be a tuple"
        )

    if not drafts:
        raise InvestigationPlanError(
            "investigation plan requires at least one step"
        )

    for draft in drafts:
        if not isinstance(
            draft,
            InvestigationStepDraft,
        ):
            raise InvestigationPlanError(
                "plan drafts must contain InvestigationStepDraft values"
            )

    keys = [
        draft.step_key
        for draft in drafts
    ]

    if len(
        set(
            keys
        )
    ) != len(
        keys
    ):
        raise InvestigationPlanError(
            "duplicate step key"
        )

    if len(
        drafts
    ) > max_steps:
        raise InvestigationPlanError(
            "investigation plan exceeds step limit"
        )

    total_seconds = sum(
        draft.max_seconds
        for draft in drafts
    )

    if (
        total_seconds
        > max_total_seconds
    ):
        raise InvestigationPlanError(
            "investigation plan exceeds total time budget"
        )

    drafts_by_key = {
        draft.step_key: draft
        for draft in drafts
    }

    for draft in drafts:
        for dependency in draft.depends_on_keys:
            if dependency not in drafts_by_key:
                raise InvestigationPlanError(
                    "investigation step references unknown dependency"
                )

    ordered_keys = _topological_keys(
        drafts_by_key
    )

    step_ids_by_key: dict[
        str,
        str,
    ] = {}

    compiled_by_key: dict[
        str,
        InvestigationStep,
    ] = {}

    for key in ordered_keys:
        draft = drafts_by_key[
            key
        ]

        dependency_step_ids = tuple(
            sorted(
                step_ids_by_key[
                    dependency
                ]
                for dependency
                in draft.depends_on_keys
            )
        )

        step_payload = {
            "purpose": draft.purpose,
            "operation": draft.operation,
            "depends_on_step_ids": (
                dependency_step_ids
            ),
            "expected_information": (
                draft.expected_information
            ),
            "max_seconds": (
                draft.max_seconds
            ),
        }

        step_id = _identity(
            "investigation-step:",
            step_payload,
        )

        if (
            step_id
            in step_ids_by_key.values()
        ):
            raise InvestigationPlanError(
                "duplicate investigation step identity"
            )

        step = InvestigationStep(
            source_step_key=(
                draft.step_key
            ),
            purpose=draft.purpose,
            operation=draft.operation,
            depends_on_step_ids=(
                dependency_step_ids
            ),
            expected_information=(
                draft.expected_information
            ),
            max_seconds=(
                draft.max_seconds
            ),
            step_id=step_id,
        )

        step_ids_by_key[
            key
        ] = step_id

        compiled_by_key[
            key
        ] = step

    canonical_steps = tuple(
        sorted(
            compiled_by_key.values(),
            key=lambda step: (
                step.step_id
            ),
        )
    )

    plan_payload = {
        "proposal_id": proposal_id,
        "question_id": question_id,
        "steps": canonical_steps,
        "max_steps": max_steps,
        "max_total_seconds": (
            max_total_seconds
        ),
    }

    plan_id = _identity(
        "investigation-plan:",
        plan_payload,
    )

    return InvestigationPlan(
        proposal_id=proposal_id,
        question_id=question_id,
        steps=canonical_steps,
        max_steps=max_steps,
        max_total_seconds=(
            max_total_seconds
        ),
        plan_id=plan_id,
    )
