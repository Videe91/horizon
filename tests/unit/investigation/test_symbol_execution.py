from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from horizon.claims.evidence_backed import (
    EvidenceBackedClaim,
)
from horizon.claims.epistemic import (
    EpistemicAssessment,
)
from horizon.investigation.execution import (
    InvestigationExecutionError,
    InvestigationSymbolObservation,
    execute_investigation_operation,
)
from horizon.investigation.plan import (
    InspectSymbolOperation,
)
from horizon.languages.python.structure import (
    PythonStructureKind,
)
from horizon.repository.git_blob import (
    read_observed_blob,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
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


def _repository(
    tmp_path: Path,
) -> tuple[
    Path,
    str,
]:
    repository = (
        tmp_path
        / "repository"
    )

    repository.mkdir()

    _git(
        repository,
        "init",
        "-q",
    )

    _git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    _git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    source = (
        repository
        / "src"
        / "pkg"
    )

    source.mkdir(
        parents=True
    )

    (
        source
        / "policy.py"
    ).write_bytes(
        b"""\
def helper():
    return None


class RetryFailedFlows:
    @staticmethod
    async def before_transition():
        helper()
        context.run()


class OtherRule:
    def before_transition(self):
        unrelated()
"""
    )

    _git(
        repository,
        "add",
        ".",
    )

    _git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    return (
        repository,
        _git(
            repository,
            "rev-parse",
            "HEAD",
        ),
    )


def test_inspect_symbol_returns_exact_definition_fact(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    result = execute_investigation_operation(
        repository,
        observation,
        InspectSymbolOperation(
            path="src/pkg/policy.py",
            symbol="RetryFailedFlows",
        ),
    )

    assert isinstance(
        result,
        InvestigationSymbolObservation,
    )

    assert result.path == "src/pkg/policy.py"
    assert result.symbol == "RetryFailedFlows"
    assert result.commit_sha == commit

    definition = result.definition

    assert (
        definition.kind
        is PythonStructureKind.CLASS_DEFINITION
    )

    assert definition.name == "RetryFailedFlows"
    assert definition.scope == ()

    assert (
        definition.source_evidence_id
        == result.source_blob_evidence_id
    )


def test_inspect_symbol_returns_structural_descendants_only(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    result = execute_investigation_operation(
        repository,
        observation,
        InspectSymbolOperation(
            path="src/pkg/policy.py",
            symbol="RetryFailedFlows",
        ),
    )

    names = {
        (
            fact.kind,
            fact.name,
            fact.scope,
        )
        for fact
        in result.facts
    }

    assert (
        PythonStructureKind.CLASS_DEFINITION,
        "RetryFailedFlows",
        (),
    ) in names

    assert (
        PythonStructureKind.ASYNC_FUNCTION_DEFINITION,
        "before_transition",
        ("RetryFailedFlows",),
    ) in names

    assert (
        PythonStructureKind.DECORATOR,
        "staticmethod",
        (
            "RetryFailedFlows",
            "before_transition",
        ),
    ) in names

    assert (
        PythonStructureKind.CALL,
        "helper",
        (
            "RetryFailedFlows",
            "before_transition",
        ),
    ) in names

    assert (
        PythonStructureKind.CALL,
        "context.run",
        (
            "RetryFailedFlows",
            "before_transition",
        ),
    ) in names

    assert not any(
        fact.name == "OtherRule"
        for fact
        in result.facts
    )

    assert not any(
        fact.name == "unrelated"
        for fact
        in result.facts
    )


def test_inspect_nested_symbol_uses_lexical_scope(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    result = execute_investigation_operation(
        repository,
        observation,
        InspectSymbolOperation(
            path="src/pkg/policy.py",
            symbol=(
                "RetryFailedFlows."
                "before_transition"
            ),
        ),
    )

    assert (
        result.definition.kind
        is PythonStructureKind.ASYNC_FUNCTION_DEFINITION
    )

    assert (
        result.definition.name
        == "before_transition"
    )

    assert (
        result.definition.scope
        == (
            "RetryFailedFlows",
        )
    )

    assert all(
        (
            fact.evidence_id
            == result.definition.evidence_id
            or fact.scope[
                :2
            ]
            == (
                "RetryFailedFlows",
                "before_transition",
            )
        )
        for fact
        in result.facts
    )


def test_inspect_symbol_preserves_structure_analysis_identity(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    blob = read_observed_blob(
        repository,
        observation,
        "src/pkg/policy.py",
    )

    result = execute_investigation_operation(
        repository,
        observation,
        InspectSymbolOperation(
            path="src/pkg/policy.py",
            symbol="RetryFailedFlows",
        ),
    )

    assert (
        result.source_blob_evidence_id
        == blob.evidence_id
    )

    assert (
        result.source_object_id
        == blob.object_id
    )

    assert result.structure_analysis_id.startswith(
        "python-structure-analysis:"
    )


def test_inspect_symbol_definition_span_points_to_exact_blob_bytes(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    blob = read_observed_blob(
        repository,
        observation,
        "src/pkg/policy.py",
    )

    result = execute_investigation_operation(
        repository,
        observation,
        InspectSymbolOperation(
            path="src/pkg/policy.py",
            symbol="RetryFailedFlows",
        ),
    )

    definition = result.definition

    source = blob.content[
        definition.byte_start:
        definition.byte_end
    ]

    assert source.startswith(
        b"class RetryFailedFlows:"
    )

    assert (
        b"async def before_transition"
        in source
    )

    assert (
        b"class OtherRule:"
        not in source
    )


def test_inspect_symbol_is_deterministic(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    operation = InspectSymbolOperation(
        path="src/pkg/policy.py",
        symbol="RetryFailedFlows",
    )

    first = execute_investigation_operation(
        repository,
        observation,
        operation,
    )

    second = execute_investigation_operation(
        repository,
        observation,
        operation,
    )

    assert first == second

    assert (
        first.observation_id
        == second.observation_id
    )


def test_missing_symbol_is_explicit(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    with pytest.raises(
        InvestigationExecutionError,
        match="not found",
    ):
        execute_investigation_operation(
            repository,
            observation,
            InspectSymbolOperation(
                path="src/pkg/policy.py",
                symbol="MissingRule",
            ),
        )


def test_duplicate_symbol_in_same_scope_is_ambiguous(
    tmp_path: Path,
) -> None:
    repository = (
        tmp_path
        / "ambiguous"
    )

    repository.mkdir()

    _git(
        repository,
        "init",
        "-q",
    )

    _git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    _git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    (
        repository
        / "duplicate.py"
    ).write_bytes(
        b"""\
class Duplicate:
    pass

class Duplicate:
    pass
"""
    )

    _git(
        repository,
        "add",
        ".",
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

    with pytest.raises(
        InvestigationExecutionError,
        match="ambiguous",
    ):
        execute_investigation_operation(
            repository,
            observation,
            InspectSymbolOperation(
                path="duplicate.py",
                symbol="Duplicate",
            ),
        )


def test_invalid_python_is_explicit(
    tmp_path: Path,
) -> None:
    repository = (
        tmp_path
        / "broken"
    )

    repository.mkdir()

    _git(
        repository,
        "init",
        "-q",
    )

    _git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    _git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    (
        repository
        / "broken.py"
    ).write_bytes(
        b"def broken(:\n"
    )

    _git(
        repository,
        "add",
        ".",
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

    with pytest.raises(
        InvestigationExecutionError,
        match="Python structure",
    ):
        execute_investigation_operation(
            repository,
            observation,
            InspectSymbolOperation(
                path="broken.py",
                symbol="broken",
            ),
        )


def test_inspect_symbol_does_not_mutate_repository(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    before_head = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    before_status = _git(
        repository,
        "status",
        "--porcelain",
    )

    execute_investigation_operation(
        repository,
        observation,
        InspectSymbolOperation(
            path="src/pkg/policy.py",
            symbol="RetryFailedFlows",
        ),
    )

    after_head = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    after_status = _git(
        repository,
        "status",
        "--porcelain",
    )

    assert before_head == after_head
    assert before_status == after_status == ""


def test_symbol_observation_is_not_world_model_truth(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _repository(
            tmp_path
        )
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    result = execute_investigation_operation(
        repository,
        observation,
        InspectSymbolOperation(
            path="src/pkg/policy.py",
            symbol="RetryFailedFlows",
        ),
    )

    assert not isinstance(
        result,
        EvidenceBackedClaim,
    )

    assert not isinstance(
        result,
        EpistemicAssessment,
    )

    assert not isinstance(
        result,
        WorldModelAssertion,
    )
