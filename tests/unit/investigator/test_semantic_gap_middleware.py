from __future__ import annotations

import dataclasses
import json
import subprocess

from pathlib import Path

import pytest

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.investigation.semantic_gap import (
    RepositorySemanticGapSection,
    discover_repository_semantic_gaps,
)
from horizon.investigator.middleware import (
    CanonicalEvidenceRecord,
    InvestigationMiddlewareError,
    InvestigationRequestOrigin,
    compile_semantic_gap_investigation_request,
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


def git(
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


def create_repository(
    tmp_path: Path,
) -> Path:
    repository = (
        tmp_path
        / "repo"
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

    return repository


def commit_all(
    repository: Path,
    message: str = "fixture",
) -> str:
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
        message,
    )

    return git(
        repository,
        "rev-parse",
        "HEAD",
    )


def record(
    evidence_id: str,
    evidence_kind: str,
    payload: object,
) -> CanonicalEvidenceRecord:
    return CanonicalEvidenceRecord(
        evidence_id=evidence_id,
        evidence_kind=evidence_kind,
        canonical_payload=json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ),
    )


def prepare(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "pyproject.toml"
    ).write_text(
        """\
[project]
name = "acme"
version = "1.0.0"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2,<3",
]

[tool.hatch.build.targets.wheel]
packages = ["src/acme"]
""",
        encoding="utf-8",
    )

    package = (
        repository
        / "src"
        / "acme"
    )

    package.mkdir(
        parents=True
    )

    (
        package
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    index = index_python_repository(
        repository,
        observation,
        cache,
    )

    blob = read_observed_blob(
        repository,
        observation,
        "pyproject.toml",
    )

    layout = (
        discover_hatch_wheel_import_roots(
            blob
        )
    )

    dependencies = (
        discover_declared_project_dependencies(
            blob
        )
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    question = next(
        value
        for value
        in gaps.questions
        if value.section
        is RepositorySemanticGapSection.WHAT_IT_IS
    )

    root = layout.import_roots[0]

    records = (
        record(
            blob.evidence_id,
            "GIT_BLOB",
            {
                "path": blob.path,
                "commit_sha": blob.commit_sha,
                "repository_observation_id": (
                    blob.repository_observation_id
                ),
                "object_id": blob.object_id,
                "content_utf8": (
                    blob.content.decode(
                        "utf-8"
                    )
                ),
            },
        ),
        record(
            layout.layout_id,
            "PYTHON_PACKAGE_LAYOUT",
            {
                "source_evidence_id": (
                    layout.source_evidence_id
                ),
                "import_roots": [
                    value.evidence_id
                    for value
                    in layout.import_roots
                ],
            },
        ),
        record(
            root.evidence_id,
            "PYTHON_IMPORT_ROOT",
            {
                "root_path": root.root_path,
                "package_path": (
                    root.package_path
                ),
                "top_level_package": (
                    root.top_level_package
                ),
                "source_evidence_id": (
                    root.source_evidence_id
                ),
            },
        ),
        record(
            dependencies.evidence_id,
            "DECLARED_PROJECT_DEPENDENCIES",
            {
                "project_name": (
                    dependencies.project_name
                ),
                "dependencies": list(
                    dependencies.dependencies
                ),
                "source_evidence_id": (
                    dependencies.source_evidence_id
                ),
            },
        ),
    )

    return (
        repository,
        observation,
        index,
        model,
        question,
        records,
    )


def test_semantic_gap_compiles_to_investigator_request_without_fake_relationship(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    request = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=records,
        )
    )

    assert request.origin is (
        InvestigationRequestOrigin.REPOSITORY_SEMANTIC_GAP
    )

    assert (
        request.question_id
        == question.question_id
    )

    assert (
        request.question
        == question.question
    )

    assert request.relationship_id is None
    assert request.relationship_kind is None
    assert request.relationship_reason is None

    assert (
        request.semantic_gap_id
        == question.gap_id
    )

    assert (
        request.semantic_gap_section
        == question.section.value
    )


def test_semantic_gap_request_contains_exact_bounded_world_model_context(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    request = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=records,
        )
    )

    assert (
        request.assertion_ids
        == question.context_assertion_ids
    )

    assert (
        request.claim_ids
        == question.context_claim_ids
    )

    assert (
        request.assessment_ids
        == question.context_assessment_ids
    )

    assert (
        request.evidence_reference_ids
        == question.context_evidence_reference_ids
    )


def test_semantic_gap_request_contains_canonical_evidence_content_not_only_ids(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    request = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=records,
        )
    )

    assert len(
        request.evidence_records
    ) == 4

    assert all(
        value.canonical_payload
        for value
        in request.evidence_records
    )

    payloads = {
        value.evidence_id:
        value.canonical_payload
        for value
        in request.evidence_records
    }

    assert any(
        "pyproject.toml"
        in payload
        for payload
        in payloads.values()
    )

    assert any(
        "httpx"
        in payload
        for payload
        in payloads.values()
    )


def test_unrelated_evidence_record_is_not_leaked_into_request(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    unrelated = CanonicalEvidenceRecord(
        evidence_id=(
            "static-evidence:unrelated"
        ),
        evidence_kind="STATIC",
        canonical_payload=(
            '{"value":"unrelated"}'
        ),
    )

    request = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=(
                unrelated,
                *records,
            ),
        )
    )

    assert (
        "static-evidence:unrelated"
        not in {
            value.evidence_id
            for value
            in request.evidence_records
        }
    )


def test_missing_canonical_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    with pytest.raises(
        InvestigationMiddlewareError,
        match="canonical evidence content is missing",
    ):
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=(
                records[:-1]
            ),
        )


def test_duplicate_canonical_evidence_identity_fails_closed(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    with pytest.raises(
        InvestigationMiddlewareError,
        match="duplicate canonical evidence identity",
    ):
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=(
                records
                + (
                    records[0],
                )
            ),
        )


def test_forged_gap_context_fails_closed(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    forged = dataclasses.replace(
        question,
        context_claim_ids=(),
    )

    with pytest.raises(
        InvestigationMiddlewareError,
        match="context",
    ):
        compile_semantic_gap_investigation_request(
            forged,
            model=model,
            evidence_records=records,
        )


def test_gap_and_world_model_must_share_exact_snapshot(
    tmp_path: Path,
) -> None:
    (
        repository,
        _,
        _,
        _,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    (
        repository
        / "later.py"
    ).write_text(
        "value = 2\n",
        encoding="utf-8",
    )

    second_commit = commit_all(
        repository,
        "second",
    )

    second_observation = (
        observe_git_commit(
            repository,
            second_commit,
        )
    )

    second_cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache-second"
        )
    )

    second_index = (
        index_python_repository(
            repository,
            second_observation,
            second_cache,
        )
    )

    second_model = (
        build_repository_deterministic_world_model(
            second_index
        )
    )

    with pytest.raises(
        InvestigationMiddlewareError,
        match="snapshot",
    ):
        compile_semantic_gap_investigation_request(
            question,
            model=second_model,
            evidence_records=records,
        )


def test_semantic_gap_request_is_deterministic_and_record_order_independent(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    first = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=records,
        )
    )

    second = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=tuple(
                reversed(
                    records
                )
            ),
        )
    )

    assert first == second

    assert first.request_id.startswith(
        "investigation-request:"
    )


def test_empty_world_model_semantic_gap_can_compile_with_empty_context(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "value = 1\n",
        encoding="utf-8",
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "empty-cache"
        )
    )

    index = index_python_repository(
        repository,
        observation,
        cache,
    )

    model = (
        build_repository_deterministic_world_model(
            index
        )
    )

    gaps = (
        discover_repository_semantic_gaps(
            index,
            model,
        )
    )

    question = next(
        value
        for value
        in gaps.questions
        if value.section
        is RepositorySemanticGapSection.WHAT_IT_IS
    )

    request = (
        compile_semantic_gap_investigation_request(
            question,
            model=model,
            evidence_records=(),
        )
    )

    assert request.assertion_ids == ()
    assert request.claim_ids == ()
    assert request.assessment_ids == ()
    assert request.evidence_reference_ids == ()
    assert request.evidence_records == ()

    assert request.relationship_id is None

    assert (
        request.semantic_gap_id
        == question.gap_id
    )


def test_request_compilation_does_not_mutate_gap_or_world_model(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        model,
        question,
        records,
    ) = prepare(
        tmp_path
    )

    question_before = question
    snapshot_before = model.snapshot

    compile_semantic_gap_investigation_request(
        question,
        model=model,
        evidence_records=records,
    )

    assert question == question_before
    assert model.snapshot == snapshot_before
