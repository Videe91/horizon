from __future__ import annotations

import dataclasses

import pytest

from horizon.investigation.plan import (
    InspectSymbolOperation,
    InvestigationOperationKind,
    InvestigationPlanError,
    InvestigationStepDraft,
    ReadSourceOperation,
    ResolveCallOperation,
    ResolveTypeOperation,
    SearchSourceOperation,
    TraceHttpContractOperation,
    compile_investigation_plan,
)


def _search(
    *,
    key: str,
    depends_on: tuple[str, ...] = (),
) -> InvestigationStepDraft:
    return InvestigationStepDraft(
        step_key=key,
        purpose=(
            "Locate source relevant to the "
            "retry-eligibility question."
        ),
        operation=SearchSourceOperation(
            query="RetryFailedFlows",
            path_prefix="src/prefect",
        ),
        depends_on_keys=depends_on,
        expected_information=(
            "Relevant frozen-Prefect source locations."
        ),
        max_seconds=20,
    )


def test_initial_operation_vocabulary_is_closed_and_read_only() -> None:
    assert tuple(
        kind.value
        for kind in InvestigationOperationKind
    ) == (
        "SEARCH_SOURCE",
        "READ_SOURCE",
        "INSPECT_SYMBOL",
        "RESOLVE_CALL",
        "RESOLVE_TYPE",
        "TRACE_HTTP_CONTRACT",
    )


def test_operation_contracts_have_no_shell_or_command_escape_hatch() -> None:
    operation_types = (
        SearchSourceOperation,
        ReadSourceOperation,
        InspectSymbolOperation,
        ResolveCallOperation,
        ResolveTypeOperation,
        TraceHttpContractOperation,
    )

    forbidden = {
        "command",
        "shell",
        "argv",
        "script",
        "python",
        "code",
        "environment",
        "env",
    }

    for operation_type in operation_types:
        field_names = {
            field.name
            for field in dataclasses.fields(
                operation_type
            )
        }

        assert not (
            field_names
            & forbidden
        )


def test_search_source_is_typed_and_frozen() -> None:
    operation = SearchSourceOperation(
        query="RetryFailedFlows",
        path_prefix="src/prefect",
    )

    assert (
        operation.kind
        is InvestigationOperationKind.SEARCH_SOURCE
    )

    assert operation.query == "RetryFailedFlows"
    assert operation.path_prefix == "src/prefect"

    with pytest.raises(
        dataclasses.FrozenInstanceError
    ):
        operation.query = "other"  # type: ignore[misc]


def test_repository_paths_cannot_escape_target() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="repository-relative",
    ):
        ReadSourceOperation(
            path="/tmp/escape.py",
            start_line=1,
            end_line=10,
        )

    with pytest.raises(
        InvestigationPlanError,
        match="escape",
    ):
        ReadSourceOperation(
            path="../outside.py",
            start_line=1,
            end_line=10,
        )


def test_read_source_requires_valid_line_window() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="line",
    ):
        ReadSourceOperation(
            path="src/prefect/flow_engine.py",
            start_line=20,
            end_line=10,
        )


def test_position_operations_require_valid_coordinates() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="line",
    ):
        ResolveCallOperation(
            path="src/prefect/flow_engine.py",
            line=0,
            character=3,
        )

    with pytest.raises(
        InvestigationPlanError,
        match="character",
    ):
        ResolveTypeOperation(
            path="src/prefect/flow_engine.py",
            line=10,
            character=-1,
        )


def test_plan_compiler_assigns_horizon_step_ids() -> None:
    draft = _search(
        key="find-policy",
    )

    plan = compile_investigation_plan(
        proposal_id="investigation-proposal:abc",
        question_id="world-model-open-question:def",
        drafts=(
            draft,
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    assert len(
        plan.steps
    ) == 1

    step = plan.steps[0]

    assert step.source_step_key == "find-policy"

    assert step.step_id.startswith(
        "investigation-step:"
    )

    assert (
        step.step_id
        != draft.step_key
    )

    assert (
        step.operation
        == draft.operation
    )


def test_plan_compiler_resolves_dependencies_to_horizon_ids() -> None:
    first = _search(
        key="find-policy",
    )

    second = InvestigationStepDraft(
        step_key="inspect-policy",
        purpose=(
            "Inspect the policy source that "
            "the search identifies."
        ),
        operation=InspectSymbolOperation(
            path=(
                "src/prefect/server/"
                "orchestration/core_policy.py"
            ),
            symbol="RetryFailedFlows",
        ),
        depends_on_keys=(
            "find-policy",
        ),
        expected_information=(
            "The exact policy implementation."
        ),
        max_seconds=30,
    )

    plan = compile_investigation_plan(
        proposal_id="investigation-proposal:abc",
        question_id="world-model-open-question:def",
        drafts=(
            first,
            second,
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    by_key = {
        step.source_step_key: step
        for step in plan.steps
    }

    assert (
        by_key[
            "inspect-policy"
        ].depends_on_step_ids
        == (
            by_key[
                "find-policy"
            ].step_id,
        )
    )


def test_same_logical_plan_is_deterministic_under_draft_reordering() -> None:
    first = _search(
        key="a",
    )

    second = InvestigationStepDraft(
        step_key="b",
        purpose=(
            "Read a distinct frozen-Prefect "
            "source window."
        ),
        operation=ReadSourceOperation(
            path="src/prefect/flow_engine.py",
            start_line=1,
            end_line=20,
        ),
        depends_on_keys=(),
        expected_information=(
            "A distinct frozen-Prefect "
            "source observation."
        ),
        max_seconds=20,
    )

    plan_one = compile_investigation_plan(
        proposal_id="investigation-proposal:abc",
        question_id="world-model-open-question:def",
        drafts=(
            first,
            second,
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    plan_two = compile_investigation_plan(
        proposal_id="investigation-proposal:abc",
        question_id="world-model-open-question:def",
        drafts=(
            second,
            first,
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    assert plan_one == plan_two
    assert (
        plan_one.plan_id
        == plan_two.plan_id
    )


def test_duplicate_semantic_steps_cannot_be_split_by_local_labels() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="duplicate investigation step identity",
    ):
        compile_investigation_plan(
            proposal_id="investigation-proposal:abc",
            question_id="world-model-open-question:def",
            drafts=(
                _search(
                    key="first-label",
                ),
                _search(
                    key="second-label",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_duplicate_step_keys_are_rejected() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="duplicate step key",
    ):
        compile_investigation_plan(
            proposal_id="investigation-proposal:abc",
            question_id="world-model-open-question:def",
            drafts=(
                _search(
                    key="same",
                ),
                _search(
                    key="same",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_unknown_dependency_is_rejected() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="unknown dependency",
    ):
        compile_investigation_plan(
            proposal_id="investigation-proposal:abc",
            question_id="world-model-open-question:def",
            drafts=(
                _search(
                    key="inspect",
                    depends_on=(
                        "missing",
                    ),
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_dependency_cycle_is_rejected() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="cycle",
    ):
        compile_investigation_plan(
            proposal_id="investigation-proposal:abc",
            question_id="world-model-open-question:def",
            drafts=(
                _search(
                    key="a",
                    depends_on=(
                        "b",
                    ),
                ),
                _search(
                    key="b",
                    depends_on=(
                        "a",
                    ),
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_plan_step_budget_is_bounded() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="step limit",
    ):
        compile_investigation_plan(
            proposal_id="investigation-proposal:abc",
            question_id="world-model-open-question:def",
            drafts=(
                _search(
                    key="a",
                ),
                _search(
                    key="b",
                ),
            ),
            max_steps=1,
            max_total_seconds=120,
        )


def test_plan_total_time_budget_is_bounded() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="time budget",
    ):
        compile_investigation_plan(
            proposal_id="investigation-proposal:abc",
            question_id="world-model-open-question:def",
            drafts=(
                _search(
                    key="a",
                ),
                _search(
                    key="b",
                ),
            ),
            max_steps=4,
            max_total_seconds=30,
        )


def test_plan_requires_real_proposal_and_question_identity() -> None:
    with pytest.raises(
        InvestigationPlanError,
        match="proposal",
    ):
        compile_investigation_plan(
            proposal_id="",
            question_id="world-model-open-question:def",
            drafts=(
                _search(
                    key="a",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )

    with pytest.raises(
        InvestigationPlanError,
        match="question",
    ):
        compile_investigation_plan(
            proposal_id="investigation-proposal:abc",
            question_id="",
            drafts=(
                _search(
                    key="a",
                ),
            ),
            max_steps=4,
            max_total_seconds=120,
        )


def test_plan_is_not_world_model_truth() -> None:
    from horizon.claims.evidence_backed import (
        EvidenceBackedClaim,
    )
    from horizon.claims.epistemic import (
        EpistemicAssessment,
    )
    from horizon.world_model.assertion import (
        WorldModelAssertion,
    )

    plan = compile_investigation_plan(
        proposal_id="investigation-proposal:abc",
        question_id="world-model-open-question:def",
        drafts=(
            _search(
                key="a",
            ),
        ),
        max_steps=4,
        max_total_seconds=120,
    )

    assert not isinstance(
        plan,
        EvidenceBackedClaim,
    )

    assert not isinstance(
        plan,
        EpistemicAssessment,
    )

    assert not isinstance(
        plan,
        WorldModelAssertion,
    )



def test_read_source_may_request_observed_eof() -> None:
    operation = ReadSourceOperation(
        path="src/prefect/flow_engine.py",
        start_line=20,
        end_line=None,
    )

    assert (
        operation.start_line
        == 20
    )

    assert (
        operation.end_line
        is None
    )
