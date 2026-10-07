from __future__ import annotations

import base64
import json

import pytest

from horizon.claims.evidence_backed import (
    EvidenceBackedClaim,
)
from horizon.claims.epistemic import (
    EpistemicAssessment,
)
from horizon.investigation.evidence_records import (
    InvestigationEvidenceRecordError,
    canonical_search_observation_evidence_record,
    canonical_search_observation_evidence_records,
)
from horizon.investigation.execution import (
    InvestigationSearchObservation,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
)
from horizon.repository.git_search import (
    GitTextMatch,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
)


def _match(
    *,
    evidence_id: str,
    path: str,
    line_number: int,
    line: bytes,
    byte_start: int,
) -> GitTextMatch:
    return GitTextMatch(
        path=path,
        object_id=(
            "a" * 40
        ),
        line_number=line_number,
        line=line,
        byte_start=byte_start,
        byte_end=(
            byte_start
            + len(
                b"class Flow"
            )
        ),
        evidence_id=evidence_id,
    )


def _observation(
    *,
    observation_id: str = (
        "investigation-search-observation:test"
    ),
) -> InvestigationSearchObservation:
    return InvestigationSearchObservation(
        query="class Flow",
        path_prefix="src/prefect",
        commit_sha=(
            "b" * 40
        ),
        repository_observation_id=(
            "git-commit-observation:test"
        ),
        source_search_id=(
            "git-text-search:test"
        ),
        matches=(
            _match(
                evidence_id="git-search-match:one",
                path="src/prefect/flows.py",
                line_number=145,
                line=b"class Flow(Generic[P, R]):",
                byte_start=1000,
            ),
            _match(
                evidence_id="git-search-match:two",
                path=(
                    "src/prefect/client/"
                    "schemas/objects.py"
                ),
                line_number=1129,
                line=(
                    b"class Flow(ObjectBaseModel):"
                ),
                byte_start=9000,
            ),
        ),
        observation_id=observation_id,
    )


def test_search_observation_becomes_canonical_evidence_record() -> None:
    observation = _observation()

    record = (
        canonical_search_observation_evidence_record(
            observation
        )
    )

    assert isinstance(
        record,
        CanonicalEvidenceRecord,
    )

    assert (
        record.evidence_id
        == observation.observation_id
    )

    assert (
        record.evidence_kind
        == "INVESTIGATION_SEARCH_OBSERVATION"
    )


def test_payload_preserves_exact_search_provenance() -> None:
    observation = _observation()

    record = (
        canonical_search_observation_evidence_record(
            observation
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert payload[
        "operation_kind"
    ] == "SEARCH_SOURCE"

    assert payload[
        "query"
    ] == "class Flow"

    assert payload[
        "path_prefix"
    ] == "src/prefect"

    assert payload[
        "commit_sha"
    ] == observation.commit_sha

    assert payload[
        "repository_observation_id"
    ] == observation.repository_observation_id

    assert payload[
        "source_search_id"
    ] == observation.source_search_id

    assert payload[
        "observation_id"
    ] == observation.observation_id


def test_payload_preserves_every_underlying_git_match_identity() -> None:
    observation = _observation()

    record = (
        canonical_search_observation_evidence_record(
            observation
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    assert [
        item[
            "evidence_id"
        ]
        for item
        in payload[
            "matches"
        ]
    ] == [
        "git-search-match:one",
        "git-search-match:two",
    ]


def test_payload_preserves_exact_line_bytes_losslessly() -> None:
    observation = InvestigationSearchObservation(
        query="needle",
        path_prefix="src",
        commit_sha="c" * 40,
        repository_observation_id=(
            "git-commit-observation:bytes"
        ),
        source_search_id=(
            "git-text-search:bytes"
        ),
        matches=(
            GitTextMatch(
                path="src/example.py",
                object_id="d" * 40,
                line_number=3,
                line=b"\xffneedle\x00",
                byte_start=10,
                byte_end=16,
                evidence_id=(
                    "git-search-match:bytes"
                ),
            ),
        ),
        observation_id=(
            "investigation-search-observation:bytes"
        ),
    )

    record = (
        canonical_search_observation_evidence_record(
            observation
        )
    )

    payload = json.loads(
        record.canonical_payload
    )

    encoded = payload[
        "matches"
    ][
        0
    ][
        "line_base64"
    ]

    assert (
        base64.b64decode(
            encoded
        )
        == b"\xffneedle\x00"
    )


def test_record_is_deterministic() -> None:
    observation = _observation()

    first = (
        canonical_search_observation_evidence_record(
            observation
        )
    )

    second = (
        canonical_search_observation_evidence_record(
            observation
        )
    )

    assert first == second


def test_match_order_is_preserved_exactly() -> None:
    observation = _observation()

    payload = json.loads(
        canonical_search_observation_evidence_record(
            observation
        ).canonical_payload
    )

    assert [
        item[
            "path"
        ]
        for item
        in payload[
            "matches"
        ]
    ] == [
        "src/prefect/flows.py",
        (
            "src/prefect/client/"
            "schemas/objects.py"
        ),
    ]


def test_duplicate_match_evidence_ids_are_rejected() -> None:
    duplicate = GitTextMatch(
        path="src/prefect/other.py",
        object_id="e" * 40,
        line_number=1,
        line=b"class Flow:",
        byte_start=0,
        byte_end=10,
        evidence_id="git-search-match:one",
    )

    original = _observation()

    observation = (
        InvestigationSearchObservation(
            query=original.query,
            path_prefix=(
                original.path_prefix
            ),
            commit_sha=(
                original.commit_sha
            ),
            repository_observation_id=(
                original.repository_observation_id
            ),
            source_search_id=(
                original.source_search_id
            ),
            matches=(
                original.matches[
                    0
                ],
                duplicate,
            ),
            observation_id=(
                original.observation_id
            ),
        )
    )

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="duplicate",
    ):
        canonical_search_observation_evidence_record(
            observation
        )


def test_wrong_input_type_is_rejected() -> None:
    with pytest.raises(
        InvestigationEvidenceRecordError,
    ):
        canonical_search_observation_evidence_record(
            object()
        )


def test_multiple_observations_become_multiple_records() -> None:
    first = _observation(
        observation_id=(
            "investigation-search-observation:first"
        ),
    )

    second = _observation(
        observation_id=(
            "investigation-search-observation:second"
        ),
    )

    records = (
        canonical_search_observation_evidence_records(
            (
                first,
                second,
            )
        )
    )

    assert len(
        records
    ) == 2

    assert [
        record.evidence_id
        for record
        in records
    ] == [
        first.observation_id,
        second.observation_id,
    ]


def test_duplicate_observation_identity_is_rejected() -> None:
    observation = _observation()

    with pytest.raises(
        InvestigationEvidenceRecordError,
        match="duplicate",
    ):
        canonical_search_observation_evidence_records(
            (
                observation,
                observation,
            )
        )


def test_evidence_record_is_not_horizon_truth() -> None:
    record = (
        canonical_search_observation_evidence_record(
            _observation()
        )
    )

    assert not isinstance(
        record,
        EvidenceBackedClaim,
    )

    assert not isinstance(
        record,
        EpistemicAssessment,
    )

    assert not isinstance(
        record,
        WorldModelAssertion,
    )
