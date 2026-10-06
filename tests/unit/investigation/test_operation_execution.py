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
    InvestigationSearchObservation,
    UnsupportedInvestigationOperationError,
    execute_investigation_operation,
)
from horizon.investigation.plan import (
    ReadSourceOperation,
    SearchSourceOperation,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.git_search import (
    search_observed_text,
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

    (
        repository
        / "src"
        / "pkg"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "tests"
    ).mkdir()

    (
        repository
        / "src"
        / "pkg"
        / "policy.py"
    ).write_text(
        (
            "class RetryFailedFlows:\n"
            "    pass\n"
        ),
        encoding="utf-8",
    )

    (
        repository
        / "src"
        / "pkg"
        / "engine.py"
    ).write_text(
        (
            "def run():\n"
            "    RetryFailedFlows\n"
        ),
        encoding="utf-8",
    )

    (
        repository
        / "tests"
        / "test_policy.py"
    ).write_text(
        (
            "def test_name():\n"
            "    RetryFailedFlows\n"
        ),
        encoding="utf-8",
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


def test_search_source_executes_through_observed_git_evidence(
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

    operation = SearchSourceOperation(
        query="RetryFailedFlows",
        path_prefix="src/pkg",
    )

    result = (
        execute_investigation_operation(
            repository,
            observation,
            operation,
        )
    )

    assert isinstance(
        result,
        InvestigationSearchObservation,
    )

    assert (
        result.repository_observation_id
        == observation.observation_id
    )

    assert (
        result.commit_sha
        == commit
    )

    assert (
        result.query
        == "RetryFailedFlows"
    )

    assert (
        result.path_prefix
        == "src/pkg"
    )

    assert len(
        result.matches
    ) == 2

    assert {
        match.path
        for match
        in result.matches
    } == {
        "src/pkg/engine.py",
        "src/pkg/policy.py",
    }


def test_execution_preserves_original_git_search_evidence_ids(
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

    direct = search_observed_text(
        repository,
        observation,
        "RetryFailedFlows",
    )

    result = (
        execute_investigation_operation(
            repository,
            observation,
            SearchSourceOperation(
                query="RetryFailedFlows",
                path_prefix="src/pkg",
            ),
        )
    )

    expected = tuple(
        match.evidence_id
        for match
        in direct.matches
        if match.path.startswith(
            "src/pkg/"
        )
    )

    actual = tuple(
        match.evidence_id
        for match
        in result.matches
    )

    assert actual == expected

    assert (
        result.source_search_id
        == direct.search_id
    )


def test_path_prefix_filters_without_reinterpreting_evidence(
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

    result = (
        execute_investigation_operation(
            repository,
            observation,
            SearchSourceOperation(
                query="RetryFailedFlows",
                path_prefix="tests",
            ),
        )
    )

    assert len(
        result.matches
    ) == 1

    assert (
        result.matches[0].path
        == "tests/test_policy.py"
    )


def test_no_prefix_preserves_all_search_matches(
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

    direct = search_observed_text(
        repository,
        observation,
        "RetryFailedFlows",
    )

    result = (
        execute_investigation_operation(
            repository,
            observation,
            SearchSourceOperation(
                query="RetryFailedFlows",
            ),
        )
    )

    assert (
        result.matches
        == direct.matches
    )


def test_no_matches_is_truthful_observation_not_error(
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

    result = (
        execute_investigation_operation(
            repository,
            observation,
            SearchSourceOperation(
                query="definitely-absent",
                path_prefix="src/pkg",
            ),
        )
    )

    assert (
        result.matches
        == ()
    )

    assert result.observation_id.startswith(
        "investigation-search-observation:"
    )


def test_execution_is_deterministic(
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

    operation = SearchSourceOperation(
        query="RetryFailedFlows",
        path_prefix="src/pkg",
    )

    first = (
        execute_investigation_operation(
            repository,
            observation,
            operation,
        )
    )

    second = (
        execute_investigation_operation(
            repository,
            observation,
            operation,
        )
    )

    assert first == second

    assert (
        first.observation_id
        == second.observation_id
    )


def test_execution_does_not_mutate_repository(
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
        SearchSourceOperation(
            query="RetryFailedFlows",
            path_prefix="src/pkg",
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


def test_execution_rejects_unobserved_repository_state(
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

    (
        repository
        / "untracked.txt"
    ).write_text(
        "mutation\n",
        encoding="utf-8",
    )

    with pytest.raises(
        InvestigationExecutionError,
        match="working tree",
    ):
        execute_investigation_operation(
            repository,
            observation,
            SearchSourceOperation(
                query="RetryFailedFlows",
            ),
        )


def test_execution_rejects_wrong_checked_out_commit(
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

    (
        repository
        / "later.txt"
    ).write_text(
        "later\n",
        encoding="utf-8",
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
        "later",
    )

    with pytest.raises(
        InvestigationExecutionError,
        match="commit",
    ):
        execute_investigation_operation(
            repository,
            observation,
            SearchSourceOperation(
                query="RetryFailedFlows",
            ),
        )


def test_unimplemented_typed_operation_is_explicitly_rejected(
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
        end_line=2,
    )

    with pytest.raises(
        UnsupportedInvestigationOperationError,
        match="READ_SOURCE",
    ):
        execute_investigation_operation(
            repository,
            observation,
            operation,
        )


def test_operation_result_is_observation_not_truth(
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

    result = (
        execute_investigation_operation(
            repository,
            observation,
            SearchSourceOperation(
                query="RetryFailedFlows",
            ),
        )
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
