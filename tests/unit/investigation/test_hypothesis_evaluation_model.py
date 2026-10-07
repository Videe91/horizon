from __future__ import annotations

import base64
import json
import math

from dataclasses import replace
from decimal import Decimal

import pytest

from horizon.investigation.hypothesis_evaluation_model import (
    HypothesisEvaluationModelError,
    canonical_hypothesis_evaluation_model_input,
    make_hypothesis_evaluation_model_invocation,
    make_hypothesis_evaluation_request_view,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)


def generic_record(
    identity: str = "evidence:generic",
    *,
    payload: str = '{"value":"generic"}',
) -> CanonicalEvidenceRecord:
    return CanonicalEvidenceRecord(
        evidence_id=identity,
        evidence_kind=(
            "GIT_BLOB_EVIDENCE"
        ),
        canonical_payload=payload,
    )


def source_record(
    identity: str = (
        "investigation-source-observation:source"
    ),
    *,
    first: bytes = b"line one",
    second: bytes = b"line two",
) -> CanonicalEvidenceRecord:
    payload = {
        "commit_sha": (
            "a" * 40
        ),
        "end_line": 11,
        "line_count": 2,
        "lines": [
            {
                "content_base64": (
                    base64.b64encode(
                        first
                    ).decode(
                        "ascii"
                    )
                ),
                "line_number": 10,
            },
            {
                "content_base64": (
                    base64.b64encode(
                        second
                    ).decode(
                        "ascii"
                    )
                ),
                "line_number": 11,
            },
        ],
        "observation_id": identity,
        "operation_kind": "READ_SOURCE",
        "path": "src/acme.py",
        "repository_observation_id": (
            "git-observation:test"
        ),
        "source_blob_evidence_id": (
            "git-blob-evidence:test"
        ),
        "source_object_id": (
            "b" * 40
        ),
        "start_line": 10,
    }

    return CanonicalEvidenceRecord(
        evidence_id=identity,
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload=json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=True,
        ),
    )


def request(
    *,
    source: CanonicalEvidenceRecord | None = None,
) -> InvestigationRequest:
    if source is None:
        source = source_record()

    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary "
            "software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(
            generic_record(),
            source,
        ),
        request_id=(
            "semantic-gap-followup-investigation-request:test"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
        ),
        semantic_gap_section=(
            "WHAT_IT_IS"
        ),
    )


def hypothesis(
    value: InvestigationRequest,
):
    return parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_HYPOTHESIS",
            "question_id": (
                value.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "hypothesis": (
                "The repository primarily implements "
                "Python workflow orchestration."
            ),
            "test_questions": [
                (
                    "Does declared repository purpose "
                    "support this interpretation?"
                ),
                (
                    "Do the principal abstractions "
                    "support this interpretation?"
                ),
            ],
        },
    )


def invocation(
    value: InvestigationRequest | None = None,
):
    if value is None:
        value = request()

    return (
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=hypothesis(
                value
            ),
            instruction=(
                b"Evaluate only the supplied hypothesis "
                b"against the supplied evidence."
            ),
            temperature=None,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )
    )


def test_view_preserves_semantic_and_hypothesis_identity() -> None:
    value = request()
    proposed = hypothesis(
        value
    )

    view = (
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=proposed,
        )
    )

    assert (
        view.request_id
        == value.request_id
    )

    assert (
        view.question_id
        == value.question_id
    )

    assert (
        view.question
        == value.question
    )

    assert (
        view.semantic_gap_id
        == value.semantic_gap_id
    )

    assert (
        view.semantic_gap_section
        == "WHAT_IT_IS"
    )

    assert (
        view.source_proposal_id
        == proposed.proposal_id
    )

    assert (
        view.hypothesis
        == proposed.hypothesis
    )

    assert (
        view.test_questions
        == proposed.test_questions
    )

    assert view.view_id.startswith(
        "hypothesis-evaluation-request-view:"
    )


def test_all_request_evidence_remains_visible_by_identity() -> None:
    value = request()

    view = (
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=hypothesis(
                value
            ),
        )
    )

    assert tuple(
        item.evidence_id
        for item
        in view.evidence_records
    ) == tuple(
        item.evidence_id
        for item
        in value.evidence_records
    )


def test_non_source_evidence_is_metadata_only() -> None:
    value = request()

    view = (
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=hypothesis(
                value
            ),
        )
    )

    generic = view.evidence_records[0]

    assert (
        generic.evidence_kind
        == "GIT_BLOB_EVIDENCE"
    )

    assert (
        generic.source_excerpt
        is None
    )

    assert generic.canonical_payload_bytes > 0

    assert (
        generic.canonical_payload_sha256
        .startswith(
            "sha256:"
        )
    )


def test_source_read_exposes_exact_model_readable_lines() -> None:
    value = request()

    view = (
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=hypothesis(
                value
            ),
        )
    )

    source = view.evidence_records[1]

    assert (
        source.evidence_kind
        == "INVESTIGATION_SOURCE_OBSERVATION"
    )

    assert source.source_excerpt is not None

    assert (
        source.source_excerpt.path
        == "src/acme.py"
    )

    assert (
        source.source_excerpt.start_line
        == 10
    )

    assert (
        source.source_excerpt.end_line
        == 11
    )

    assert tuple(
        (
            item.line_number,
            item.text,
        )
        for item
        in source.source_excerpt.lines
    ) == (
        (
            10,
            "line one",
        ),
        (
            11,
            "line two",
        ),
    )


def test_model_view_does_not_include_full_canonical_payload() -> None:
    value = request()

    view = (
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=hypothesis(
                value
            ),
        )
    )

    assert all(
        not hasattr(
            item,
            "canonical_payload",
        )
        for item
        in view.evidence_records
    )


def test_invalid_source_payload_json_is_rejected() -> None:
    bad = CanonicalEvidenceRecord(
        evidence_id=(
            "investigation-source-observation:bad"
        ),
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload="{",
    )

    value = request(
        source=bad
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="JSON",
    ):
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=hypothesis(
                value
            ),
        )


def test_source_observation_identity_must_match_record_identity() -> None:
    value = request()

    raw = json.loads(
        value.evidence_records[
            1
        ].canonical_payload
    )

    raw[
        "observation_id"
    ] = (
        "investigation-source-observation:foreign"
    )

    bad = CanonicalEvidenceRecord(
        evidence_id=(
            value.evidence_records[
                1
            ].evidence_id
        ),
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload=json.dumps(
            raw,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )

    changed = replace(
        value,
        evidence_records=(
            value.evidence_records[0],
            bad,
        ),
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="identity",
    ):
        make_hypothesis_evaluation_request_view(
            request=changed,
            source_proposal=hypothesis(
                changed
            ),
        )


def test_source_read_must_be_read_source_operation() -> None:
    value = request()

    raw = json.loads(
        value.evidence_records[
            1
        ].canonical_payload
    )

    raw[
        "operation_kind"
    ] = "SEARCH_SOURCE"

    bad = CanonicalEvidenceRecord(
        evidence_id=(
            value.evidence_records[
                1
            ].evidence_id
        ),
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload=json.dumps(
            raw,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )

    changed = replace(
        value,
        evidence_records=(
            value.evidence_records[0],
            bad,
        ),
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="READ_SOURCE",
    ):
        make_hypothesis_evaluation_request_view(
            request=changed,
            source_proposal=hypothesis(
                changed
            ),
        )


def test_source_line_coordinates_must_be_contiguous() -> None:
    value = request()

    raw = json.loads(
        value.evidence_records[
            1
        ].canonical_payload
    )

    raw[
        "lines"
    ][1][
        "line_number"
    ] = 12

    bad = CanonicalEvidenceRecord(
        evidence_id=(
            value.evidence_records[
                1
            ].evidence_id
        ),
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload=json.dumps(
            raw,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )

    changed = replace(
        value,
        evidence_records=(
            value.evidence_records[0],
            bad,
        ),
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="coordinates",
    ):
        make_hypothesis_evaluation_request_view(
            request=changed,
            source_proposal=hypothesis(
                changed
            ),
        )


def test_invalid_base64_is_rejected() -> None:
    value = request()

    raw = json.loads(
        value.evidence_records[
            1
        ].canonical_payload
    )

    raw[
        "lines"
    ][0][
        "content_base64"
    ] = "%%%"

    bad = CanonicalEvidenceRecord(
        evidence_id=(
            value.evidence_records[
                1
            ].evidence_id
        ),
        evidence_kind=(
            "INVESTIGATION_SOURCE_OBSERVATION"
        ),
        canonical_payload=json.dumps(
            raw,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )

    changed = replace(
        value,
        evidence_records=(
            value.evidence_records[0],
            bad,
        ),
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="base64",
    ):
        make_hypothesis_evaluation_request_view(
            request=changed,
            source_proposal=hypothesis(
                changed
            ),
        )


def test_non_utf8_source_is_rejected_fail_closed() -> None:
    value = request(
        source=source_record(
            first=b"\xff",
        )
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="UTF-8",
    ):
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=hypothesis(
                value
            ),
        )


def test_only_semantic_gap_request_is_accepted() -> None:
    value = request()

    changed = replace(
        value,
        origin=(
            "WORLD_MODEL_CONFLICT"
        ),
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="semantic-gap",
    ):
        make_hypothesis_evaluation_request_view(
            request=changed,
            source_proposal=hypothesis(
                changed
            ),
        )


def test_request_relationship_must_be_absent() -> None:
    value = request()

    proposed = hypothesis(
        value
    )

    changed = replace(
        value,
        relationship_id=(
            "world-model-relationship:test"
        ),
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="relationship",
    ):
        make_hypothesis_evaluation_request_view(
            request=changed,
            source_proposal=proposed,
        )


def test_only_propose_hypothesis_can_be_evaluated() -> None:
    value = request()

    proposed = parse_investigation_proposal(
        value,
        {
            "type": "PROPOSE_INVESTIGATION",
            "question_id": (
                value.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": [
                "What should be inspected?"
            ],
        },
    )

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="PROPOSE_HYPOTHESIS",
    ):
        make_hypothesis_evaluation_request_view(
            request=value,
            source_proposal=proposed,
        )


def test_invocation_retains_full_internal_authority() -> None:
    value = request()
    proposed = hypothesis(
        value
    )

    sealed = (
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=proposed,
            instruction=b"Evaluate.",
            temperature=None,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )
    )

    assert (
        sealed.request
        == value
    )

    assert (
        sealed.source_proposal
        == proposed
    )

    assert (
        sealed.request.evidence_records[
            1
        ].canonical_payload
        == value.evidence_records[
            1
        ].canonical_payload
    )


def test_model_input_uses_compact_request_view() -> None:
    sealed = invocation()

    payload = (
        canonical_hypothesis_evaluation_model_input(
            sealed
        )
    )

    assert (
        payload[
            "request"
        ][
            "request_id"
        ]
        == sealed.request.request_id
    )

    assert (
        payload[
            "request"
        ][
            "source_proposal_id"
        ]
        == sealed.source_proposal.proposal_id
    )

    assert (
        payload[
            "request"
        ][
            "hypothesis"
        ]
        == sealed.source_proposal.hypothesis
    )

    for item in payload[
        "request"
    ][
        "evidence_records"
    ]:
        assert (
            "canonical_payload"
            not in item
        )


def test_invocation_is_content_addressed() -> None:
    first = invocation()
    second = invocation()

    assert (
        first.invocation_id
        == second.invocation_id
    )

    assert (
        first.canonical_input_hash
        == second.canonical_input_hash
    )

    assert first.invocation_id.startswith(
        "hypothesis-evaluation-model-invocation:"
    )


def test_source_content_change_changes_view_and_invocation_identity() -> None:
    first_request = request()

    second_request = request(
        source=source_record(
            second=b"changed",
        )
    )

    first = invocation(
        first_request
    )

    second = invocation(
        second_request
    )

    assert (
        first.request_view.view_id
        != second.request_view.view_id
    )

    assert (
        first.canonical_input_hash
        != second.canonical_input_hash
    )

    assert (
        first.invocation_id
        != second.invocation_id
    )


def test_instruction_change_changes_invocation_identity() -> None:
    value = request()
    proposed = hypothesis(
        value
    )

    first = (
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=proposed,
            instruction=b"Evaluate A.",
            temperature=None,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )
    )

    second = (
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=proposed,
            instruction=b"Evaluate B.",
            temperature=None,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )
    )

    assert (
        first.invocation_id
        != second.invocation_id
    )


@pytest.mark.parametrize(
    "instruction",
    [
        b"",
        b"   ",
    ],
)
def test_instruction_must_be_nonempty(
    instruction: bytes,
) -> None:
    value = request()

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="instruction",
    ):
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=hypothesis(
                value
            ),
            instruction=instruction,
            temperature=None,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )


@pytest.mark.parametrize(
    "temperature",
    [
        math.nan,
        math.inf,
        -math.inf,
        -0.1,
        2.1,
    ],
)
def test_temperature_must_be_none_or_finite_zero_to_two(
    temperature: float,
) -> None:
    value = request()

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="temperature",
    ):
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=hypothesis(
                value
            ),
            instruction=b"Evaluate.",
            temperature=temperature,
            cost_cap_usd=Decimal(
                "0.200000"
            ),
        )


@pytest.mark.parametrize(
    "cost",
    [
        Decimal("0"),
        Decimal("-0.1"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_cost_cap_must_be_finite_positive(
    cost: Decimal,
) -> None:
    value = request()

    with pytest.raises(
        HypothesisEvaluationModelError,
        match="cost cap",
    ):
        make_hypothesis_evaluation_model_invocation(
            request=value,
            source_proposal=hypothesis(
                value
            ),
            instruction=b"Evaluate.",
            temperature=None,
            cost_cap_usd=cost,
        )


def test_schema_hash_is_bound_into_invocation() -> None:
    sealed = invocation()

    assert (
        sealed.schema_hash
        .startswith(
            "sha256:"
        )
    )

    payload = (
        canonical_hypothesis_evaluation_model_input(
            sealed
        )
    )

    assert (
        payload[
            "schema_hash"
        ]
        == sealed.schema_hash
    )


def test_canonical_model_input_contains_no_authoritative_output_fields() -> None:
    payload = (
        canonical_hypothesis_evaluation_model_input(
            invocation()
        )
    )

    encoded = json.dumps(
        payload,
        sort_keys=True,
    )

    assert (
        "claim_id"
        not in encoded
    )

    assert (
        "assessment_id"
        not in encoded
    )

    assert (
        "world_model_assertion_id"
        not in encoded
    )


def test_compact_view_does_not_scale_with_hidden_non_source_body() -> None:
    small = request()

    large = replace(
        small,
        evidence_records=(
            generic_record(
                payload=(
                    "x" * 500_000
                )
            ),
            small.evidence_records[1],
        ),
        request_id=(
            "semantic-gap-followup-investigation-request:large"
        ),
    )

    small_view = (
        make_hypothesis_evaluation_request_view(
            request=small,
            source_proposal=hypothesis(
                small
            ),
        )
    )

    large_view = (
        make_hypothesis_evaluation_request_view(
            request=large,
            source_proposal=hypothesis(
                large
            ),
        )
    )

    small_json = json.dumps(
        canonical_hypothesis_evaluation_model_input(
            make_hypothesis_evaluation_model_invocation(
                request=small,
                source_proposal=hypothesis(
                    small
                ),
                instruction=b"Evaluate.",
                temperature=None,
                cost_cap_usd=Decimal(
                    "0.200000"
                ),
            )
        ),
        sort_keys=True,
    )

    large_json = json.dumps(
        canonical_hypothesis_evaluation_model_input(
            make_hypothesis_evaluation_model_invocation(
                request=large,
                source_proposal=hypothesis(
                    large
                ),
                instruction=b"Evaluate.",
                temperature=None,
                cost_cap_usd=Decimal(
                    "0.200000"
                ),
            )
        ),
        sort_keys=True,
    )

    assert (
        large_view.evidence_records[
            0
        ].canonical_payload_bytes
        == 500_000
    )

    assert (
        len(
            large_json
        )
        - len(
            small_json
        )
        < 500
    )

    assert (
        large_view.view_id
        != small_view.view_id
    )
