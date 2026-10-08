"""Bounded autonomous coordination for repository WHAT_IT_IS understanding.

AI proposes.
Horizon verifies.
Evidence changes knowledge.

This coordinator composes already-certified Horizon authority boundaries.
It does not provide a new model runtime, retry system, or truth path.

The state machine is bounded by:

- investigator rounds;
- hypothesis-testing rounds;
- plan steps;
- plan wall-clock budgets;
- evidence-record bytes;
- total evidence bytes;
- adaptive per-call model budget authority derived from remaining aggregate budget;
- aggregate model cost.

Only canonical READ_SOURCE observations gathered by this coordinator are
currently eligible as material supporting evidence for automatic promotion.

RESOLVE_CALL is deliberately rejected before execution because the current
production tree has no canonical InvestigationCallObservation evidence-record
bridge. That operation may enter this coordinator only after that bridge is
implemented and certified.
"""

from __future__ import annotations

import json
import math

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from time import monotonic

from horizon.investigation.bounded_evidence import (
    bound_search_observation_evidence_record,
)
from horizon.investigation.evidence_records import (
    canonical_search_observation_evidence_record,
    canonical_source_observation_evidence_record,
    canonical_symbol_observation_evidence_record,
)
from horizon.investigation.execution import (
    InvestigationCallObservation,
    InvestigationSearchObservation,
    InvestigationSourceObservation,
    InvestigationSymbolObservation,
    execute_investigation_operation,
)
from horizon.investigation.followup_request import (
    extend_semantic_gap_investigation_request,
)
from horizon.investigation.hypothesis_evaluation import (
    HypothesisEvidenceEvaluation,
    HypothesisEvaluationVerdict,
)
from horizon.investigation.hypothesis_evaluation_model import (
    HypothesisEvaluationModel,
    HypothesisEvaluationModelValidationResult,
    execute_hypothesis_evaluation_model,
)
from horizon.investigation.hypothesis_promotion import (
    materialize_supported_what_it_is_hypothesis,
)
from horizon.investigation.hypothesis_test_planning import (
    bridge_hypothesis_tests_to_typed_planning,
)
from horizon.investigation.plan import (
    InvestigationPlan,
    ReadSourceOperation,
    ResolveCallOperation,
)
from horizon.investigation.proposal_plan import (
    compile_semantic_gap_proposal_plan,
)
from horizon.investigation.semantic_gap import (
    RepositorySemanticGapSection,
    discover_repository_semantic_gaps,
)
from horizon.investigation.typed_planner_model import (
    SemanticGapTypedPlannerModel,
    SemanticGapTypedPlannerValidationResult,
    execute_semantic_gap_typed_planner,
)
from horizon.investigator.execution import (
    execute_investigation,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    compile_semantic_gap_investigation_request,
)
from horizon.investigator.model import (
    InvestigatorModel,
    ModelRunValidationResult,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    InvestigationProposalKind,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)
from horizon.repository.python_index import (
    PythonRepositoryIndex,
)
from horizon.world_model.repository_deterministic import (
    RepositoryDeterministicWorldModel,
)
from horizon.world_model.repository_semantic_store import (
    RepositorySemanticWorldModelStore,
    RepositorySemanticWorldModelStoreError,
)


class RepositorySemanticUnderstandingCoordinatorError(
    ValueError
):
    """The bounded semantic-understanding state machine cannot continue safely."""


class RepositorySemanticUnderstandingDisposition(
    str,
    Enum,
):
    ALREADY_KNOWN = "ALREADY_KNOWN"

    PROMOTED = "PROMOTED"

    EVALUATION_NOT_SUPPORTED = (
        "EVALUATION_NOT_SUPPORTED"
    )

    DECLARED_INSUFFICIENT_EVIDENCE = (
        "DECLARED_INSUFFICIENT_EVIDENCE"
    )

    REFINEMENT_REQUIRED = (
        "REFINEMENT_REQUIRED"
    )

    BOUNDED_STOP = "BOUNDED_STOP"


@dataclass(
    frozen=True,
    slots=True,
)
class RepositorySemanticUnderstandingLimits:
    max_investigator_rounds: int
    max_hypothesis_rounds: int

    max_plan_steps: int
    max_plan_total_seconds: int

    max_evidence_record_bytes: int
    max_total_evidence_bytes: int

    max_total_model_cost_usd: Decimal

    def __post_init__(
        self,
    ) -> None:
        for name, value in (
            (
                "max_investigator_rounds",
                self.max_investigator_rounds,
            ),
            (
                "max_hypothesis_rounds",
                self.max_hypothesis_rounds,
            ),
            (
                "max_plan_steps",
                self.max_plan_steps,
            ),
            (
                "max_plan_total_seconds",
                self.max_plan_total_seconds,
            ),
            (
                "max_evidence_record_bytes",
                self.max_evidence_record_bytes,
            ),
            (
                "max_total_evidence_bytes",
                self.max_total_evidence_bytes,
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
                raise RepositorySemanticUnderstandingCoordinatorError(
                    name
                    + " must be a positive integer"
                )

        value = (
            self.max_total_model_cost_usd
        )

        if (
            not isinstance(
                value,
                Decimal,
            )
            or not value.is_finite()
            or value <= 0
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "max_total_model_cost_usd must be "
                "a positive finite Decimal"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class RepositorySemanticUnderstandingExecution:
    disposition: (
        RepositorySemanticUnderstandingDisposition
    )

    base_model: (
        RepositoryDeterministicWorldModel
    )

    final_model: (
        RepositoryDeterministicWorldModel
    )

    request: InvestigationRequest | None

    proposal: InvestigationProposal | None

    evaluation: (
        HypothesisEvidenceEvaluation
        | None
    )

    investigator_run_ids: tuple[
        str,
        ...,
    ]

    planner_run_ids: tuple[
        str,
        ...,
    ]

    evaluation_run_ids: tuple[
        str,
        ...,
    ]

    operation_observation_ids: tuple[
        str,
        ...,
    ]

    evidence_record_ids: tuple[
        str,
        ...,
    ]

    investigator_rounds_completed: int

    hypothesis_rounds_completed: int

    total_model_cost_usd: Decimal

    persisted_overlay_path: str | None


def _require_instruction(
    value: object,
    *,
    name: str,
) -> bytes:
    if (
        not isinstance(
            value,
            bytes,
        )
        or not value
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            name
            + " must be nonempty bytes"
        )

    return value


def _hypothesis_round_typed_planner_instruction(
    instruction: bytes,
    *,
    current_round: int,
    max_rounds: int,
    source_hypothesis: str,
    source_basis_paths: tuple[str, ...],
) -> bytes:
    """Seal bounded hypothesis-round authority into planner instructions."""

    _require_instruction(
        instruction,
        name=(
            "typed_planner_instruction"
        ),
    )

    if (
        not isinstance(
            source_hypothesis,
            str,
        )
        or not source_hypothesis.strip()
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "source_hypothesis must be nonempty text"
        )

    if (
        not isinstance(
            source_basis_paths,
            tuple,
        )
        or any(
            (
                not isinstance(
                    path,
                    str,
                )
                or not path.strip()
            )
            for path
            in source_basis_paths
        )
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "source_basis_paths must be a tuple "
            "of nonempty paths"
        )

    if (
        len(
            source_basis_paths
        )
        != len(
            set(
                source_basis_paths
            )
        )
        or source_basis_paths
        != tuple(
            sorted(
                source_basis_paths
            )
        )
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "source_basis_paths must be unique "
            "and canonically ordered"
        )

    for name, value in (
        (
            "current_round",
            current_round,
        ),
        (
            "max_rounds",
            max_rounds,
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
            raise RepositorySemanticUnderstandingCoordinatorError(
                name
                + " must be a positive integer"
            )

    if current_round > max_rounds:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "current hypothesis round may not exceed maximum rounds"
        )

    remaining = (
        max_rounds
        - current_round
    )

    final_round = (
        remaining
        == 0
    )

    context = (
        "\n\n"
        "Horizon bounded hypothesis-round execution context:\n"
        "current_hypothesis_round="
        + str(
            current_round
        )
        + "\n"
        "max_hypothesis_rounds="
        + str(
            max_rounds
        )
        + "\n"
        "remaining_hypothesis_rounds_after_this="
        + str(
            remaining
        )
        + "\n"
        "final_hypothesis_round="
        + (
            "true"
            if final_round
            else "false"
        )
        + "\n"
    )

    context += (
        "source_hypothesis="
        + json.dumps(
            source_hypothesis,
            ensure_ascii=True,
            separators=(
                ",",
                ":",
            ),
        )
        + "\n"
        + "source_hypothesis_material_basis_paths="
        + json.dumps(
            list(
                source_basis_paths
            ),
            ensure_ascii=True,
            separators=(
                ",",
                ":",
            ),
        )
        + "\n"
    )

    if final_round:
        context += (
            "final_round_rule="
            "There is no future hypothesis-test replan after this response.\n"
            "final_round_material_evidence_rule="
            "For every exact investigation question, this returned plan "
            "must contain at least one legal READ_SOURCE operation capable "
            "of gathering material source evidence for that question. "
            "SEARCH_SOURCE may not be the only evidence path for any "
            "question on the final round. Dependencies are ordering-only; "
            "SEARCH_SOURCE results cannot dynamically populate a later "
            "operation in the same compiled plan.\n"
            "final_round_source_basis_rule="
            "The source hypothesis and its selected source-backed evidence "
            "basis are supplied above. Metadata or hashes are not semantic "
            "proof. Every path listed in "
            "source_hypothesis_material_basis_paths must be considered for "
            "material READ_SOURCE coverage before final evaluation; when "
            "the hypothesis explicitly depends on such a source, the plan "
            "must read that source rather than relying on its opaque "
            "metadata record.\n"
        )

    else:
        context += (
            "nonfinal_round_rule="
            "Future hypothesis-test replanning remains available within "
            "the sealed round bound. SEARCH_SOURCE may be used for bounded "
            "discovery when exact source coordinates are not yet known.\n"
        )

    return (
        instruction
        + context.encode(
            "utf-8"
        )
    )


def _validate_final_hypothesis_round_material_paths(
    *,
    proposal: InvestigationProposal,
    bindings,
    final_round: bool,
    source_basis_paths: tuple[str, ...],
) -> None:
    """Fail closed when final-round material evidence is not source-complete."""

    if not final_round:
        return

    if (
        not isinstance(
            source_basis_paths,
            tuple,
        )
        or any(
            (
                not isinstance(
                    path,
                    str,
                )
                or not path.strip()
            )
            for path
            in source_basis_paths
        )
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "source_basis_paths must be a tuple "
            "of nonempty paths"
        )

    if (
        len(
            source_basis_paths
        )
        != len(
            set(
                source_basis_paths
            )
        )
        or source_basis_paths
        != tuple(
            sorted(
                source_basis_paths
            )
        )
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "source_basis_paths must be unique "
            "and canonically ordered"
        )

    material_read_bindings = tuple(
        binding
        for binding
        in bindings
        if isinstance(
            binding.draft.operation,
            ReadSourceOperation,
        )
    )

    missing_questions = []

    for question in (
        proposal.investigation_questions
    ):
        has_material_read = any(
            (
                binding.investigation_question
                == question
            )
            for binding
            in material_read_bindings
        )

        if not has_material_read:
            missing_questions.append(
                question
            )

    if missing_questions:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "final hypothesis round requires at least one "
            "READ_SOURCE material-evidence path for every exact "
            "investigation question; missing material path for "
            + str(
                len(
                    missing_questions
                )
            )
            + " question(s): "
            + " | ".join(
                missing_questions
            )
        )

    material_read_paths = {
        binding.draft.operation.path
        for binding
        in material_read_bindings
    }

    missing_source_basis_paths = tuple(
        path
        for path
        in source_basis_paths
        if path not in material_read_paths
    )

    if missing_source_basis_paths:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "final hypothesis round requires READ_SOURCE "
            "coverage for every selected source-backed "
            "hypothesis basis path; missing source basis "
            "path(s): "
            + " | ".join(
                missing_source_basis_paths
            )
        )


def _require_decimal_cost_cap(
    value: object,
    *,
    name: str,
) -> Decimal:
    if (
        not isinstance(
            value,
            Decimal,
        )
        or not value.is_finite()
        or value <= 0
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            name
            + " must be a positive finite Decimal"
        )

    return value


def _require_temperature(
    value: object,
    *,
    name: str,
    allow_none: bool,
) -> float | None:
    if (
        value is None
        and allow_none
    ):
        return None

    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            (
                int,
                float,
            ),
        )
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            name
            + " must be a finite number"
        )

    normalized = float(
        value
    )

    if not math.isfinite(
        normalized
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            name
            + " must be finite"
        )

    return normalized


def _validate_snapshot_identity(
    *,
    observation: GitCommitObservation,
    index: PythonRepositoryIndex,
    base_model: RepositoryDeterministicWorldModel,
) -> None:
    if not isinstance(
        observation,
        GitCommitObservation,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "observation must be a GitCommitObservation"
        )

    if not isinstance(
        index,
        PythonRepositoryIndex,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "index must be a PythonRepositoryIndex"
        )

    if not isinstance(
        base_model,
        RepositoryDeterministicWorldModel,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "base_model must be a "
            "RepositoryDeterministicWorldModel"
        )

    if (
        index.commit_sha
        != observation.commit_sha
        or (
            index.repository_observation_id
            != observation.observation_id
        )
        or (
            base_model.source_commit
            != observation.commit_sha
        )
        or (
            base_model.repository_observation_id
            != observation.observation_id
        )
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "observation, index, and deterministic World Model "
            "must identify the same exact repository snapshot"
        )

    if (
        base_model.what_it_is_assertion_ids
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "base_model must be the deterministic pre-semantic model"
        )


def _evidence_size(
    record: CanonicalEvidenceRecord,
) -> int:
    return len(
        record.canonical_payload.encode(
            "utf-8"
        )
    )


def _validate_evidence_budget(
    records: tuple[
        CanonicalEvidenceRecord,
        ...,
    ],
    *,
    limits: RepositorySemanticUnderstandingLimits,
) -> None:
    if not isinstance(
        records,
        tuple,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "evidence records must be a tuple"
        )

    ids = []

    total = 0

    for record in records:
        if not isinstance(
            record,
            CanonicalEvidenceRecord,
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "every evidence record must be canonical"
            )

        size = _evidence_size(
            record
        )

        if (
            size
            > limits.max_evidence_record_bytes
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "evidence record exceeds coordinator byte limit"
            )

        total += size

        ids.append(
            record.evidence_id
        )

    if len(
        ids
    ) != len(
        set(
            ids
        )
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "evidence records contain duplicate identities"
        )

    if (
        total
        > limits.max_total_evidence_bytes
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "total evidence exceeds coordinator byte limit"
        )


def _remaining_model_budget(
    current: Decimal,
    *,
    limits: RepositorySemanticUnderstandingLimits,
) -> Decimal:
    """Return the exact budget still authorized before the next model call."""

    if not isinstance(
        limits,
        RepositorySemanticUnderstandingLimits,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "limits must be RepositorySemanticUnderstandingLimits"
        )

    if (
        not isinstance(
            current,
            Decimal,
        )
        or not current.is_finite()
        or current < 0
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "current model cost must be a finite nonnegative Decimal"
        )

    maximum = (
        limits.max_total_model_cost_usd
    )

    if current > maximum:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "current model cost already exceeds coordinator budget"
        )

    remaining = (
        maximum
        - current
    )

    if remaining <= 0:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "no model budget remains for another provider call"
        )

    return remaining



def _add_model_cost(
    current: Decimal,
    value: Decimal,
    *,
    limits: RepositorySemanticUnderstandingLimits,
) -> Decimal:
    updated = (
        current
        + value
    )

    if (
        updated
        > limits.max_total_model_cost_usd
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "total model cost exceeded coordinator budget"
        )

    return updated


def _what_it_is_question(
    *,
    index: PythonRepositoryIndex,
    model: RepositoryDeterministicWorldModel,
):
    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    matches = tuple(
        question
        for question
        in gaps.questions
        if (
            question.section
            is RepositorySemanticGapSection
            .WHAT_IT_IS
        )
    )

    if len(
        matches
    ) != 1:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "WHAT_IT_IS must be exactly one open semantic gap"
        )

    return matches[
        0
    ]


def _canonical_operation_evidence(
    observation,
    *,
    limits: RepositorySemanticUnderstandingLimits,
) -> tuple[
    CanonicalEvidenceRecord,
    bool,
]:
    material_source = False

    if isinstance(
        observation,
        InvestigationSearchObservation,
    ):
        record = (
            canonical_search_observation_evidence_record(
                observation
            )
        )

        record = (
            bound_search_observation_evidence_record(
                record,
                max_payload_bytes=(
                    limits.max_evidence_record_bytes
                ),
            )
        )

    elif isinstance(
        observation,
        InvestigationSourceObservation,
    ):
        record = (
            canonical_source_observation_evidence_record(
                observation
            )
        )

        material_source = True

    elif isinstance(
        observation,
        InvestigationSymbolObservation,
    ):
        record = (
            canonical_symbol_observation_evidence_record(
                observation
            )
        )

    elif isinstance(
        observation,
        InvestigationCallObservation,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "InvestigationCallObservation has no canonical "
            "evidence-record bridge"
        )

    else:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "operation returned an unsupported observation type"
        )

    if (
        _evidence_size(
            record
        )
        > limits.max_evidence_record_bytes
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "operation evidence exceeds coordinator byte limit"
        )

    return (
        record,
        material_source,
    )


def _execute_plan(
    *,
    repository: Path,
    observation: GitCommitObservation,
    plan: InvestigationPlan,
    limits: RepositorySemanticUnderstandingLimits,
    pyright_typeserver: str | Path | None,
) -> tuple[
    tuple[
        CanonicalEvidenceRecord,
        ...,
    ],
    tuple[
        str,
        ...,
    ],
    tuple[
        str,
        ...,
    ],
]:
    if len(
        plan.steps
    ) > limits.max_plan_steps:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "compiled plan exceeds coordinator step limit"
        )

    if (
        plan.max_total_seconds
        > limits.max_plan_total_seconds
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "compiled plan exceeds coordinator time limit"
        )

    records = []

    observation_ids = []

    material_source_ids = []

    completed = set()

    plan_started = monotonic()

    for step in plan.steps:
        missing_dependencies = (
            set(
                step.depends_on_step_ids
            )
            - completed
        )

        if missing_dependencies:
            raise RepositorySemanticUnderstandingCoordinatorError(
                "plan dependency order is not executable"
            )

        if isinstance(
            step.operation,
            ResolveCallOperation,
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "RESOLVE_CALL has no canonical "
                "InvestigationCallObservation evidence-record bridge"
            )

        if (
            monotonic()
            - plan_started
            > plan.max_total_seconds
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "plan exceeded total execution time before next step"
            )

        step_started = (
            monotonic()
        )

        operation_observation = (
            execute_investigation_operation(
                repository,
                observation,
                step.operation,
                pyright_typeserver=(
                    pyright_typeserver
                ),
            )
        )

        step_elapsed = (
            monotonic()
            - step_started
        )

        if (
            step_elapsed
            > step.max_seconds
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "investigation operation exceeded its step time limit"
            )

        if (
            monotonic()
            - plan_started
            > plan.max_total_seconds
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "plan exceeded total execution time"
            )

        (
            record,
            material_source,
        ) = (
            _canonical_operation_evidence(
                operation_observation,
                limits=limits,
            )
        )

        records.append(
            record
        )

        observation_ids.append(
            operation_observation
            .observation_id
        )

        if material_source:
            material_source_ids.append(
                record.evidence_id
            )

        completed.add(
            step.step_id
        )

    return (
        tuple(
            records
        ),
        tuple(
            observation_ids
        ),
        tuple(
            material_source_ids
        ),
    )


def _make_result(
    *,
    disposition: RepositorySemanticUnderstandingDisposition,
    base_model: RepositoryDeterministicWorldModel,
    final_model: RepositoryDeterministicWorldModel,
    request: InvestigationRequest | None,
    proposal: InvestigationProposal | None,
    evaluation: HypothesisEvidenceEvaluation | None,
    investigator_run_ids: list[str],
    planner_run_ids: list[str],
    evaluation_run_ids: list[str],
    operation_observation_ids: list[str],
    investigator_rounds_completed: int,
    hypothesis_rounds_completed: int,
    total_model_cost_usd: Decimal,
    persisted_overlay_path: Path | None,
) -> RepositorySemanticUnderstandingExecution:
    evidence_ids = (
        ()
        if request is None
        else tuple(
            record.evidence_id
            for record
            in request.evidence_records
        )
    )

    return (
        RepositorySemanticUnderstandingExecution(
            disposition=disposition,
            base_model=base_model,
            final_model=final_model,
            request=request,
            proposal=proposal,
            evaluation=evaluation,
            investigator_run_ids=tuple(
                investigator_run_ids
            ),
            planner_run_ids=tuple(
                planner_run_ids
            ),
            evaluation_run_ids=tuple(
                evaluation_run_ids
            ),
            operation_observation_ids=tuple(
                operation_observation_ids
            ),
            evidence_record_ids=(
                evidence_ids
            ),
            investigator_rounds_completed=(
                investigator_rounds_completed
            ),
            hypothesis_rounds_completed=(
                hypothesis_rounds_completed
            ),
            total_model_cost_usd=(
                total_model_cost_usd
            ),
            persisted_overlay_path=(
                None
                if persisted_overlay_path
                is None
                else str(
                    persisted_overlay_path
                )
            ),
        )
    )


def run_repository_what_it_is_semantic_understanding(
    *,
    repository: str | Path,
    observation: GitCommitObservation,
    index: PythonRepositoryIndex,
    base_model: RepositoryDeterministicWorldModel,
    initial_evidence_records: tuple[
        CanonicalEvidenceRecord,
        ...,
    ],
    semantic_store: RepositorySemanticWorldModelStore,
    investigator_model: InvestigatorModel,
    typed_planner_model: SemanticGapTypedPlannerModel,
    evaluation_model: HypothesisEvaluationModel,
    investigator_instruction: bytes,
    investigator_temperature: float | None,
    investigator_cost_cap_usd: Decimal,
    typed_planner_instruction: bytes,
    typed_planner_temperature: float | None,
    typed_planner_cost_cap_usd: Decimal,
    evaluation_instruction: bytes,
    evaluation_temperature: float | None,
    evaluation_cost_cap_usd: Decimal,
    limits: RepositorySemanticUnderstandingLimits,
    pyright_typeserver: str | Path | None = None,
) -> RepositorySemanticUnderstandingExecution:
    """Run one bounded WHAT_IT_IS semantic-understanding state machine.

    Autonomous provider calls derive their hard call authority from the
    aggregate model budget remaining at the exact moment of dispatch.

    The three caller-supplied per-role cost-cap arguments are retained
    temporarily for API compatibility only. They no longer determine
    autonomous call authorization.
    """

    repository_path = Path(
        repository
    ).resolve()

    if (
        not repository_path.exists()
        or not repository_path.is_dir()
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "repository must identify an existing directory"
        )

    _validate_snapshot_identity(
        observation=observation,
        index=index,
        base_model=base_model,
    )

    if not isinstance(
        semantic_store,
        RepositorySemanticWorldModelStore,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "semantic_store must be a RepositorySemanticWorldModelStore"
        )

    if not isinstance(
        limits,
        RepositorySemanticUnderstandingLimits,
    ):
        raise RepositorySemanticUnderstandingCoordinatorError(
            "limits must be RepositorySemanticUnderstandingLimits"
        )

    investigator_instruction = (
        _require_instruction(
            investigator_instruction,
            name=(
                "investigator_instruction"
            ),
        )
    )

    typed_planner_instruction = (
        _require_instruction(
            typed_planner_instruction,
            name=(
                "typed_planner_instruction"
            ),
        )
    )

    evaluation_instruction = (
        _require_instruction(
            evaluation_instruction,
            name=(
                "evaluation_instruction"
            ),
        )
    )

    investigator_temperature = (
        _require_temperature(
            investigator_temperature,
            name=(
                "investigator_temperature"
            ),
            allow_none=True,
        )
    )

    typed_planner_temperature = (
        _require_temperature(
            typed_planner_temperature,
            name=(
                "typed_planner_temperature"
            ),
            allow_none=True,
        )
    )

    evaluation_temperature = (
        _require_temperature(
            evaluation_temperature,
            name=(
                "evaluation_temperature"
            ),
            allow_none=True,
        )
    )

    investigator_cost_cap_usd = (
        _require_decimal_cost_cap(
            investigator_cost_cap_usd,
            name=(
                "investigator_cost_cap_usd"
            ),
        )
    )

    typed_planner_cost_cap_usd = (
        _require_decimal_cost_cap(
            typed_planner_cost_cap_usd,
            name=(
                "typed_planner_cost_cap_usd"
            ),
        )
    )

    evaluation_cost_cap_usd = (
        _require_decimal_cost_cap(
            evaluation_cost_cap_usd,
            name=(
                "evaluation_cost_cap_usd"
            ),
        )
    )

    try:
        current_model = (
            semantic_store.load(
                base_model
            )
        )

    except RepositorySemanticWorldModelStoreError as exc:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "persisted semantic World Model could not be loaded"
        ) from exc

    if (
        current_model
        .what_it_is_assertion_ids
    ):
        return _make_result(
            disposition=(
                RepositorySemanticUnderstandingDisposition
                .ALREADY_KNOWN
            ),
            base_model=base_model,
            final_model=(
                current_model
            ),
            request=None,
            proposal=None,
            evaluation=None,
            investigator_run_ids=[],
            planner_run_ids=[],
            evaluation_run_ids=[],
            operation_observation_ids=[],
            investigator_rounds_completed=0,
            hypothesis_rounds_completed=0,
            total_model_cost_usd=(
                Decimal(
                    "0"
                )
            ),
            persisted_overlay_path=(
                semantic_store.path_for(
                    base_model
                )
            ),
        )

    if current_model != base_model:
        raise RepositorySemanticUnderstandingCoordinatorError(
            "semantic store returned an unsupported partial overlay"
        )

    _validate_evidence_budget(
        initial_evidence_records,
        limits=limits,
    )

    question = (
        _what_it_is_question(
            index=index,
            model=current_model,
        )
    )

    request = (
        compile_semantic_gap_investigation_request(
            question,
            model=current_model,
            evidence_records=(
                initial_evidence_records
            ),
        )
    )

    investigator_run_ids = []

    planner_run_ids = []

    evaluation_run_ids = []

    operation_observation_ids = []

    material_source_evidence_ids = set()

    total_model_cost = Decimal(
        "0"
    )

    active_hypothesis = None

    latest_proposal = None

    latest_evaluation = None

    investigator_rounds_completed = 0

    hypothesis_rounds_completed = 0


    #
    # Phase 1:
    # Discover enough evidence to reach one explicit hypothesis.
    #

    for investigator_round in range(
        1,
        limits.max_investigator_rounds
        + 1,
    ):
        investigator_execution = (
            execute_investigation(
                model=investigator_model,
                request=request,
                instruction=(
                    investigator_instruction
                ),
                temperature=(
                    investigator_temperature
                ),
                cost_cap_usd=(
                    _remaining_model_budget(
                        total_model_cost,
                        limits=limits,
                    )
                ),
            )
        )

        investigator_rounds_completed = (
            investigator_round
        )

        investigator_run_ids.append(
            investigator_execution
            .run
            .run_id
        )

        total_model_cost = (
            _add_model_cost(
                total_model_cost,
                investigator_execution
                .run
                .cost_usd,
                limits=limits,
            )
        )

        if (
            investigator_execution
            .run
            .validation_result
            is not ModelRunValidationResult
            .VALID
            or investigator_execution
            .proposal
            is None
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "investigator model run was not valid"
            )

        proposal = (
            investigator_execution
            .proposal
        )

        latest_proposal = (
            proposal
        )

        if (
            proposal.kind
            is InvestigationProposalKind
            .PROPOSE_HYPOTHESIS
        ):
            active_hypothesis = (
                proposal
            )

            break

        if (
            proposal.kind
            is InvestigationProposalKind
            .DECLARE_INSUFFICIENT_EVIDENCE
        ):
            return _make_result(
                disposition=(
                    RepositorySemanticUnderstandingDisposition
                    .DECLARED_INSUFFICIENT_EVIDENCE
                ),
                base_model=base_model,
                final_model=current_model,
                request=request,
                proposal=proposal,
                evaluation=None,
                investigator_run_ids=(
                    investigator_run_ids
                ),
                planner_run_ids=(
                    planner_run_ids
                ),
                evaluation_run_ids=(
                    evaluation_run_ids
                ),
                operation_observation_ids=(
                    operation_observation_ids
                ),
                investigator_rounds_completed=(
                    investigator_rounds_completed
                ),
                hypothesis_rounds_completed=0,
                total_model_cost_usd=(
                    total_model_cost
                ),
                persisted_overlay_path=None,
            )

        if (
            proposal.kind
            is InvestigationProposalKind
            .REFINE_OBJECT
        ):
            return _make_result(
                disposition=(
                    RepositorySemanticUnderstandingDisposition
                    .REFINEMENT_REQUIRED
                ),
                base_model=base_model,
                final_model=current_model,
                request=request,
                proposal=proposal,
                evaluation=None,
                investigator_run_ids=(
                    investigator_run_ids
                ),
                planner_run_ids=(
                    planner_run_ids
                ),
                evaluation_run_ids=(
                    evaluation_run_ids
                ),
                operation_observation_ids=(
                    operation_observation_ids
                ),
                investigator_rounds_completed=(
                    investigator_rounds_completed
                ),
                hypothesis_rounds_completed=0,
                total_model_cost_usd=(
                    total_model_cost
                ),
                persisted_overlay_path=None,
            )

        if (
            proposal.kind
            is not InvestigationProposalKind
            .PROPOSE_INVESTIGATION
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "investigator returned an unsupported proposal transition"
            )

        planner_execution = (
            execute_semantic_gap_typed_planner(
                model=(
                    typed_planner_model
                ),
                request=request,
                proposal=proposal,
                instruction=(
                    typed_planner_instruction
                ),
                temperature=(
                    typed_planner_temperature
                ),
                cost_cap_usd=(
                    _remaining_model_budget(
                        total_model_cost,
                        limits=limits,
                    )
                ),
            )
        )

        planner_run_ids.append(
            planner_execution
            .run
            .run_id
        )

        total_model_cost = (
            _add_model_cost(
                total_model_cost,
                planner_execution
                .run
                .cost_usd,
                limits=limits,
            )
        )

        if (
            planner_execution
            .run
            .validation_result
            is not
            SemanticGapTypedPlannerValidationResult
            .VALID
            or planner_execution
            .planner_output
            is None
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "typed planner model run was not valid"
            )

        plan = (
            compile_semantic_gap_proposal_plan(
                request=request,
                proposal=proposal,
                bindings=(
                    planner_execution
                    .planner_output
                    .bindings
                ),
                max_steps=(
                    limits.max_plan_steps
                ),
                max_total_seconds=(
                    limits.max_plan_total_seconds
                ),
            )
        )

        (
            supplemental,
            observation_ids,
            material_ids,
        ) = (
            _execute_plan(
                repository=(
                    repository_path
                ),
                observation=(
                    observation
                ),
                plan=plan,
                limits=limits,
                pyright_typeserver=(
                    pyright_typeserver
                ),
            )
        )

        if not supplemental:
            raise RepositorySemanticUnderstandingCoordinatorError(
                "investigation plan produced no evidence"
            )

        operation_observation_ids.extend(
            observation_ids
        )

        material_source_evidence_ids.update(
            material_ids
        )

        request = (
            extend_semantic_gap_investigation_request(
                request,
                supplemental_evidence_records=(
                    supplemental
                ),
            )
        )

        _validate_evidence_budget(
            request.evidence_records,
            limits=limits,
        )


    if active_hypothesis is None:
        return _make_result(
            disposition=(
                RepositorySemanticUnderstandingDisposition
                .BOUNDED_STOP
            ),
            base_model=base_model,
            final_model=current_model,
            request=request,
            proposal=(
                latest_proposal
            ),
            evaluation=None,
            investigator_run_ids=(
                investigator_run_ids
            ),
            planner_run_ids=(
                planner_run_ids
            ),
            evaluation_run_ids=(
                evaluation_run_ids
            ),
            operation_observation_ids=(
                operation_observation_ids
            ),
            investigator_rounds_completed=(
                investigator_rounds_completed
            ),
            hypothesis_rounds_completed=0,
            total_model_cost_usd=(
                total_model_cost
            ),
            persisted_overlay_path=None,
        )


    #
    # Phase 2:
    # Use the hypothesis's exact test questions to gather evidence,
    # then evaluate the SAME hypothesis against the expanded request.
    #
    # STILL_INCOMPLETE loops only within the pre-registered round bound.
    #

    for hypothesis_round in range(
        1,
        limits.max_hypothesis_rounds
        + 1,
    ):
        hypothesis_rounds_completed = (
            hypothesis_round
        )

        final_hypothesis_round = (
            hypothesis_round
            == limits.max_hypothesis_rounds
        )

        bridge = (
            bridge_hypothesis_tests_to_typed_planning(
                request=request,
                proposal=(
                    active_hypothesis
                ),
            )
        )

        round_typed_planner_instruction = (
            _hypothesis_round_typed_planner_instruction(
                typed_planner_instruction,
                current_round=(
                    hypothesis_round
                ),
                max_rounds=(
                    limits.max_hypothesis_rounds
                ),
                source_hypothesis=(
                    bridge.source_hypothesis
                ),
                source_basis_paths=(
                    bridge.source_basis_paths
                ),
            )
        )

        planning_proposal = (
            bridge.planning_proposal
        )

        planner_execution = (
            execute_semantic_gap_typed_planner(
                model=(
                    typed_planner_model
                ),
                request=request,
                proposal=(
                    planning_proposal
                ),
                instruction=(
                    round_typed_planner_instruction
                ),
                temperature=(
                    typed_planner_temperature
                ),
                cost_cap_usd=(
                    _remaining_model_budget(
                        total_model_cost,
                        limits=limits,
                    )
                ),
            )
        )

        planner_run_ids.append(
            planner_execution
            .run
            .run_id
        )

        total_model_cost = (
            _add_model_cost(
                total_model_cost,
                planner_execution
                .run
                .cost_usd,
                limits=limits,
            )
        )

        if (
            planner_execution
            .run
            .validation_result
            is not
            SemanticGapTypedPlannerValidationResult
            .VALID
            or planner_execution
            .planner_output
            is None
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "hypothesis-test typed planner run was not valid"
            )

        _validate_final_hypothesis_round_material_paths(
            proposal=(
                planning_proposal
            ),
            bindings=(
                planner_execution
                .planner_output
                .bindings
            ),
            final_round=(
                final_hypothesis_round
            ),
            source_basis_paths=(
                bridge.source_basis_paths
            ),
        )

        plan = (
            compile_semantic_gap_proposal_plan(
                request=request,
                proposal=(
                    planning_proposal
                ),
                bindings=(
                    planner_execution
                    .planner_output
                    .bindings
                ),
                max_steps=(
                    limits.max_plan_steps
                ),
                max_total_seconds=(
                    limits.max_plan_total_seconds
                ),
            )
        )

        (
            supplemental,
            observation_ids,
            material_ids,
        ) = (
            _execute_plan(
                repository=(
                    repository_path
                ),
                observation=(
                    observation
                ),
                plan=plan,
                limits=limits,
                pyright_typeserver=(
                    pyright_typeserver
                ),
            )
        )

        if not supplemental:
            raise RepositorySemanticUnderstandingCoordinatorError(
                "hypothesis-test plan produced no evidence"
            )

        operation_observation_ids.extend(
            observation_ids
        )

        material_source_evidence_ids.update(
            material_ids
        )

        request = (
            extend_semantic_gap_investigation_request(
                request,
                supplemental_evidence_records=(
                    supplemental
                ),
            )
        )

        _validate_evidence_budget(
            request.evidence_records,
            limits=limits,
        )

        evaluation_execution = (
            execute_hypothesis_evaluation_model(
                model=evaluation_model,
                request=request,
                source_proposal=(
                    active_hypothesis
                ),
                instruction=(
                    evaluation_instruction
                ),
                temperature=(
                    evaluation_temperature
                ),
                cost_cap_usd=(
                    _remaining_model_budget(
                        total_model_cost,
                        limits=limits,
                    )
                ),
            )
        )

        evaluation_run_ids.append(
            evaluation_execution
            .run
            .run_id
        )

        total_model_cost = (
            _add_model_cost(
                total_model_cost,
                evaluation_execution
                .run
                .cost_usd,
                limits=limits,
            )
        )

        if (
            evaluation_execution
            .run
            .validation_result
            is not
            HypothesisEvaluationModelValidationResult
            .VALID
            or evaluation_execution
            .evaluation
            is None
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "hypothesis evaluation model run was not valid"
            )

        evaluation = (
            evaluation_execution
            .evaluation
        )

        latest_evaluation = (
            evaluation
        )

        if (
            evaluation.verdict
            is HypothesisEvaluationVerdict
            .CONTRADICTED
        ):
            return _make_result(
                disposition=(
                    RepositorySemanticUnderstandingDisposition
                    .EVALUATION_NOT_SUPPORTED
                ),
                base_model=base_model,
                final_model=current_model,
                request=request,
                proposal=(
                    active_hypothesis
                ),
                evaluation=(
                    evaluation
                ),
                investigator_run_ids=(
                    investigator_run_ids
                ),
                planner_run_ids=(
                    planner_run_ids
                ),
                evaluation_run_ids=(
                    evaluation_run_ids
                ),
                operation_observation_ids=(
                    operation_observation_ids
                ),
                investigator_rounds_completed=(
                    investigator_rounds_completed
                ),
                hypothesis_rounds_completed=(
                    hypothesis_rounds_completed
                ),
                total_model_cost_usd=(
                    total_model_cost
                ),
                persisted_overlay_path=None,
            )

        if (
            evaluation.verdict
            is HypothesisEvaluationVerdict
            .STILL_INCOMPLETE
        ):
            continue

        if (
            evaluation.verdict
            is not HypothesisEvaluationVerdict
            .SUPPORTED
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "evaluation returned an unknown disposition"
            )

        supporting_ids = set(
            evaluation
            .supporting_evidence_ids
        )

        #
        # Current evaluation model boundary exposes complete source
        # excerpts only for executed READ_SOURCE observations.
        #
        # A model saying SUPPORTED is insufficient by itself.
        # Every material supporting citation must come from source
        # evidence this coordinator actually gathered.
        #
        if (
            not supporting_ids
            or not supporting_ids.issubset(
                material_source_evidence_ids
            )
        ):
            continue

        promoted = (
            materialize_supported_what_it_is_hypothesis(
                index=index,
                model=current_model,
                request=request,
                source_proposal=(
                    active_hypothesis
                ),
                evaluation=(
                    evaluation
                ),
            )
        )

        try:
            persisted_path = (
                semantic_store.save(
                    base_model,
                    promoted,
                )
            )

            reloaded = (
                semantic_store.load(
                    base_model
                )
            )

        except RepositorySemanticWorldModelStoreError as exc:
            raise RepositorySemanticUnderstandingCoordinatorError(
                "promoted semantic World Model could not be persisted"
            ) from exc

        if (
            reloaded
            != promoted
        ):
            raise RepositorySemanticUnderstandingCoordinatorError(
                "persisted semantic World Model did not reload exactly"
            )

        return _make_result(
            disposition=(
                RepositorySemanticUnderstandingDisposition
                .PROMOTED
            ),
            base_model=base_model,
            final_model=promoted,
            request=request,
            proposal=(
                active_hypothesis
            ),
            evaluation=(
                evaluation
            ),
            investigator_run_ids=(
                investigator_run_ids
            ),
            planner_run_ids=(
                planner_run_ids
            ),
            evaluation_run_ids=(
                evaluation_run_ids
            ),
            operation_observation_ids=(
                operation_observation_ids
            ),
            investigator_rounds_completed=(
                investigator_rounds_completed
            ),
            hypothesis_rounds_completed=(
                hypothesis_rounds_completed
            ),
            total_model_cost_usd=(
                total_model_cost
            ),
            persisted_overlay_path=(
                persisted_path
            ),
        )


    return _make_result(
        disposition=(
            RepositorySemanticUnderstandingDisposition
            .BOUNDED_STOP
        ),
        base_model=base_model,
        final_model=current_model,
        request=request,
        proposal=(
            active_hypothesis
        ),
        evaluation=(
            latest_evaluation
        ),
        investigator_run_ids=(
            investigator_run_ids
        ),
        planner_run_ids=(
            planner_run_ids
        ),
        evaluation_run_ids=(
            evaluation_run_ids
        ),
        operation_observation_ids=(
            operation_observation_ids
        ),
        investigator_rounds_completed=(
            investigator_rounds_completed
        ),
        hypothesis_rounds_completed=(
            hypothesis_rounds_completed
        ),
        total_model_cost_usd=(
            total_model_cost
        ),
        persisted_overlay_path=None,
    )
