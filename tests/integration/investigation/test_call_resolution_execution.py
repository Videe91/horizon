from __future__ import annotations

import json
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
    InvestigationCallObservation,
    InvestigationExecutionError,
    execute_investigation_operation,
)
from horizon.investigation.plan import (
    ResolveCallOperation,
)
from horizon.languages.python.structure import (
    PythonStructureKind,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
)


def _typeserver() -> Path:
    root = Path(
        __file__
    ).resolve().parents[3]

    result = (
        root
        / "node_modules"
        / ".bin"
        / "pyright-typeserver"
    )

    assert result.is_file()

    return result


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

    (
        repository
        / "sample.py"
    ).write_bytes(
        b"""\
def target(value: int) -> int:
    return value


def caller() -> int:
    return target(1)
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


def test_resolve_call_returns_existing_pyright_semantic_evidence(
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
        ResolveCallOperation(
            path="sample.py",
            line=6,
            character=12,
        ),
        pyright_typeserver=(
            _typeserver()
        ),
    )

    assert isinstance(
        result,
        InvestigationCallObservation,
    )

    assert result.path == "sample.py"
    assert result.line == 6
    assert result.character == 12

    assert result.commit_sha == commit

    assert (
        result.repository_observation_id
        == observation.observation_id
    )

    assert (
        result.call.kind
        is PythonStructureKind.CALL
    )

    assert result.call.name == "target"

    assert (
        result.call.callee_expression
        == "target"
    )

    assert (
        result.semantic_evidence.source_evidence_id
        == result.source_blob_evidence_id
    )

    assert (
        result.semantic_evidence.call_evidence_id
        == result.call.evidence_id
    )

    assert (
        result.semantic_evidence.callee_evidence_id
        == result.call.callee_evidence_id
    )

    assert (
        result.semantic_evidence.callee_expression
        == "target"
    )

    assert (
        result.semantic_evidence.pyright_version
        == "1.1.414"
    )

    assert (
        result.semantic_evidence.protocol_version
        == "0.4.1"
    )

    computed = json.loads(
        result.semantic_evidence.computed_type_json
    )

    assert isinstance(
        computed,
        dict,
    )

    assert (
        result.semantic_evidence.evidence_id.startswith(
            "python-pyright-callee-type:"
        )
    )

    assert result.observation_id.startswith(
        "investigation-call-observation:"
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


def test_resolve_call_accepts_position_inside_exact_callee_span(
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

    first = execute_investigation_operation(
        repository,
        observation,
        ResolveCallOperation(
            path="sample.py",
            line=6,
            character=11,
        ),
        pyright_typeserver=(
            _typeserver()
        ),
    )

    second = execute_investigation_operation(
        repository,
        observation,
        ResolveCallOperation(
            path="sample.py",
            line=6,
            character=15,
        ),
        pyright_typeserver=(
            _typeserver()
        ),
    )

    assert (
        first.call.evidence_id
        == second.call.evidence_id
    )

    assert (
        first.semantic_evidence.evidence_id
        == second.semantic_evidence.evidence_id
    )

    assert (
        first.observation_id
        != second.observation_id
    )


def test_resolve_call_rejects_position_with_no_call(
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
        match="CALL fact",
    ):
        execute_investigation_operation(
            repository,
            observation,
            ResolveCallOperation(
                path="sample.py",
                line=6,
                character=4,
            ),
            pyright_typeserver=(
                _typeserver()
            ),
        )


def test_resolve_call_requires_trusted_typeserver_configuration(
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
        match="Pyright type server",
    ):
        execute_investigation_operation(
            repository,
            observation,
            ResolveCallOperation(
                path="sample.py",
                line=6,
                character=12,
            ),
        )


def test_resolve_call_rejects_missing_typeserver(
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

    missing = (
        tmp_path
        / "missing-pyright-typeserver"
    )

    with pytest.raises(
        InvestigationExecutionError,
        match="Pyright call resolution",
    ):
        execute_investigation_operation(
            repository,
            observation,
            ResolveCallOperation(
                path="sample.py",
                line=6,
                character=12,
            ),
            pyright_typeserver=missing,
        )


def test_resolve_call_does_not_mutate_repository(
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
        ResolveCallOperation(
            path="sample.py",
            line=6,
            character=12,
        ),
        pyright_typeserver=(
            _typeserver()
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
