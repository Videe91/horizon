from __future__ import annotations

import ast
import dis
import platform
import sys
import tokenize
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from io import BytesIO

from horizon.languages.python.structure import (
    PythonStructureKind,
    PythonSyntaxEvidenceError,
    analyze_python_blob,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)


class PythonCompilerBindingEvidenceError(Exception):
    """CPython compiler binding evidence could not be established."""


class PythonCompiledBindingOperation(str, Enum):
    STORE = "STORE"
    DELETE = "DELETE"


class PythonCompiledBindingStatus(str, Enum):
    DIRECT_SINGLE_ORIGIN = "DIRECT_SINGLE_ORIGIN"
    MULTIPLE_STORES = "MULTIPLE_STORES"
    DELETED = "DELETED"
    NO_DIRECT_ORIGIN = "NO_DIRECT_ORIGIN"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class PythonCompiledBindingOperationEvidence:
    operation: PythonCompiledBindingOperation
    opcode: str
    offset: int
    line: int | None
    source_evidence_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class PythonCompiledModuleBindingEvidence:
    name: str
    status: PythonCompiledBindingStatus
    source_evidence_id: str

    direct_origin_evidence_id: str | None

    operations: tuple[
        PythonCompiledBindingOperationEvidence,
        ...,
    ]

    python_implementation: str
    python_version: str

    evidence_id: str


def _decode_python_source(
    content: bytes,
) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(
            BytesIO(
                content
            ).readline
        )

        return content.decode(
            encoding
        )

    except (
        SyntaxError,
        UnicodeDecodeError,
        LookupError,
    ) as exc:
        raise PythonCompilerBindingEvidenceError(
            f"unable to decode Python source: {exc}"
        ) from exc


def _hash_parts(
    prefix: bytes,
    *parts: str,
) -> str:
    digest = sha256()

    digest.update(
        prefix
    )

    for part in parts:
        digest.update(
            part.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(
            b"\0"
        )

    return digest.hexdigest()


def _operation_identity(
    *,
    source_evidence_id: str,
    name: str,
    operation: PythonCompiledBindingOperation,
    opcode: str,
    offset: int,
    line: int | None,
    python_implementation: str,
    python_version: str,
) -> str:
    return (
        "python-compiled-binding-operation:"
        + _hash_parts(
            b"horizon.python-compiled-binding-operation.v1\0",
            source_evidence_id,
            name,
            operation.value,
            opcode,
            str(
                offset
            ),
            (
                ""
                if line is None
                else str(
                    line
                )
            ),
            python_implementation,
            python_version,
        )
    )


def _evidence_identity(
    *,
    source_evidence_id: str,
    name: str,
    status: PythonCompiledBindingStatus,
    direct_origin_evidence_id: str | None,
    operations: tuple[
        PythonCompiledBindingOperationEvidence,
        ...,
    ],
    python_implementation: str,
    python_version: str,
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.python-compiled-module-binding.v1\0"
    )

    for value in (
        source_evidence_id,
        name,
        status.value,
        direct_origin_evidence_id or "",
        python_implementation,
        python_version,
    ):
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(
            b"\0"
        )

    for operation in operations:
        digest.update(
            operation.evidence_id.encode(
                "ascii"
            )
        )
        digest.update(
            b"\0"
        )

    return (
        "python-compiled-module-binding:"
        + digest.hexdigest()
    )


def _direct_ast_definition(
    tree: ast.Module,
    name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None:
    matches = [
        node
        for node in tree.body
        if (
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            )
            and node.name == name
        )
    ]

    if len(
        matches
    ) != 1:
        return None

    return matches[0]


def _structure_kind_for_node(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> PythonStructureKind:
    if isinstance(
        node,
        ast.AsyncFunctionDef,
    ):
        return (
            PythonStructureKind.ASYNC_FUNCTION_DEFINITION
        )

    if isinstance(
        node,
        ast.FunctionDef,
    ):
        return (
            PythonStructureKind.FUNCTION_DEFINITION
        )

    return (
        PythonStructureKind.CLASS_DEFINITION
    )


def _direct_origin_evidence_id(
    *,
    blob: GitBlobEvidence,
    tree: ast.Module,
    name: str,
) -> tuple[
    str | None,
    int | None,
]:
    direct_node = _direct_ast_definition(
        tree,
        name,
    )

    if direct_node is None:
        return (
            None,
            None,
        )

    try:
        structure = analyze_python_blob(
            blob
        )
    except PythonSyntaxEvidenceError as exc:
        raise PythonCompilerBindingEvidenceError(
            "unable to analyze Python structure "
            f"for {blob.path!r}: {exc}"
        ) from exc

    kind = _structure_kind_for_node(
        direct_node
    )

    matches = [
        fact
        for fact in structure.facts
        if (
            fact.kind == kind
            and fact.name == name
            and fact.scope == ()
            and fact.line_start
            == direct_node.lineno
        )
    ]

    if len(
        matches
    ) != 1:
        return (
            None,
            direct_node.lineno,
        )

    return (
        matches[0].evidence_id,
        direct_node.lineno,
    )


def _compiled_operations(
    *,
    code,
    name: str,
    source_evidence_id: str,
    python_implementation: str,
    python_version: str,
) -> tuple[
    PythonCompiledBindingOperationEvidence,
    ...,
]:
    output: list[
        PythonCompiledBindingOperationEvidence
    ] = []

    store_opcodes = {
        "STORE_NAME",
        "STORE_GLOBAL",
    }

    delete_opcodes = {
        "DELETE_NAME",
        "DELETE_GLOBAL",
    }

    for instruction in dis.get_instructions(
        code
    ):
        if instruction.argval != name:
            continue

        if instruction.opname in store_opcodes:
            operation = (
                PythonCompiledBindingOperation.STORE
            )

        elif instruction.opname in delete_opcodes:
            operation = (
                PythonCompiledBindingOperation.DELETE
            )

        else:
            continue

        positions = instruction.positions

        line = (
            positions.lineno
            if positions is not None
            else instruction.starts_line
        )

        evidence_id = (
            _operation_identity(
                source_evidence_id=(
                    source_evidence_id
                ),
                name=name,
                operation=operation,
                opcode=(
                    instruction.opname
                ),
                offset=(
                    instruction.offset
                ),
                line=line,
                python_implementation=(
                    python_implementation
                ),
                python_version=(
                    python_version
                ),
            )
        )

        output.append(
            PythonCompiledBindingOperationEvidence(
                operation=operation,
                opcode=instruction.opname,
                offset=instruction.offset,
                line=line,
                source_evidence_id=(
                    source_evidence_id
                ),
                evidence_id=evidence_id,
            )
        )

    return tuple(
        output
    )


def analyze_compiled_module_binding(
    blob: GitBlobEvidence,
    name: str,
) -> PythonCompiledModuleBindingEvidence:
    if (
        not isinstance(
            name,
            str,
        )
        or not name
    ):
        raise PythonCompilerBindingEvidenceError(
            "binding name must be a non-empty string"
        )

    source = _decode_python_source(
        blob.content
    )

    try:
        tree = ast.parse(
            source,
            filename=blob.path,
            mode="exec",
        )

        code = compile(
            source,
            blob.path,
            "exec",
        )

    except (
        SyntaxError,
        ValueError,
        TypeError,
    ) as exc:
        raise PythonCompilerBindingEvidenceError(
            "unable to compile Python binding evidence "
            f"for {blob.path!r}: {exc}"
        ) from exc

    python_implementation = (
        sys.implementation.name
    )

    python_version = (
        platform.python_version()
    )

    (
        direct_origin_evidence_id,
        direct_origin_line,
    ) = _direct_origin_evidence_id(
        blob=blob,
        tree=tree,
        name=name,
    )

    operations = _compiled_operations(
        code=code,
        name=name,
        source_evidence_id=(
            blob.evidence_id
        ),
        python_implementation=(
            python_implementation
        ),
        python_version=(
            python_version
        ),
    )

    stores = [
        operation
        for operation in operations
        if (
            operation.operation
            == PythonCompiledBindingOperation.STORE
        )
    ]

    deletes = [
        operation
        for operation in operations
        if (
            operation.operation
            == PythonCompiledBindingOperation.DELETE
        )
    ]

    if deletes:
        status = (
            PythonCompiledBindingStatus.DELETED
        )

    elif len(
        stores
    ) > 1:
        status = (
            PythonCompiledBindingStatus.MULTIPLE_STORES
        )

    elif len(
        stores
    ) == 0:
        status = (
            PythonCompiledBindingStatus.NOT_FOUND
        )

    elif (
        direct_origin_evidence_id is not None
        and (
            direct_origin_line is None
            or stores[0].line
            == direct_origin_line
        )
    ):
        status = (
            PythonCompiledBindingStatus.DIRECT_SINGLE_ORIGIN
        )

    else:
        status = (
            PythonCompiledBindingStatus.NO_DIRECT_ORIGIN
        )

    evidence_id = (
        _evidence_identity(
            source_evidence_id=(
                blob.evidence_id
            ),
            name=name,
            status=status,
            direct_origin_evidence_id=(
                direct_origin_evidence_id
            ),
            operations=operations,
            python_implementation=(
                python_implementation
            ),
            python_version=(
                python_version
            ),
        )
    )

    return PythonCompiledModuleBindingEvidence(
        name=name,
        status=status,
        source_evidence_id=(
            blob.evidence_id
        ),
        direct_origin_evidence_id=(
            direct_origin_evidence_id
        ),
        operations=operations,
        python_implementation=(
            python_implementation
        ),
        python_version=(
            python_version
        ),
        evidence_id=evidence_id,
    )
