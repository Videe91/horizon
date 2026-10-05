from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from io import BytesIO
import platform
import symtable
import sys
import tokenize

from horizon.repository.git_blob import (
    GitBlobEvidence,
)


class PythonBindingEvidenceError(Exception):
    """CPython could not produce binding evidence for Python source."""


class PythonScopeKind(str, Enum):
    MODULE = "MODULE"
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    ANNOTATION = "ANNOTATION"
    TYPE_ALIAS = "TYPE_ALIAS"
    TYPE_PARAMETERS = "TYPE_PARAMETERS"
    TYPE_VARIABLE = "TYPE_VARIABLE"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class PythonBindingSymbol:
    name: str
    scope: tuple[str, ...]
    scope_kind: PythonScopeKind
    scope_line: int

    is_referenced: bool
    is_imported: bool
    is_parameter: bool
    is_type_parameter: bool

    is_global: bool
    is_nonlocal: bool
    is_declared_global: bool
    is_local: bool
    is_free: bool
    is_free_class: bool

    is_assigned: bool
    is_annotated: bool
    is_namespace: bool

    is_comp_iter: bool
    is_comp_cell: bool

    source_evidence_id: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class PythonBindingAnalysis:
    path: str
    source_evidence_id: str
    python_implementation: str
    python_version: str
    symbols: tuple[PythonBindingSymbol, ...]
    analysis_id: str


def _decode_python_source(
    content: bytes,
) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(
            BytesIO(content).readline,
        )

        return content.decode(
            encoding,
        )

    except (
        SyntaxError,
        UnicodeDecodeError,
        LookupError,
    ) as exc:
        raise PythonBindingEvidenceError(
            f"unable to decode Python source: {exc}"
        ) from exc


def _scope_kind(
    table: symtable.SymbolTable,
) -> PythonScopeKind:
    raw_type = table.get_type()

    value = getattr(
        raw_type,
        "value",
        raw_type,
    )

    normalized = str(
        value
    ).lower()

    mapping = {
        "module": PythonScopeKind.MODULE,
        "function": PythonScopeKind.FUNCTION,
        "class": PythonScopeKind.CLASS,
        "annotation": PythonScopeKind.ANNOTATION,
        "type alias": PythonScopeKind.TYPE_ALIAS,
        "type parameters": PythonScopeKind.TYPE_PARAMETERS,
        "type variable": PythonScopeKind.TYPE_VARIABLE,
    }

    return mapping.get(
        normalized,
        PythonScopeKind.OTHER,
    )


def _optional_symbol_flag(
    symbol: symtable.Symbol,
    method_name: str,
) -> bool:
    method = getattr(
        symbol,
        method_name,
        None,
    )

    if method is None:
        return False

    return bool(
        method()
    )


def _symbol_identity(
    *,
    source_evidence_id: str,
    python_implementation: str,
    python_version: str,
    name: str,
    scope: tuple[str, ...],
    scope_kind: PythonScopeKind,
    scope_line: int,
    flags: tuple[bool, ...],
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.python-binding-symbol.v1\0"
    )

    values = (
        source_evidence_id,
        python_implementation,
        python_version,
        name,
        "/".join(scope),
        scope_kind.value,
        str(scope_line),
    )

    for value in values:
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(b"\0")

    for flag in flags:
        digest.update(
            b"1\0"
            if flag
            else b"0\0"
        )

    return (
        "python-binding-symbol:"
        + digest.hexdigest()
    )


def _table_sort_key(
    table: symtable.SymbolTable,
) -> tuple[int, str, str]:
    return (
        table.get_lineno(),
        table.get_name(),
        _scope_kind(
            table
        ).value,
    )


def _collect_symbols(
    *,
    table: symtable.SymbolTable,
    scope: tuple[str, ...],
    source_evidence_id: str,
    python_implementation: str,
    python_version: str,
    output: list[PythonBindingSymbol],
) -> None:
    scope_kind = _scope_kind(
        table
    )

    scope_line = table.get_lineno()

    symbols = sorted(
        table.get_symbols(),
        key=lambda symbol: symbol.get_name(),
    )

    for symbol in symbols:
        is_referenced = (
            symbol.is_referenced()
        )

        is_imported = (
            symbol.is_imported()
        )

        is_parameter = (
            symbol.is_parameter()
        )

        is_type_parameter = (
            _optional_symbol_flag(
                symbol,
                "is_type_parameter",
            )
        )

        is_global = (
            symbol.is_global()
        )

        is_nonlocal = (
            symbol.is_nonlocal()
        )

        is_declared_global = (
            symbol.is_declared_global()
        )

        is_local = (
            symbol.is_local()
        )

        is_free = (
            symbol.is_free()
        )

        is_free_class = (
            _optional_symbol_flag(
                symbol,
                "is_free_class",
            )
        )

        is_assigned = (
            symbol.is_assigned()
        )

        is_annotated = (
            symbol.is_annotated()
        )

        is_namespace = (
            symbol.is_namespace()
        )

        is_comp_iter = (
            _optional_symbol_flag(
                symbol,
                "is_comp_iter",
            )
        )

        is_comp_cell = (
            _optional_symbol_flag(
                symbol,
                "is_comp_cell",
            )
        )

        flags = (
            is_referenced,
            is_imported,
            is_parameter,
            is_type_parameter,
            is_global,
            is_nonlocal,
            is_declared_global,
            is_local,
            is_free,
            is_free_class,
            is_assigned,
            is_annotated,
            is_namespace,
            is_comp_iter,
            is_comp_cell,
        )

        evidence_id = (
            _symbol_identity(
                source_evidence_id=(
                    source_evidence_id
                ),
                python_implementation=(
                    python_implementation
                ),
                python_version=(
                    python_version
                ),
                name=symbol.get_name(),
                scope=scope,
                scope_kind=scope_kind,
                scope_line=scope_line,
                flags=flags,
            )
        )

        output.append(
            PythonBindingSymbol(
                name=symbol.get_name(),
                scope=scope,
                scope_kind=scope_kind,
                scope_line=scope_line,
                is_referenced=is_referenced,
                is_imported=is_imported,
                is_parameter=is_parameter,
                is_type_parameter=(
                    is_type_parameter
                ),
                is_global=is_global,
                is_nonlocal=is_nonlocal,
                is_declared_global=(
                    is_declared_global
                ),
                is_local=is_local,
                is_free=is_free,
                is_free_class=(
                    is_free_class
                ),
                is_assigned=is_assigned,
                is_annotated=is_annotated,
                is_namespace=is_namespace,
                is_comp_iter=is_comp_iter,
                is_comp_cell=is_comp_cell,
                source_evidence_id=(
                    source_evidence_id
                ),
                evidence_id=evidence_id,
            )
        )

    children = sorted(
        table.get_children(),
        key=_table_sort_key,
    )

    for child in children:
        child_scope = (
            scope
            + (
                child.get_name(),
            )
        )

        _collect_symbols(
            table=child,
            scope=child_scope,
            source_evidence_id=(
                source_evidence_id
            ),
            python_implementation=(
                python_implementation
            ),
            python_version=(
                python_version
            ),
            output=output,
        )


def _analysis_identity(
    *,
    source_evidence_id: str,
    python_implementation: str,
    python_version: str,
    symbols: tuple[
        PythonBindingSymbol,
        ...,
    ],
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.python-binding-analysis.v1\0"
    )

    for value in (
        source_evidence_id,
        python_implementation,
        python_version,
    ):
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(b"\0")

    for symbol in symbols:
        digest.update(
            symbol.evidence_id.encode(
                "ascii"
            )
        )
        digest.update(b"\0")

    return (
        "python-binding-analysis:"
        + digest.hexdigest()
    )


def analyze_python_bindings(
    blob: GitBlobEvidence,
) -> PythonBindingAnalysis:
    source = _decode_python_source(
        blob.content
    )

    try:
        root = symtable.symtable(
            source,
            blob.path,
            "exec",
        )

    except (
        SyntaxError,
        ValueError,
        TypeError,
    ) as exc:
        raise PythonBindingEvidenceError(
            "unable to compile Python binding evidence "
            f"for {blob.path!r}: {exc}"
        ) from exc

    python_implementation = (
        sys.implementation.name
    )

    python_version = (
        platform.python_version()
    )

    collected: list[
        PythonBindingSymbol
    ] = []

    _collect_symbols(
        table=root,
        scope=(),
        source_evidence_id=(
            blob.evidence_id
        ),
        python_implementation=(
            python_implementation
        ),
        python_version=(
            python_version
        ),
        output=collected,
    )

    symbols = tuple(
        collected
    )

    return PythonBindingAnalysis(
        path=blob.path,
        source_evidence_id=(
            blob.evidence_id
        ),
        python_implementation=(
            python_implementation
        ),
        python_version=(
            python_version
        ),
        symbols=symbols,
        analysis_id=_analysis_identity(
            source_evidence_id=(
                blob.evidence_id
            ),
            python_implementation=(
                python_implementation
            ),
            python_version=(
                python_version
            ),
            symbols=symbols,
        ),
    )
