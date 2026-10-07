from __future__ import annotations

import subprocess

from pathlib import Path

import pytest

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.claims.epistemic import (
    EpistemicStatus,
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
from horizon.world_model.assertion import (
    WorldModelRelationKind,
)
from horizon.world_model.repository_deterministic import (
    RepositoryDeterministicWorldModelError,
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
        "fixture",
    )

    return git(
        repository,
        "rev-parse",
        "HEAD",
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
name = "acme-distribution"
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

    return (
        repository,
        observation,
        blob,
        layout,
        dependencies,
        index,
    )


def test_package_and_dependency_evidence_become_world_model_assertions(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    assert len(
        model.snapshot.claims
    ) == 2

    assert len(
        model.snapshot.assessments
    ) == 2

    assert len(
        model.snapshot.assertions
    ) == 2

    assert len(
        model.where_it_sits_assertion_ids
    ) == 1

    assert len(
        model.what_it_depends_on_assertion_ids
    ) == 1


def test_all_automatic_deterministic_assessments_are_proven(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    assert all(
        assessment.status
        is EpistemicStatus.PROVEN
        for assessment
        in model.snapshot.assessments
    )


def test_package_placement_claim_preserves_exact_frozen_metadata(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    package_assertion_id = (
        model.where_it_sits_assertion_ids[0]
    )

    assertion = next(
        assertion
        for assertion
        in model.snapshot.assertions
        if assertion.assertion_id
        == package_assertion_id
    )

    claim = next(
        claim
        for claim
        in model.snapshot.claims
        if claim.claim_id
        == assertion.claim_id
    )

    assert (
        "declared Python package path is 'src/acme'"
        in claim.proposition
    )

    assert (
        "under import root 'src'"
        in claim.proposition
    )

    assert (
        "top-level package 'acme'"
        in claim.proposition
    )

    assert (
        assertion.subject_id
        == "python-package:acme"
    )

    assert (
        assertion.relation
        is WorldModelRelationKind.DEPENDS_ON
    )

    assert (
        assertion.object_id
        == "python-import-root:src"
    )


def test_dependency_claim_does_not_confuse_distribution_with_python_package(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    dependency_assertion_id = (
        model.what_it_depends_on_assertion_ids[0]
    )

    assertion = next(
        assertion
        for assertion
        in model.snapshot.assertions
        if assertion.assertion_id
        == dependency_assertion_id
    )

    claim = next(
        claim
        for claim
        in model.snapshot.claims
        if claim.claim_id
        == assertion.claim_id
    )

    assert (
        "project 'acme-distribution' declares 2 direct project dependencies"
        in claim.proposition
    )

    assert (
        assertion.subject_id
        == "python-project:acme-distribution"
    )

    assert (
        assertion.relation
        is WorldModelRelationKind.DEPENDS_ON
    )

    assert (
        assertion.object_id
        == dependencies.evidence_id
    )


def test_world_model_claims_trace_to_exact_pyproject_evidence(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    evidence_ids = {
        reference.evidence_id
        for claim
        in model.snapshot.claims
        for reference
        in claim.evidence
    }

    assert blob.evidence_id in evidence_ids

    assert layout.layout_id in evidence_ids

    assert dependencies.evidence_id in evidence_ids

    assert all(
        root.evidence_id
        in evidence_ids
        for root
        in layout.import_roots
    )


def test_only_dependency_relations_are_created(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    assert {
        assertion.relation
        for assertion
        in model.snapshot.assertions
    } == {
        WorldModelRelationKind.DEPENDS_ON
    }

    assert not any(
        assertion.relation
        is WorldModelRelationKind.OWNS_RESPONSIBILITY_FOR
        for assertion
        in model.snapshot.assertions
    )

    assert not any(
        assertion.relation
        is WorldModelRelationKind.AFFECTS_BEHAVIOR_OF
        for assertion
        in model.snapshot.assertions
    )

    assert not any(
        assertion.relation
        is WorldModelRelationKind.CALLS
        for assertion
        in model.snapshot.assertions
    )


def test_no_supported_evidence_produces_empty_world_model(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        _,
        _,
        _,
        index,
    ) = prepare(
        tmp_path
    )

    model = (
        build_repository_deterministic_world_model(
            index
        )
    )

    assert model.snapshot.claims == ()
    assert model.snapshot.assessments == ()
    assert model.snapshot.assertions == ()

    assert (
        model.where_it_sits_assertion_ids
        == ()
    )

    assert (
        model.what_it_depends_on_assertion_ids
        == ()
    )


def test_world_model_identity_is_deterministic(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    first = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    second = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    assert first == second

    assert (
        first.snapshot.snapshot_id
        == second.snapshot.snapshot_id
    )


def test_stale_pyproject_blob_is_rejected(
    tmp_path: Path,
) -> None:
    (
        repository,
        _,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    (
        repository
        / "other.py"
    ).write_text(
        "value = 1\n"
    )

    second_commit = commit_all(
        repository
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
            / "cache-2"
        )
    )

    second_index = (
        index_python_repository(
            repository,
            second_observation,
            second_cache,
        )
    )

    assert (
        second_index.repository_observation_id
        != blob.repository_observation_id
    )

    with pytest.raises(
        RepositoryDeterministicWorldModelError,
        match="snapshot",
    ):
        build_repository_deterministic_world_model(
            second_index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )


def test_layout_source_must_match_supplied_pyproject_blob(
    tmp_path: Path,
) -> None:
    (
        repository,
        observation,
        blob,
        layout,
        dependencies,
        index,
    ) = prepare(
        tmp_path
    )

    (
        repository
        / "alternate.toml"
    ).write_text(
        """\
[project]
name = "alternate"
version = "1.0.0"
dependencies = ["other"]

[tool.hatch.build.targets.wheel]
packages = ["src/other"]
""",
        encoding="utf-8",
    )

    git(
        repository,
        "add",
        "alternate.toml",
    )

    # The current frozen observation does not contain this working-tree
    # mutation. We deliberately forge no evidence here; the existing layout
    # must remain tied to the supplied exact pyproject blob.
    model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=blob,
            package_layout=layout,
            project_dependencies=dependencies,
        )
    )

    assert len(
        model.snapshot.assertions
    ) == 2

    assert (
        blob.repository_observation_id
        == observation.observation_id
    )
