from __future__ import annotations

import subprocess
from pathlib import Path

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


def analyze_source(
    tmp_path: Path,
    source: bytes,
):
    repo = create_repository(
        tmp_path,
    )

    (
        repo
        / "sample.py"
    ).write_bytes(
        source,
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

    return analyze_python_blob(
        blob,
    )


def test_class_is_structurally_owned_by_module(
    tmp_path: Path,
) -> None:
    analysis = analyze_source(
        tmp_path,
        b"""\
class Flow:
    pass
""",
    )

    module = next(
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.MODULE
        )
    )

    flow = next(
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.CLASS_DEFINITION
            and fact.name == "Flow"
        )
    )

    assert (
        module.structural_parent_id
        is None
    )

    assert (
        flow.structural_parent_id
        == module.evidence_id
    )


def test_same_named_definitions_have_exact_structural_identity(
    tmp_path: Path,
) -> None:
    analysis = analyze_source(
        tmp_path,
        b"""\
class Flow:
    def __call__(self, value: int):
        ...

    def __call__(self, value: str):
        ...

    def __call__(self, value):
        return value
""",
    )

    flow = next(
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.CLASS_DEFINITION
            and fact.name == "Flow"
        )
    )

    definitions = sorted(
        (
            fact
            for fact in analysis.facts
            if (
                fact.kind
                == PythonStructureKind.FUNCTION_DEFINITION
                and fact.name == "__call__"
                and fact.scope == ("Flow",)
            )
        ),
        key=lambda fact: fact.line_start,
    )

    assert len(
        definitions
    ) == 3

    assert len(
        {
            fact.evidence_id
            for fact in definitions
        }
    ) == 3

    assert all(
        fact.structural_parent_id
        == flow.evidence_id
        for fact in definitions
    )


def test_decorator_is_attached_to_exact_same_named_definition(
    tmp_path: Path,
) -> None:
    analysis = analyze_source(
        tmp_path,
        b"""\
class Flow:
    @overload
    def __call__(self, value: int):
        ...

    @overload
    def __call__(self, value: str):
        ...

    def __call__(self, value):
        return run_flow(value)
""",
    )

    definitions = sorted(
        (
            fact
            for fact in analysis.facts
            if (
                fact.kind
                == PythonStructureKind.FUNCTION_DEFINITION
                and fact.name == "__call__"
                and fact.scope == ("Flow",)
            )
        ),
        key=lambda fact: fact.line_start,
    )

    decorators = sorted(
        (
            fact
            for fact in analysis.facts
            if (
                fact.kind
                == PythonStructureKind.DECORATOR
                and fact.name == "overload"
                and fact.scope == ("Flow", "__call__")
            )
        ),
        key=lambda fact: fact.line_start,
    )

    assert len(
        definitions
    ) == 3

    assert len(
        decorators
    ) == 2

    assert (
        decorators[0].structural_parent_id
        == definitions[0].evidence_id
    )

    assert (
        decorators[1].structural_parent_id
        == definitions[1].evidence_id
    )

    assert all(
        decorator.structural_parent_id
        != definitions[2].evidence_id
        for decorator in decorators
    )


def test_body_call_is_attached_to_exact_implementation_definition(
    tmp_path: Path,
) -> None:
    analysis = analyze_source(
        tmp_path,
        b"""\
class Flow:
    @overload
    def __call__(self, value: int):
        ...

    @overload
    def __call__(self, value: str):
        ...

    def __call__(self, value):
        return run_flow(value)
""",
    )

    definitions = sorted(
        (
            fact
            for fact in analysis.facts
            if (
                fact.kind
                == PythonStructureKind.FUNCTION_DEFINITION
                and fact.name == "__call__"
                and fact.scope == ("Flow",)
            )
        ),
        key=lambda fact: fact.line_start,
    )

    call = next(
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and fact.name == "run_flow"
            and fact.scope == ("Flow", "__call__")
        )
    )

    assert (
        call.structural_parent_id
        == definitions[2].evidence_id
    )

    assert (
        call.structural_parent_id
        != definitions[0].evidence_id
    )

    assert (
        call.structural_parent_id
        != definitions[1].evidence_id
    )


def test_nested_definition_preserves_exact_parent_chain(
    tmp_path: Path,
) -> None:
    analysis = analyze_source(
        tmp_path,
        b"""\
def outer():
    def inner():
        helper()
""",
    )

    outer = next(
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.FUNCTION_DEFINITION
            and fact.name == "outer"
        )
    )

    inner = next(
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.FUNCTION_DEFINITION
            and fact.name == "inner"
        )
    )

    call = next(
        fact
        for fact in analysis.facts
        if (
            fact.kind
            == PythonStructureKind.CALL
            and fact.name == "helper"
        )
    )

    assert (
        inner.structural_parent_id
        == outer.evidence_id
    )

    assert (
        call.structural_parent_id
        == inner.evidence_id
    )
