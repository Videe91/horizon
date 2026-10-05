from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from horizon.repository.git_observation import (
    GitCommitObservation,
    observe_git_commit,
)
from horizon.runtime.causal_experiment import (
    CausalExperimentEvidenceError,
    SourceInterventionChangeEvidence,
    SourceInterventionComparisonEvidence,
    compare_source_intervention,
)
from horizon.runtime.observation import (
    RuntimeEvidence,
    RuntimeEventEvidence,
    RuntimeLimits,
    observe_runtime,
)


EXPERIMENT_ID = (
    "source-intervention-experiment-v1"
)

INTERVENTION_ID = (
    "change-attempt-count"
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


def _program(
    attempts: int,
    *,
    marker: str,
) -> str:
    return f"""\
import json
import os
from pathlib import Path

INTERVENTION_MARKER = {marker!r}

event_path = Path(
    os.environ[
        "HORIZON_RUNTIME_EVENT_FILE"
    ]
)

event = {{
    "kind": "final_outcome",
    "process_id": os.getpid(),
    "payload": {{
        "attempts": {attempts},
    }},
}}

event_path.write_text(
    json.dumps(
        event,
        sort_keys=True,
    )
    + "\\n",
    encoding="utf-8",
)
"""


def _init_repository(
    root: Path,
    *,
    intervention_attempts: int = 1,
) -> tuple[
    Path,
    str,
    str,
]:
    repository = (
        root
        / "repository"
    )

    repository.mkdir()

    subprocess.run(
        [
            "git",
            "init",
            "-q",
            "-b",
            "main",
            str(repository),
        ],
        check=True,
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

    program = (
        repository
        / "program.py"
    )

    program.write_text(
        _program(
            2,
            marker="baseline",
        ),
        encoding="utf-8",
    )

    _git(
        repository,
        "add",
        "program.py",
    )

    _git(
        repository,
        "commit",
        "-q",
        "-m",
        "baseline",
    )

    baseline_commit = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    program.write_text(
        _program(
            intervention_attempts,
            marker="intervention",
        ),
        encoding="utf-8",
    )

    _git(
        repository,
        "add",
        "program.py",
    )

    _git(
        repository,
        "commit",
        "-q",
        "-m",
        "intervention",
    )

    intervention_commit = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    assert (
        baseline_commit
        != intervention_commit
    )

    return (
        repository,
        baseline_commit,
        intervention_commit,
    )


def _limits() -> RuntimeLimits:
    return RuntimeLimits(
        timeout_seconds=5.0,
        disk_growth_limit_bytes=(
            10_000_000
        ),
    )


def _observe_pair(
    root: Path,
    *,
    intervention_attempts: int = 1,
) -> tuple[
    GitCommitObservation,
    GitCommitObservation,
    RuntimeEvidence,
    RuntimeEvidence,
    RuntimeEventEvidence,
    RuntimeEventEvidence,
]:
    (
        repository,
        baseline_commit,
        intervention_commit,
    ) = _init_repository(
        root,
        intervention_attempts=(
            intervention_attempts
        ),
    )

    baseline_source = (
        observe_git_commit(
            repository,
            baseline_commit,
        )
    )

    intervention_source = (
        observe_git_commit(
            repository,
            intervention_commit,
        )
    )

    command = (
        sys.executable,
        "program.py",
    )

    configuration = {
        "HORIZON_TEST_MODE": (
            "controlled"
        ),
    }

    baseline = observe_runtime(
        repository,
        baseline_source,
        command,
        limits=_limits(),
        configuration=configuration,
        experiment_id=(
            EXPERIMENT_ID
        ),
    )

    intervention = observe_runtime(
        repository,
        intervention_source,
        command,
        limits=_limits(),
        configuration=configuration,
        experiment_id=(
            EXPERIMENT_ID
        ),
        intervention_id=(
            INTERVENTION_ID
        ),
    )

    assert len(
        baseline.events
    ) == 1

    assert len(
        intervention.events
    ) == 1

    return (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline.events[
            0
        ],
        intervention.events[
            0
        ],
    )


def _compare(
    baseline_source,
    intervention_source,
    baseline,
    intervention,
    baseline_outcome,
    intervention_outcome,
):
    return compare_source_intervention(
        baseline,
        intervention,
        baseline_source=(
            baseline_source
        ),
        intervention_source=(
            intervention_source
        ),
        baseline_outcome=(
            baseline_outcome
        ),
        intervention_outcome=(
            intervention_outcome
        ),
    )


def test_source_intervention_preserves_exact_controlled_comparison(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    evidence = _compare(
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    )

    assert isinstance(
        evidence,
        SourceInterventionComparisonEvidence,
    )

    assert (
        evidence.experiment_id
        == EXPERIMENT_ID
    )

    assert (
        evidence.intervention_id
        == INTERVENTION_ID
    )

    assert (
        evidence.baseline_runtime_evidence_id
        == baseline.evidence_id
    )

    assert (
        evidence.intervention_runtime_evidence_id
        == intervention.evidence_id
    )

    assert (
        evidence.baseline_source_observation_id
        == baseline_source.observation_id
    )

    assert (
        evidence.intervention_source_observation_id
        == intervention_source.observation_id
    )

    assert (
        evidence.baseline_source_commit
        == baseline_source.commit_sha
    )

    assert (
        evidence.intervention_source_commit
        == intervention_source.commit_sha
    )

    assert (
        evidence.baseline_source_commit
        != evidence.intervention_source_commit
    )

    assert len(
        evidence.source_changes
    ) == 1

    change = evidence.source_changes[
        0
    ]

    assert isinstance(
        change,
        SourceInterventionChangeEvidence,
    )

    assert change.path == "program.py"

    assert (
        change.baseline_object_id
        is not None
    )

    assert (
        change.intervention_object_id
        is not None
    )

    assert (
        change.baseline_object_id
        != change.intervention_object_id
    )

    assert (
        change.baseline_mode
        == change.intervention_mode
    )

    assert (
        change.baseline_object_type
        == "blob"
    )

    assert (
        change.intervention_object_type
        == "blob"
    )

    assert (
        change.evidence_id.startswith(
            "source-intervention-change:"
        )
    )

    assert (
        evidence.source_delta_id.startswith(
            "source-intervention-delta:"
        )
    )

    assert (
        evidence.baseline_outcome_event_evidence_id
        == baseline_outcome.evidence_id
    )

    assert (
        evidence.intervention_outcome_event_evidence_id
        == intervention_outcome.evidence_id
    )

    assert (
        evidence.outcome_kind
        == "final_outcome"
    )

    assert (
        json.loads(
            evidence.baseline_outcome_payload_json
        )
        == {
            "attempts": 2,
        }
    )

    assert (
        json.loads(
            evidence.intervention_outcome_payload_json
        )
        == {
            "attempts": 1,
        }
    )

    assert evidence.outcome_changed is True

    assert (
        evidence.evidence_id.startswith(
            "source-intervention-comparison:"
        )
    )


def test_source_delta_is_derived_from_observed_git_trees_not_label(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    evidence = _compare(
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    )

    assert tuple(
        change.path
        for change in evidence.source_changes
    ) == (
        "program.py",
    )

    assert (
        evidence.source_changes[
            0
        ].baseline_object_id
        != evidence.source_changes[
            0
        ].intervention_object_id
    )

    assert (
        evidence.intervention_id
        == INTERVENTION_ID
    )


def test_source_intervention_requires_sources_to_match_runtime_evidence(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="source observation",
    ):
        _compare(
            intervention_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_same_experiment_identity(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    intervention = dataclasses.replace(
        intervention,
        experiment_id=(
            "different-experiment"
        ),
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="experiment",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_baseline_without_intervention(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    baseline = dataclasses.replace(
        baseline,
        intervention_id=(
            "baseline-must-not-have-one"
        ),
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="baseline",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_intervention_identity(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    intervention = dataclasses.replace(
        intervention,
        intervention_id=None,
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="intervention",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_same_command(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    intervention = dataclasses.replace(
        intervention,
        command=(
            sys.executable,
            "different.py",
        ),
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="command",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_same_explicit_configuration(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    intervention = dataclasses.replace(
        intervention,
        configuration=(
            (
                "HORIZON_TEST_MODE",
                "different",
            ),
        ),
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="configuration",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_actual_source_delta(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        _intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    intervention = dataclasses.replace(
        intervention,
        source_observation_id=(
            baseline.source_observation_id
        ),
        source_commit=(
            baseline.source_commit
        ),
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="source",
    ):
        _compare(
            baseline_source,
            baseline_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_outcomes_to_belong_to_their_runs(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        _baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="outcome",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            intervention_outcome,
            intervention_outcome,
        )


def test_source_intervention_requires_comparable_outcome_kind(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    intervention_outcome = (
        dataclasses.replace(
            intervention_outcome,
            kind="different_outcome",
        )
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="kind",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            intervention_outcome,
        )


def test_source_intervention_records_real_unchanged_outcome_truthfully(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path,
        intervention_attempts=2,
    )

    assert (
        baseline_source.observation_id
        != intervention_source.observation_id
    )

    assert (
        baseline_outcome.payload_json
        == intervention_outcome.payload_json
    )

    evidence = _compare(
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    )

    assert evidence.outcome_changed is False

    assert (
        evidence.baseline_outcome_payload_json
        == evidence.intervention_outcome_payload_json
    )


def test_source_intervention_rejects_forged_outcome_event(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    forged_intervention_outcome = (
        dataclasses.replace(
            intervention_outcome,
            payload_json=(
                baseline_outcome.payload_json
            ),
        )
    )

    assert (
        forged_intervention_outcome
        not in intervention.events
    )

    with pytest.raises(
        CausalExperimentEvidenceError,
        match="outcome",
    ):
        _compare(
            baseline_source,
            intervention_source,
            baseline,
            intervention,
            baseline_outcome,
            forged_intervention_outcome,
        )


def test_source_intervention_comparison_identity_is_deterministic(
    tmp_path: Path,
) -> None:
    (
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    ) = _observe_pair(
        tmp_path
    )

    first = _compare(
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    )

    second = _compare(
        baseline_source,
        intervention_source,
        baseline,
        intervention,
        baseline_outcome,
        intervention_outcome,
    )

    assert first == second

    assert (
        first.evidence_id
        == second.evidence_id
    )

    assert (
        first.source_delta_id
        == second.source_delta_id
    )

    assert (
        first.source_changes
        == second.source_changes
    )
