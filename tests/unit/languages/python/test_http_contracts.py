from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

from horizon.languages.python.structure import (
    PythonStructureKind,
    analyze_python_blob,
)
from horizon.repository.git_blob import (
    read_observed_blob,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)


CLIENT_SOURCE = b"""\
class BaseClient:
    pass


class FlowRunClient(BaseClient):
    def set_flow_run_state(
        self,
        flow_run_id,
        state,
        force=False,
    ):
        response = self.request(
            "POST",
            "/flow_runs/{id}/set_state",
            path_params={"id": flow_run_id},
            json={
                "state": state,
                "force": force,
            },
        )
        return response
"""


SERVER_SOURCE = b"""\
class Router:
    def __init__(self, *, prefix, tags):
        pass

    def post(self, route):
        return lambda fn: fn

    def get(self, route):
        return lambda fn: fn


router: Router = Router(
    prefix="/flow_runs",
    tags=["Flow Runs"],
)


@router.post("/{id:uuid}/set_state")
async def set_flow_run_state(
    flow_run_id,
    state,
):
    return state
"""


WRONG_STATIC_PATH_SOURCE = b"""\
class Router:
    def __init__(self, *, prefix):
        pass

    def post(self, route):
        return lambda fn: fn


router = Router(
    prefix="/task_runs",
)


@router.post("/{id:uuid}/set_state")
async def set_flow_run_state(
    flow_run_id,
    state,
):
    return state
"""


WRONG_METHOD_SOURCE = b"""\
class Router:
    def __init__(self, *, prefix):
        pass

    def get(self, route):
        return lambda fn: fn


router = Router(
    prefix="/flow_runs",
)


@router.get("/{id:uuid}/set_state")
async def set_flow_run_state(
    flow_run_id,
    state,
):
    return state
"""


def _git(
    repository: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            *args,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return completed.stdout.strip()


def _fixture(
    tmp_path: Path,
    *,
    server_source: bytes = SERVER_SOURCE,
):
    repository = (
        tmp_path
        / "repository"
    )

    repository.mkdir()

    _git(
        repository,
        "init",
        "-q",
        "-b",
        "main",
    )

    _git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    _git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    (
        repository
        / "client.py"
    ).write_bytes(
        CLIENT_SOURCE
    )

    (
        repository
        / "server.py"
    ).write_bytes(
        server_source
    )

    _git(
        repository,
        "add",
        "client.py",
        "server.py",
    )

    _git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    client_blob = read_observed_blob(
        repository,
        observation,
        "client.py",
    )

    server_blob = read_observed_blob(
        repository,
        observation,
        "server.py",
    )

    client_analysis = (
        analyze_python_blob(
            client_blob
        )
    )

    server_analysis = (
        analyze_python_blob(
            server_blob
        )
    )

    return (
        client_blob,
        client_analysis,
        server_blob,
        server_analysis,
    )


def _api():
    module = importlib.import_module(
        "horizon.languages.python."
        "http_contracts"
    )

    return (
        module.extract_http_request_contract,
        module.extract_http_route_contract,
        module.match_http_contracts,
        module.PythonHttpContractMatchStatus,
    )


def _request_call(
    analysis,
):
    matches = [
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and fact.callee_expression
            == "self.request"
            and fact.scope
            == (
                "FlowRunClient",
                "set_flow_run_state",
            )
        )
    ]

    assert len(matches) == 1

    return matches[0]


def _handler(
    analysis,
):
    matches = [
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == (
                PythonStructureKind
                .ASYNC_FUNCTION_DEFINITION
            )
            and fact.name
            == "set_flow_run_state"
            and fact.scope == ()
        )
    ]

    assert len(matches) == 1

    return matches[0]


def _contracts(
    tmp_path: Path,
    *,
    server_source: bytes = SERVER_SOURCE,
):
    (
        client_blob,
        client_analysis,
        server_blob,
        server_analysis,
    ) = _fixture(
        tmp_path,
        server_source=server_source,
    )

    (
        extract_request,
        extract_route,
        match_contracts,
        status_type,
    ) = _api()

    request_call = _request_call(
        client_analysis
    )

    handler = _handler(
        server_analysis
    )

    request = extract_request(
        blob=client_blob,
        call_fact=request_call,
    )

    route = extract_route(
        blob=server_blob,
        handler_fact=handler,
    )

    return (
        request,
        route,
        match_contracts,
        status_type,
        client_blob,
        request_call,
        server_blob,
        handler,
    )


def test_extracts_literal_outbound_http_contract(
    tmp_path: Path,
) -> None:
    (
        request,
        _,
        _,
        _,
        client_blob,
        request_call,
        _,
        _,
    ) = _contracts(
        tmp_path
    )

    assert (
        request.source_evidence_id
        == client_blob.evidence_id
    )

    assert (
        request.call_evidence_id
        == request_call.evidence_id
    )

    assert request.method == "POST"

    assert (
        request.route_template
        == "/flow_runs/{id}/set_state"
    )

    assert (
        request.evidence_id.startswith(
            "python-http-request-contract:"
        )
    )


def test_extracts_prefixed_inbound_http_route_contract(
    tmp_path: Path,
) -> None:
    (
        _,
        route,
        _,
        _,
        _,
        _,
        server_blob,
        handler,
    ) = _contracts(
        tmp_path
    )

    assert (
        route.source_evidence_id
        == server_blob.evidence_id
    )

    assert (
        route.handler_evidence_id
        == handler.evidence_id
    )

    assert route.method == "POST"

    assert (
        route.router_prefix
        == "/flow_runs"
    )

    assert (
        route.route_template
        == "/{id:uuid}/set_state"
    )

    assert (
        route.full_route_template
        == (
            "/flow_runs/"
            "{id:uuid}/set_state"
        )
    )

    assert (
        route.decorator_evidence_id
        is not None
    )

    assert (
        route.evidence_id.startswith(
            "python-http-route-contract:"
        )
    )


def test_parameter_converter_difference_is_preserved_but_shape_matches(
    tmp_path: Path,
) -> None:
    (
        request,
        route,
        match_contracts,
        status_type,
        *_,
    ) = _contracts(
        tmp_path
    )

    edge = match_contracts(
        request=request,
        route=route,
    )

    assert (
        edge.status
        is (
            status_type
            .TEMPLATE_SHAPE_MATCH
        )
    )

    assert (
        edge.client_route_template
        == "/flow_runs/{id}/set_state"
    )

    assert (
        edge.server_route_template
        == (
            "/flow_runs/"
            "{id:uuid}/set_state"
        )
    )

    assert (
        edge.client_route_template
        != edge.server_route_template
    )

    assert (
        edge.request_contract_evidence_id
        == request.evidence_id
    )

    assert (
        edge.route_contract_evidence_id
        == route.evidence_id
    )

    assert (
        edge.evidence_id.startswith(
            "http-contract-edge:"
        )
    )


@pytest.mark.parametrize(
    "server_source",
    [
        WRONG_STATIC_PATH_SOURCE,
        WRONG_METHOD_SOURCE,
    ],
)
def test_does_not_match_different_http_contract(
    tmp_path: Path,
    server_source: bytes,
) -> None:
    (
        request,
        route,
        match_contracts,
        status_type,
        *_,
    ) = _contracts(
        tmp_path,
        server_source=server_source,
    )

    edge = match_contracts(
        request=request,
        route=route,
    )

    assert (
        edge.status
        is status_type.NO_MATCH
    )


def test_http_contract_edge_does_not_claim_runtime_topology(
    tmp_path: Path,
) -> None:
    (
        request,
        route,
        match_contracts,
        status_type,
        *_,
    ) = _contracts(
        tmp_path
    )

    edge = match_contracts(
        request=request,
        route=route,
    )

    assert (
        edge.status
        is (
            status_type
            .TEMPLATE_SHAPE_MATCH
        )
    )

    assert not hasattr(
        edge,
        "process_boundary",
    )

    assert not hasattr(
        edge,
        "network_boundary",
    )

    assert not hasattr(
        edge,
        "remote",
    )
