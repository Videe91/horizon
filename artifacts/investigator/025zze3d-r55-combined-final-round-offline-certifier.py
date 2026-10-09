from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile

from decimal import Decimal
from pathlib import Path


from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.investigation.evidence_records import (
    canonical_source_observation_evidence_record,
)
from horizon.investigation.execution import (
    InvestigationSourceObservation,
    execute_investigation_operation,
)
from horizon.investigation.proposal_plan import (
    compile_semantic_gap_proposal_plan,
)
from horizon.investigation.providers.openai_responses import (
    _canonical_input_json,
)
from horizon.investigation.semantic_understanding_coordinator import (
    _hypothesis_round_typed_planner_instruction,
    _validate_final_hypothesis_round_material_paths,
)
from horizon.investigation.typed_planner_address_hints import (
    compile_typed_planner_repository_address_hints,
    typed_planner_repository_address_hints_payload,
)
from horizon.investigation.typed_planner_model import (
    SemanticGapTypedPlannerModelResult,
    SemanticGapTypedPlannerValidationResult,
    execute_semantic_gap_typed_planner,
    make_semantic_gap_typed_planner_invocation,
)
from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    parse_investigation_proposal,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.python_index import (
    index_python_repository,
)


EXPECTED_TARGET_HEAD = (
    "6151aad2081d9a849a6aac7a6081a2d7b32c4334"
)

EXPECTED_TARGET_TREE = (
    "373ebadeac1ad41fa2532c113f4a850ca379d962"
)

EXPECTED_R45_CERT_ID = (
    "planner-addressability-offline-certification:"
    "ce79abfef17fa181a40733789a3253eb5a1520a5982557b491acb1f6944ccf40"
)

EXPECTED_R46_CERT_ID = (
    "final-round-address-hint-consumption-certification:"
    "1e4fe612e2b99e741f9393dd84d76ea2b9cc716ed252616bd1265016ff3e143a"
)

EXPECTED_R54_CERT_ID = (
    "typed-planner-plan-time-budget-contract-certification:"
    "a1291ce200b9f8544f1132268b6eecf77225ef8aafeac55e0b31162102536598"
)

EXPECTED_SELECTED_PATHS = (
    "src/horizon/world_model/repository_semantic_store.py",
    "tests/unit/world_model/test_repository_semantic_store.py",
    "src/horizon/world_model/repository_deterministic.py",
    "tests/unit/cards/test_repository_world_model_projection.py",
    "src/horizon/cards/repository.py",
    "pyproject.toml",
)

MAX_STEPS = 6
MAX_TOTAL_SECONDS = 120
PER_STEP_SECONDS = 20


def canonical_bytes(
    value: object,
) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode(
        "utf-8"
    )


def sha256_file(
    path: Path,
) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    )


def identity(
    prefix: str,
    value: object,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            canonical_bytes(
                value
            )
        ).hexdigest()
    )


def git(
    repository: Path,
    *arguments: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return completed.stdout.strip()


class FakePlanner:
    def __init__(
        self,
        output: dict[str, object],
        *,
        request_id: str,
    ) -> None:
        self.output = output
        self.request_id = request_id
        self.calls = []

    def invoke(
        self,
        invocation,
    ):
        self.calls.append(
            invocation
        )

        return (
            SemanticGapTypedPlannerModelResult(
                provider="R55_OFFLINE_FAKE",
                model_id="r55-offline-fake-planner",
                output=self.output,
                input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal("0"),
                api_request_id=(
                    self.request_id
                ),
            )
        )


def make_request(
    questions: tuple[str, ...],
):
    assert questions

    return InvestigationRequest(
        question_id=(
            "repository-semantic-gap-question:"
            "627bdd67d2987320db7e045a86ea8c87a4c256ab4bf3c44c86b90c52d8775ab8"
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
            "investigation-request:r55-combined-final-round"
        ),
        origin=(
            InvestigationRequestOrigin
            .REPOSITORY_SEMANTIC_GAP
        ),
        semantic_gap_id=(
            "repository-semantic-gap:"
            "b530b9c5bd7f0108fe555ddbd2d74250c07ca5e854e2e1ddda5dcc030fb01e5d"
        ),
        semantic_gap_section="WHAT_IT_IS",
    )


def make_planning_proposal(
    request: InvestigationRequest,
    questions: tuple[str, ...],
):
    return parse_investigation_proposal(
        request,
        {
            "type": "PROPOSE_INVESTIGATION",
            "question_id": (
                request.question_id
            ),
            "relationship_id": None,
            "assertion_ids": [],
            "claim_ids": [],
            "assessment_ids": [],
            "evidence_reference_ids": [],
            "investigation_questions": list(
                questions
            ),
        },
    )


def planner_output(
    *,
    proposal,
    request,
    path_question_pairs,
    per_step_seconds: int,
):
    return {
        "proposal_id": (
            proposal.proposal_id
        ),
        "question_id": (
            request.question_id
        ),
        "bindings": [
            {
                "investigation_question": question,
                "step_key": (
                    "read_"
                    + f"{number:02d}"
                ),
                "purpose": (
                    "Materialize exact frozen final-round "
                    "source evidence."
                ),
                "operation": {
                    "type": "READ_SOURCE",
                    "path": path,
                    "start_line": 1,
                    "end_line": None,
                },
                "depends_on_keys": [],
                "expected_information": (
                    "Complete observed source through "
                    "frozen repository EOF."
                ),
                "max_seconds": (
                    per_step_seconds
                ),
            }
            for number, (
                path,
                question,
            )
            in enumerate(
                path_question_pairs,
                start=1,
            )
        ],
    }


def main() -> None:
    if len(sys.argv) != 7:
        raise SystemExit(
            "usage: certifier TARGET R45 R46 R54 R53 OUTPUT"
        )

    target = Path(
        sys.argv[1]
    ).resolve()

    r45_path = Path(
        sys.argv[2]
    ).resolve()

    r46_path = Path(
        sys.argv[3]
    ).resolve()

    r54_path = Path(
        sys.argv[4]
    ).resolve()

    r53_path = Path(
        sys.argv[5]
    ).resolve()

    output_path = Path(
        sys.argv[6]
    ).resolve()

    if output_path.exists():
        raise RuntimeError(
            "R55 certificate already exists"
        )

    r45 = json.loads(
        r45_path.read_text(
            encoding="utf-8"
        )
    )

    r46 = json.loads(
        r46_path.read_text(
            encoding="utf-8"
        )
    )

    r54 = json.loads(
        r54_path.read_text(
            encoding="utf-8"
        )
    )

    r53 = json.loads(
        r53_path.read_text(
            encoding="utf-8"
        )
    )


    #
    # Prior authority chain.
    #
    assert (
        r45["certification_id"]
        == EXPECTED_R45_CERT_ID
    )

    assert (
        r46["certification_id"]
        == EXPECTED_R46_CERT_ID
    )

    assert (
        r54["certification_id"]
        == EXPECTED_R54_CERT_ID
    )

    assert (
        r53["attempt"]["state"]
        == "PERMANENTLY_CLOSED"
    )


    #
    # Exact frozen target authority.
    #
    assert (
        git(
            target,
            "rev-parse",
            "HEAD",
        )
        == EXPECTED_TARGET_HEAD
    )

    assert (
        git(
            target,
            "rev-parse",
            "HEAD^{tree}",
        )
        == EXPECTED_TARGET_TREE
    )

    assert (
        git(
            target,
            "status",
            "--short",
        )
        == ""
    )

    assert (
        git(
            target,
            "remote",
        )
        == ""
    )


    #
    # Exact 3B final-round questions.
    #
    questions = tuple(
        r45[
            "exact_3b_replay"
        ][
            "missing_questions"
        ]
    )

    assert len(
        questions
    ) == 3

    assert len(
        set(
            questions
        )
    ) == 3


    r46_round = r46[
        "exact_3b_final_round"
    ]

    selected_paths = tuple(
        r46_round[
            "selected_read_source_paths"
        ]
    )

    assert (
        selected_paths
        == EXPECTED_SELECTED_PATHS
    )

    assert (
        r46_round[
            "source_basis_paths"
        ]
        == [
            "pyproject.toml",
        ]
    )


    #
    # Map each exact R46 selected path to the exact
    # final-round question it was selected to answer.
    #
    materialized = (
        r46_round[
            "materialized_source_records"
        ]
    )

    question_by_path = {
        record["path"]: record["question"]
        for record in materialized
    }

    assert (
        set(
            question_by_path
        )
        == set(
            selected_paths
        )
    )

    assert all(
        question
        in questions
        for question
        in question_by_path.values()
    )

    path_question_pairs = tuple(
        (
            path,
            question_by_path[
                path
            ],
        )
        for path
        in selected_paths
    )


    #
    # Recompute R45 address hints from the actual frozen target.
    #
    observation = (
        observe_git_commit(
            target,
            EXPECTED_TARGET_HEAD,
        )
    )

    with tempfile.TemporaryDirectory(
        prefix="horizon-r55-cache-",
    ) as temporary:
        cache = (
            ContentAddressedExtractionCache(
                Path(temporary)
                / "cache"
            )
        )

        index = (
            index_python_repository(
                target,
                observation,
                cache,
            )
        )

        hints = (
            compile_typed_planner_repository_address_hints(
                index=index,
                planning_questions=(
                    questions
                ),
            )
        )


    expected_hints = (
        r45[
            "exact_3b_replay"
        ][
            "address_hints"
        ]
    )

    assert (
        hints.address_hints_id
        == expected_hints[
            "address_hints_id"
        ]
    )

    assert (
        hints.python_repository_index_id
        == expected_hints[
            "python_repository_index_id"
        ]
    )

    assert (
        hints.source_commit
        == EXPECTED_TARGET_HEAD
    )


    hint_payload = (
        typed_planner_repository_address_hints_payload(
            hints
        )
    )

    candidates_by_question = {
        item["question"]: {
            candidate["path"]
            for candidate
            in item["candidates"]
        }
        for item
        in hint_payload[
            "questions"
        ]
    }

    assert (
        set(
            candidates_by_question
        )
        == set(
            questions
        )
    )


    #
    # Every R46-selected address-hint path must still be
    # addressable for its exact question.
    #
    addressable_hint_paths = []

    for path, question in path_question_pairs:
        if path == "pyproject.toml":
            continue

        assert (
            path
            in candidates_by_question[
                question
            ]
        )

        addressable_hint_paths.append(
            path
        )

    assert len(
        addressable_hint_paths
    ) == 5


    #
    # Exact production final-round instruction builder.
    #
    instruction = (
        _hypothesis_round_typed_planner_instruction(
            b"R55_OFFLINE_BASE",
            current_round=2,
            max_rounds=2,
            source_hypothesis=(
                "Horizon is intended to provide continuously "
                "maintained software understanding for AI agents."
            ),
            source_basis_paths=(
                "pyproject.toml",
            ),
            repository_address_hints=(
                hints
            ),
        )
    )

    instruction_text = (
        instruction.decode(
            "utf-8"
        )
    )

    assert (
        "final_hypothesis_round=true"
        in instruction_text
    )

    assert (
        "repository_address_hints="
        in instruction_text
    )

    assert (
        "They are NOT evidence"
        in instruction_text
    )


    #
    # Exact semantic-gap planning envelope.
    #
    request = make_request(
        questions
    )

    proposal = (
        make_planning_proposal(
            request,
            questions,
        )
    )


    legal_output = planner_output(
        proposal=proposal,
        request=request,
        path_question_pairs=(
            path_question_pairs
        ),
        per_step_seconds=(
            PER_STEP_SECONDS
        ),
    )

    legal_planner = FakePlanner(
        legal_output,
        request_id=(
            "r55-offline-legal"
        ),
    )


    #
    # R54 boundary + R45/R46 final path together.
    #
    legal_execution = (
        execute_semantic_gap_typed_planner(
            model=legal_planner,
            request=request,
            proposal=proposal,
            instruction=instruction,
            temperature=None,
            max_plan_total_seconds=(
                MAX_TOTAL_SECONDS
            ),
            cost_cap_usd=Decimal(
                "1"
            ),
        )
    )

    assert len(
        legal_planner.calls
    ) == 1

    assert (
        legal_execution
        .run
        .validation_result
        is
        SemanticGapTypedPlannerValidationResult
        .VALID
    )

    assert (
        legal_execution.planner_output
        is not None
    )

    invocation = (
        legal_execution.invocation
    )

    assert (
        invocation.max_plan_total_seconds
        == MAX_TOTAL_SECONDS
    )


    #
    # Prove the exact model-facing payload contains
    # the same aggregate budget.
    #
    provider_payload = json.loads(
        _canonical_input_json(
            invocation
        )
    )

    assert (
        provider_payload[
            "plan_budget"
        ]
        == {
            "max_total_seconds": (
                MAX_TOTAL_SECONDS
            ),
        }
    )


    #
    # Prove budget authority changes immutable identity.
    #
    changed_budget_invocation = (
        make_semantic_gap_typed_planner_invocation(
            request=request,
            proposal=proposal,
            instruction=instruction,
            temperature=None,
            max_plan_total_seconds=121,
            cost_cap_usd=Decimal(
                "1"
            ),
        )
    )

    assert (
        changed_budget_invocation
        .canonical_input_hash
        != invocation
        .canonical_input_hash
    )

    assert (
        changed_budget_invocation
        .invocation_id
        != invocation
        .invocation_id
    )


    bindings = (
        legal_execution
        .planner_output
        .bindings
    )

    assert len(
        bindings
    ) == MAX_STEPS

    aggregate_seconds = sum(
        binding.draft.max_seconds
        for binding
        in bindings
    )

    assert (
        aggregate_seconds
        == MAX_TOTAL_SECONDS
    )


    #
    # Real production final-round completeness guard.
    #
    _validate_final_hypothesis_round_material_paths(
        proposal=proposal,
        bindings=bindings,
        final_round=True,
        source_basis_paths=(
            "pyproject.toml",
        ),
    )


    #
    # Real deterministic compiler.
    #
    plan = (
        compile_semantic_gap_proposal_plan(
            request=request,
            proposal=proposal,
            bindings=bindings,
            max_steps=MAX_STEPS,
            max_total_seconds=(
                MAX_TOTAL_SECONDS
            ),
        )
    )

    assert len(
        plan.steps
    ) == MAX_STEPS

    assert (
        plan.max_steps
        == MAX_STEPS
    )

    assert (
        plan.max_total_seconds
        == MAX_TOTAL_SECONDS
    )

    assert (
        sum(
            step.max_seconds
            for step
            in plan.steps
        )
        == MAX_TOTAL_SECONDS
    )


    compiled_paths = tuple(
        step.operation.path
        for step
        in plan.steps
    )

    #
    # InvestigationPlan canonicalizes compiled steps by
    # Horizon-owned step_id. Canonical compiled order is
    # therefore intentionally independent of planner/input
    # selection order. The authority requirement here is
    # exact unique path-set preservation.
    #
    assert len(
        compiled_paths
    ) == len(
        EXPECTED_SELECTED_PATHS
    )

    assert len(
        set(
            compiled_paths
        )
    ) == len(
        compiled_paths
    )

    assert (
        set(
            compiled_paths
        )
        == set(
            EXPECTED_SELECTED_PATHS
        )
    )


    #
    # Execute exact frozen READ_SOURCE operations.
    #
    evidence_manifest = []

    for step in plan.steps:
        observed = (
            execute_investigation_operation(
                target,
                observation,
                step.operation,
            )
        )

        assert isinstance(
            observed,
            InvestigationSourceObservation,
        )

        assert (
            observed.ends_at_observed_eof
            is True
        )

        assert (
            observed.end_line
            == observed
            .observed_source_line_count
        )

        record = (
            canonical_source_observation_evidence_record(
                observed
            )
        )

        assert (
            record.evidence_id
            == observed.observation_id
        )

        evidence_manifest.append(
            {
                "path": (
                    step.operation.path
                ),
                "evidence_id": (
                    record.evidence_id
                ),
                "observation_id": (
                    observed.observation_id
                ),
                "observed_source_line_count": (
                    observed.observed_source_line_count
                ),
                "ends_at_observed_eof": (
                    observed.ends_at_observed_eof
                ),
            }
        )


    assert len(
        evidence_manifest
    ) == 6

    assert len(
        {
            item[
                "evidence_id"
            ]
            for item
            in evidence_manifest
        }
    ) == 6


    #
    # Negative proof:
    # same six exact paths at 21 seconds each = 126.
    #
    over_budget_output = planner_output(
        proposal=proposal,
        request=request,
        path_question_pairs=(
            path_question_pairs
        ),
        per_step_seconds=21,
    )

    over_budget_planner = FakePlanner(
        over_budget_output,
        request_id=(
            "r55-offline-over-budget"
        ),
    )

    over_budget_execution = (
        execute_semantic_gap_typed_planner(
            model=over_budget_planner,
            request=request,
            proposal=proposal,
            instruction=instruction,
            temperature=None,
            max_plan_total_seconds=(
                MAX_TOTAL_SECONDS
            ),
            cost_cap_usd=Decimal(
                "1"
            ),
        )
    )

    assert (
        over_budget_execution
        .run
        .validation_result
        is
        SemanticGapTypedPlannerValidationResult
        .INVALID
    )

    assert (
        over_budget_execution
        .planner_output
        is None
    )

    assert (
        over_budget_execution
        .run
        .rejection_reason
        == (
            "planner output aggregate max_seconds "
            "exceeds pre-registered plan time budget"
        )
    )


    #
    # Final certification.
    #
    certifier_path = Path(
        __file__
    ).resolve()

    payload = {
        "schema_version": 1,

        "certification": {
            "stage": "025ZZE-3D-R55",
            "kind": (
                "OFFLINE_FINAL_ROUND_ADDRESSABILITY_BUDGET_COMPOSITION"
            ),
            "status": "PASS",
        },

        "authority": {
            "r45_certification_id": (
                EXPECTED_R45_CERT_ID
            ),
            "r45_certificate_sha256": (
                sha256_file(
                    r45_path
                )
            ),
            "r46_certification_id": (
                EXPECTED_R46_CERT_ID
            ),
            "r46_certificate_sha256": (
                sha256_file(
                    r46_path
                )
            ),
            "r54_certification_id": (
                EXPECTED_R54_CERT_ID
            ),
            "r54_certificate_sha256": (
                sha256_file(
                    r54_path
                )
            ),
            "frozen_target_head": (
                EXPECTED_TARGET_HEAD
            ),
            "frozen_target_tree": (
                EXPECTED_TARGET_TREE
            ),
        },

        "exact_final_round": {
            "current_hypothesis_round": 2,
            "max_hypothesis_rounds": 2,
            "final_hypothesis_round": True,
            "planning_question_count": (
                len(
                    questions
                )
            ),
            "planning_questions": list(
                questions
            ),
            "address_hints_id": (
                hints.address_hints_id
            ),
            "python_repository_index_id": (
                hints
                .python_repository_index_id
            ),
            "selected_read_source_paths": list(
                selected_paths
            ),
            "address_hint_selected_path_count": 5,
            "source_basis_paths": [
                "pyproject.toml",
            ],
            "plan_step_count": (
                len(
                    plan.steps
                )
            ),
            "per_step_max_seconds": (
                PER_STEP_SECONDS
            ),
            "aggregate_plan_seconds": (
                aggregate_seconds
            ),
            "sealed_max_total_seconds": (
                MAX_TOTAL_SECONDS
            ),
            "compiled_plan_id": (
                plan.plan_id
            ),
        },

        "budget_contract": {
            "invocation_max_plan_total_seconds": (
                invocation
                .max_plan_total_seconds
            ),
            "provider_payload_plan_budget": (
                provider_payload[
                    "plan_budget"
                ]
            ),
            "canonical_input_hash": (
                invocation
                .canonical_input_hash
            ),
            "invocation_id": (
                invocation
                .invocation_id
            ),
            "changed_budget_changes_canonical_input_hash": True,
            "changed_budget_changes_invocation_id": True,
            "legal_120_second_plan_valid": True,
            "over_budget_seconds": 126,
            "over_budget_rejected_before_plan_compilation": True,
            "over_budget_rejection_reason": (
                over_budget_execution
                .run
                .rejection_reason
            ),
            "silent_clipping": False,
        },

        "material_evidence": {
            "read_source_count": (
                len(
                    evidence_manifest
                )
            ),
            "all_reads_end_at_observed_eof": True,
            "canonical_evidence_count": (
                len(
                    evidence_manifest
                )
            ),
            "records": (
                evidence_manifest
            ),
        },

        "proved": {
            "r45_exact_address_hints_recomputed_on_frozen_target": True,
            "r46_selected_final_round_paths_still_addressable": True,
            "r46_source_basis_path_covered": True,
            "r54_budget_visible_in_exact_planner_invocation": True,
            "r54_budget_visible_in_provider_facing_payload": True,
            "six_step_final_round_fits_exact_120_second_budget": True,
            "final_round_material_path_validator_passes": True,
            "strict_deterministic_plan_compiler_accepts_legal_plan": True,
            "real_investigation_executor_materializes_all_six_reads": True,
            "canonical_material_evidence_created_offline": True,
            "over_budget_plan_rejected_at_typed_planner_boundary": True,
        },

        "not_proved": {
            "gpt_6_astra_will_choose_this_legal_plan_live": True,
            "final_evaluator_will_return_supported": True,
            "ai_agent_card_delivery_exists": True,
        },

        "safety": {
            "provider_network_calls": 0,
            "paid_calls": 0,
            "paid_spend_usd": "0",
            "OPENAI_API_KEY_read": False,
            "frozen_target_mutations": 0,
            "semantic_overlay_created": False,
            "world_model_mutations": 0,
            "3d_replayed": False,
            "3d_namespace_reused": False,
            "third_hypothesis_round_added": False,
        },

        "certifier": {
            "path": (
                str(
                    certifier_path
                    .relative_to(
                        Path.cwd()
                        .resolve()
                    )
                )
            ),
            "sha256": (
                sha256_file(
                    certifier_path
                )
            ),
        },

        "next_authorized_stage": (
            "Commit and push this exact R55 offline combined "
            "certification. Only after R55 is durable may a fresh "
            "025ZZE-3E preregistration be considered. R55 itself "
            "does not authorize or execute any paid provider call."
        ),
    }


    payload[
        "certification_id"
    ] = identity(
        "final-round-addressability-budget-composition-certification:",
        payload,
    )


    output_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )


    print(
        "R45_EXACT_ADDRESS_HINTS_RECOMPUTED=PASS"
    )

    print(
        "R46_SELECTED_PATHS_ADDRESSABLE=PASS"
    )

    print(
        "FINAL_ROUND_QUESTIONS=3"
    )

    print(
        "FINAL_ROUND_READ_SOURCE_STEPS=6"
    )

    print(
        "FINAL_ROUND_PER_STEP_SECONDS=20"
    )

    print(
        "FINAL_ROUND_TOTAL_SECONDS=120"
    )

    print(
        "MODEL_FACING_PLAN_BUDGET_SECONDS=120"
    )

    print(
        "FINAL_ROUND_MATERIAL_VALIDATOR=PASS"
    )

    print(
        "STRICT_PLAN_COMPILER=PASS"
    )

    print(
        "REAL_READ_SOURCE_EXECUTION=PASS"
    )

    print(
        "CANONICAL_EVIDENCE_RECORDS=6"
    )

    print(
        "OVER_BUDGET_126_SECONDS_PRECOMPILE_REJECTION=PASS"
    )

    print(
        "PROVIDER_CALLS=0"
    )

    print(
        "PAID_SPEND_USD=0"
    )

    print(
        "R55_CERTIFICATION_ID="
        + payload[
            "certification_id"
        ]
    )


if __name__ == "__main__":
    main()
