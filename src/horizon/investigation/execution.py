"""Execution boundary for typed Horizon investigation operations.

This module executes only operations Horizon explicitly implements.

The first executable operation is SEARCH_SOURCE. It delegates repository
search to Horizon's existing immutable Git observation/search evidence
layer.

Execution returns observations. It does not create claims, epistemic
assessments, architectural conclusions, or world-model assertions.
"""

from __future__ import annotations

import hashlib
import json
import subprocess

from dataclasses import dataclass
from pathlib import Path

from horizon.investigation.plan import (
    InspectSymbolOperation,
    InvestigationOperation,
    ReadSourceOperation,
    ResolveCallOperation,
    SearchSourceOperation,
)
from horizon.languages.python.pyright_callee import (
    PythonPyrightCalleeEvidenceError,
    PythonPyrightCalleeTypeEvidence,
    analyze_pyright_callee_type,
)
from horizon.languages.python.structure import (
    PythonStructureAnalysis,
    PythonStructureFact,
    PythonStructureKind,
    PythonSyntaxEvidenceError,
    analyze_python_blob,
)
from horizon.repository.git_blob import (
    GitBlobError,
    read_observed_blob,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)
from horizon.repository.git_search import (
    GitTextMatch,
    search_observed_text,
)


class InvestigationExecutionError(
    ValueError
):
    """A typed investigation operation cannot be executed faithfully."""


class UnsupportedInvestigationOperationError(
    InvestigationExecutionError
):
    """The typed operation exists but has no executor yet."""


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationSearchObservation:
    query: str
    path_prefix: str | None

    commit_sha: str
    repository_observation_id: str

    source_search_id: str
    matches: tuple[
        GitTextMatch,
        ...,
    ]

    observation_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationSourceLine:
    line_number: int
    content: bytes


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationSourceObservation:
    path: str
    start_line: int
    end_line: int

    commit_sha: str
    repository_observation_id: str

    source_blob_evidence_id: str
    source_object_id: str

    lines: tuple[
        InvestigationSourceLine,
        ...,
    ]

    observation_id: str

    observed_source_line_count: int | None = None
    ends_at_observed_eof: bool | None = None


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationSymbolObservation:
    path: str
    symbol: str

    commit_sha: str
    repository_observation_id: str

    source_blob_evidence_id: str
    source_object_id: str
    structure_analysis_id: str

    definition: PythonStructureFact
    facts: tuple[
        PythonStructureFact,
        ...,
    ]

    observation_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class InvestigationCallObservation:
    path: str
    line: int
    character: int

    commit_sha: str
    repository_observation_id: str

    source_blob_evidence_id: str
    source_object_id: str
    structure_analysis_id: str

    call: PythonStructureFact
    semantic_evidence: PythonPyrightCalleeTypeEvidence

    observation_id: str


def _git(
    repository: Path,
    *args: str,
) -> str:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(
                    repository
                ),
                *args,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise InvestigationExecutionError(
            "repository state could not be verified"
        ) from exc

    return completed.stdout.strip()


def _verify_repository_state(
    repository: Path,
    observation: GitCommitObservation,
) -> None:
    if not isinstance(
        observation,
        GitCommitObservation,
    ):
        raise InvestigationExecutionError(
            "observation must be a GitCommitObservation"
        )

    head = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    if (
        head
        != observation.commit_sha
    ):
        raise InvestigationExecutionError(
            "repository commit does not match observation"
        )

    status = _git(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )

    if status:
        raise InvestigationExecutionError(
            "repository working tree must be clean"
        )


def _path_is_within_prefix(
    path: str,
    prefix: str,
) -> bool:
    return (
        path == prefix
        or path.startswith(
            prefix
            + "/"
        )
    )


def _search_observation_identity(
    *,
    operation: SearchSourceOperation,
    observation: GitCommitObservation,
    source_search_id: str,
    matches: tuple[
        GitTextMatch,
        ...,
    ],
) -> str:
    payload = {
        "operation_kind": (
            operation.kind.value
        ),
        "query": (
            operation.query
        ),
        "path_prefix": (
            operation.path_prefix
        ),
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.observation_id
        ),
        "source_search_id": (
            source_search_id
        ),
        "match_evidence_ids": [
            match.evidence_id
            for match
            in matches
        ],
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        "investigation-search-observation:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _execute_search_source(
    repository: Path,
    observation: GitCommitObservation,
    operation: SearchSourceOperation,
) -> InvestigationSearchObservation:
    search = search_observed_text(
        repository,
        observation,
        operation.query,
    )

    if (
        operation.path_prefix
        is None
    ):
        matches = search.matches
    else:
        matches = tuple(
            match
            for match
            in search.matches
            if _path_is_within_prefix(
                match.path,
                operation.path_prefix,
            )
        )

    return InvestigationSearchObservation(
        query=operation.query,
        path_prefix=(
            operation.path_prefix
        ),
        commit_sha=(
            observation.commit_sha
        ),
        repository_observation_id=(
            observation.observation_id
        ),
        source_search_id=(
            search.search_id
        ),
        matches=matches,
        observation_id=(
            _search_observation_identity(
                operation=operation,
                observation=observation,
                source_search_id=(
                    search.search_id
                ),
                matches=matches,
            )
        ),
    )


def _source_observation_identity(
    *,
    operation: ReadSourceOperation,
    observation: GitCommitObservation,
    source_blob_evidence_id: str,
    source_object_id: str,
    effective_end_line: int,
) -> str:
    payload = {
        "operation_kind": (
            operation.kind.value
        ),
        "path": operation.path,
        "start_line": (
            operation.start_line
        ),
        "end_line": (
            effective_end_line
        ),
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.observation_id
        ),
        "source_blob_evidence_id": (
            source_blob_evidence_id
        ),
        "source_object_id": (
            source_object_id
        ),
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        "investigation-source-observation:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _execute_read_source(
    repository: Path,
    observation: GitCommitObservation,
    operation: ReadSourceOperation,
) -> InvestigationSourceObservation:
    try:
        blob = read_observed_blob(
            repository,
            observation,
            operation.path,
        )
    except GitBlobError as exc:
        raise InvestigationExecutionError(
            "source path is not an observed Git blob"
        ) from exc

    source_lines = (
        blob.content.splitlines()
    )

    observed_source_line_count = len(
        source_lines
    )

    if (
        operation.start_line
        > observed_source_line_count
    ):
        raise InvestigationExecutionError(
            "requested line window exceeds observed source"
        )

    effective_end_line = (
        observed_source_line_count
        if operation.end_line is None
        else operation.end_line
    )

    if (
        effective_end_line
        > observed_source_line_count
    ):
        raise InvestigationExecutionError(
            "requested line window exceeds observed source"
        )

    lines = tuple(
        InvestigationSourceLine(
            line_number=(
                line_number
            ),
            content=(
                source_lines[
                    line_number - 1
                ]
            ),
        )
        for line_number
        in range(
            operation.start_line,
            effective_end_line + 1,
        )
    )

    return InvestigationSourceObservation(
        path=operation.path,
        start_line=(
            operation.start_line
        ),
        end_line=(
            effective_end_line
        ),
        commit_sha=(
            observation.commit_sha
        ),
        repository_observation_id=(
            observation.observation_id
        ),
        source_blob_evidence_id=(
            blob.evidence_id
        ),
        source_object_id=(
            blob.object_id
        ),
        lines=lines,
        observation_id=(
            _source_observation_identity(
                operation=operation,
                observation=observation,
                source_blob_evidence_id=(
                    blob.evidence_id
                ),
                source_object_id=(
                    blob.object_id
                ),
                effective_end_line=(
                    effective_end_line
                ),
            )
        ),
        observed_source_line_count=(
            observed_source_line_count
        ),
        ends_at_observed_eof=(
            effective_end_line
            == observed_source_line_count
        ),
    )


_DEFINITION_KINDS = {
    PythonStructureKind.CLASS_DEFINITION,
    PythonStructureKind.FUNCTION_DEFINITION,
    PythonStructureKind.ASYNC_FUNCTION_DEFINITION,
}


def _resolve_symbol_definition(
    analysis: PythonStructureAnalysis,
    symbol: str,
) -> PythonStructureFact:
    parts = tuple(
        symbol.split(
            "."
        )
    )

    if (
        not parts
        or any(
            not part
            for part in parts
        )
    ):
        raise InvestigationExecutionError(
            "symbol must be a dotted lexical name"
        )

    expected_scope = parts[
        :-1
    ]

    expected_name = parts[
        -1
    ]

    matches = tuple(
        fact
        for fact
        in analysis.facts
        if (
            fact.kind
            in _DEFINITION_KINDS
            and fact.name
            == expected_name
            and fact.scope
            == expected_scope
        )
    )

    if not matches:
        raise InvestigationExecutionError(
            f"symbol not found in observed Python structure: {symbol!r}"
        )

    if len(
        matches
    ) != 1:
        raise InvestigationExecutionError(
            f"symbol is ambiguous in observed Python structure: {symbol!r}"
        )

    return matches[
        0
    ]


def _structural_subtree(
    analysis: PythonStructureAnalysis,
    definition: PythonStructureFact,
) -> tuple[
    PythonStructureFact,
    ...,
]:
    selected_ids = {
        definition.evidence_id
    }

    changed = True

    while changed:
        changed = False

        for fact in analysis.facts:
            if (
                fact.evidence_id
                in selected_ids
            ):
                continue

            if (
                fact.structural_parent_id
                in selected_ids
            ):
                selected_ids.add(
                    fact.evidence_id
                )

                changed = True

    return tuple(
        fact
        for fact
        in analysis.facts
        if fact.evidence_id
        in selected_ids
    )


def _symbol_observation_identity(
    *,
    operation: InspectSymbolOperation,
    observation: GitCommitObservation,
    source_blob_evidence_id: str,
    source_object_id: str,
    structure_analysis_id: str,
    definition: PythonStructureFact,
    facts: tuple[
        PythonStructureFact,
        ...,
    ],
) -> str:
    payload = {
        "operation_kind": (
            operation.kind.value
        ),
        "path": operation.path,
        "symbol": operation.symbol,
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.observation_id
        ),
        "source_blob_evidence_id": (
            source_blob_evidence_id
        ),
        "source_object_id": (
            source_object_id
        ),
        "structure_analysis_id": (
            structure_analysis_id
        ),
        "definition_evidence_id": (
            definition.evidence_id
        ),
        "fact_evidence_ids": [
            fact.evidence_id
            for fact
            in facts
        ],
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        "investigation-symbol-observation:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _execute_inspect_symbol(
    repository: Path,
    observation: GitCommitObservation,
    operation: InspectSymbolOperation,
) -> InvestigationSymbolObservation:
    try:
        blob = read_observed_blob(
            repository,
            observation,
            operation.path,
        )
    except GitBlobError as exc:
        raise InvestigationExecutionError(
            "symbol path is not an observed Git blob"
        ) from exc

    try:
        analysis = analyze_python_blob(
            blob
        )
    except PythonSyntaxEvidenceError as exc:
        raise InvestigationExecutionError(
            "observed source could not produce Python structure evidence"
        ) from exc

    definition = _resolve_symbol_definition(
        analysis,
        operation.symbol,
    )

    facts = _structural_subtree(
        analysis,
        definition,
    )

    return InvestigationSymbolObservation(
        path=operation.path,
        symbol=operation.symbol,
        commit_sha=(
            observation.commit_sha
        ),
        repository_observation_id=(
            observation.observation_id
        ),
        source_blob_evidence_id=(
            blob.evidence_id
        ),
        source_object_id=(
            blob.object_id
        ),
        structure_analysis_id=(
            analysis.analysis_id
        ),
        definition=definition,
        facts=facts,
        observation_id=(
            _symbol_observation_identity(
                operation=operation,
                observation=observation,
                source_blob_evidence_id=(
                    blob.evidence_id
                ),
                source_object_id=(
                    blob.object_id
                ),
                structure_analysis_id=(
                    analysis.analysis_id
                ),
                definition=definition,
                facts=facts,
            )
        ),
    )


def _source_line_byte_start(
    content: bytes,
    line: int,
) -> int:
    if line <= 0:
        raise InvestigationExecutionError(
            "source line must be positive"
        )

    current_line = 1
    offset = 0

    if line == 1:
        return 0

    for index, value in enumerate(
        content
    ):
        if value != 10:
            continue

        current_line += 1
        offset = index + 1

        if current_line == line:
            return offset

    raise InvestigationExecutionError(
        "requested source line does not exist"
    )


def _source_line_content(
    content: bytes,
    line_start: int,
) -> bytes:
    newline = content.find(
        b"\n",
        line_start,
    )

    if newline < 0:
        raw = content[
            line_start:
        ]
    else:
        raw = content[
            line_start:newline
        ]

    if raw.endswith(
        b"\r"
    ):
        raw = raw[
            :-1
        ]

    return raw


def _call_at_position(
    *,
    analysis: PythonStructureAnalysis,
    blob_content: bytes,
    line: int,
    character: int,
) -> PythonStructureFact:
    line_start = (
        _source_line_byte_start(
            blob_content,
            line,
        )
    )

    line_content = (
        _source_line_content(
            blob_content,
            line_start,
        )
    )

    if (
        character < 0
        or character
        >= len(
            line_content
        )
    ):
        raise InvestigationExecutionError(
            "requested source character does not exist"
        )

    absolute_position = (
        line_start
        + character
    )

    matches = tuple(
        fact
        for fact
        in analysis.facts
        if (
            fact.kind
            is PythonStructureKind.CALL
            and fact.callee_byte_start
            is not None
            and fact.callee_byte_end
            is not None
            and fact.callee_byte_start
            <= absolute_position
            < fact.callee_byte_end
        )
    )

    if not matches:
        raise InvestigationExecutionError(
            "no CALL fact exists at requested source position"
        )

    if len(
        matches
    ) != 1:
        raise InvestigationExecutionError(
            "requested source position is ambiguous across CALL facts"
        )

    return matches[
        0
    ]


def _call_observation_identity(
    *,
    operation: ResolveCallOperation,
    observation: GitCommitObservation,
    source_blob_evidence_id: str,
    source_object_id: str,
    structure_analysis_id: str,
    call: PythonStructureFact,
    semantic_evidence: PythonPyrightCalleeTypeEvidence,
) -> str:
    payload = {
        "operation_kind": (
            operation.kind.value
        ),
        "path": operation.path,
        "line": operation.line,
        "character": (
            operation.character
        ),
        "commit_sha": (
            observation.commit_sha
        ),
        "repository_observation_id": (
            observation.observation_id
        ),
        "source_blob_evidence_id": (
            source_blob_evidence_id
        ),
        "source_object_id": (
            source_object_id
        ),
        "structure_analysis_id": (
            structure_analysis_id
        ),
        "call_evidence_id": (
            call.evidence_id
        ),
        "callee_evidence_id": (
            call.callee_evidence_id
        ),
        "semantic_evidence_id": (
            semantic_evidence.evidence_id
        ),
    }

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        "investigation-call-observation:"
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def _execute_resolve_call(
    repository: Path,
    observation: GitCommitObservation,
    operation: ResolveCallOperation,
    *,
    pyright_typeserver: str | Path | None,
) -> InvestigationCallObservation:
    if pyright_typeserver is None:
        raise InvestigationExecutionError(
            "trusted Pyright type server configuration is required"
        )

    try:
        blob = read_observed_blob(
            repository,
            observation,
            operation.path,
        )
    except GitBlobError as exc:
        raise InvestigationExecutionError(
            "call path is not an observed Git blob"
        ) from exc

    try:
        analysis = analyze_python_blob(
            blob
        )
    except PythonSyntaxEvidenceError as exc:
        raise InvestigationExecutionError(
            "observed source could not produce Python structure evidence"
        ) from exc

    call = _call_at_position(
        analysis=analysis,
        blob_content=(
            blob.content
        ),
        line=operation.line,
        character=(
            operation.character
        ),
    )

    try:
        semantic_evidence = (
            analyze_pyright_callee_type(
                repository=repository,
                observation=observation,
                blob=blob,
                call_fact=call,
                pyright_typeserver=str(
                    pyright_typeserver
                ),
            )
        )
    except PythonPyrightCalleeEvidenceError as exc:
        raise InvestigationExecutionError(
            "Pyright call resolution failed"
        ) from exc

    return InvestigationCallObservation(
        path=operation.path,
        line=operation.line,
        character=(
            operation.character
        ),
        commit_sha=(
            observation.commit_sha
        ),
        repository_observation_id=(
            observation.observation_id
        ),
        source_blob_evidence_id=(
            blob.evidence_id
        ),
        source_object_id=(
            blob.object_id
        ),
        structure_analysis_id=(
            analysis.analysis_id
        ),
        call=call,
        semantic_evidence=(
            semantic_evidence
        ),
        observation_id=(
            _call_observation_identity(
                operation=operation,
                observation=observation,
                source_blob_evidence_id=(
                    blob.evidence_id
                ),
                source_object_id=(
                    blob.object_id
                ),
                structure_analysis_id=(
                    analysis.analysis_id
                ),
                call=call,
                semantic_evidence=(
                    semantic_evidence
                ),
            )
        ),
    )


def execute_investigation_operation(
    repository: str | Path,
    observation: GitCommitObservation,
    operation: InvestigationOperation,
    *,
    pyright_typeserver: str | Path | None = None,
) -> (
    InvestigationSearchObservation
    | InvestigationSourceObservation
    | InvestigationSymbolObservation
    | InvestigationCallObservation
):
    """Execute one supported typed operation against one observed repo."""

    repository_path = Path(
        repository
    ).resolve()

    if (
        not repository_path.exists()
        or not repository_path.is_dir()
    ):
        raise InvestigationExecutionError(
            "repository path must identify an existing directory"
        )

    _verify_repository_state(
        repository_path,
        observation,
    )

    if isinstance(
        operation,
        SearchSourceOperation,
    ):
        return _execute_search_source(
            repository_path,
            observation,
            operation,
        )

    if isinstance(
        operation,
        ReadSourceOperation,
    ):
        return _execute_read_source(
            repository_path,
            observation,
            operation,
        )

    if isinstance(
        operation,
        InspectSymbolOperation,
    ):
        return _execute_inspect_symbol(
            repository_path,
            observation,
            operation,
        )

    if isinstance(
        operation,
        ResolveCallOperation,
    ):
        return _execute_resolve_call(
            repository_path,
            observation,
            operation,
            pyright_typeserver=(
                pyright_typeserver
            ),
        )

    kind = getattr(
        operation,
        "kind",
        None,
    )

    kind_text = (
        kind.value
        if kind is not None
        else type(
            operation
        ).__name__
    )

    raise UnsupportedInvestigationOperationError(
        "no executor exists yet for "
        f"{kind_text}"
    )
