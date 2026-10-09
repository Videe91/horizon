from __future__ import annotations

import json

from decimal import Decimal
from types import SimpleNamespace

from horizon.investigation.providers.openai_responses import (
    OpenAIResponsesTypedPlannerModel,
    OpenAITypedPlannerTokenPricing,
)
from horizon.investigation.typed_planner_model import (
    make_semantic_gap_typed_planner_invocation,
)
from horizon.investigation.typed_planner_semantics import (
    semantic_gap_typed_planner_operation_semantics,
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
            "question_id": value.question_id,
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": [
                (
                    "Which frozen source locations "
                    "should Horizon inspect?"
                ),
            ],
        },
    )


def invocation():
    return (
        make_semantic_gap_typed_planner_invocation(
            request=request(),
            proposal=proposal(),
            instruction=(
                b"Obey the supplied operation semantics."
            ),
            temperature=None,
            max_plan_total_seconds=120,
            cost_cap_usd=Decimal(
                "0.100000"
            ),
        )
    )


def operation(
    kind: str,
):
    contract = (
        semantic_gap_typed_planner_operation_semantics()
    )

    return next(
        item
        for item
        in contract.operations
        if item.kind == kind
    )


def test_semantics_contract_is_content_addressed() -> None:
    first = (
        semantic_gap_typed_planner_operation_semantics()
    )

    second = (
        semantic_gap_typed_planner_operation_semantics()
    )

    assert first == second

    assert first.contract_id.startswith(
        "typed-planner-operation-semantics:"
    )


def test_semantics_contract_covers_exact_current_executable_vocabulary() -> None:
    contract = (
        semantic_gap_typed_planner_operation_semantics()
    )

    assert {
        item.kind
        for item
        in contract.operations
    } == {
        "SEARCH_SOURCE",
        "READ_SOURCE",
        "INSPECT_SYMBOL",
        "RESOLVE_CALL",
    }


def test_search_query_is_explicitly_literal_not_regex_or_glob() -> None:
    rules = dict(
        operation(
            "SEARCH_SOURCE"
        ).rules
    )

    assert rules[
        "QUERY_MODE"
    ] == (
        "EXACT_CASE_SENSITIVE_LITERAL_UTF8_SUBSTRING"
    )

    assert rules[
        "REGEX_SUPPORTED"
    ] == "NO"

    assert rules[
        "GLOB_SUPPORTED"
    ] == "NO"

    assert rules[
        "REGEX_METACHARACTERS"
    ] == (
        "HAVE_NO_SPECIAL_MEANING"
    )


def test_search_operates_on_frozen_observed_git_blob_bytes() -> None:
    rules = dict(
        operation(
            "SEARCH_SOURCE"
        ).rules
    )

    assert rules[
        "SOURCE"
    ] == (
        "FROZEN_OBSERVED_GIT_BLOB_BYTES"
    )

    assert rules[
        "PATH_PREFIX"
    ] == (
        "OPTIONAL_REPOSITORY_RELATIVE_LITERAL_PREFIX_FILTER"
    )


def test_read_source_coordinates_are_explicit() -> None:
    rules = dict(
        operation(
            "READ_SOURCE"
        ).rules
    )

    assert rules[
        "PATH"
    ] == (
        "EXACT_REPOSITORY_RELATIVE_OBSERVED_GIT_BLOB_PATH"
    )

    assert rules[
        "START_LINE"
    ] == "ONE_BASED_INCLUSIVE"

    assert rules[
        "END_LINE"
    ] == (
        "ONE_BASED_INCLUSIVE_OR_NULL"
    )

    assert rules[
        "NULL_END_LINE"
    ] == (
        "READ_THROUGH_OBSERVED_SOURCE_EOF"
    )

    assert rules[
        "INTEGER_END_LINE_REQUIREMENT"
    ] == (
        "MUST_NOT_EXCEED_OBSERVED_SOURCE_LENGTH"
    )


def test_symbol_lookup_semantics_are_explicit() -> None:
    rules = dict(
        operation(
            "INSPECT_SYMBOL"
        ).rules
    )

    assert rules[
        "PATH"
    ] == (
        "EXACT_REPOSITORY_RELATIVE_PYTHON_BLOB_PATH"
    )

    assert rules[
        "SYMBOL"
    ] == (
        "EXACT_DOTTED_LEXICAL_DEFINITION_NAME"
    )

    assert rules[
        "FUZZY_LOOKUP"
    ] == "NO"


def test_call_coordinates_are_explicit() -> None:
    rules = dict(
        operation(
            "RESOLVE_CALL"
        ).rules
    )

    assert rules[
        "LINE"
    ] == "ONE_BASED"

    assert rules[
        "CHARACTER"
    ] == (
        "ZERO_BASED_BYTE_OFFSET_WITHIN_SOURCE_LINE"
    )

    assert rules[
        "POSITION_REQUIREMENT"
    ] == (
        "MUST_FALL_INSIDE_OBSERVED_CALLEE_EXPRESSION"
    )


def test_planner_laws_forbid_inventing_unknown_addresses() -> None:
    contract = (
        semantic_gap_typed_planner_operation_semantics()
    )

    laws = dict(
        contract.planner_laws
    )

    assert laws[
        "OPERATION_ARGUMENT_BINDING"
    ] == (
        "STATIC_AT_PLAN_COMPILE_TIME"
    )

    assert laws[
        "DEPENDENCY_SEMANTICS"
    ] == (
        "ORDERING_ONLY_NO_OUTPUT_SUBSTITUTION"
    )

    assert laws[
        "UNKNOWN_PATH_SYMBOL_OR_COORDINATE"
    ] == (
        "DO_NOT_INVENT_SEARCH_THEN_REPLAN"
    )


def test_invocation_records_exact_operation_semantics_identity() -> None:
    value = invocation()

    contract = (
        semantic_gap_typed_planner_operation_semantics()
    )

    assert (
        value.operation_semantics
        == contract
    )

    assert (
        value.operation_semantics_id
        == contract.contract_id
    )


def test_semantics_identity_participates_in_canonical_model_input() -> None:
    value = invocation()

    assert (
        value.operation_semantics_id
        in json.dumps(
            {
                "id": (
                    value.operation_semantics_id
                ),
                "hash": (
                    value.canonical_input_hash
                ),
            },
            sort_keys=True,
        )
    )

    assert value.canonical_input_hash.startswith(
        "sha256:"
    )


class FakeResponses:
    def __init__(
        self,
        response,
    ) -> None:
        self.response = response
        self.calls = []

    def create(
        self,
        **kwargs,
    ):
        self.calls.append(
            kwargs
        )

        return self.response


class FakeClient:
    def __init__(
        self,
        response,
    ) -> None:
        self.responses = FakeResponses(
            response
        )


def test_openai_model_receives_operation_semantics_in_bounded_input() -> None:
    value = invocation()

    response = SimpleNamespace(
        status="completed",
        model="gpt-6-astra",
        _request_id="req-semantics-test",
        output_text=json.dumps(
            {
                "proposal_id": (
                    value.proposal.proposal_id
                ),
                "question_id": (
                    value.request.question_id
                ),
                "bindings": [
                    {
                        "investigation_question": (
                            value.proposal
                            .investigation_questions[0]
                        ),
                        "step_key": "search",
                        "purpose": "search",
                        "operation": {
                            "type": "SEARCH_SOURCE",
                            "query": "flow",
                            "path_prefix": "src",
                        },
                        "depends_on_keys": [],
                        "expected_information": (
                            "literal matches"
                        ),
                        "max_seconds": 10,
                    },
                ],
            }
        ),
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=50,
            input_tokens_details=(
                SimpleNamespace(
                    cached_tokens=0,
                    cache_write_tokens=0,
                )
            ),
        ),
    )

    client = FakeClient(
        response
    )

    model = OpenAIResponsesTypedPlannerModel(
        client=client,
        model_id="gpt-6-astra",
        reasoning_effort="high",
        max_output_tokens=4096,
        pricing=(
            OpenAITypedPlannerTokenPricing(
                input_per_million=Decimal(
                    "10"
                ),
                cached_input_per_million=Decimal(
                    "1"
                ),
                cache_write_per_million=Decimal(
                    "12.5"
                ),
                output_per_million=Decimal(
                    "50"
                ),
            )
        ),
    )

    model.invoke(
        value
    )

    payload = json.loads(
        client.responses.calls[
            0
        ][
            "input"
        ]
    )

    assert (
        payload[
            "operation_semantics_id"
        ]
        == value.operation_semantics_id
    )

    search = next(
        item
        for item
        in payload[
            "operation_semantics"
        ][
            "operations"
        ]
        if item[
            "kind"
        ] == "SEARCH_SOURCE"
    )

    rules = dict(
        search[
            "rules"
        ]
    )

    assert rules[
        "QUERY_MODE"
    ] == (
        "EXACT_CASE_SENSITIVE_LITERAL_UTF8_SUBSTRING"
    )

    assert rules[
        "REGEX_SUPPORTED"
    ] == "NO"



def test_read_source_eof_semantics_are_versioned() -> None:
    contract = (
        semantic_gap_typed_planner_operation_semantics()
    )

    assert (
        contract.schema_version
        == 2
    )
