from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import pytest

from horizon.languages.python.compiler_bindings import (
    PythonCompilerBindingEvidenceError,
    PythonCompiledBindingOperation,
    PythonCompiledBindingStatus,
    analyze_compiled_module_binding,
)
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


def git(
    repo: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            *args,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return completed.stdout.strip()


def create_repository(
    tmp_path: Path,
) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)

    git(
        repo,
        "init",
        "-q",
        "-b",
        "main",
    )

    git(
        repo,
        "config",
        "user.name",
        "Horizon Test",
    )

    git(
        repo,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    return repo


def prepare_blob(
    tmp_path: Path,
    source: bytes,
):
    repo = create_repository(
        tmp_path
    )

    target = repo / "sample.py"

    target.write_bytes(
        source
    )

    git(
        repo,
        "add",
        "sample.py",
    )

    git(
        repo,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = git(
        repo,
        "rev-parse",
        "HEAD",
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    blob = read_observed_blob(
        repo,
        observation,
        "sample.py",
    )

    return (
        repo,
        target,
        observation,
        blob,
    )


def test_direct_function_has_single_compiler_backed_origin(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
def run_flow():
    return 1
""",
    )

    structure = analyze_python_blob(
        blob
    )

    definition = next(
        fact
        for fact in structure.facts
        if (
            fact.kind
            == PythonStructureKind.FUNCTION_DEFINITION
            and fact.name == "run_flow"
            and fact.scope == ()
        )
    )

    evidence = analyze_compiled_module_binding(
        blob,
        "run_flow",
    )

    assert (
        evidence.status
        == PythonCompiledBindingStatus.DIRECT_SINGLE_ORIGIN
    )

    assert (
        evidence.direct_origin_evidence_id
        == definition.evidence_id
    )

    assert len(
        evidence.operations
    ) == 1

    operation = evidence.operations[0]

    assert (
        operation.operation
        == PythonCompiledBindingOperation.STORE
    )

    assert operation.opcode == "STORE_NAME"
    assert operation.line == 1


def test_direct_class_has_single_compiler_backed_origin(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
class Engine:
    pass
""",
    )

    structure = analyze_python_blob(
        blob
    )

    definition = next(
        fact
        for fact in structure.facts
        if (
            fact.kind
            == PythonStructureKind.CLASS_DEFINITION
            and fact.name == "Engine"
            and fact.scope == ()
        )
    )

    evidence = analyze_compiled_module_binding(
        blob,
        "Engine",
    )

    assert (
        evidence.status
        == PythonCompiledBindingStatus.DIRECT_SINGLE_ORIGIN
    )

    assert (
        evidence.direct_origin_evidence_id
        == definition.evidence_id
    )


def test_rebinding_is_not_reported_as_single_origin(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
def target():
    return 1

target = object()
""",
    )

    evidence = analyze_compiled_module_binding(
        blob,
        "target",
    )

    assert (
        evidence.status
        == PythonCompiledBindingStatus.MULTIPLE_STORES
    )

    stores = [
        operation
        for operation in evidence.operations
        if (
            operation.operation
            == PythonCompiledBindingOperation.STORE
        )
    ]

    assert len(
        stores
    ) == 2


def test_delete_is_exposed_explicitly(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
def target():
    return 1

del target
""",
    )

    evidence = analyze_compiled_module_binding(
        blob,
        "target",
    )

    assert (
        evidence.status
        == PythonCompiledBindingStatus.DELETED
    )

    deletes = [
        operation
        for operation in evidence.operations
        if (
            operation.operation
            == PythonCompiledBindingOperation.DELETE
        )
    ]

    assert len(
        deletes
    ) == 1


def test_conditional_definition_is_not_called_direct_origin(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
if enabled:
    def target():
        return 1
""",
    )

    evidence = analyze_compiled_module_binding(
        blob,
        "target",
    )

    assert (
        evidence.status
        == PythonCompiledBindingStatus.NO_DIRECT_ORIGIN
    )

    assert (
        evidence.direct_origin_evidence_id
        is None
    )


def test_nested_function_binding_does_not_pollute_module_binding(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
def outer():
    def target():
        return 1

    return target
""",
    )

    evidence = analyze_compiled_module_binding(
        blob,
        "target",
    )

    assert (
        evidence.status
        == PythonCompiledBindingStatus.NOT_FOUND
    )

    assert (
        evidence.operations
        == ()
    )


def test_evidence_is_bound_to_frozen_blob_and_deterministic(
    tmp_path: Path,
) -> None:
    (
        _,
        target,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
def original():
    return 1
""",
    )

    target.write_bytes(
        b"""\
def changed():
    return 2
"""
    )

    first = analyze_compiled_module_binding(
        blob,
        "original",
    )

    second = analyze_compiled_module_binding(
        blob,
        "original",
    )

    assert first == second

    assert (
        first.evidence_id
        == second.evidence_id
    )

    assert (
        first.source_evidence_id
        == blob.evidence_id
    )

    assert (
        first.status
        == PythonCompiledBindingStatus.DIRECT_SINGLE_ORIGIN
    )


def test_compiler_identity_is_recorded(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"""\
def target():
    return 1
""",
    )

    evidence = analyze_compiled_module_binding(
        blob,
        "target",
    )

    assert (
        evidence.python_implementation
        == "cpython"
    )

    assert (
        evidence.python_version
        == platform.python_version()
    )


def test_invalid_python_is_explicit(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        blob,
    ) = prepare_blob(
        tmp_path,
        b"def broken(:\n",
    )

    with pytest.raises(
        PythonCompilerBindingEvidenceError
    ):
        analyze_compiled_module_binding(
            blob,
            "broken",
        )
