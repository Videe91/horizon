from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from horizon.languages.python.structure import (
    PythonStructureKind,
    PythonSyntaxEvidenceError,
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

    result = analyze_python_blob(
        blob,
    )

    return observation, blob, result


def test_recognizes_core_python_structure(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    source = b"""\
import os as operating_system
from prefect.flow_engine import run_flow as execute_flow

@flow
def outer():
    run_flow()
    client.run_flow()

class Example:
    @classmethod
    async def execute(cls):
        return run_flow()
"""

    (
        repo
        / "sample.py"
    ).write_bytes(
        source,
    )

    commit = commit_all(
        repo,
    )

    _, _, result = analyze_path(
        repo,
        commit,
        "sample.py",
    )

    facts = {
        (
            fact.kind,
            fact.name,
            fact.module,
            fact.alias,
            fact.scope,
        )
        for fact in result.facts
    }

    assert (
        PythonStructureKind.MODULE,
        "sample.py",
        None,
        None,
        (),
    ) in facts

    assert (
        PythonStructureKind.IMPORT,
        "os",
        None,
        "operating_system",
        (),
    ) in facts

    assert (
        PythonStructureKind.FROM_IMPORT,
        "run_flow",
        "prefect.flow_engine",
        "execute_flow",
        (),
    ) in facts

    assert (
        PythonStructureKind.FUNCTION_DEFINITION,
        "outer",
        None,
        None,
        (),
    ) in facts

    assert (
        PythonStructureKind.DECORATOR,
        "flow",
        None,
        None,
        ("outer",),
    ) in facts

    assert (
        PythonStructureKind.CALL,
        "run_flow",
        None,
        None,
        ("outer",),
    ) in facts

    assert (
        PythonStructureKind.CALL,
        "client.run_flow",
        None,
        None,
        ("outer",),
    ) in facts

    assert (
        PythonStructureKind.CLASS_DEFINITION,
        "Example",
        None,
        None,
        (),
    ) in facts

    assert (
        PythonStructureKind.ASYNC_FUNCTION_DEFINITION,
        "execute",
        None,
        None,
        ("Example",),
    ) in facts

    assert (
        PythonStructureKind.DECORATOR,
        "classmethod",
        None,
        None,
        ("Example", "execute"),
    ) in facts

    assert (
        PythonStructureKind.CALL,
        "run_flow",
        None,
        None,
        ("Example", "execute"),
    ) in facts


def test_preserves_lexical_scope(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "nested.py"
    ).write_bytes(
        b"""\
def outer():
    def inner():
        helper()
"""
    )

    commit = commit_all(
        repo,
    )

    _, _, result = analyze_path(
        repo,
        commit,
        "nested.py",
    )

    inner = next(
        fact
        for fact in result.facts
        if (
            fact.kind
            == PythonStructureKind.FUNCTION_DEFINITION
            and fact.name == "inner"
        )
    )

    call = next(
        fact
        for fact in result.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and fact.name == "helper"
        )
    )

    assert inner.scope == (
        "outer",
    )

    assert call.scope == (
        "outer",
        "inner",
    )


def test_structure_is_bound_to_exact_blob_evidence(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "app.py"
    ).write_bytes(
        b"""\
def original():
    return 1
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
        "app.py",
    )

    (
        repo
        / "app.py"
    ).write_bytes(
        b"""\
def changed():
    return 999
"""
    )

    result = analyze_python_blob(
        blob,
    )

    names = {
        fact.name
        for fact in result.facts
    }

    assert "original" in names
    assert "changed" not in names

    assert (
        result.source_evidence_id
        == blob.evidence_id
    )

    assert all(
        fact.source_evidence_id
        == blob.evidence_id
        for fact in result.facts
    )


def test_records_exact_source_byte_span(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    source = (
        "π = 1\n"
        "\n"
        "def target():\n"
        "    return helper()\n"
    ).encode(
        "utf-8",
    )

    (
        repo
        / "unicode.py"
    ).write_bytes(
        source,
    )

    commit = commit_all(
        repo,
    )

    _, blob, result = analyze_path(
        repo,
        commit,
        "unicode.py",
    )

    call = next(
        fact
        for fact in result.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and fact.name == "helper"
        )
    )

    assert (
        blob.content[
            call.byte_start:
            call.byte_end
        ]
        == b"helper()"
    )

    assert call.line_start == 4
    assert call.line_end == 4


def test_analysis_identity_is_deterministic(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "app.py"
    ).write_bytes(
        b"""\
def run():
    work()
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
        "app.py",
    )

    first = analyze_python_blob(
        blob,
    )

    second = analyze_python_blob(
        blob,
    )

    assert first == second

    assert (
        first.analysis_id
        == second.analysis_id
    )

    assert all(
        first_fact.evidence_id
        == second_fact.evidence_id
        for first_fact, second_fact
        in zip(
            first.facts,
            second.facts,
            strict=True,
        )
    )


def test_same_bytes_at_different_paths_have_distinct_analysis_identity(
    tmp_path: Path,
) -> None:
    repo = create_repository(
        tmp_path,
    )

    content = b"""\
def run():
    return 1
"""

    (
        repo
        / "a.py"
    ).write_bytes(
        content,
    )

    (
        repo
        / "b.py"
    ).write_bytes(
        content,
    )

    commit = commit_all(
        repo,
    )

    observation = observe_git_commit(
        repo,
        commit,
    )

    first_blob = read_observed_blob(
        repo,
        observation,
        "a.py",
    )

    second_blob = read_observed_blob(
        repo,
        observation,
        "b.py",
    )

    assert (
        first_blob.object_id
        == second_blob.object_id
    )

    first = analyze_python_blob(
        first_blob,
    )

    second = analyze_python_blob(
        second_blob,
    )

    assert (
        first.analysis_id
        != second.analysis_id
    )


def test_invalid_python_is_explicit_not_silently_ignored(
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
        PythonSyntaxEvidenceError,
    ):
        analyze_python_blob(
            blob,
        )
