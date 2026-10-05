from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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


def _analyze(
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

    return blob, analysis


def _call_by_exact_source(
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


@pytest.mark.parametrize(
    (
        "source",
        "call_source",
        "expected_callee",
    ),
    [
        (
            b"""\
def run():
    plain()
""",
            b"plain()",
            b"plain",
        ),
        (
            b"""\
def run():
    client.execute()
""",
            b"client.execute()",
            b"client.execute",
        ),
        (
            b"""\
def run():
    FlowRunEngine[P, R]()
""",
            b"FlowRunEngine[P, R]()",
            b"FlowRunEngine[P, R]",
        ),
        (
            b"""\
def run(name):
    self.registry.get(name)()
""",
            b"self.registry.get(name)()",
            b"self.registry.get(name)",
        ),
        (
            b"""\
def run(obj):
    (obj.method)()
""",
            b"(obj.method)()",
            b"(obj.method)",
        ),
    ],
)
def test_preserves_exact_callee_expression_for_general_python_shapes(
    tmp_path: Path,
    source: bytes,
    call_source: bytes,
    expected_callee: bytes,
) -> None:
    blob, analysis = _analyze(
        tmp_path,
        source,
    )

    call = _call_by_exact_source(
        blob,
        analysis,
        call_source,
    )

    assert (
        call.callee_expression
        == expected_callee.decode(
            "utf-8"
        )
    )

    assert isinstance(
        call.callee_byte_start,
        int,
    )

    assert isinstance(
        call.callee_byte_end,
        int,
    )

    assert (
        blob.content[
            call.callee_byte_start:
            call.callee_byte_end
        ]
        == expected_callee
    )

    assert call.callee_evidence_id

    assert (
        call.callee_evidence_id.startswith(
            "python-callee-expression:"
        )
    )


def test_distinct_complex_callee_shapes_are_not_collapsed(
    tmp_path: Path,
) -> None:
    blob, analysis = _analyze(
        tmp_path,
        b"""\
def run(name):
    Factory[T]()
    registry.get(name)()
""",
    )

    first = _call_by_exact_source(
        blob,
        analysis,
        b"Factory[T]()",
    )

    second = _call_by_exact_source(
        blob,
        analysis,
        b"registry.get(name)()",
    )

    assert (
        first.callee_expression
        == "Factory[T]"
    )

    assert (
        second.callee_expression
        == "registry.get(name)"
    )

    assert (
        first.callee_expression
        != second.callee_expression
    )

    assert (
        first.callee_evidence_id
        != second.callee_evidence_id
    )
