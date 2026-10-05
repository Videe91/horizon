from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import pytest

from horizon.languages.python.import_use_provenance import (
    PythonImportUseEvidenceError,
    PythonImportUseOperationKind,
    PythonImportUseStatus,
    analyze_import_to_call_provenance,
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


def prepare(
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

    structure = analyze_python_blob(
        blob
    )

    return (
        repo,
        target,
        blob,
        structure,
    )


def select_import_and_call(
    structure,
    *,
    module: str,
    imported_name: str,
    call_name: str,
):
    import_fact = next(
        fact
        for fact in structure.facts
        if (
            fact.kind
            == PythonStructureKind.FROM_IMPORT
            and fact.module == module
            and fact.name == imported_name
        )
    )

    call_fact = next(
        fact
        for fact in structure.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and fact.name == call_name
        )
    )

    return (
        import_fact,
        call_fact,
    )


def test_direct_function_local_import_flows_to_call(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def execute():
    from package.worker import run
    return run()
""",
    )

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="run",
    )

    evidence = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    assert (
        evidence.status
        == PythonImportUseStatus.PROVEN_LOCAL_IMPORT_TO_CALL
    )

    assert evidence.module_name == "package.worker"
    assert evidence.imported_name == "run"
    assert evidence.local_name == "run"

    assert (
        evidence.import_fact_evidence_id
        == import_fact.evidence_id
    )

    assert (
        evidence.call_fact_evidence_id
        == call_fact.evidence_id
    )

    assert (
        evidence.parent_definition_evidence_id
        == import_fact.structural_parent_id
    )

    kinds = tuple(
        operation.kind
        for operation in evidence.operations
    )

    assert kinds == (
        PythonImportUseOperationKind.IMPORT_MODULE,
        PythonImportUseOperationKind.IMPORT_MEMBER,
        PythonImportUseOperationKind.LOCAL_STORE,
        PythonImportUseOperationKind.LOCAL_LOAD,
        PythonImportUseOperationKind.CALL,
    )


def test_import_alias_flows_through_alias_local(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def execute():
    from package.worker import run as execute_run
    return execute_run()
""",
    )

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="execute_run",
    )

    evidence = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    assert (
        evidence.status
        == PythonImportUseStatus.PROVEN_LOCAL_IMPORT_TO_CALL
    )

    assert evidence.imported_name == "run"
    assert evidence.local_name == "execute_run"


def test_rebinding_between_import_and_call_is_exposed(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def execute():
    from package.worker import run
    run = replacement
    return run()
""",
    )

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="run",
    )

    evidence = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    assert (
        evidence.status
        == PythonImportUseStatus.REBOUND_BEFORE_CALL
    )


def test_delete_between_import_and_call_is_exposed(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def execute():
    from package.worker import run
    del run
    return run()
""",
    )

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="run",
    )

    evidence = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    assert (
        evidence.status
        == PythonImportUseStatus.DELETED_BEFORE_CALL
    )


def test_call_before_import_is_not_proven(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def execute():
    run()
    from package.worker import run
""",
    )

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="run",
    )

    evidence = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    assert (
        evidence.status
        == PythonImportUseStatus.NO_IMPORT_TO_CALL_FLOW
    )


def test_exact_same_named_definition_parent_is_used(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
class Flow:
    def __call__(self, value: int):
        ...

    def __call__(self):
        from package.worker import run
        return run()
""",
    )

    definitions = sorted(
        (
            fact
            for fact in structure.facts
            if (
                fact.kind
                == PythonStructureKind.FUNCTION_DEFINITION
                and fact.name == "__call__"
                and fact.scope == ("Flow",)
            )
        ),
        key=lambda fact: fact.line_start,
    )

    assert len(definitions) == 2

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="run",
    )

    evidence = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    assert (
        evidence.status
        == PythonImportUseStatus.PROVEN_LOCAL_IMPORT_TO_CALL
    )

    assert (
        evidence.parent_definition_evidence_id
        == definitions[1].evidence_id
    )

    assert (
        evidence.parent_definition_evidence_id
        != definitions[0].evidence_id
    )


def test_import_and_call_from_different_functions_are_rejected(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def first():
    from package.worker import run
    return run

def second():
    return run()
""",
    )

    import_fact = next(
        fact
        for fact in structure.facts
        if (
            fact.kind
            == PythonStructureKind.FROM_IMPORT
            and fact.name == "run"
        )
    )

    call_fact = next(
        fact
        for fact in structure.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and fact.name == "run"
        )
    )

    with pytest.raises(
        PythonImportUseEvidenceError
    ):
        analyze_import_to_call_provenance(
            blob,
            import_fact.evidence_id,
            call_fact.evidence_id,
        )


def test_evidence_is_frozen_and_deterministic(
    tmp_path: Path,
) -> None:
    (
        _,
        target,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def execute():
    from package.worker import run
    return run()
""",
    )

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="run",
    )

    target.write_bytes(
        b"""\
def execute():
    from package.changed import changed
    return changed()
"""
    )

    first = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    second = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
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


def test_compiler_identity_and_raw_opcodes_are_preserved(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        structure,
    ) = prepare(
        tmp_path,
        b"""\
def execute():
    from package.worker import run
    return run()
""",
    )

    (
        import_fact,
        call_fact,
    ) = select_import_and_call(
        structure,
        module="package.worker",
        imported_name="run",
        call_name="run",
    )

    evidence = analyze_import_to_call_provenance(
        blob,
        import_fact.evidence_id,
        call_fact.evidence_id,
    )

    assert (
        evidence.python_implementation
        == "cpython"
    )

    assert (
        evidence.python_version
        == platform.python_version()
    )

    assert all(
        operation.raw_opcode
        for operation in evidence.operations
    )

    local_load = next(
        operation
        for operation in evidence.operations
        if (
            operation.kind
            == PythonImportUseOperationKind.LOCAL_LOAD
        )
    )

    assert (
        local_load.raw_opcode.startswith(
            "LOAD_FAST"
        )
    )
