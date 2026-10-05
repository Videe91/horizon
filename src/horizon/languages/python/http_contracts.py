from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from horizon.languages.python.structure import (
    PythonStructureFact,
    PythonStructureKind,
    _line_starts,
    _node_span,
    analyze_python_blob,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)


class PythonHttpContractEvidenceError(
    Exception
):
    """Static Python evidence cannot establish an HTTP contract."""


class PythonHttpContractMatchStatus(
    str,
    Enum,
):
    EXACT_MATCH = "EXACT_MATCH"
    TEMPLATE_SHAPE_MATCH = (
        "TEMPLATE_SHAPE_MATCH"
    )
    NO_MATCH = "NO_MATCH"


@dataclass(
    frozen=True,
    slots=True,
)
class PythonHttpRequestContract:
    source_evidence_id: str
    call_evidence_id: str
    callee_evidence_id: str

    method: str
    route_template: str

    evidence_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class PythonHttpRouteContract:
    source_evidence_id: str
    handler_evidence_id: str
    decorator_evidence_id: str

    method: str
    router_prefix: str
    route_template: str
    full_route_template: str

    evidence_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class PythonHttpContractEdge:
    request_contract_evidence_id: str
    route_contract_evidence_id: str

    method: str
    client_route_template: str
    server_route_template: str

    status: PythonHttpContractMatchStatus

    evidence_id: str


def _identity(
    prefix: bytes,
    *values: str,
) -> str:
    digest = sha256()

    digest.update(
        prefix
    )

    for value in values:
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )

        digest.update(
            b"\0"
        )

    return digest.hexdigest()


def _parse(
    blob: GitBlobEvidence,
) -> ast.Module:
    try:
        return ast.parse(
            blob.content,
            filename=blob.path,
            type_comments=True,
        )

    except (
        SyntaxError,
        ValueError,
    ) as exc:
        raise (
            PythonHttpContractEvidenceError(
                "unable to parse Python source "
                "for HTTP contract evidence"
            )
        ) from exc


def _validate_fact_source(
    *,
    blob: GitBlobEvidence,
    fact: PythonStructureFact,
) -> None:
    if (
        fact.source_evidence_id
        != blob.evidence_id
    ):
        raise (
            PythonHttpContractEvidenceError(
                "structural fact and source "
                "blob do not match"
            )
        )


def _node_for_fact(
    *,
    blob: GitBlobEvidence,
    fact: PythonStructureFact,
    node_types: tuple[
        type[ast.AST],
        ...,
    ],
) -> ast.AST:
    _validate_fact_source(
        blob=blob,
        fact=fact,
    )

    tree = _parse(
        blob
    )

    starts = _line_starts(
        blob.content
    )

    matches: list[
        ast.AST
    ] = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            node_types,
        ):
            continue

        (
            line_start,
            line_end,
            byte_start,
            byte_end,
        ) = _node_span(
            node,
            starts,
        )

        if (
            line_start
            == fact.line_start
            and line_end
            == fact.line_end
            and byte_start
            == fact.byte_start
            and byte_end
            == fact.byte_end
        ):
            matches.append(
                node
            )

    if len(
        matches
    ) != 1:
        raise (
            PythonHttpContractEvidenceError(
                "structural fact did not map "
                "to exactly one Python AST node"
            )
        )

    return matches[
        0
    ]


def _literal_string(
    node: ast.AST,
    *,
    description: str,
) -> str:
    if (
        not isinstance(
            node,
            ast.Constant,
        )
        or not isinstance(
            node.value,
            str,
        )
    ):
        raise (
            PythonHttpContractEvidenceError(
                f"{description} is not a "
                "literal string"
            )
        )

    return node.value


def extract_http_request_contract(
    *,
    blob: GitBlobEvidence,
    call_fact: PythonStructureFact,
) -> PythonHttpRequestContract:
    if (
        call_fact.kind
        != PythonStructureKind.CALL
    ):
        raise (
            PythonHttpContractEvidenceError(
                "outbound HTTP contract "
                "requires a CALL fact"
            )
        )

    if (
        call_fact.callee_evidence_id
        is None
    ):
        raise (
            PythonHttpContractEvidenceError(
                "CALL fact is missing exact "
                "callee evidence"
            )
        )

    node = _node_for_fact(
        blob=blob,
        fact=call_fact,
        node_types=(
            ast.Call,
        ),
    )

    assert isinstance(
        node,
        ast.Call,
    )

    if len(
        node.args
    ) < 2:
        raise (
            PythonHttpContractEvidenceError(
                "HTTP request call does not "
                "contain literal method and "
                "route positional arguments"
            )
        )

    method = _literal_string(
        node.args[
            0
        ],
        description="HTTP method",
    ).upper()

    route_template = (
        _literal_string(
            node.args[
                1
            ],
            description=(
                "HTTP route template"
            ),
        )
    )

    evidence_id = (
        "python-http-request-contract:"
        + _identity(
            b"horizon.python-http-request-contract.v1\0",
            blob.evidence_id,
            call_fact.evidence_id,
            call_fact.callee_evidence_id,
            method,
            route_template,
        )
    )

    return PythonHttpRequestContract(
        source_evidence_id=(
            blob.evidence_id
        ),
        call_evidence_id=(
            call_fact.evidence_id
        ),
        callee_evidence_id=(
            call_fact.callee_evidence_id
        ),
        method=method,
        route_template=(
            route_template
        ),
        evidence_id=evidence_id,
    )


_HTTP_DECORATORS = {
    "delete": "DELETE",
    "get": "GET",
    "head": "HEAD",
    "options": "OPTIONS",
    "patch": "PATCH",
    "post": "POST",
    "put": "PUT",
}


def _router_prefix(
    *,
    tree: ast.Module,
    router_name: str,
) -> str:
    prefixes: list[
        str
    ] = []

    for statement in tree.body:
        value: ast.AST | None = None

        if (
            isinstance(
                statement,
                ast.AnnAssign,
            )
            and isinstance(
                statement.target,
                ast.Name,
            )
            and statement.target.id
            == router_name
        ):
            value = (
                statement.value
            )

        elif (
            isinstance(
                statement,
                ast.Assign,
            )
            and any(
                isinstance(
                    target,
                    ast.Name,
                )
                and target.id
                == router_name
                for target
                in statement.targets
            )
        ):
            value = (
                statement.value
            )

        if not isinstance(
            value,
            ast.Call,
        ):
            continue

        for keyword in value.keywords:
            if (
                keyword.arg
                != "prefix"
            ):
                continue

            prefixes.append(
                _literal_string(
                    keyword.value,
                    description=(
                        "router prefix"
                    ),
                )
            )

    if not prefixes:
        return ""

    if len(
        prefixes
    ) != 1:
        raise (
            PythonHttpContractEvidenceError(
                "router prefix is ambiguous"
            )
        )

    return prefixes[
        0
    ]


def _join_route(
    prefix: str,
    route: str,
) -> str:
    if not prefix:
        return route

    if not route:
        return prefix

    return (
        prefix.rstrip(
            "/"
        )
        + "/"
        + route.lstrip(
            "/"
        )
    )


def extract_http_route_contract(
    *,
    blob: GitBlobEvidence,
    handler_fact: PythonStructureFact,
) -> PythonHttpRouteContract:
    if handler_fact.kind not in {
        PythonStructureKind.FUNCTION_DEFINITION,
        PythonStructureKind.ASYNC_FUNCTION_DEFINITION,
    }:
        raise (
            PythonHttpContractEvidenceError(
                "inbound HTTP contract "
                "requires a function definition"
            )
        )

    node = _node_for_fact(
        blob=blob,
        fact=handler_fact,
        node_types=(
            ast.FunctionDef,
            ast.AsyncFunctionDef,
        ),
    )

    assert isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
        ),
    )

    candidates: list[
        tuple[
            str,
            str,
            str,
            ast.Call,
        ]
    ] = []

    for decorator in (
        node.decorator_list
    ):
        if not isinstance(
            decorator,
            ast.Call,
        ):
            continue

        function = (
            decorator.func
        )

        if (
            not isinstance(
                function,
                ast.Attribute,
            )
            or not isinstance(
                function.value,
                ast.Name,
            )
        ):
            continue

        method = (
            _HTTP_DECORATORS.get(
                function.attr
            )
        )

        if method is None:
            continue

        if not decorator.args:
            raise (
                PythonHttpContractEvidenceError(
                    "HTTP route decorator "
                    "has no route template"
                )
            )

        route_template = (
            _literal_string(
                decorator.args[
                    0
                ],
                description=(
                    "HTTP route template"
                ),
            )
        )

        candidates.append(
            (
                function.value.id,
                method,
                route_template,
                decorator,
            )
        )

    if len(
        candidates
    ) != 1:
        raise (
            PythonHttpContractEvidenceError(
                "handler does not expose "
                "exactly one supported literal "
                "HTTP route decorator"
            )
        )

    (
        router_name,
        method,
        route_template,
        decorator_node,
    ) = candidates[
        0
    ]

    tree = _parse(
        blob
    )

    router_prefix = (
        _router_prefix(
            tree=tree,
            router_name=(
                router_name
            ),
        )
    )

    full_route_template = (
        _join_route(
            router_prefix,
            route_template,
        )
    )

    structure = (
        analyze_python_blob(
            blob
        )
    )

    starts = _line_starts(
        blob.content
    )

    (
        decorator_line_start,
        decorator_line_end,
        decorator_byte_start,
        decorator_byte_end,
    ) = _node_span(
        decorator_node,
        starts,
    )

    decorator_facts = [
        fact
        for fact in structure.facts
        if (
            fact.kind
            == PythonStructureKind.DECORATOR
            and fact.structural_parent_id
            == handler_fact.evidence_id
            and fact.line_start
            == decorator_line_start
            and fact.line_end
            == decorator_line_end
            and fact.byte_start
            == decorator_byte_start
            and fact.byte_end
            == decorator_byte_end
        )
    ]

    if len(
        decorator_facts
    ) != 1:
        raise (
            PythonHttpContractEvidenceError(
                "route decorator did not map "
                "to exactly one structural "
                "evidence fact"
            )
        )

    decorator_fact = (
        decorator_facts[
            0
        ]
    )

    evidence_id = (
        "python-http-route-contract:"
        + _identity(
            b"horizon.python-http-route-contract.v1\0",
            blob.evidence_id,
            handler_fact.evidence_id,
            decorator_fact.evidence_id,
            method,
            router_prefix,
            route_template,
            full_route_template,
        )
    )

    return PythonHttpRouteContract(
        source_evidence_id=(
            blob.evidence_id
        ),
        handler_evidence_id=(
            handler_fact.evidence_id
        ),
        decorator_evidence_id=(
            decorator_fact.evidence_id
        ),
        method=method,
        router_prefix=(
            router_prefix
        ),
        route_template=(
            route_template
        ),
        full_route_template=(
            full_route_template
        ),
        evidence_id=evidence_id,
    )


_PARAMETER = re.compile(
    r"\{[^{}]+\}"
)


def _template_shape(
    template: str,
) -> str:
    return _PARAMETER.sub(
        "{parameter}",
        template,
    )


def match_http_contracts(
    *,
    request: PythonHttpRequestContract,
    route: PythonHttpRouteContract,
) -> PythonHttpContractEdge:
    if (
        request.method
        != route.method
    ):
        status = (
            PythonHttpContractMatchStatus
            .NO_MATCH
        )

    elif (
        request.route_template
        == route.full_route_template
    ):
        status = (
            PythonHttpContractMatchStatus
            .EXACT_MATCH
        )

    elif (
        _template_shape(
            request.route_template
        )
        == _template_shape(
            route.full_route_template
        )
    ):
        status = (
            PythonHttpContractMatchStatus
            .TEMPLATE_SHAPE_MATCH
        )

    else:
        status = (
            PythonHttpContractMatchStatus
            .NO_MATCH
        )

    evidence_id = (
        "http-contract-edge:"
        + _identity(
            b"horizon.http-contract-edge.v1\0",
            request.evidence_id,
            route.evidence_id,
            request.method,
            request.route_template,
            route.full_route_template,
            status.value,
        )
    )

    return PythonHttpContractEdge(
        request_contract_evidence_id=(
            request.evidence_id
        ),
        route_contract_evidence_id=(
            route.evidence_id
        ),
        method=request.method,
        client_route_template=(
            request.route_template
        ),
        server_route_template=(
            route.full_route_template
        ),
        status=status,
        evidence_id=evidence_id,
    )
