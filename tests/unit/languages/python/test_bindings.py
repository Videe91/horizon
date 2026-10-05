from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from horizon.languages.python.bindings import (
    PythonBindingEvidenceError,
    PythonScopeKind,
    analyze_python_bindings,
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


def commit_all(
    repo: Path,
) -> str:
    git(
        repo,
        "add",
        "-A",
    )

    git(
        repo,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    return git(
        repo,
        "rev-parse",
        "HEAD",
    )


def analyze_path(
    repo: Path,
    commit: str,
    path: str,
):
    observation = observe_git_commit(
        repo,
        commit,
    )

    blob = read_observed_blob(
        repo,
        observation,
        path,
    )

    analysis = analyze_python_bindings(
        blob,
    )

    return observation, blob, analysis


def find_symbol(
    analysis,
    *,
    scope: tuple[str, ...],
    name: str,
):
    return next(
        symbol
        for symbol in analysis.symbols
        if (
            symbol.scope == scope
            and symbol.name == name
        )
    )


def test_import_inside_method_is_local_imported_binding(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        b"""\
class Flow:
    def __call__(self):
        from prefect.flow_engine import run_flow
        return run_flow()
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, analysis = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    symbol = find_symbol(
        analysis,
        scope=("Flow", "__call__"),
        name="run_flow",
    )

    assert symbol.scope_kind == PythonScopeKind.FUNCTION
    assert symbol.is_imported is True
    assert symbol.is_local is True
    assert symbol.is_referenced is True
    assert symbol.is_global is False
    assert symbol.is_free is False


def test_import_alias_creates_binding_under_alias_name(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        b"""\
from prefect.flow_engine import run_flow as execute

execute()
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, analysis = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    execute = find_symbol(
        analysis,
        scope=(),
        name="execute",
    )

    assert execute.is_imported is True
    assert execute.is_local is True
    assert execute.is_referenced is True

    assert not any(
        symbol.scope == ()
        and symbol.name == "run_flow"
        for symbol in analysis.symbols
    )


def test_local_assignment_shadows_outer_import(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        b"""\
from package import target

def execute():
    target = 42
    return target
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, analysis = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    module_target = find_symbol(
        analysis,
        scope=(),
        name="target",
    )

    function_target = find_symbol(
        analysis,
        scope=("execute",),
        name="target",
    )

    assert module_target.is_imported is True

    assert function_target.is_local is True
    assert function_target.is_assigned is True
    assert function_target.is_imported is False
    assert function_target.is_referenced is True


def test_global_declaration_is_compiler_evidence(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        b"""\
value = 1

def update():
    global value
    value = 2
    return value
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, analysis = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    value = find_symbol(
        analysis,
        scope=("update",),
        name="value",
    )

    assert value.is_global is True
    assert value.is_declared_global is True
    assert value.is_local is False
    assert value.is_assigned is True
    assert value.is_referenced is True


def test_nonlocal_and_free_binding_are_exposed(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        b"""\
def outer():
    value = 1

    def inner():
        nonlocal value
        value = value + 1
        return value

    return inner
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, analysis = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    outer_value = find_symbol(
        analysis,
        scope=("outer",),
        name="value",
    )

    inner_value = find_symbol(
        analysis,
        scope=("outer", "inner"),
        name="value",
    )

    assert outer_value.is_local is True
    assert outer_value.is_assigned is True

    assert inner_value.is_nonlocal is True
    assert inner_value.is_free is True
    assert inner_value.is_local is False
    assert inner_value.is_referenced is True


def test_class_scope_is_not_treated_as_function_closure(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        b"""\
class Example:
    value = 1

    def read(self):
        return value
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, analysis = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    class_value = find_symbol(
        analysis,
        scope=("Example",),
        name="value",
    )

    method_value = find_symbol(
        analysis,
        scope=("Example", "read"),
        name="value",
    )

    assert class_value.is_local is True
    assert class_value.is_assigned is True

    assert method_value.is_global is True
    assert method_value.is_free is False
    assert method_value.is_local is False


def test_parameter_binding_is_exposed(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        b"""\
def execute(flow):
    return flow()
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, analysis = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    flow = find_symbol(
        analysis,
        scope=("execute",),
        name="flow",
    )

    assert flow.is_parameter is True
    assert flow.is_local is True
    assert flow.is_referenced is True


def test_analysis_is_bound_to_exact_blob_and_deterministic(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    target = repo / "sample.py"

    target.write_bytes(
        b"""\
from package import original

def execute():
    return original()
"""
    )

    commit = commit_all(
        repo,
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

    target.write_bytes(
        b"""\
from package import changed

def execute():
    return changed()
"""
    )

    first = analyze_python_bindings(
        blob,
    )

    second = analyze_python_bindings(
        blob,
    )

    assert first == second
    assert first.analysis_id == second.analysis_id
    assert first.source_evidence_id == blob.evidence_id

    names = {
        symbol.name
        for symbol in first.symbols
    }

    assert "original" in names
    assert "changed" not in names

    assert all(
        symbol.source_evidence_id == blob.evidence_id
        for symbol in first.symbols
    )


def test_invalid_python_is_explicit(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "broken.py"
    ).write_bytes(
        b"def broken(:\n",
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    blob = read_observed_blob(
        repo,
        observation,
        "broken.py",
    )

    with pytest.raises(
        PythonBindingEvidenceError,
    ):
        analyze_python_bindings(
            blob,
        )
