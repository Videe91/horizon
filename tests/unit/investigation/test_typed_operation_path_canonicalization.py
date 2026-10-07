from __future__ import annotations

import pytest

from horizon.investigation.execution import (
    _path_is_within_prefix,
)
from horizon.investigation.plan import (
    InspectSymbolOperation,
    InvestigationPlanError,
    InvestigationStepDraft,
    ReadSourceOperation,
    ResolveCallOperation,
    ResolveTypeOperation,
    SearchSourceOperation,
    TraceHttpContractOperation,
    compile_investigation_plan,
)


def test_search_source_path_prefix_is_canonicalized() -> None:
    operation = SearchSourceOperation(
        query="class Flow",
        path_prefix="./src//prefect/",
    )

    assert operation.path_prefix == "src/prefect"


def test_search_source_none_prefix_remains_none() -> None:
    operation = SearchSourceOperation(
        query="class Flow",
        path_prefix=None,
    )

    assert operation.path_prefix is None


def test_read_source_path_is_canonicalized() -> None:
    operation = ReadSourceOperation(
        path="./src//prefect/flows.py",
        start_line=1,
        end_line=10,
    )

    assert operation.path == "src/prefect/flows.py"


def test_inspect_symbol_path_is_canonicalized() -> None:
    operation = InspectSymbolOperation(
        path="./src//prefect/flows.py",
        symbol="Flow",
    )

    assert operation.path == "src/prefect/flows.py"


def test_resolve_call_path_is_canonicalized() -> None:
    operation = ResolveCallOperation(
        path="./src//prefect/flows.py",
        line=100,
        character=4,
    )

    assert operation.path == "src/prefect/flows.py"


def test_resolve_type_path_is_canonicalized() -> None:
    operation = ResolveTypeOperation(
        path="./src//prefect/flows.py",
        line=100,
        character=4,
    )

    assert operation.path == "src/prefect/flows.py"


def test_http_paths_are_both_canonicalized() -> None:
    operation = TraceHttpContractOperation(
        client_path="./src//prefect/client.py",
        server_path="src/prefect//server.py/",
        route_hint="/api/example",
    )

    assert operation.client_path == "src/prefect/client.py"
    assert operation.server_path == "src/prefect/server.py"


def test_equivalent_search_prefix_forms_create_equal_operations() -> None:
    canonical = SearchSourceOperation(
        query="class Flow",
        path_prefix="src/prefect",
    )

    trailing = SearchSourceOperation(
        query="class Flow",
        path_prefix="src/prefect/",
    )

    redundant = SearchSourceOperation(
        query="class Flow",
        path_prefix="./src//prefect/",
    )

    assert trailing == canonical
    assert redundant == canonical


def test_canonicalized_search_prefix_matches_descendants() -> None:
    operation = SearchSourceOperation(
        query="class Flow",
        path_prefix="src/prefect/",
    )

    assert operation.path_prefix == "src/prefect"

    assert _path_is_within_prefix(
        "src/prefect/flows.py",
        operation.path_prefix,
    )


def _plan(
    path_prefix: str,
):
    return compile_investigation_plan(
        proposal_id="investigation-proposal:test",
        question_id="repository-semantic-gap-question:test",
        drafts=(
            InvestigationStepDraft(
                step_key="find-flow",
                purpose="Locate candidate flow declarations.",
                operation=SearchSourceOperation(
                    query="class Flow",
                    path_prefix=path_prefix,
                ),
                depends_on_keys=(),
                expected_information="Observed source locations.",
                max_seconds=10,
            ),
        ),
        max_steps=4,
        max_total_seconds=60,
    )


def test_equivalent_path_forms_have_same_step_and_plan_identity() -> None:
    canonical = _plan("src/prefect")
    trailing = _plan("src/prefect/")
    redundant = _plan("./src//prefect/")

    assert (
        trailing.steps[0].step_id
        == canonical.steps[0].step_id
    )

    assert (
        redundant.steps[0].step_id
        == canonical.steps[0].step_id
    )

    assert trailing.plan_id == canonical.plan_id
    assert redundant.plan_id == canonical.plan_id


@pytest.mark.parametrize(
    "path_prefix",
    (
        "../prefect",
        "src/../prefect",
        "/absolute/prefect",
    ),
)
def test_canonicalization_does_not_weaken_escape_guards(
    path_prefix: str,
) -> None:
    with pytest.raises(
        InvestigationPlanError,
    ):
        SearchSourceOperation(
            query="flow",
            path_prefix=path_prefix,
        )
