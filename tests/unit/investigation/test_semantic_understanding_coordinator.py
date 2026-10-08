from __future__ import annotations

import json
import subprocess

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

import horizon.investigation.semantic_understanding_coordinator as coordinator_module

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.claims.epistemic import (
    EpistemicStatus,
)
from horizon.investigation.deterministic_evidence_records import (
    canonical_repository_deterministic_evidence_records,
)
from horizon.investigation.hypothesis_evaluation import (
    HypothesisEvaluationVerdict,
)
from horizon.investigation.hypothesis_evaluation_model import (
    HypothesisEvaluationModelResult,
)
from horizon.investigation.providers.openai_responses import (
    SemanticGapTypedPlannerModelResult,
)
from horizon.investigation.semantic_gap import (
    RepositorySemanticGapSection,
    discover_repository_semantic_gaps,
)
from horizon.investigation.semantic_understanding_coordinator import (
    RepositorySemanticUnderstandingCoordinatorError,
    RepositorySemanticUnderstandingDisposition,
    RepositorySemanticUnderstandingLimits,
    run_repository_what_it_is_semantic_understanding,
)
from horizon.investigator.model import (
    InvestigatorModelResult,
)
from horizon.languages.python.project_dependencies import (
    discover_declared_project_dependencies,
)
from horizon.languages.python.repository_modules import (
    discover_hatch_wheel_import_roots,
)
from horizon.repository.git_blob import (
    read_observed_blob,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.python_index import (
    index_python_repository,
)
from horizon.world_model.repository_deterministic import (
    build_repository_deterministic_world_model,
)
from horizon.world_model.repository_semantic_store import (
    RepositorySemanticWorldModelStore,
)


DISCOVERY_QUESTION = (
    "Which exact README statement describes "
    "the repository's software purpose?"
)

HYPOTHESIS = (
    "At this frozen repository snapshot, "
    "the repository primarily implements "
    "workflow orchestration software."
)

TEST_QUESTION = (
    "Does the exact README source support "
    "workflow orchestration as the repository purpose?"
)


@dataclass(
    frozen=True,
)
class Fixture:
    repository: Path
    observation: object
    index: object
    base_model: object
    initial_evidence: tuple
    store: RepositorySemanticWorldModelStore


def git(
    repository: Path,
    *arguments: str,
) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(
                repository
            ),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()


def prepare(
    tmp_path: Path,
) -> Fixture:
    repository = (
        tmp_path
        / "repository"
    )

    repository.mkdir()

    git(
        repository,
        "init",
        "-q",
    )

    git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    (
        repository
        / "pyproject.toml"
    ).write_text(
        """[project]
name = "semantic-demo"
dependencies = ["requests>=2"]

[tool.hatch.build.targets.wheel]
packages = ["src/demo"]
""",
        encoding="utf-8",
    )

    (
        repository
        / "README.md"
    ).write_text(
        (
            "Semantic Demo provides workflow orchestration software.\n"
            "It coordinates and executes declared workflow tasks.\n"
        ),
        encoding="utf-8",
    )

    package = (
        repository
        / "src"
        / "demo"
    )

    package.mkdir(
        parents=True
    )

    (
        package
        / "__init__.py"
    ).write_text(
        (
            '"""Semantic demo package."""\n'
            "\n"
            "def run():\n"
            "    return None\n"
        ),
        encoding="utf-8",
    )

    git(
        repository,
        "add",
        ".",
    )

    git(
        repository,
        "commit",
        "-q",
        "-m",
        "initial",
    )

    commit = git(
        repository,
        "rev-parse",
        "HEAD",
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    cache = ContentAddressedExtractionCache(
        tmp_path
        / "cache"
    )

    index = index_python_repository(
        repository,
        observation,
        cache,
    )

    pyproject_blob = read_observed_blob(
        repository,
        observation,
        "pyproject.toml",
    )

    package_layout = (
        discover_hatch_wheel_import_roots(
            pyproject_blob
        )
    )

    dependencies = (
        discover_declared_project_dependencies(
            pyproject_blob
        )
    )

    base_model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=(
                pyproject_blob
            ),
            package_layout=(
                package_layout
            ),
            project_dependencies=(
                dependencies
            ),
        )
    )

    initial_evidence = (
        canonical_repository_deterministic_evidence_records(
            pyproject_blob=(
                pyproject_blob
            ),
            package_layout=(
                package_layout
            ),
            project_dependencies=(
                dependencies
            ),
        )
    )

    store = (
        RepositorySemanticWorldModelStore(
            tmp_path
            / "semantic-state"
        )
    )

    return Fixture(
        repository=repository,
        observation=observation,
        index=index,
        base_model=base_model,
        initial_evidence=(
            initial_evidence
        ),
        store=store,
    )


def common(
    request,
) -> dict[
    str,
    object,
]:
    return {
        "question_id": (
            request.question_id
        ),
        "relationship_id": (
            request.relationship_id
        ),
        "assertion_ids": list(
            request.assertion_ids
        ),
        "claim_ids": list(
            request.claim_ids
        ),
        "assessment_ids": list(
            request.assessment_ids
        ),
        "evidence_reference_ids": list(
            request.evidence_reference_ids
        ),
    }


class FakeInvestigator:
    def __init__(
        self,
        mode: str = "sequence",
    ) -> None:
        self.mode = mode
        self.calls = []

    def invoke(
        self,
        invocation,
    ):
        self.calls.append(
            invocation
        )

        request = (
            invocation.request
        )

        call_number = len(
            self.calls
        )

        if (
            self.mode
            == "hypothesis"
        ):
            kind = "hypothesis"

        elif (
            self.mode
            == "investigation_forever"
        ):
            kind = "investigation"

        elif call_number == 1:
            kind = "investigation"

        else:
            kind = "hypothesis"

        if kind == "investigation":
            output = {
                "type": (
                    "PROPOSE_INVESTIGATION"
                ),
                **common(
                    request
                ),
                "investigation_questions": [
                    DISCOVERY_QUESTION,
                ],
            }

        else:
            output = {
                "type": (
                    "PROPOSE_HYPOTHESIS"
                ),
                **common(
                    request
                ),
                "hypothesis": (
                    HYPOTHESIS
                ),
                "test_questions": [
                    TEST_QUESTION,
                ],
            }

        return InvestigatorModelResult(
            provider=(
                "FAKE_INVESTIGATOR"
            ),
            model_id=(
                "fake-investigator-v1"
            ),
            output=output,
            input_tokens=10,
            output_tokens=5,
            cost_usd=Decimal(
                "0.001000"
            ),
            api_request_id=(
                "fake-investigator-"
                + str(
                    call_number
                )
            ),
        )


class FakePlanner:
    def __init__(
        self,
        mode: str = "read",
    ) -> None:
        self.mode = mode
        self.calls = []

    def invoke(
        self,
        invocation,
    ):
        self.calls.append(
            invocation
        )

        proposal = (
            invocation.proposal
        )

        question = (
            proposal
            .investigation_questions[
                0
            ]
        )

        instruction_text = (
            invocation
            .instruction
            .decode(
                "utf-8"
            )
        )

        final_hypothesis_round = (
            "final_hypothesis_round=true"
            in instruction_text
        )

        source_basis_paths = ()

        for line in (
            instruction_text
            .splitlines()
        ):
            prefix = (
                "source_hypothesis_material_basis_paths="
            )

            if line.startswith(
                prefix
            ):
                parsed = json.loads(
                    line[
                        len(
                            prefix
                        ):
                    ]
                )

                assert isinstance(
                    parsed,
                    list,
                )

                assert all(
                    isinstance(
                        path,
                        str,
                    )
                    and path
                    for path
                    in parsed
                )

                source_basis_paths = tuple(
                    parsed
                )

                break

        if self.mode == "resolve":
            operation = {
                "type": (
                    "RESOLVE_CALL"
                ),
                "path": (
                    "src/demo/__init__.py"
                ),
                "line": 4,
                "character": 4,
            }

        elif self.mode == "search":
            operation = {
                "type": (
                    "SEARCH_SOURCE"
                ),
                "query": "workflow",
                "path_prefix": None,
            }

        else:
            if (
                self.mode
                == "wrong_basis"
            ):
                path = (
                    "README.md"
                )

                line = 1

            elif (
                final_hypothesis_round
                and source_basis_paths
            ):
                path = (
                    source_basis_paths[
                        0
                    ]
                )

                line = 1

            else:
                path = (
                    "README.md"
                )

                if (
                    self.mode
                    == "round_read"
                ):
                    line = len(
                        self.calls
                    )

                elif (
                    question
                    == DISCOVERY_QUESTION
                ):
                    line = 1

                else:
                    line = 2

            operation = {
                "type": (
                    "READ_SOURCE"
                ),
                "path": path,
                "start_line": line,
                "end_line": line,
            }

        output = {
            "proposal_id": (
                proposal.proposal_id
            ),
            "question_id": (
                invocation
                .request
                .question_id
            ),
            "bindings": [
                {
                    "investigation_question": (
                        question
                    ),
                    "step_key": (
                        "step_"
                        + str(
                            len(
                                self.calls
                            )
                        )
                    ),
                    "purpose": (
                        "Gather exact frozen "
                        "repository evidence."
                    ),
                    "operation": (
                        operation
                    ),
                    "depends_on_keys": [],
                    "expected_information": (
                        "Exact source evidence "
                        "for the semantic question."
                    ),
                    "max_seconds": 5,
                },
            ],
        }

        return (
            SemanticGapTypedPlannerModelResult(
                provider=(
                    "FAKE_PLANNER"
                ),
                model_id=(
                    "fake-planner-v1"
                ),
                output=output,
                input_tokens=10,
                output_tokens=5,
                cost_usd=Decimal(
                    "0.001000"
                ),
                api_request_id=(
                    "fake-planner-"
                    + str(
                        len(
                            self.calls
                        )
                    )
                ),
            )
        )


class FakeEvaluator:
    def __init__(
        self,
        mode: str = "supported",
    ) -> None:
        self.mode = mode
        self.calls = []

    def invoke(
        self,
        invocation,
    ):
        self.calls.append(
            invocation
        )

        request = (
            invocation.request
        )

        source_ids = [
            record.evidence_id
            for record
            in request.evidence_records
            if (
                record.evidence_id
                .startswith(
                    "investigation-source-observation:"
                )
            )
        ]

        assert source_ids

        if (
            self.mode
            == "supported_metadata"
        ):
            metadata = next(
                record.evidence_id
                for record
                in request.evidence_records
                if (
                    record.evidence_id
                    not in source_ids
                )
            )

            verdict = "SUPPORTED"

            supporting = [
                metadata,
            ]

            contradicting = []
            missing = []

        elif (
            self.mode
            == "incomplete"
        ):
            verdict = (
                "STILL_INCOMPLETE"
            )

            supporting = [
                source_ids[
                    -1
                ],
            ]

            contradicting = []

            missing = [
                (
                    "Inspect another exact "
                    "source location."
                ),
            ]

        elif (
            self.mode
            == "contradicted"
        ):
            verdict = "CONTRADICTED"

            supporting = []

            contradicting = [
                source_ids[
                    -1
                ],
            ]

            missing = []

        else:
            verdict = "SUPPORTED"

            supporting = list(
                source_ids
            )

            contradicting = []
            missing = []

        output = {
            "request_id": (
                request.request_id
            ),
            "question_id": (
                request.question_id
            ),
            "source_proposal_id": (
                invocation
                .source_proposal
                .proposal_id
            ),
            "verdict": verdict,
            "supporting_evidence_ids": (
                supporting
            ),
            "contradicting_evidence_ids": (
                contradicting
            ),
            "missing_evidence_questions": (
                missing
            ),
        }

        return (
            HypothesisEvaluationModelResult(
                provider=(
                    "FAKE_EVALUATOR"
                ),
                model_id=(
                    "fake-evaluator-v1"
                ),
                output=output,
                input_tokens=10,
                output_tokens=5,
                cost_usd=Decimal(
                    "0.001000"
                ),
                api_request_id=(
                    "fake-evaluator-"
                    + str(
                        len(
                            self.calls
                        )
                    )
                ),
            )
        )


class ExplodingModel:
    def invoke(
        self,
        invocation,
    ):
        raise AssertionError(
            "model must not be called"
        )


def limits(
    *,
    investigator_rounds: int = 2,
    hypothesis_rounds: int = 1,
    total_model_cost: str = "0.050000",
) -> RepositorySemanticUnderstandingLimits:
    return (
        RepositorySemanticUnderstandingLimits(
            max_investigator_rounds=(
                investigator_rounds
            ),
            max_hypothesis_rounds=(
                hypothesis_rounds
            ),
            max_plan_steps=4,
            max_plan_total_seconds=30,
            max_evidence_record_bytes=(
                250_000
            ),
            max_total_evidence_bytes=(
                1_000_000
            ),
            max_total_model_cost_usd=(
                Decimal(
                    total_model_cost
                )
            ),
        )
    )


def run(
    fixture: Fixture,
    *,
    investigator,
    planner,
    evaluator,
    value_limits=None,
    investigator_temperature=0.0,
    legacy_cost_cap: str = "0.010000",
):
    return (
        run_repository_what_it_is_semantic_understanding(
            repository=(
                fixture.repository
            ),
            observation=(
                fixture.observation
            ),
            index=fixture.index,
            base_model=(
                fixture.base_model
            ),
            initial_evidence_records=(
                fixture.initial_evidence
            ),
            semantic_store=(
                fixture.store
            ),
            investigator_model=(
                investigator
            ),
            typed_planner_model=(
                planner
            ),
            evaluation_model=(
                evaluator
            ),
            investigator_instruction=(
                b"Propose only bounded semantic investigation."
            ),
            investigator_temperature=(
                investigator_temperature
            ),
            investigator_cost_cap_usd=(
                Decimal(
                    legacy_cost_cap
                )
            ),
            typed_planner_instruction=(
                b"Translate questions into legal typed operations only."
            ),
            typed_planner_temperature=(
                None
            ),
            typed_planner_cost_cap_usd=(
                Decimal(
                    legacy_cost_cap
                )
            ),
            evaluation_instruction=(
                b"Evaluate only against visible repository evidence."
            ),
            evaluation_temperature=(
                None
            ),
            evaluation_cost_cap_usd=(
                Decimal(
                    legacy_cost_cap
                )
            ),
            limits=(
                value_limits
                or limits()
            ),
        )
    )


def test_full_offline_loop_discovers_tests_evaluates_promotes_and_persists(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    investigator = (
        FakeInvestigator()
    )

    planner = FakePlanner()

    evaluator = (
        FakeEvaluator()
    )

    result = run(
        fixture,
        investigator=(
            investigator
        ),
        planner=planner,
        evaluator=evaluator,
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .PROMOTED
    )

    assert (
        result.investigator_rounds_completed
        == 2
    )

    assert (
        result.hypothesis_rounds_completed
        == 1
    )

    assert len(
        investigator.calls
    ) == 2

    assert len(
        planner.calls
    ) == 2

    assert len(
        evaluator.calls
    ) == 1

    assert len(
        result.operation_observation_ids
    ) == 2

    assert (
        result.total_model_cost_usd
        == Decimal(
            "0.005000"
        )
    )

    assert len(
        result.final_model
        .what_it_is_assertion_ids
    ) == 1

    assert (
        result.persisted_overlay_path
        is not None
    )

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == result.final_model
    )

    remaining = {
        question.section
        for question
        in discover_repository_semantic_gaps(
            fixture.index,
            result.final_model,
        ).questions
    }

    assert (
        RepositorySemanticGapSection
        .WHAT_IT_IS
        not in remaining
    )

    assertion_id = (
        result.final_model
        .what_it_is_assertion_ids[
            0
        ]
    )

    assertion = next(
        value
        for value
        in result
        .final_model
        .snapshot
        .assertions
        if (
            value.assertion_id
            == assertion_id
        )
    )

    assessment = next(
        value
        for value
        in result
        .final_model
        .snapshot
        .assessments
        if (
            value.assessment_id
            == assertion.assessment_id
        )
    )

    assert (
        assessment.status
        is EpistemicStatus
        .SUPPORTED_HYPOTHESIS
    )


def test_existing_semantic_knowledge_short_circuits_without_any_model_call(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    first = run(
        fixture,
        investigator=(
            FakeInvestigator()
        ),
        planner=FakePlanner(),
        evaluator=(
            FakeEvaluator()
        ),
    )

    assert (
        first.disposition
        is RepositorySemanticUnderstandingDisposition
        .PROMOTED
    )

    second = run(
        fixture,
        investigator=(
            ExplodingModel()
        ),
        planner=(
            ExplodingModel()
        ),
        evaluator=(
            ExplodingModel()
        ),
    )

    assert (
        second.disposition
        is RepositorySemanticUnderstandingDisposition
        .ALREADY_KNOWN
    )

    assert (
        second.total_model_cost_usd
        == Decimal(
            "0"
        )
    )

    assert (
        second.operation_observation_ids
        == ()
    )

    assert (
        second.final_model
        == first.final_model
    )


def test_supported_metadata_only_evaluation_cannot_promote(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    result = run(
        fixture,
        investigator=(
            FakeInvestigator(
                mode="hypothesis"
            )
        ),
        planner=FakePlanner(),
        evaluator=(
            FakeEvaluator(
                mode=(
                    "supported_metadata"
                )
            )
        ),
        value_limits=(
            limits(
                investigator_rounds=1,
                hypothesis_rounds=1,
            )
        ),
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .BOUNDED_STOP
    )

    assert (
        result.evaluation
        is not None
    )

    assert (
        result.evaluation.verdict
        is HypothesisEvaluationVerdict
        .SUPPORTED
    )

    assert (
        result.final_model
        == fixture.base_model
    )

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == fixture.base_model
    )


def test_incomplete_evaluation_stops_without_promotion_when_bound_is_reached(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    result = run(
        fixture,
        investigator=(
            FakeInvestigator(
                mode="hypothesis"
            )
        ),
        planner=FakePlanner(),
        evaluator=(
            FakeEvaluator(
                mode="incomplete"
            )
        ),
        value_limits=(
            limits(
                investigator_rounds=1,
                hypothesis_rounds=1,
            )
        ),
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .BOUNDED_STOP
    )

    assert (
        result.evaluation
        is not None
    )

    assert (
        result.evaluation.verdict
        is HypothesisEvaluationVerdict
        .STILL_INCOMPLETE
    )

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == fixture.base_model
    )


def test_contradicted_evaluation_stops_without_promotion(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    result = run(
        fixture,
        investigator=(
            FakeInvestigator(
                mode="hypothesis"
            )
        ),
        planner=FakePlanner(),
        evaluator=(
            FakeEvaluator(
                mode="contradicted"
            )
        ),
        value_limits=(
            limits(
                investigator_rounds=1,
                hypothesis_rounds=1,
            )
        ),
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .EVALUATION_NOT_SUPPORTED
    )

    assert (
        result.evaluation.verdict
        is HypothesisEvaluationVerdict
        .CONTRADICTED
    )

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == fixture.base_model
    )


def test_total_model_cost_budget_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    planner = FakePlanner()

    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match="total model cost",
    ):
        run(
            fixture,
            investigator=(
                FakeInvestigator()
            ),
            planner=planner,
            evaluator=(
                FakeEvaluator()
            ),
            value_limits=(
                limits(
                    total_model_cost=(
                        "0.000500"
                    )
                )
            ),
        )

    assert planner.calls == []

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == fixture.base_model
    )


def test_resolve_call_fails_before_operation_execution_without_evidence_bridge(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = prepare(
        tmp_path
    )

    executed = []

    def forbidden_executor(
        *args,
        **kwargs,
    ):
        executed.append(
            (
                args,
                kwargs,
            )
        )

        raise AssertionError(
            "RESOLVE_CALL must be rejected before execution"
        )

    monkeypatch.setattr(
        coordinator_module,
        "execute_investigation_operation",
        forbidden_executor,
    )

    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match="RESOLVE_CALL",
    ):
        run(
            fixture,
            investigator=(
                FakeInvestigator(
                    mode=(
                        "investigation_forever"
                    )
                )
            ),
            planner=(
                FakePlanner(
                    mode="resolve"
                )
            ),
            evaluator=(
                FakeEvaluator()
            ),
            value_limits=(
                limits(
                    investigator_rounds=1,
                )
            ),
        )

    assert executed == []


def test_discovery_round_limit_is_hard(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    evaluator = (
        FakeEvaluator()
    )

    result = run(
        fixture,
        investigator=(
            FakeInvestigator(
                mode=(
                    "investigation_forever"
                )
            )
        ),
        planner=FakePlanner(),
        evaluator=evaluator,
        value_limits=(
            limits(
                investigator_rounds=1,
            )
        ),
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .BOUNDED_STOP
    )

    assert (
        result.investigator_rounds_completed
        == 1
    )

    assert (
        result.hypothesis_rounds_completed
        == 0
    )

    assert len(
        result.operation_observation_ids
    ) == 1

    assert evaluator.calls == []

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == fixture.base_model
    )


def test_investigator_temperature_may_be_omitted_for_reasoning_model(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    result = run(
        fixture,
        investigator=(
            FakeInvestigator()
        ),
        planner=(
            FakePlanner()
        ),
        evaluator=(
            FakeEvaluator()
        ),
        investigator_temperature=None,
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .PROMOTED
    )

    assert len(
        result.investigator_run_ids
    ) == 2

    assert (
        result.total_model_cost_usd
        == Decimal(
            "0.005000"
        )
    )


def test_hypothesis_typed_planner_receives_exact_round_budget_and_finality(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    planner = (
        FakePlanner(
            mode="round_read"
        )
    )

    result = run(
        fixture,
        investigator=(
            FakeInvestigator(
                mode="hypothesis"
            )
        ),
        planner=planner,
        evaluator=(
            FakeEvaluator(
                mode="incomplete"
            )
        ),
        value_limits=(
            limits(
                investigator_rounds=1,
                hypothesis_rounds=2,
            )
        ),
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .BOUNDED_STOP
    )

    assert len(
        planner.calls
    ) == 2

    assert (
        planner.calls[
            0
        ]
        .proposal
        .investigation_questions
        == (
            TEST_QUESTION,
        )
    )

    assert (
        planner.calls[
            1
        ]
        .proposal
        .investigation_questions
        == (
            "Inspect another exact "
            "source location.",
        )
    )

    assert (
        planner.calls[
            1
        ]
        .proposal
        .investigation_questions
        != planner.calls[
            0
        ]
        .proposal
        .investigation_questions
    )

    first_instruction = (
        planner.calls[
            0
        ]
        .instruction
        .decode(
            "utf-8"
        )
    )

    second_instruction = (
        planner.calls[
            1
        ]
        .instruction
        .decode(
            "utf-8"
        )
    )

    assert (
        "current_hypothesis_round=1"
        in first_instruction
    ), "ROUND_CONTEXT_CURRENT_1_MISSING"

    assert (
        "max_hypothesis_rounds=2"
        in first_instruction
    )

    assert (
        "remaining_hypothesis_rounds_after_this=1"
        in first_instruction
    )

    assert (
        "final_hypothesis_round=false"
        in first_instruction
    )

    assert (
        "current_hypothesis_round=2"
        in second_instruction
    )

    assert (
        "max_hypothesis_rounds=2"
        in second_instruction
    )

    assert (
        "remaining_hypothesis_rounds_after_this=0"
        in second_instruction
    )

    assert (
        "final_hypothesis_round=true"
        in second_instruction
    )

    assert (
        "There is no future hypothesis-test replan"
        in second_instruction
    )

    assert (
        "READ_SOURCE"
        in second_instruction
    )

    assert (
        "source_hypothesis="
        in second_instruction
    )

    assert (
        HYPOTHESIS
        in second_instruction
    )

    assert (
        "source_hypothesis_material_basis_paths="
        in second_instruction
    )

    assert (
        planner.calls[
            0
        ]
        .instruction_hash
        != planner.calls[
            1
        ]
        .instruction_hash
    )


def test_final_hypothesis_round_rejects_missing_source_basis_read_before_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = prepare(
        tmp_path
    )

    planner = (
        FakePlanner(
            mode=(
                "wrong_basis"
            )
        )
    )

    evaluator = (
        FakeEvaluator()
    )

    executed = []

    def forbidden_executor(
        *args,
        **kwargs,
    ):
        executed.append(
            (
                args,
                kwargs,
            )
        )

        raise AssertionError(
            "missing hypothesis source-basis "
            "coverage must fail before execution"
        )

    monkeypatch.setattr(
        coordinator_module,
        "execute_investigation_operation",
        forbidden_executor,
    )

    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match=(
            "selected source-backed "
            "hypothesis basis path"
        ),
    ):
        run(
            fixture,
            investigator=(
                FakeInvestigator(
                    mode=(
                        "hypothesis"
                    )
                )
            ),
            planner=(
                planner
            ),
            evaluator=(
                evaluator
            ),
            value_limits=(
                limits(
                    investigator_rounds=1,
                    hypothesis_rounds=1,
                )
            ),
        )

    assert len(
        planner.calls
    ) == 1

    planner_instruction = (
        planner.calls[
            0
        ]
        .instruction
        .decode(
            "utf-8"
        )
    )

    assert (
        "final_hypothesis_round=true"
        in planner_instruction
    )

    assert (
        "source_hypothesis_material_basis_paths="
        in planner_instruction
    )

    assert (
        "pyproject.toml"
        in planner_instruction
    )

    assert evaluator.calls == []

    assert executed == []

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == fixture.base_model
    )


def test_final_hypothesis_round_rejects_discovery_only_plan_before_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fixture = prepare(
        tmp_path
    )

    planner = (
        FakePlanner(
            mode="search"
        )
    )

    evaluator = (
        FakeEvaluator()
    )

    executed = []

    def forbidden_executor(
        *args,
        **kwargs,
    ):
        executed.append(
            (
                args,
                kwargs,
            )
        )

        raise AssertionError(
            "final-round discovery-only plan "
            "must fail before repository execution"
        )

    monkeypatch.setattr(
        coordinator_module,
        "execute_investigation_operation",
        forbidden_executor,
    )

    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match=(
            "final hypothesis round requires "
            "at least one READ_SOURCE"
        ),
    ):
        run(
            fixture,
            investigator=(
                FakeInvestigator(
                    mode="hypothesis"
                )
            ),
            planner=planner,
            evaluator=evaluator,
            value_limits=(
                limits(
                    investigator_rounds=1,
                    hypothesis_rounds=1,
                )
            ),
        )

    assert len(
        planner.calls
    ) == 1

    assert evaluator.calls == []

    assert executed == []

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == fixture.base_model
    )

def test_remaining_model_budget_starts_with_full_aggregate_budget() -> None:
    remaining = (
        coordinator_module
        ._remaining_model_budget(
            Decimal(
                "0"
            ),
            limits=(
                limits(
                    total_model_cost=(
                        "2.700000"
                    )
                )
            ),
        )
    )

    assert (
        remaining
        == Decimal(
            "2.700000"
        )
    )


def test_remaining_model_budget_adapts_to_actual_spend() -> None:
    remaining = (
        coordinator_module
        ._remaining_model_budget(
            Decimal(
                "1.538588"
            ),
            limits=(
                limits(
                    total_model_cost=(
                        "2.700000"
                    )
                )
            ),
        )
    )

    assert (
        remaining
        == Decimal(
            "1.161412"
        )
    )


def test_remaining_model_budget_changes_after_each_actual_cost() -> None:
    value_limits = limits(
        total_model_cost=(
            "2.700000"
        )
    )

    first = (
        coordinator_module
        ._remaining_model_budget(
            Decimal(
                "0.500000"
            ),
            limits=(
                value_limits
            ),
        )
    )

    second = (
        coordinator_module
        ._remaining_model_budget(
            Decimal(
                "1.250000"
            ),
            limits=(
                value_limits
            ),
        )
    )

    assert (
        first
        == Decimal(
            "2.200000"
        )
    )

    assert (
        second
        == Decimal(
            "1.450000"
        )
    )

    assert second < first


def test_remaining_model_budget_fails_closed_when_budget_is_exhausted() -> None:
    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match=(
            "no model budget remains"
        ),
    ):
        (
            coordinator_module
            ._remaining_model_budget(
                Decimal(
                    "2.700000"
                ),
                limits=(
                    limits(
                        total_model_cost=(
                            "2.700000"
                        )
                    )
                ),
            )
        )


def test_remaining_model_budget_rejects_already_overspent_state() -> None:
    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match=(
            "already exceeds coordinator budget"
        ),
    ):
        (
            coordinator_module
            ._remaining_model_budget(
                Decimal(
                    "2.700001"
                ),
                limits=(
                    limits(
                        total_model_cost=(
                            "2.700000"
                        )
                    )
                ),
            )
        )


@pytest.mark.parametrize(
    "current",
    [
        Decimal("-0.000001"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_remaining_model_budget_rejects_invalid_current_cost(
    current: Decimal,
) -> None:
    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match=(
            "finite nonnegative Decimal"
        ),
    ):
        (
            coordinator_module
            ._remaining_model_budget(
                current,
                limits=(
                    limits(
                        total_model_cost=(
                            "2.700000"
                        )
                    )
                ),
            )
        )

def test_autonomous_model_calls_use_remaining_aggregate_budget_not_fixed_caps(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    investigator = (
        FakeInvestigator()
    )

    planner = (
        FakePlanner()
    )

    evaluator = (
        FakeEvaluator()
    )

    result = run(
        fixture,
        investigator=(
            investigator
        ),
        planner=(
            planner
        ),
        evaluator=(
            evaluator
        ),
        value_limits=(
            limits(
                total_model_cost=(
                    "0.050000"
                )
            )
        ),

        # Deliberately far below every fake model's
        # actual $0.001000 cost.
        #
        # If the legacy fixed caps still controlled
        # authorization, this run would fail.
        legacy_cost_cap=(
            "0.000001"
        ),
    )

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .PROMOTED
    )

    assert (
        result.total_model_cost_usd
        == Decimal(
            "0.005000"
        )
    )

    assert [
        call.cost_cap_usd
        for call
        in investigator.calls
    ] == [
        Decimal(
            "0.050000"
        ),
        Decimal(
            "0.048000"
        ),
    ]

    assert [
        call.cost_cap_usd
        for call
        in planner.calls
    ] == [
        Decimal(
            "0.049000"
        ),
        Decimal(
            "0.047000"
        ),
    ]

    assert [
        call.cost_cap_usd
        for call
        in evaluator.calls
    ] == [
        Decimal(
            "0.046000"
        ),
    ]

    assert all(
        call.cost_cap_usd
        > Decimal(
            "0.000001"
        )
        for call
        in (
            *investigator.calls,
            *planner.calls,
            *evaluator.calls,
        )
    )


def test_coordinator_fails_before_next_model_call_when_aggregate_budget_exhausted(
    tmp_path: Path,
) -> None:
    fixture = prepare(
        tmp_path
    )

    investigator = (
        FakeInvestigator()
    )

    planner = (
        FakePlanner()
    )

    evaluator = (
        FakeEvaluator()
    )

    with pytest.raises(
        RepositorySemanticUnderstandingCoordinatorError,
        match=(
            "no model budget remains"
        ),
    ):
        run(
            fixture,
            investigator=(
                investigator
            ),
            planner=(
                planner
            ),
            evaluator=(
                evaluator
            ),
            value_limits=(
                limits(
                    total_model_cost=(
                        "0.003000"
                    )
                )
            ),
            legacy_cost_cap=(
                "99.000000"
            ),
        )

    #
    # Exact call sequence before exhaustion:
    #
    # investigator #1 -> $0.001
    # planner      #1 -> $0.001
    # investigator #2 -> $0.001
    #
    # Aggregate budget is now zero.
    #
    # The hypothesis-test planner MUST NOT be
    # dispatched.
    #
    assert len(
        investigator.calls
    ) == 2

    assert len(
        planner.calls
    ) == 1

    assert len(
        evaluator.calls
    ) == 0

    assert (
        investigator.calls[
            0
        ].cost_cap_usd
        == Decimal(
            "0.003000"
        )
    )

    assert (
        planner.calls[
            0
        ].cost_cap_usd
        == Decimal(
            "0.002000"
        )
    )

    assert (
        investigator.calls[
            1
        ].cost_cap_usd
        == Decimal(
            "0.001000"
        )
    )




def test_repaired_two_round_hypothesis_loop_is_coherent_offline(
    tmp_path: Path,
) -> None:
    from horizon.investigation.typed_planner_operational_evidence import (
        TypedPlannerSourceObservationView,
    )
    from horizon.investigation.typed_planner_request_view import (
        make_typed_planner_request_view,
    )

    followup_question = (
        "Which exact pyproject.toml source passage "
        "provides the remaining source-backed basis?"
    )

    fixture = prepare(
        tmp_path
    )

    class CoherentPlanner:
        def __init__(
            self,
        ) -> None:
            self.calls = []
            self.source_contexts = []

        def invoke(
            self,
            invocation,
        ):
            self.calls.append(
                invocation
            )

            call_number = len(
                self.calls
            )

            proposal = (
                invocation.proposal
            )

            assert (
                len(
                    proposal
                    .investigation_questions
                )
                == 1
            )

            question = (
                proposal
                .investigation_questions[
                    0
                ]
            )

            instruction = (
                invocation
                .instruction
                .decode(
                    "utf-8"
                )
            )

            assert (
                "source_hypothesis="
                in instruction
            )

            assert (
                HYPOTHESIS
                in instruction
            )

            assert (
                'source_hypothesis_material_basis_paths='
                '["pyproject.toml"]'
                in instruction
            )

            request_view = (
                make_typed_planner_request_view(
                    invocation.request
                )
            )

            source_contexts = tuple(
                record.operational_context
                for record
                in request_view.evidence_records
                if isinstance(
                    record.operational_context,
                    TypedPlannerSourceObservationView,
                )
            )

            self.source_contexts.append(
                source_contexts
            )

            if call_number == 1:
                assert (
                    question
                    == TEST_QUESTION
                )

                assert (
                    "current_hypothesis_round=1"
                    in instruction
                )

                assert (
                    "final_hypothesis_round=false"
                    in instruction
                )

                assert source_contexts == ()

                path = "README.md"

            elif call_number == 2:
                assert (
                    question
                    == followup_question
                )

                assert (
                    "current_hypothesis_round=2"
                    in instruction
                )

                assert (
                    "final_hypothesis_round=true"
                    in instruction
                )

                assert (
                    len(
                        source_contexts
                    )
                    == 1
                )

                previous = (
                    source_contexts[
                        0
                    ]
                )

                assert (
                    previous.path
                    == "README.md"
                )

                assert (
                    previous.start_line
                    == 1
                )

                assert (
                    previous.end_line
                    == 2
                )

                assert (
                    previous.line_count
                    == 2
                )

                assert (
                    previous.visible_line_count
                    == 2
                )

                assert (
                    previous.omitted_line_count
                    == 0
                )

                assert (
                    previous.selection_mode
                    == "ALL"
                )

                assert (
                    previous.observed_source_line_count
                    == 2
                )

                assert (
                    previous.ends_at_observed_eof
                    is True
                )

                assert tuple(
                    line.line_text
                    for line
                    in previous.lines
                ) == (
                    (
                        "Semantic Demo provides workflow "
                        "orchestration software."
                    ),
                    (
                        "It coordinates and executes "
                        "declared workflow tasks."
                    ),
                )

                #
                # R34 final-round source-basis closure:
                # the selected hypothesis basis is pyproject.toml,
                # so the final round materializes that exact path.
                #
                path = "pyproject.toml"

            else:
                raise AssertionError(
                    "certification permits exactly "
                    "two hypothesis planner calls"
                )

            output = {
                "proposal_id": (
                    proposal.proposal_id
                ),
                "question_id": (
                    invocation
                    .request
                    .question_id
                ),
                "bindings": [
                    {
                        "investigation_question": (
                            question
                        ),
                        "step_key": (
                            "certify_round_"
                            + str(
                                call_number
                            )
                        ),
                        "purpose": (
                            "Gather complete frozen "
                            "source evidence."
                        ),
                        "operation": {
                            "type": (
                                "READ_SOURCE"
                            ),
                            "path": path,
                            "start_line": 1,

                            #
                            # R35:
                            # Horizon, not the planner,
                            # resolves actual frozen EOF.
                            #
                            "end_line": None,
                        },
                        "depends_on_keys": [],
                        "expected_information": (
                            "Complete observed source "
                            "through repository EOF."
                        ),
                        "max_seconds": 5,
                    },
                ],
            }

            return (
                SemanticGapTypedPlannerModelResult(
                    provider=(
                        "R38_FAKE_PLANNER"
                    ),
                    model_id=(
                        "r38-fake-planner-v1"
                    ),
                    output=output,
                    input_tokens=10,
                    output_tokens=5,
                    cost_usd=Decimal(
                        "0.001000"
                    ),
                    api_request_id=(
                        "r38-fake-planner-"
                        + str(
                            call_number
                        )
                    ),
                )
            )

    class CoherentEvaluator:
        def __init__(
            self,
        ) -> None:
            self.calls = []
            self.verdicts = []

        def invoke(
            self,
            invocation,
        ):
            self.calls.append(
                invocation
            )

            call_number = len(
                self.calls
            )

            request = (
                invocation.request
            )

            source_records = tuple(
                record
                for record
                in request.evidence_records
                if (
                    record.evidence_id
                    .startswith(
                        "investigation-source-observation:"
                    )
                )
            )

            source_ids = tuple(
                record.evidence_id
                for record
                in source_records
            )

            if call_number == 1:
                assert (
                    len(
                        source_records
                    )
                    == 1
                )

                payload = json.loads(
                    source_records[
                        0
                    ].canonical_payload
                )

                assert (
                    payload[
                        "path"
                    ]
                    == "README.md"
                )

                assert (
                    payload[
                        "ends_at_observed_eof"
                    ]
                    is True
                )

                assert (
                    payload[
                        "end_line"
                    ]
                    == payload[
                        "observed_source_line_count"
                    ]
                )

                verdict = (
                    "STILL_INCOMPLETE"
                )

                supporting = [
                    source_ids[
                        0
                    ],
                ]

                missing = [
                    followup_question,
                ]

            elif call_number == 2:
                assert (
                    len(
                        source_records
                    )
                    == 2
                )

                payloads = tuple(
                    json.loads(
                        record.canonical_payload
                    )
                    for record
                    in source_records
                )

                assert {
                    payload[
                        "path"
                    ]
                    for payload
                    in payloads
                } == {
                    "README.md",
                    "pyproject.toml",
                }

                assert all(
                    payload[
                        "ends_at_observed_eof"
                    ]
                    is True
                    for payload
                    in payloads
                )

                assert all(
                    payload[
                        "end_line"
                    ]
                    == payload[
                        "observed_source_line_count"
                    ]
                    for payload
                    in payloads
                )

                verdict = "SUPPORTED"

                #
                # Promotion support is exclusively canonical
                # material READ_SOURCE evidence gathered by
                # the coordinator.
                #
                supporting = list(
                    source_ids
                )

                missing = []

            else:
                raise AssertionError(
                    "certification permits exactly "
                    "two evaluator calls"
                )

            self.verdicts.append(
                verdict
            )

            return (
                HypothesisEvaluationModelResult(
                    provider=(
                        "R38_FAKE_EVALUATOR"
                    ),
                    model_id=(
                        "r38-fake-evaluator-v1"
                    ),
                    output={
                        "request_id": (
                            request.request_id
                        ),
                        "question_id": (
                            request.question_id
                        ),
                        "source_proposal_id": (
                            invocation
                            .source_proposal
                            .proposal_id
                        ),
                        "verdict": verdict,
                        "supporting_evidence_ids": (
                            supporting
                        ),
                        "contradicting_evidence_ids": [],
                        "missing_evidence_questions": (
                            missing
                        ),
                    },
                    input_tokens=10,
                    output_tokens=5,
                    cost_usd=Decimal(
                        "0.001000"
                    ),
                    api_request_id=(
                        "r38-fake-evaluator-"
                        + str(
                            call_number
                        )
                    ),
                )
            )

    planner = CoherentPlanner()

    evaluator = CoherentEvaluator()

    result = run(
        fixture,
        investigator=(
            FakeInvestigator(
                mode="hypothesis"
            )
        ),
        planner=(
            planner
        ),
        evaluator=(
            evaluator
        ),
        value_limits=(
            limits(
                investigator_rounds=1,
                hypothesis_rounds=2,
            )
        ),
    )

    #
    # --------------------------------------------------------
    # R33:
    # hypothesis and source basis survived planning.
    #
    # R34:
    # final round successfully satisfied pyproject.toml
    # source-basis READ_SOURCE closure.
    #
    # R35:
    # both reads used end_line=None and were resolved to EOF.
    #
    # R36:
    # evaluator's exact missing question became round 2's
    # exact planning question.
    #
    # R37:
    # round 2 saw bounded semantic content from round 1.
    #
    # Promotion:
    # only material executed READ_SOURCE IDs supported it.
    # --------------------------------------------------------
    #

    assert (
        result.disposition
        is RepositorySemanticUnderstandingDisposition
        .PROMOTED
    )

    assert (
        result.hypothesis_rounds_completed
        == 2
    )

    assert (
        len(
            planner.calls
        )
        == 2
    )

    assert (
        len(
            evaluator.calls
        )
        == 2
    )

    assert (
        evaluator.verdicts
        == [
            "STILL_INCOMPLETE",
            "SUPPORTED",
        ]
    )

    assert (
        planner.calls[
            0
        ]
        .proposal
        .investigation_questions
        == (
            TEST_QUESTION,
        )
    )

    assert (
        planner.calls[
            1
        ]
        .proposal
        .investigation_questions
        == (
            followup_question,
        )
    )

    assert (
        planner.calls[
            0
        ]
        .proposal
        .investigation_questions
        != planner.calls[
            1
        ]
        .proposal
        .investigation_questions
    )

    assert (
        len(
            planner.source_contexts[
                0
            ]
        )
        == 0
    )

    assert (
        len(
            planner.source_contexts[
                1
            ]
        )
        == 1
    )

    assert (
        len(
            result.operation_observation_ids
        )
        == 2
    )

    assert (
        result.evaluation
        is not None
    )

    assert (
        result.evaluation.verdict
        is HypothesisEvaluationVerdict
        .SUPPORTED
    )

    assert (
        len(
            result.evaluation
            .supporting_evidence_ids
        )
        == 2
    )

    assert all(
        evidence_id.startswith(
            "investigation-source-observation:"
        )
        for evidence_id
        in result.evaluation
        .supporting_evidence_ids
    )

    assert (
        len(
            result.final_model
            .what_it_is_assertion_ids
        )
        == 1
    )

    assert (
        result.final_model
        != fixture.base_model
    )

    assert (
        result.persisted_overlay_path
        is not None
    )

    assert (
        fixture.store.load(
            fixture.base_model
        )
        == result.final_model
    )

    remaining = {
        question.section
        for question
        in discover_repository_semantic_gaps(
            fixture.index,
            result.final_model,
        ).questions
    }

    assert (
        RepositorySemanticGapSection
        .WHAT_IT_IS
        not in remaining
    )
