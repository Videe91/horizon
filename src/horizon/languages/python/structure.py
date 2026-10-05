from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from horizon.repository.git_blob import (
    GitBlobEvidence,
)


class PythonSyntaxEvidenceError(Exception):
    """Python source could not be parsed into structural evidence."""


class PythonStructureKind(str, Enum):
    MODULE = "MODULE"
    CLASS_DEFINITION = "CLASS_DEFINITION"
    FUNCTION_DEFINITION = "FUNCTION_DEFINITION"
    ASYNC_FUNCTION_DEFINITION = "ASYNC_FUNCTION_DEFINITION"
    IMPORT = "IMPORT"
    FROM_IMPORT = "FROM_IMPORT"
    CALL = "CALL"
    DECORATOR = "DECORATOR"


@dataclass(frozen=True, slots=True)
class PythonStructureFact:
    kind: PythonStructureKind
    name: str
    module: str | None
    alias: str | None
    scope: tuple[str, ...]
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int
    structural_parent_id: str | None
    source_evidence_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class PythonStructureAnalysis:
    path: str
    source_evidence_id: str
    facts: tuple[PythonStructureFact, ...]
    analysis_id: str


def _qualified_name(
    node: ast.AST,
) -> str | None:
    if isinstance(
        node,
        ast.Name,
    ):
        return node.id

    if isinstance(
        node,
        ast.Attribute,
    ):
        prefix = _qualified_name(
            node.value,
        )

        if prefix is None:
            return node.attr

        return (
            prefix
            + "."
            + node.attr
        )

    if isinstance(
        node,
        ast.Call,
    ):
        return _qualified_name(
            node.func,
        )

    return None


def _line_starts(
    content: bytes,
) -> tuple[int, ...]:
    starts = [0]

    for index, value in enumerate(
        content
    ):
        if value == 10:
            starts.append(
                index + 1
            )

    return tuple(starts)


def _node_span(
    node: ast.AST,
    starts: tuple[int, ...],
) -> tuple[
    int,
    int,
    int,
    int,
]:
    lineno = getattr(
        node,
        "lineno",
        None,
    )

    end_lineno = getattr(
        node,
        "end_lineno",
        None,
    )

    col_offset = getattr(
        node,
        "col_offset",
        None,
    )

    end_col_offset = getattr(
        node,
        "end_col_offset",
        None,
    )

    if (
        lineno is None
        or end_lineno is None
        or col_offset is None
        or end_col_offset is None
    ):
        raise PythonSyntaxEvidenceError(
            "Python syntax node does not expose "
            "a complete source span"
        )

    byte_start = (
        starts[lineno - 1]
        + col_offset
    )

    byte_end = (
        starts[end_lineno - 1]
        + end_col_offset
    )

    return (
        lineno,
        end_lineno,
        byte_start,
        byte_end,
    )


def _fact_identity(
    *,
    source_evidence_id: str,
    kind: PythonStructureKind,
    name: str,
    module: str | None,
    alias: str | None,
    scope: tuple[str, ...],
    structural_parent_id: str | None,
    line_start: int,
    line_end: int,
    byte_start: int,
    byte_end: int,
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.python-structure-fact.v1\0"
    )

    values = (
        source_evidence_id,
        kind.value,
        name,
        module or "",
        alias or "",
        "/".join(scope),
        structural_parent_id or "",
        str(line_start),
        str(line_end),
        str(byte_start),
        str(byte_end),
    )

    for value in values:
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(b"\0")

    return (
        "python-structure-fact:"
        + digest.hexdigest()
    )


class _StructureVisitor(
    ast.NodeVisitor,
):
    def __init__(
        self,
        *,
        blob: GitBlobEvidence,
    ) -> None:
        self._blob = blob

        self._starts = _line_starts(
            blob.content
        )

        self._scope: list[str] = []

        self._structural_parent_ids: list[str] = []

        self.facts: list[
            PythonStructureFact
        ] = []

    def _add_fact(
        self,
        *,
        kind: PythonStructureKind,
        name: str,
        node: ast.AST | None,
        module: str | None = None,
        alias: str | None = None,
        scope: tuple[str, ...] | None = None,
        structural_parent_id: str | None = None,
    ) -> PythonStructureFact:
        if scope is None:
            scope = tuple(
                self._scope
            )

        if (
            structural_parent_id is None
            and self._structural_parent_ids
        ):
            structural_parent_id = (
                self._structural_parent_ids[-1]
            )

        if node is None:
            line_start = 1

            line_end = max(
                1,
                len(
                    self._blob.content.splitlines()
                ),
            )

            byte_start = 0
            byte_end = len(
                self._blob.content
            )

        else:
            (
                line_start,
                line_end,
                byte_start,
                byte_end,
            ) = _node_span(
                node,
                self._starts,
            )

        evidence_id = _fact_identity(
            source_evidence_id=(
                self._blob.evidence_id
            ),
            kind=kind,
            name=name,
            module=module,
            alias=alias,
            scope=scope,
            structural_parent_id=(
                structural_parent_id
            ),
            line_start=line_start,
            line_end=line_end,
            byte_start=byte_start,
            byte_end=byte_end,
        )

        fact = PythonStructureFact(
            kind=kind,
            name=name,
            module=module,
            alias=alias,
            scope=scope,
            line_start=line_start,
            line_end=line_end,
            byte_start=byte_start,
            byte_end=byte_end,
            structural_parent_id=(
                structural_parent_id
            ),
            source_evidence_id=(
                self._blob.evidence_id
            ),
            evidence_id=evidence_id,
        )

        self.facts.append(
            fact
        )

        return fact

    def add_module(
        self,
    ) -> None:
        fact = self._add_fact(
            kind=(
                PythonStructureKind.MODULE
            ),
            name=self._blob.path,
            node=None,
            scope=(),
            structural_parent_id=None,
        )

        self._structural_parent_ids.append(
            fact.evidence_id
        )

    def visit_Import(
        self,
        node: ast.Import,
    ) -> None:
        for imported in node.names:
            self._add_fact(
                kind=(
                    PythonStructureKind.IMPORT
                ),
                name=imported.name,
                alias=imported.asname,
                node=node,
            )

    def visit_ImportFrom(
        self,
        node: ast.ImportFrom,
    ) -> None:
        module = (
            ("." * node.level)
            + (node.module or "")
        )

        for imported in node.names:
            self._add_fact(
                kind=(
                    PythonStructureKind.FROM_IMPORT
                ),
                name=imported.name,
                module=module,
                alias=imported.asname,
                node=node,
            )

    def _visit_decorators(
        self,
        decorators: list[ast.expr],
        decorated_scope: tuple[str, ...],
        definition_id: str,
    ) -> None:
        for decorator in decorators:
            name = _qualified_name(
                decorator
            )

            if name is None:
                name = "<dynamic>"

            decorator_fact = self._add_fact(
                kind=(
                    PythonStructureKind.DECORATOR
                ),
                name=name,
                node=decorator,
                scope=decorated_scope,
                structural_parent_id=(
                    definition_id
                ),
            )

            self._structural_parent_ids.append(
                decorator_fact.evidence_id
            )

            try:
                self.visit(
                    decorator
                )
            finally:
                self._structural_parent_ids.pop()

    def visit_ClassDef(
        self,
        node: ast.ClassDef,
    ) -> None:
        parent_scope = tuple(
            self._scope
        )

        class_fact = self._add_fact(
            kind=(
                PythonStructureKind.CLASS_DEFINITION
            ),
            name=node.name,
            node=node,
            scope=parent_scope,
        )

        decorated_scope = (
            parent_scope
            + (node.name,)
        )

        self._visit_decorators(
            node.decorator_list,
            decorated_scope,
            class_fact.evidence_id,
        )

        self._scope.append(
            node.name
        )

        self._structural_parent_ids.append(
            class_fact.evidence_id
        )

        try:
            for statement in node.body:
                self.visit(
                    statement
                )
        finally:
            self._structural_parent_ids.pop()
            self._scope.pop()

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
    ) -> None:
        self._visit_function(
            node,
            PythonStructureKind.FUNCTION_DEFINITION,
        )

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        self._visit_function(
            node,
            PythonStructureKind.ASYNC_FUNCTION_DEFINITION,
        )

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        kind: PythonStructureKind,
    ) -> None:
        parent_scope = tuple(
            self._scope
        )

        function_fact = self._add_fact(
            kind=kind,
            name=node.name,
            node=node,
            scope=parent_scope,
        )

        decorated_scope = (
            parent_scope
            + (node.name,)
        )

        self._visit_decorators(
            node.decorator_list,
            decorated_scope,
            function_fact.evidence_id,
        )

        self._scope.append(
            node.name
        )

        self._structural_parent_ids.append(
            function_fact.evidence_id
        )

        try:
            for statement in node.body:
                self.visit(
                    statement
                )
        finally:
            self._structural_parent_ids.pop()
            self._scope.pop()

    def visit_Call(
        self,
        node: ast.Call,
    ) -> None:
        name = _qualified_name(
            node.func
        )

        if name is None:
            name = "<dynamic>"

        call_fact = self._add_fact(
            kind=(
                PythonStructureKind.CALL
            ),
            name=name,
            node=node,
        )

        self._structural_parent_ids.append(
            call_fact.evidence_id
        )

        try:
            self.generic_visit(
                node
            )
        finally:
            self._structural_parent_ids.pop()


def _analysis_identity(
    *,
    source_evidence_id: str,
    facts: tuple[
        PythonStructureFact,
        ...,
    ],
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.python-structure-analysis.v1\0"
    )

    digest.update(
        source_evidence_id.encode(
            "ascii"
        )
    )
    digest.update(b"\0")

    for fact in facts:
        digest.update(
            fact.evidence_id.encode(
                "ascii"
            )
        )
        digest.update(b"\0")

    return (
        "python-structure-analysis:"
        + digest.hexdigest()
    )


def analyze_python_blob(
    blob: GitBlobEvidence,
) -> PythonStructureAnalysis:
    try:
        tree = ast.parse(
            blob.content,
            filename=blob.path,
            type_comments=True,
        )
    except (
        SyntaxError,
        ValueError,
    ) as exc:
        raise PythonSyntaxEvidenceError(
            f"unable to parse Python evidence "
            f"{blob.path!r}: {exc}"
        ) from exc

    visitor = _StructureVisitor(
        blob=blob,
    )

    visitor.add_module()

    visitor.visit(
        tree
    )

    facts = tuple(
        visitor.facts
    )

    return PythonStructureAnalysis(
        path=blob.path,
        source_evidence_id=(
            blob.evidence_id
        ),
        facts=facts,
        analysis_id=_analysis_identity(
            source_evidence_id=(
                blob.evidence_id
            ),
            facts=facts,
        ),
    )
