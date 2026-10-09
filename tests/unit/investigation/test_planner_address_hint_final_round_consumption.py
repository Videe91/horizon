from __future__ import annotations

import json
import subprocess

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
from horizon.investigation.plan import (
    InvestigationStepDraft,
    ReadSourceOperation,
)
from horizon.investigation.proposal_plan import (
    ProposedInvestigationStepDraft,
)
from horizon.investigation.semantic_understanding_coordinator import (
    _hypothesis_round_typed_planner_instruction,
    _validate_final_hypothesis_round_material_paths,
)
from horizon.investigation.typed_planner_address_hints import (
    compile_typed_planner_repository_address_hints,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    InvestigationProposalKind,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.python_index import (
    index_python_repository,
)


QUESTION_ONE = (
    "Which implementation or test passages establish what "
    "software-understanding assertions "
    "build_repository_deterministic_world_model produces and "
    "RepositorySemanticWorldModelStore.load restores?"
)

QUESTION_TWO = (
    "Which implementation or test passages demonstrate how changes "
    "in repository source or evidence are incorporated into updated "
    "World Model state and regenerated Cards over time?"
)

QUESTION_THREE = (
    "Which implementation or test passages demonstrate how AI agents "
    "receive or retrieve Cards or other software-understanding context "
    "beyond render_repository_card returning a string?"
)

QUESTIONS = (
    QUESTION_ONE,
    QUESTION_TWO,
    QUESTION_THREE,
)


def git(
    repository: Path,
    *arguments: str,
) -> str:
    completed = subprocess.run(
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

    return (
        completed
        .stdout
        .strip()
    )


def write(
    repository: Path,
    relative: str,
    text: str,
) -> None:
    path = (
        repository
        / relative
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        text,
        encoding="utf-8",
    )


def prepare_repository(
    tmp_path: Path,
):
    repository = (
        tmp_path
        / "repository"
    )

    repository.mkdir()

    git(
        repository,
        "init",
        "-q",
        "-b",
        "main",
    )

    git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    write(
        repository,
        "pyproject.toml",
        (
            "[project]\n"
            'name = "address-demo"\n'
            'version = "1.0.0"\n'
        ),
    )

    write(
        repository,
        (
            "src/acme/world_model/"
            "repository_deterministic.py"
        ),
        (
            "def build_repository_deterministic_world_model():\n"
            "    return 'deterministic-world-model'\n"
        ),
    )

    write(
        repository,
        (
            "src/acme/world_model/"
            "repository_semantic_store.py"
        ),
        (
            "class RepositorySemanticWorldModelStore:\n"
            "    def load(self):\n"
            "        return 'semantic-world-model'\n"
        ),
    )

    write(
        repository,
        "src/acme/cards/repository.py",
        (
            "def render_repository_card():\n"
            "    return 'repository-card'\n"
        ),
    )

    write(
        repository,
        "src/acme/cards/repository_auto.py",
        (
            "def build_repository_card_automatically():\n"
            "    return 'automatic-card'\n"
        ),
    )

    write(
        repository,
        (
            "tests/unit/world_model/"
            "test_repository_deterministic.py"
        ),
        (
            "def test_deterministic_world_model():\n"
            "    assert True\n"
        ),
    )

    write(
        repository,
        (
            "tests/unit/world_model/"
            "test_repository_semantic_store.py"
        ),
        (
            "def test_semantic_store_reload():\n"
            "    assert True\n"
        ),
    )

    write(
        repository,
        (
            "tests/unit/cards/"
            "test_repository_world_model_projection.py"
        ),
        (
            "def test_repository_world_model_projection():\n"
            "    assert True\n"
        ),
    )

    write(
        repository,
        (
            "tests/unit/cards/"
            "test_repository_card.py"
        ),
        (
            "def test_repository_card():\n"
            "    assert True\n"
        ),
    )

    git(
        repository,
        "add",
        "-A",
    )

    git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = git(
        repository,
        "rev-parse",
        "HEAD",
    )

    observation = (
        observe_git_commit(
            repository,
            commit,
        )
    )

    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    index = (
        index_python_repository(
            repository,
            observation,
            cache,
        )
    )

    return (
        repository,
        observation,
        index,
    )


def address_payload_from_instruction(
    instruction: bytes,
):
    text = instruction.decode(
        "utf-8"
    )

    prefix = (
        "repository_address_hints="
    )

    for line in text.splitlines():
        if line.startswith(
            prefix
        ):
            return json.loads(
                line[
                    len(
                        prefix
                    ):
                ]
            )

    raise AssertionError(
        "repository address hints missing"
    )


def choose_candidate(
    candidates,
    *,
    test_path: bool,
):
    matches = [
        candidate
        for candidate
        in candidates
        if (
            candidate[
                "test_path"
            ]
            is test_path
        )
    ]

    assert matches

    return matches[
        0
    ][
        "path"
    ]


def final_round_bindings_from_instruction(
    instruction: bytes,
):
    payload = (
        address_payload_from_instruction(
            instruction
        )
    )

    by_question = {
        value[
            "question"
        ]: value[
            "candidates"
        ]
        for value
        in payload[
            "questions"
        ]
    }

    assert set(
        by_question
    ) == set(
        QUESTIONS
    )

    #
    # Six-step sealed final-round budget:
    #
    # Q1:
    #   strongest implementation path
    #   strongest test path
    #
    # Q2:
    #   strongest implementation path
    #   strongest test path
    #
    # Q3:
    #   strongest implementation path
    #
    # Plus:
    #   exact declared source-hypothesis basis path
    #
    selections = (
        (
            QUESTION_ONE,
            choose_candidate(
                by_question[
                    QUESTION_ONE
                ],
                test_path=False,
            ),
        ),
        (
            QUESTION_ONE,
            choose_candidate(
                by_question[
                    QUESTION_ONE
                ],
                test_path=True,
            ),
        ),
        (
            QUESTION_TWO,
            choose_candidate(
                by_question[
                    QUESTION_TWO
                ],
                test_path=False,
            ),
        ),
        (
            QUESTION_TWO,
            choose_candidate(
                by_question[
                    QUESTION_TWO
                ],
                test_path=True,
            ),
        ),
        (
            QUESTION_THREE,
            choose_candidate(
                by_question[
                    QUESTION_THREE
                ],
                test_path=False,
            ),
        ),
        (
            QUESTION_ONE,
            "pyproject.toml",
        ),
    )

    bindings = tuple(
        ProposedInvestigationStepDraft(
            investigation_question=(
                question
            ),
            draft=InvestigationStepDraft(
                step_key=(
                    "read_"
                    + str(
                        number
                    )
                ),
                purpose=(
                    "Materialize exact frozen "
                    "source evidence from an "
                    "addressable final-round path."
                ),
                operation=(
                    ReadSourceOperation(
                        path=path,
                        start_line=1,
                        end_line=None,
                    )
                ),
                depends_on_keys=(),
                expected_information=(
                    "Complete observed source "
                    "through frozen repository EOF."
                ),
                max_seconds=5,
            ),
        )
        for number, (
            question,
            path,
        )
        in enumerate(
            selections,
            start=1,
        )
    )

    return bindings


def test_final_round_address_hints_can_drive_legal_material_reads(
    tmp_path: Path,
) -> None:
    (
        repository,
        observation,
        index,
    ) = prepare_repository(
        tmp_path
    )

    hints = (
        compile_typed_planner_repository_address_hints(
            index=index,
            planning_questions=(
                QUESTIONS
            ),
        )
    )

    instruction = (
        _hypothesis_round_typed_planner_instruction(
            b"BASE",
            current_round=2,
            max_rounds=2,
            source_hypothesis=(
                "The repository declares and implements "
                "software-understanding behavior."
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
        "navigation hints only"
        in instruction_text
    )

    assert (
        "They are NOT evidence"
        in instruction_text
    )

    bindings = (
        final_round_bindings_from_instruction(
            instruction
        )
    )

    assert len(
        bindings
    ) == 6

    paths = tuple(
        binding
        .draft
        .operation
        .path
        for binding
        in bindings
    )

    assert (
        "src/acme/world_model/repository_semantic_store.py"
        in paths
    )

    assert (
        "tests/unit/world_model/test_repository_semantic_store.py"
        in paths
    )

    assert (
        "src/acme/world_model/repository_deterministic.py"
        in paths
    )

    assert (
        "tests/unit/cards/test_repository_world_model_projection.py"
        in paths
    )

    assert (
        "src/acme/cards/repository.py"
        in paths
    )

    assert (
        "pyproject.toml"
        in paths
    )

    proposal = InvestigationProposal(
        kind=(
            InvestigationProposalKind
            .PROPOSE_INVESTIGATION
        ),
        question_id=(
            "repository-semantic-gap-question:test"
        ),
        relationship_id=None,
        assertion_ids=(),
        claim_ids=(),
        assessment_ids=(),
        evidence_reference_ids=(),
        investigation_questions=(
            QUESTIONS
        ),
    )

    #
    # This is the same production final-round fail-closed
    # validator used by the coordinator.
    #
    _validate_final_hypothesis_round_material_paths(
        proposal=proposal,
        bindings=bindings,
        final_round=True,
        source_basis_paths=(
            "pyproject.toml",
        ),
    )

    records = []

    for binding in bindings:
        observed = (
            execute_investigation_operation(
                repository,
                observation,
                binding
                .draft
                .operation,
            )
        )

        assert isinstance(
            observed,
            InvestigationSourceObservation,
        )

        assert (
            observed
            .ends_at_observed_eof
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

        records.append(
            record
        )

    assert len(
        records
    ) == 6

    assert len(
        {
            record.evidence_id
            for record
            in records
        }
    ) == 6

    assert all(
        record.evidence_id.startswith(
            "investigation-source-observation:"
        )
        for record
        in records
    )
