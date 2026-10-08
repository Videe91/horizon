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
    InvestigationSourceObservation,
    execute_investigation_operation,
)
from horizon.investigation.plan import (
    ReadSourceOperation,
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
        (
            b"class RetryFailedFlows:\n"
            b"    def before_transition(self):\n"
            b"        retries = 3\n"
            b"        return retries\n"
            b"\n"
            b"VALUE = 1\n"
        )
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


def test_read_source_uses_exact_observed_git_blob(
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

    operation = ReadSourceOperation(
        path="src/pkg/policy.py",
        start_line=2,
        end_line=4,
    )

    result = execute_investigation_operation(
        repository,
        observation,
        operation,
    )

    assert isinstance(
        result,
        InvestigationSourceObservation,
    )

    assert result.path == "src/pkg/policy.py"
    assert result.start_line == 2
    assert result.end_line == 4
    assert result.commit_sha == commit

    assert (
        result.repository_observation_id
        == observation.observation_id
    )

    assert tuple(
        (
            line.line_number,
            line.content,
        )
        for line
        in result.lines
    ) == (
        (
            2,
            b"    def before_transition(self):",
        ),
        (
            3,
            b"        retries = 3",
        ),
        (
            4,
            b"        return retries",
        ),
    )


def test_read_source_preserves_exact_blob_evidence_identity(
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
        ReadSourceOperation(
            path="src/pkg/policy.py",
            start_line=1,
            end_line=2,
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


def test_read_source_is_deterministic(
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

    operation = ReadSourceOperation(
        path="src/pkg/policy.py",
        start_line=1,
        end_line=4,
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


def test_read_source_rejects_line_window_beyond_observed_blob(
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
        match="line window",
    ):
        execute_investigation_operation(
            repository,
            observation,
            ReadSourceOperation(
                path="src/pkg/policy.py",
                start_line=1,
                end_line=100,
            ),
        )


def test_read_source_rejects_missing_observed_path(
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
        match="observed Git blob",
    ):
        execute_investigation_operation(
            repository,
            observation,
            ReadSourceOperation(
                path="src/pkg/missing.py",
                start_line=1,
                end_line=1,
            ),
        )


def test_read_source_does_not_mutate_repository(
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
        ReadSourceOperation(
            path="src/pkg/policy.py",
            start_line=1,
            end_line=3,
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


def test_read_source_result_is_observation_not_truth(
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
        ReadSourceOperation(
            path="src/pkg/policy.py",
            start_line=1,
            end_line=3,
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



def test_read_source_null_end_line_reads_through_observed_eof(
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
        ReadSourceOperation(
            path="src/pkg/policy.py",
            start_line=2,
            end_line=None,
        ),
    )

    assert (
        result.start_line
        == 2
    )

    assert (
        result.end_line
        == 6
    )

    assert (
        result.observed_source_line_count
        == 6
    )

    assert (
        result.ends_at_observed_eof
        is True
    )

    assert tuple(
        line.line_number
        for line
        in result.lines
    ) == (
        2,
        3,
        4,
        5,
        6,
    )


def test_read_source_explicit_partial_window_reports_not_eof(
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
        ReadSourceOperation(
            path="src/pkg/policy.py",
            start_line=2,
            end_line=4,
        ),
    )

    assert (
        result.observed_source_line_count
        == 6
    )

    assert (
        result.ends_at_observed_eof
        is False
    )


def test_eof_read_and_exact_explicit_eof_read_share_observation_identity(
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

    eof = execute_investigation_operation(
        repository,
        observation,
        ReadSourceOperation(
            path="src/pkg/policy.py",
            start_line=2,
            end_line=None,
        ),
    )

    explicit = execute_investigation_operation(
        repository,
        observation,
        ReadSourceOperation(
            path="src/pkg/policy.py",
            start_line=2,
            end_line=6,
        ),
    )

    assert (
        eof.observation_id
        == explicit.observation_id
    )

    assert eof == explicit
