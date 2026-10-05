from __future__ import annotations

import ast
import dis
import platform
import sys
import tokenize
import types
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


class PythonImportUseEvidenceError(Exception):
    """Compiler-backed import-to-use provenance could not be established."""


class PythonImportUseOperationKind(str, Enum):
    IMPORT_MODULE = "IMPORT_MODULE"
    IMPORT_MEMBER = "IMPORT_MEMBER"
    LOCAL_STORE = "LOCAL_STORE"
    LOCAL_LOAD = "LOCAL_LOAD"
    CALL = "CALL"


class PythonImportUseStatus(str, Enum):
    PROVEN_LOCAL_IMPORT_TO_CALL = "PROVEN_LOCAL_IMPORT_TO_CALL"
    REBOUND_BEFORE_CALL = "REBOUND_BEFORE_CALL"
    DELETED_BEFORE_CALL = "DELETED_BEFORE_CALL"
    NO_IMPORT_TO_CALL_FLOW = "NO_IMPORT_TO_CALL_FLOW"


@dataclass(frozen=True, slots=True)
class PythonImportUseOperationEvidence:
    kind: PythonImportUseOperationKind
    raw_opcode: str
    raw_argument: str
    offset: int
    line: int | None
    end_line: int | None
    evidence_id: str


@dataclass(frozen=True, slots=True)
class PythonImportUseEvidence:
    status: PythonImportUseStatus

    module_name: str
    imported_name: str
    local_name: str

    source_evidence_id: str

    import_fact_evidence_id: str
    call_fact_evidence_id: str
    parent_definition_evidence_id: str

    operations: tuple[
        PythonImportUseOperationEvidence,
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
            BytesIO(content).readline
        )

        return content.decode(
            encoding
        )

    except (
        SyntaxError,
        UnicodeDecodeError,
        LookupError,
    ) as exc:
        raise PythonImportUseEvidenceError(
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


def _instruction_line(
    instruction: dis.Instruction,
) -> int | None:
    positions = instruction.positions

    if positions is not None:
        return positions.lineno

    return instruction.starts_line


def _instruction_end_line(
    instruction: dis.Instruction,
) -> int | None:
    positions = instruction.positions

    if positions is None:
        return instruction.starts_line

    if positions.end_lineno is not None:
        return positions.end_lineno

    return positions.lineno


def _line_overlaps(
    instruction: dis.Instruction,
    *,
    start: int,
    end: int,
) -> bool:
    line = _instruction_line(
        instruction
    )

    end_line = _instruction_end_line(
        instruction
    )

    if line is None:
        return False

    if end_line is None:
        end_line = line

    return not (
        end_line < start
        or line > end
    )


def _operation_identity(
    *,
    source_evidence_id: str,
    import_fact_evidence_id: str,
    call_fact_evidence_id: str,
    kind: PythonImportUseOperationKind,
    instruction: dis.Instruction,
    python_implementation: str,
    python_version: str,
) -> str:
    line = _instruction_line(
        instruction
    )

    end_line = _instruction_end_line(
        instruction
    )

    return (
        "python-import-use-operation:"
        + _hash_parts(
            b"horizon.python-import-use-operation.v1\0",
            source_evidence_id,
            import_fact_evidence_id,
            call_fact_evidence_id,
            kind.value,
            instruction.opname,
            repr(
                instruction.argval
            ),
            str(
                instruction.offset
            ),
            (
                ""
                if line is None
                else str(line)
            ),
            (
                ""
                if end_line is None
                else str(end_line)
            ),
            python_implementation,
            python_version,
        )
    )


def _make_operation(
    *,
    source_evidence_id: str,
    import_fact_evidence_id: str,
    call_fact_evidence_id: str,
    kind: PythonImportUseOperationKind,
    instruction: dis.Instruction,
    python_implementation: str,
    python_version: str,
) -> PythonImportUseOperationEvidence:
    return PythonImportUseOperationEvidence(
        kind=kind,
        raw_opcode=instruction.opname,
        raw_argument=repr(
            instruction.argval
        ),
        offset=instruction.offset,
        line=_instruction_line(
            instruction
        ),
        end_line=_instruction_end_line(
            instruction
        ),
        evidence_id=_operation_identity(
            source_evidence_id=(
                source_evidence_id
            ),
            import_fact_evidence_id=(
                import_fact_evidence_id
            ),
            call_fact_evidence_id=(
                call_fact_evidence_id
            ),
            kind=kind,
            instruction=instruction,
            python_implementation=(
                python_implementation
            ),
            python_version=(
                python_version
            ),
        ),
    )


def _evidence_identity(
    *,
    source_evidence_id: str,
    import_fact_evidence_id: str,
    call_fact_evidence_id: str,
    parent_definition_evidence_id: str,
    status: PythonImportUseStatus,
    module_name: str,
    imported_name: str,
    local_name: str,
    operations: tuple[
        PythonImportUseOperationEvidence,
        ...,
    ],
    python_implementation: str,
    python_version: str,
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.python-import-use-provenance.v1\0"
    )

    for value in (
        source_evidence_id,
        import_fact_evidence_id,
        call_fact_evidence_id,
        parent_definition_evidence_id,
        status.value,
        module_name,
        imported_name,
        local_name,
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
        "python-import-use-provenance:"
        + digest.hexdigest()
    )


def _find_fact(
    facts,
    evidence_id: str,
):
    matches = [
        fact
        for fact in facts
        if fact.evidence_id == evidence_id
    ]

    if len(matches) != 1:
        raise PythonImportUseEvidenceError(
            "structural evidence identity does not "
            f"resolve uniquely: {evidence_id!r}"
        )

    return matches[0]


def _local_name_for_import(
    *,
    tree: ast.Module,
    module_name: str,
    imported_name: str,
    import_line: int,
) -> str:
    matches: list[str] = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.ImportFrom,
        ):
            continue

        if node.module != module_name:
            continue

        if node.lineno != import_line:
            continue

        for alias in node.names:
            if alias.name != imported_name:
                continue

            matches.append(
                alias.asname
                or alias.name
            )

    if len(matches) != 1:
        raise PythonImportUseEvidenceError(
            "unable to resolve exactly one local import "
            f"name for {module_name!r}.{imported_name!r} "
            f"at line {import_line}"
        )

    return matches[0]


def _all_code_objects(
    root: types.CodeType,
) -> tuple[types.CodeType, ...]:
    output: list[
        types.CodeType
    ] = []

    def visit(
        code: types.CodeType,
    ) -> None:
        output.append(
            code
        )

        for constant in code.co_consts:
            if isinstance(
                constant,
                types.CodeType,
            ):
                visit(
                    constant
                )

    visit(
        root
    )

    return tuple(
        output
    )


def _find_parent_code_object(
    *,
    module_code: types.CodeType,
    parent_fact,
) -> types.CodeType:
    candidates = [
        code
        for code in _all_code_objects(
            module_code
        )
        if (
            code.co_name
            == parent_fact.name
            and code.co_firstlineno
            == parent_fact.line_start
        )
    ]

    if len(candidates) == 1:
        return candidates[0]

    span_candidates = [
        code
        for code in _all_code_objects(
            module_code
        )
        if (
            code.co_name
            == parent_fact.name
            and parent_fact.line_start
            <= code.co_firstlineno
            <= parent_fact.line_end
        )
    ]

    if len(span_candidates) == 1:
        return span_candidates[0]

    raise PythonImportUseEvidenceError(
        "unable to resolve exactly one CPython code object "
        "for structural parent "
        f"{parent_fact.evidence_id!r}"
    )


def _is_local_store(
    opcode: str,
) -> bool:
    return (
        opcode.startswith(
            "STORE_FAST"
        )
        or opcode == "STORE_DEREF"
    )


def _is_local_delete(
    opcode: str,
) -> bool:
    return (
        opcode.startswith(
            "DELETE_FAST"
        )
        or opcode == "DELETE_DEREF"
    )


def _is_local_load(
    opcode: str,
) -> bool:
    return (
        opcode.startswith(
            "LOAD_FAST"
        )
        or opcode == "LOAD_DEREF"
    )


def _first_after(
    instructions: tuple[
        dis.Instruction,
        ...,
    ],
    *,
    minimum_offset: int,
    predicate,
) -> dis.Instruction | None:
    for instruction in instructions:
        if instruction.offset <= minimum_offset:
            continue

        if predicate(
            instruction
        ):
            return instruction

    return None


def analyze_import_to_call_provenance(
    blob: GitBlobEvidence,
    import_fact_evidence_id: str,
    call_fact_evidence_id: str,
) -> PythonImportUseEvidence:
    if not import_fact_evidence_id:
        raise PythonImportUseEvidenceError(
            "import structural evidence identity "
            "must be non-empty"
        )

    if not call_fact_evidence_id:
        raise PythonImportUseEvidenceError(
            "call structural evidence identity "
            "must be non-empty"
        )

    source = _decode_python_source(
        blob.content
    )

    try:
        structure = analyze_python_blob(
            blob
        )

    except PythonSyntaxEvidenceError as exc:
        raise PythonImportUseEvidenceError(
            "unable to analyze structural evidence "
            f"for {blob.path!r}: {exc}"
        ) from exc

    import_fact = _find_fact(
        structure.facts,
        import_fact_evidence_id,
    )

    call_fact = _find_fact(
        structure.facts,
        call_fact_evidence_id,
    )

    if (
        import_fact.kind
        != PythonStructureKind.FROM_IMPORT
    ):
        raise PythonImportUseEvidenceError(
            "import evidence does not identify "
            "a FROM_IMPORT structural fact"
        )

    if (
        call_fact.kind
        != PythonStructureKind.CALL
    ):
        raise PythonImportUseEvidenceError(
            "call evidence does not identify "
            "a CALL structural fact"
        )

    if (
        import_fact.structural_parent_id
        is None
        or call_fact.structural_parent_id
        is None
    ):
        raise PythonImportUseEvidenceError(
            "import and call must have exact "
            "structural parents"
        )

    if (
        import_fact.structural_parent_id
        != call_fact.structural_parent_id
    ):
        raise PythonImportUseEvidenceError(
            "import and call do not belong to "
            "the same exact structural definition"
        )

    parent_definition_evidence_id = (
        import_fact.structural_parent_id
    )

    parent_fact = _find_fact(
        structure.facts,
        parent_definition_evidence_id,
    )

    if parent_fact.kind not in {
        PythonStructureKind.FUNCTION_DEFINITION,
        PythonStructureKind.ASYNC_FUNCTION_DEFINITION,
    }:
        raise PythonImportUseEvidenceError(
            "import-to-call provenance currently requires "
            "a function or async-function parent"
        )

    if (
        import_fact.module is None
        or import_fact.name is None
    ):
        raise PythonImportUseEvidenceError(
            "FROM_IMPORT fact lacks module/name evidence"
        )

    module_name = import_fact.module
    imported_name = import_fact.name

    try:
        tree = ast.parse(
            source,
            filename=blob.path,
            mode="exec",
        )

        module_code = compile(
            source,
            blob.path,
            "exec",
        )

    except (
        SyntaxError,
        TypeError,
        ValueError,
    ) as exc:
        raise PythonImportUseEvidenceError(
            "unable to compile Python import-use "
            f"evidence for {blob.path!r}: {exc}"
        ) from exc

    local_name = _local_name_for_import(
        tree=tree,
        module_name=module_name,
        imported_name=imported_name,
        import_line=import_fact.line_start,
    )

    parent_code = _find_parent_code_object(
        module_code=module_code,
        parent_fact=parent_fact,
    )

    instructions = tuple(
        dis.get_instructions(
            parent_code
        )
    )

    python_implementation = (
        sys.implementation.name
    )

    python_version = (
        platform.python_version()
    )

    import_name_candidates = [
        instruction
        for instruction in instructions
        if (
            instruction.opname
            == "IMPORT_NAME"
            and instruction.argval
            == module_name
            and _line_overlaps(
                instruction,
                start=import_fact.line_start,
                end=import_fact.line_end,
            )
        )
    ]

    import_name = (
        import_name_candidates[0]
        if len(import_name_candidates) == 1
        else None
    )

    import_from = None

    if import_name is not None:
        import_from = _first_after(
            instructions,
            minimum_offset=(
                import_name.offset
            ),
            predicate=lambda instruction: (
                instruction.opname
                == "IMPORT_FROM"
                and instruction.argval
                == imported_name
                and _line_overlaps(
                    instruction,
                    start=(
                        import_fact.line_start
                    ),
                    end=(
                        import_fact.line_end
                    ),
                )
            ),
        )

    import_store = None

    if import_from is not None:
        import_store = _first_after(
            instructions,
            minimum_offset=(
                import_from.offset
            ),
            predicate=lambda instruction: (
                _is_local_store(
                    instruction.opname
                )
                and instruction.argval
                == local_name
                and _line_overlaps(
                    instruction,
                    start=(
                        import_fact.line_start
                    ),
                    end=(
                        import_fact.line_end
                    ),
                )
            ),
        )

    call_load_candidates = [
        instruction
        for instruction in instructions
        if (
            _is_local_load(
                instruction.opname
            )
            and instruction.argval
            == local_name
            and _line_overlaps(
                instruction,
                start=call_fact.line_start,
                end=call_fact.line_end,
            )
        )
    ]

    call_load = (
        call_load_candidates[0]
        if call_load_candidates
        else None
    )

    call_instruction = None

    if call_load is not None:
        call_candidates = [
            instruction
            for instruction in instructions
            if (
                instruction.offset
                > call_load.offset
                and instruction.opname.startswith(
                    "CALL"
                )
                and _line_overlaps(
                    instruction,
                    start=call_fact.line_start,
                    end=call_fact.line_end,
                )
            )
        ]

        # For an outer call containing calls in its arguments,
        # CPython evaluates the inner calls first. The final CALL
        # in the structural span is therefore the best compiler
        # candidate for this exact outer structural call.
        if call_candidates:
            call_instruction = (
                call_candidates[-1]
            )

    semantic_operations: list[
        PythonImportUseOperationEvidence
    ] = []

    if import_name is not None:
        semantic_operations.append(
            _make_operation(
                source_evidence_id=(
                    blob.evidence_id
                ),
                import_fact_evidence_id=(
                    import_fact_evidence_id
                ),
                call_fact_evidence_id=(
                    call_fact_evidence_id
                ),
                kind=(
                    PythonImportUseOperationKind.IMPORT_MODULE
                ),
                instruction=import_name,
                python_implementation=(
                    python_implementation
                ),
                python_version=(
                    python_version
                ),
            )
        )

    if import_from is not None:
        semantic_operations.append(
            _make_operation(
                source_evidence_id=(
                    blob.evidence_id
                ),
                import_fact_evidence_id=(
                    import_fact_evidence_id
                ),
                call_fact_evidence_id=(
                    call_fact_evidence_id
                ),
                kind=(
                    PythonImportUseOperationKind.IMPORT_MEMBER
                ),
                instruction=import_from,
                python_implementation=(
                    python_implementation
                ),
                python_version=(
                    python_version
                ),
            )
        )

    if import_store is not None:
        semantic_operations.append(
            _make_operation(
                source_evidence_id=(
                    blob.evidence_id
                ),
                import_fact_evidence_id=(
                    import_fact_evidence_id
                ),
                call_fact_evidence_id=(
                    call_fact_evidence_id
                ),
                kind=(
                    PythonImportUseOperationKind.LOCAL_STORE
                ),
                instruction=import_store,
                python_implementation=(
                    python_implementation
                ),
                python_version=(
                    python_version
                ),
            )
        )

    if call_load is not None:
        semantic_operations.append(
            _make_operation(
                source_evidence_id=(
                    blob.evidence_id
                ),
                import_fact_evidence_id=(
                    import_fact_evidence_id
                ),
                call_fact_evidence_id=(
                    call_fact_evidence_id
                ),
                kind=(
                    PythonImportUseOperationKind.LOCAL_LOAD
                ),
                instruction=call_load,
                python_implementation=(
                    python_implementation
                ),
                python_version=(
                    python_version
                ),
            )
        )

    if call_instruction is not None:
        semantic_operations.append(
            _make_operation(
                source_evidence_id=(
                    blob.evidence_id
                ),
                import_fact_evidence_id=(
                    import_fact_evidence_id
                ),
                call_fact_evidence_id=(
                    call_fact_evidence_id
                ),
                kind=(
                    PythonImportUseOperationKind.CALL
                ),
                instruction=call_instruction,
                python_implementation=(
                    python_implementation
                ),
                python_version=(
                    python_version
                ),
            )
        )

    full_sequence_exists = all(
        value is not None
        for value in (
            import_name,
            import_from,
            import_store,
            call_load,
            call_instruction,
        )
    )

    if (
        not full_sequence_exists
        or call_fact.name != local_name
        or call_load is None
        or import_store is None
        or call_load.offset
        <= import_store.offset
    ):
        status = (
            PythonImportUseStatus.NO_IMPORT_TO_CALL_FLOW
        )

    else:
        between = [
            instruction
            for instruction in instructions
            if (
                import_store.offset
                < instruction.offset
                < call_load.offset
                and instruction.argval
                == local_name
            )
        ]

        deletes = [
            instruction
            for instruction in between
            if _is_local_delete(
                instruction.opname
            )
        ]

        rebindings = [
            instruction
            for instruction in between
            if _is_local_store(
                instruction.opname
            )
        ]

        if deletes:
            status = (
                PythonImportUseStatus.DELETED_BEFORE_CALL
            )

        elif rebindings:
            status = (
                PythonImportUseStatus.REBOUND_BEFORE_CALL
            )

        else:
            status = (
                PythonImportUseStatus.PROVEN_LOCAL_IMPORT_TO_CALL
            )

    operations = tuple(
        semantic_operations
    )

    evidence_id = _evidence_identity(
        source_evidence_id=(
            blob.evidence_id
        ),
        import_fact_evidence_id=(
            import_fact_evidence_id
        ),
        call_fact_evidence_id=(
            call_fact_evidence_id
        ),
        parent_definition_evidence_id=(
            parent_definition_evidence_id
        ),
        status=status,
        module_name=module_name,
        imported_name=imported_name,
        local_name=local_name,
        operations=operations,
        python_implementation=(
            python_implementation
        ),
        python_version=(
            python_version
        ),
    )

    return PythonImportUseEvidence(
        status=status,
        module_name=module_name,
        imported_name=imported_name,
        local_name=local_name,
        source_evidence_id=(
            blob.evidence_id
        ),
        import_fact_evidence_id=(
            import_fact_evidence_id
        ),
        call_fact_evidence_id=(
            call_fact_evidence_id
        ),
        parent_definition_evidence_id=(
            parent_definition_evidence_id
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
