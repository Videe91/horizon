"""Evidence for controlled source-intervention comparisons.

This module does not infer architectural causality.

It preserves a controlled comparison between two runtime observations:

- baseline source observation
- intervention source observation
- exact observed Git tree delta
- same recorded experiment identity
- same recorded command
- same recorded explicit configuration
- exact outcome event from each runtime observation
- whether the compared outcome payload changed

The resulting evidence can later support a claim or epistemic decision.
It is not itself a claim that the intervention is universally causal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from horizon.repository.git_observation import (
    GitCommitObservation,
    GitTreeEntry,
)
from horizon.runtime.observation import (
    RuntimeEvidence,
    RuntimeEventEvidence,
)


class CausalExperimentEvidenceError(
    RuntimeError
):
    """A controlled comparison could not be represented faithfully."""


@dataclass(
    frozen=True,
    slots=True,
)
class SourceInterventionChangeEvidence:
    path: str

    baseline_mode: str | None
    baseline_object_type: str | None
    baseline_object_id: str | None

    intervention_mode: str | None
    intervention_object_type: str | None
    intervention_object_id: str | None

    evidence_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class SourceInterventionComparisonEvidence:
    experiment_id: str
    intervention_id: str

    baseline_runtime_evidence_id: str
    intervention_runtime_evidence_id: str

    baseline_source_observation_id: str
    intervention_source_observation_id: str

    baseline_source_commit: str
    intervention_source_commit: str

    source_changes: tuple[
        SourceInterventionChangeEvidence,
        ...,
    ]

    source_delta_id: str

    baseline_outcome_event_evidence_id: str
    intervention_outcome_event_evidence_id: str

    outcome_kind: str

    baseline_outcome_payload_json: str
    intervention_outcome_payload_json: str

    outcome_changed: bool

    evidence_id: str


def _canonical_identity(
    prefix: str,
    payload: dict[
        str,
        Any,
    ],
) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    return (
        prefix
        + hashlib.sha256(
            canonical
        ).hexdigest()
    )


def _entry_payload(
    entry: GitTreeEntry | None,
) -> dict[
    str,
    str | None,
]:
    if entry is None:
        return {
            "mode": None,
            "object_type": None,
            "object_id": None,
        }

    return {
        "mode": entry.mode,
        "object_type": (
            entry.object_type
        ),
        "object_id": (
            entry.object_id
        ),
    }


def _change_evidence(
    path: str,
    baseline: GitTreeEntry | None,
    intervention: GitTreeEntry | None,
) -> SourceInterventionChangeEvidence:
    baseline_payload = (
        _entry_payload(
            baseline
        )
    )

    intervention_payload = (
        _entry_payload(
            intervention
        )
    )

    evidence_id = (
        _canonical_identity(
            "source-intervention-change:",
            {
                "path": path,
                "baseline": (
                    baseline_payload
                ),
                "intervention": (
                    intervention_payload
                ),
            },
        )
    )

    return SourceInterventionChangeEvidence(
        path=path,
        baseline_mode=(
            baseline_payload[
                "mode"
            ]
        ),
        baseline_object_type=(
            baseline_payload[
                "object_type"
            ]
        ),
        baseline_object_id=(
            baseline_payload[
                "object_id"
            ]
        ),
        intervention_mode=(
            intervention_payload[
                "mode"
            ]
        ),
        intervention_object_type=(
            intervention_payload[
                "object_type"
            ]
        ),
        intervention_object_id=(
            intervention_payload[
                "object_id"
            ]
        ),
        evidence_id=(
            evidence_id
        ),
    )


def _source_changes(
    baseline: GitCommitObservation,
    intervention: GitCommitObservation,
) -> tuple[
    SourceInterventionChangeEvidence,
    ...,
]:
    baseline_by_path = {
        entry.path: entry
        for entry in baseline.entries
    }

    intervention_by_path = {
        entry.path: entry
        for entry
        in intervention.entries
    }

    paths = sorted(
        set(
            baseline_by_path
        )
        | set(
            intervention_by_path
        )
    )

    changes: list[
        SourceInterventionChangeEvidence
    ] = []

    for path in paths:
        baseline_entry = (
            baseline_by_path.get(
                path
            )
        )

        intervention_entry = (
            intervention_by_path.get(
                path
            )
        )

        if (
            baseline_entry
            == intervention_entry
        ):
            continue

        changes.append(
            _change_evidence(
                path,
                baseline_entry,
                intervention_entry,
            )
        )

    return tuple(
        changes
    )


def _validate_source_link(
    *,
    label: str,
    runtime: RuntimeEvidence,
    source: GitCommitObservation,
) -> None:
    if (
        runtime.source_observation_id
        != source.observation_id
        or runtime.source_commit
        != source.commit_sha
    ):
        raise CausalExperimentEvidenceError(
            f"{label} source observation "
            "does not match runtime evidence"
        )


def _validate_experiment(
    baseline: RuntimeEvidence,
    intervention: RuntimeEvidence,
) -> tuple[
    str,
    str,
]:
    if (
        baseline.experiment_id
        is None
        or intervention.experiment_id
        is None
        or baseline.experiment_id
        != intervention.experiment_id
    ):
        raise CausalExperimentEvidenceError(
            "baseline and intervention "
            "must share one experiment identity"
        )

    if (
        baseline.intervention_id
        is not None
    ):
        raise CausalExperimentEvidenceError(
            "baseline runtime evidence "
            "must not carry an intervention identity"
        )

    if (
        intervention.intervention_id
        is None
    ):
        raise CausalExperimentEvidenceError(
            "intervention runtime evidence "
            "must carry an intervention identity"
        )

    if (
        baseline.command
        != intervention.command
    ):
        raise CausalExperimentEvidenceError(
            "baseline and intervention "
            "command must match"
        )

    if (
        baseline.configuration
        != intervention.configuration
    ):
        raise CausalExperimentEvidenceError(
            "baseline and intervention "
            "configuration must match"
        )

    return (
        baseline.experiment_id,
        intervention.intervention_id,
    )


def _validate_outcome(
    *,
    label: str,
    runtime: RuntimeEvidence,
    outcome: RuntimeEventEvidence,
) -> None:
    if outcome not in runtime.events:
        raise CausalExperimentEvidenceError(
            f"{label} outcome event "
            "does not belong to its runtime observation"
        )


def _source_delta_identity(
    *,
    baseline: GitCommitObservation,
    intervention: GitCommitObservation,
    changes: tuple[
        SourceInterventionChangeEvidence,
        ...,
    ],
) -> str:
    return _canonical_identity(
        "source-intervention-delta:",
        {
            "baseline_source_observation_id": (
                baseline.observation_id
            ),
            "intervention_source_observation_id": (
                intervention.observation_id
            ),
            "baseline_source_commit": (
                baseline.commit_sha
            ),
            "intervention_source_commit": (
                intervention.commit_sha
            ),
            "changes": [
                change.evidence_id
                for change in changes
            ],
        },
    )


def compare_source_intervention(
    baseline: RuntimeEvidence,
    intervention: RuntimeEvidence,
    *,
    baseline_source: GitCommitObservation,
    intervention_source: GitCommitObservation,
    baseline_outcome: RuntimeEventEvidence,
    intervention_outcome: RuntimeEventEvidence,
) -> SourceInterventionComparisonEvidence:
    """Preserve one controlled source-intervention comparison."""

    _validate_source_link(
        label="baseline",
        runtime=baseline,
        source=baseline_source,
    )

    _validate_source_link(
        label="intervention",
        runtime=intervention,
        source=intervention_source,
    )

    (
        experiment_id,
        intervention_id,
    ) = _validate_experiment(
        baseline,
        intervention,
    )

    changes = _source_changes(
        baseline_source,
        intervention_source,
    )

    if not changes:
        raise CausalExperimentEvidenceError(
            "source intervention requires "
            "an actual observed source delta"
        )

    if (
        baseline_outcome.kind
        != intervention_outcome.kind
    ):
        raise CausalExperimentEvidenceError(
            "baseline and intervention "
            "outcome kind must match"
        )

    _validate_outcome(
        label="baseline",
        runtime=baseline,
        outcome=baseline_outcome,
    )

    _validate_outcome(
        label="intervention",
        runtime=intervention,
        outcome=intervention_outcome,
    )

    source_delta_id = (
        _source_delta_identity(
            baseline=baseline_source,
            intervention=(
                intervention_source
            ),
            changes=changes,
        )
    )

    outcome_changed = (
        baseline_outcome.payload_json
        != intervention_outcome.payload_json
    )

    evidence_id = (
        _canonical_identity(
            "source-intervention-comparison:",
            {
                "experiment_id": (
                    experiment_id
                ),
                "intervention_id": (
                    intervention_id
                ),
                "baseline_runtime_evidence_id": (
                    baseline.evidence_id
                ),
                "intervention_runtime_evidence_id": (
                    intervention.evidence_id
                ),
                "baseline_source_observation_id": (
                    baseline_source.observation_id
                ),
                "intervention_source_observation_id": (
                    intervention_source.observation_id
                ),
                "baseline_source_commit": (
                    baseline_source.commit_sha
                ),
                "intervention_source_commit": (
                    intervention_source.commit_sha
                ),
                "source_delta_id": (
                    source_delta_id
                ),
                "baseline_outcome_event_evidence_id": (
                    baseline_outcome.evidence_id
                ),
                "intervention_outcome_event_evidence_id": (
                    intervention_outcome.evidence_id
                ),
                "outcome_kind": (
                    baseline_outcome.kind
                ),
                "baseline_outcome_payload_json": (
                    baseline_outcome.payload_json
                ),
                "intervention_outcome_payload_json": (
                    intervention_outcome.payload_json
                ),
                "outcome_changed": (
                    outcome_changed
                ),
            },
        )
    )

    return SourceInterventionComparisonEvidence(
        experiment_id=(
            experiment_id
        ),
        intervention_id=(
            intervention_id
        ),
        baseline_runtime_evidence_id=(
            baseline.evidence_id
        ),
        intervention_runtime_evidence_id=(
            intervention.evidence_id
        ),
        baseline_source_observation_id=(
            baseline_source.observation_id
        ),
        intervention_source_observation_id=(
            intervention_source.observation_id
        ),
        baseline_source_commit=(
            baseline_source.commit_sha
        ),
        intervention_source_commit=(
            intervention_source.commit_sha
        ),
        source_changes=(
            changes
        ),
        source_delta_id=(
            source_delta_id
        ),
        baseline_outcome_event_evidence_id=(
            baseline_outcome.evidence_id
        ),
        intervention_outcome_event_evidence_id=(
            intervention_outcome.evidence_id
        ),
        outcome_kind=(
            baseline_outcome.kind
        ),
        baseline_outcome_payload_json=(
            baseline_outcome.payload_json
        ),
        intervention_outcome_payload_json=(
            intervention_outcome.payload_json
        ),
        outcome_changed=(
            outcome_changed
        ),
        evidence_id=(
            evidence_id
        ),
    )
