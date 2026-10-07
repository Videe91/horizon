from __future__ import annotations

import pytest

from horizon.investigation.plan import (
    InspectSymbolOperation,
    ReadSourceOperation,
    ResolveCallOperation,
    SearchSourceOperation,
)
from horizon.investigation.typed_planner import (
    SemanticGapTypedPlannerError,
    parse_semantic_gap_typed_planner_output,
    semantic_gap_typed_planner_schema,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)


def request() -> InvestigationRequest:
    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        question=(
            "What is this repository's primary software purpose?"
        ),
        relationship_id=None,
        relationship_kind=None,
        relationship_reason=None,
        assertions=(),
        claims=(),
        assessments=(),
        evidence_reference_ids=(),
        evidence_records=(),
        request_id=(
            "investigation-request:test"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:test"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )


def proposal():
    value = request()

    return parse_investigation_proposal(
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
                (
                    "Which source locations provide "
                    "evidence for repository purpose?"
                ),
                (
                    "Which execution symbol best exposes "
                    "the repository's primary runtime behavior?"
                ),
            ],
        },
    )


def search_binding() -> dict[str, object]:
    return {
        "investigation_question": (
            "Which source locations provide "
            "evidence for repository purpose?"
        ),
        "step_key": "search-purpose",
        "purpose": (
            "Locate source relevant to repository purpose."
        ),
        "operation": {
            "type": "SEARCH_SOURCE",
            "query": "flow",
            "path_prefix": "src/acme",
        },
        "depends_on_keys": [],
        "expected_information": (
            "Frozen source locations containing the search term."
        ),
        "max_seconds": 20,
    }


def symbol_binding() -> dict[str, object]:
    return {
        "investigation_question": (
            "Which execution symbol best exposes "
            "the repository's primary runtime behavior?"
        ),
        "step_key": "inspect-runtime",
        "purpose": (
            "Inspect the primary runtime symbol."
        ),
        "operation": {
            "type": "INSPECT_SYMBOL",
            "path": "src/acme/runtime.py",
            "symbol": "run",
        },
        "depends_on_keys": [],
        "expected_information": (
            "Observed structural evidence for the runtime symbol."
        ),
        "max_seconds": 20,
    }


def raw_output() -> dict[str, object]:
    proposed = proposal()

    return {
        "proposal_id": (
            proposed.proposal_id
        ),
        "question_id": (
            proposed.question_id
        ),
        "bindings": [
            search_binding(),
            symbol_binding(),
        ],
    }


def test_strict_typed_planner_parses_exact_bound_output() -> None:
    value = request()
    proposed = proposal()

    parsed = (
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw_output(),
        )
    )

    assert (
        parsed.proposal_id
        == proposed.proposal_id
    )

    assert (
        parsed.question_id
        == value.question_id
    )

    assert len(
        parsed.bindings
    ) == 2

    assert isinstance(
        parsed.bindings[
            0
        ].draft.operation,
        SearchSourceOperation,
    )

    assert isinstance(
        parsed.bindings[
            1
        ].draft.operation,
        InspectSymbolOperation,
    )

    assert parsed.planner_output_id.startswith(
        "semantic-gap-typed-planner-output:"
    )


def test_all_currently_executable_operation_types_parse() -> None:
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
                "q-search",
                "q-read",
                "q-symbol",
                "q-call",
            ],
        },
    )

    raw = {
        "proposal_id": (
            proposed.proposal_id
        ),
        "question_id": (
            proposed.question_id
        ),
        "bindings": [
            {
                "investigation_question": "q-search",
                "step_key": "search",
                "purpose": "search",
                "operation": {
                    "type": "SEARCH_SOURCE",
                    "query": "run",
                    "path_prefix": None,
                },
                "depends_on_keys": [],
                "expected_information": "locations",
                "max_seconds": 10,
            },
            {
                "investigation_question": "q-read",
                "step_key": "read",
                "purpose": "read",
                "operation": {
                    "type": "READ_SOURCE",
                    "path": "src/acme/runtime.py",
                    "start_line": 1,
                    "end_line": 20,
                },
                "depends_on_keys": [],
                "expected_information": "source",
                "max_seconds": 10,
            },
            {
                "investigation_question": "q-symbol",
                "step_key": "symbol",
                "purpose": "symbol",
                "operation": {
                    "type": "INSPECT_SYMBOL",
                    "path": "src/acme/runtime.py",
                    "symbol": "run",
                },
                "depends_on_keys": [],
                "expected_information": "structure",
                "max_seconds": 10,
            },
            {
                "investigation_question": "q-call",
                "step_key": "call",
                "purpose": "call",
                "operation": {
                    "type": "RESOLVE_CALL",
                    "path": "src/acme/runtime.py",
                    "line": 10,
                    "character": 4,
                },
                "depends_on_keys": [],
                "expected_information": "callee",
                "max_seconds": 10,
            },
        ],
    }

    parsed = (
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )
    )

    operation_types = tuple(
        type(
            binding.draft.operation
        )
        for binding
        in parsed.bindings
    )

    assert operation_types == (
        SearchSourceOperation,
        ReadSourceOperation,
        InspectSymbolOperation,
        ResolveCallOperation,
    )


def test_unimplemented_operation_is_rejected() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "bindings"
    ][0][
        "operation"
    ] = {
        "type": "RESOLVE_TYPE",
        "path": "src/acme/runtime.py",
        "line": 10,
        "character": 2,
    }

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="not executable",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_arbitrary_command_escape_hatch_is_rejected() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "bindings"
    ][0][
        "operation"
    ] = {
        "type": "SEARCH_SOURCE",
        "query": "flow",
        "path_prefix": "src/acme",
        "command": "rm -rf /",
    }

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="fields",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_horizon_owned_step_and_plan_ids_are_rejected() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "bindings"
    ][0][
        "step_id"
    ] = "investigation-step:model-authored"

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="fields",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_model_cannot_control_plan_budgets() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "max_steps"
    ] = 100

    raw[
        "max_total_seconds"
    ] = 9999

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="fields",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_proposal_identity_must_match_exactly() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "proposal_id"
    ] = "investigation-proposal:invented"

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="proposal",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_question_identity_must_match_exactly() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "question_id"
    ] = (
        "repository-semantic-gap-question:invented"
    )

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="question",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_binding_must_reference_exact_proposed_investigation_question() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "bindings"
    ][0][
        "investigation_question"
    ] = "A question the model never proposed."

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="proposed investigation question",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_every_proposed_question_requires_binding_coverage() -> None:
    value = request()
    proposed = proposal()

    raw = raw_output()

    raw[
        "bindings"
    ] = [
        search_binding()
    ]

    with pytest.raises(
        SemanticGapTypedPlannerError,
        match="coverage",
    ):
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw,
        )


def test_output_is_deterministic_under_mapping_key_order() -> None:
    value = request()
    proposed = proposal()

    first = (
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw_output(),
        )
    )

    raw = raw_output()

    second_raw = {
        "bindings": raw[
            "bindings"
        ],
        "question_id": raw[
            "question_id"
        ],
        "proposal_id": raw[
            "proposal_id"
        ],
    }

    second = (
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=second_raw,
        )
    )

    assert first == second


def test_schema_is_closed_and_exposes_only_currently_executable_operations() -> None:
    schema = (
        semantic_gap_typed_planner_schema()
    )

    assert (
        schema[
            "additionalProperties"
        ]
        is False
    )

    binding = (
        schema[
            "properties"
        ][
            "bindings"
        ][
            "items"
        ]
    )

    assert (
        binding[
            "additionalProperties"
        ]
        is False
    )

    alternatives = (
        binding[
            "properties"
        ][
            "operation"
        ][
            "oneOf"
        ]
    )

    operation_types = {
        alternative[
            "properties"
        ][
            "type"
        ][
            "const"
        ]
        for alternative
        in alternatives
    }

    assert operation_types == {
        "SEARCH_SOURCE",
        "READ_SOURCE",
        "INSPECT_SYMBOL",
        "RESOLVE_CALL",
    }

    for alternative in alternatives:
        assert (
            alternative[
                "additionalProperties"
            ]
            is False
        )

        assert "command" not in (
            alternative[
                "properties"
            ]
        )

        assert "shell" not in (
            alternative[
                "properties"
            ]
        )

        assert "python" not in (
            alternative[
                "properties"
            ]
        )


def test_typed_planner_output_is_not_world_model_truth() -> None:
    from horizon.claims.evidence_backed import (
        EvidenceBackedClaim,
    )
    from horizon.claims.epistemic import (
        EpistemicAssessment,
    )
    from horizon.world_model.assertion import (
        WorldModelAssertion,
    )

    value = request()
    proposed = proposal()

    parsed = (
        parse_semantic_gap_typed_planner_output(
            request=value,
            proposal=proposed,
            raw=raw_output(),
        )
    )

    assert not isinstance(
        parsed,
        EvidenceBackedClaim,
    )

    assert not isinstance(
        parsed,
        EpistemicAssessment,
    )

    assert not isinstance(
        parsed,
        WorldModelAssertion,
    )
