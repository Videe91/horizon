from __future__ import annotations

import json
import subprocess
from pathlib import Path

from horizon.languages.python.pyright_callee import (
    analyze_pyright_callee_type,
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


def _git(
    repository: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            *args,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return completed.stdout.strip()


def _typeserver() -> str:
    root = Path(
        __file__
    ).resolve().parents[4]

    executable = (
        root
        / "node_modules"
        / ".bin"
        / "pyright-typeserver"
    )

    assert executable.is_file()

    return str(executable)


def _fixture(
    tmp_path: Path,
    source: bytes,
):
    repository = tmp_path / "repository"
    repository.mkdir()

    _git(
        repository,
        "init",
        "-q",
        "-b",
        "main",
    )

    _git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    _git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    path = repository / "sample.py"
    path.write_bytes(source)

    _git(
        repository,
        "add",
        "sample.py",
    )

    _git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    blob = read_observed_blob(
        repository,
        observation,
        "sample.py",
    )

    analysis = analyze_python_blob(
        blob
    )

    return (
        repository,
        observation,
        blob,
        analysis,
    )


def _call(
    blob,
    analysis,
    call_source: bytes,
):
    matches = [
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and blob.content[
                fact.byte_start:
                fact.byte_end
            ]
            == call_source
        )
    ]

    assert len(matches) == 1

    return matches[0]


def test_pyright_returns_structured_type_for_generic_class_callee(
    tmp_path: Path,
) -> None:
    (
        repository,
        observation,
        blob,
        analysis,
    ) = _fixture(
        tmp_path,
        b"""\
from typing import Generic, TypeVar

P = TypeVar("P")
R = TypeVar("R")

class FlowRunEngine(Generic[P, R]):
    pass

def run(left: P, right: R):
    return FlowRunEngine[P, R]()
""",
    )

    call = _call(
        blob,
        analysis,
        b"FlowRunEngine[P, R]()",
    )

    evidence = analyze_pyright_callee_type(
        repository=repository,
        observation=observation,
        blob=blob,
        call_fact=call,
        pyright_typeserver=_typeserver(),
    )

    assert (
        evidence.source_evidence_id
        == blob.evidence_id
    )

    assert (
        evidence.call_evidence_id
        == call.evidence_id
    )

    assert (
        evidence.callee_expression
        == "FlowRunEngine[P, R]"
    )

    assert evidence.pyright_version == "1.1.414"

    assert (
        evidence.protocol_version
        == "0.4.1"
    )

    computed = json.loads(
        evidence.computed_type_json
    )

    assert computed["kind"] == 3

    assert (
        computed["declaration"]["name"]
        == "FlowRunEngine"
    )

    assert [
        item["declaration"]["name"]
        for item in computed["typeArgs"]
    ] == [
        "P",
        "R",
    ]

    assert (
        evidence.evidence_id.startswith(
            "python-pyright-callee-type:"
        )
    )


def test_pyright_type_is_not_invented_from_callee_spelling(
    tmp_path: Path,
) -> None:
    (
        repository,
        observation,
        blob,
        analysis,
    ) = _fixture(
        tmp_path,
        b"""\
def integer_target(value: int) -> int:
    return value

def string_target(value: str) -> str:
    return value

def first():
    target = integer_target
    return target(1)

def second():
    target = string_target
    return target("one")
""",
    )

    first_call = _call(
        blob,
        analysis,
        b"target(1)",
    )

    second_call = _call(
        blob,
        analysis,
        b'target("one")',
    )

    assert (
        first_call.callee_expression
        == second_call.callee_expression
        == "target"
    )

    first = analyze_pyright_callee_type(
        repository=repository,
        observation=observation,
        blob=blob,
        call_fact=first_call,
        pyright_typeserver=_typeserver(),
    )

    second = analyze_pyright_callee_type(
        repository=repository,
        observation=observation,
        blob=blob,
        call_fact=second_call,
        pyright_typeserver=_typeserver(),
    )

    assert (
        first.computed_type_json
        != second.computed_type_json
    )

    assert (
        "integer_target"
        in first.computed_type_json
    )

    assert (
        "string_target"
        in second.computed_type_json
    )

    assert (
        first.evidence_id
        != second.evidence_id
    )
