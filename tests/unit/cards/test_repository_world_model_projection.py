from __future__ import annotations

import inspect
import subprocess

from pathlib import Path

import pytest

import horizon.cards.repository_auto as repository_auto_module

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.cards.repository import (
    RepositoryCardError,
    RepositorySemanticSection,
    build_repository_card,
)
from horizon.cards.repository_auto import (
    build_repository_card_automatically,
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
    message: str,
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


def write_project(
    repository: Path,
) -> None:
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


def make_index(
    repository: Path,
    commit: str,
    cache_path: Path,
):
    observation = observe_git_commit(
        repository,
        commit,
    )

    cache = (
        ContentAddressedExtractionCache(
            cache_path
        )
    )

    index = index_python_repository(
        repository,
        observation,
        cache,
    )

    return observation, index


def prepare(
    tmp_path: Path,
):
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    commit = commit_all(
        repository,
        "first",
    )

    observation, index = make_index(
        repository,
        commit,
        tmp_path
        / "cache",
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

    return (
        repository,
        observation,
        index,
        blob,
        layout,
        dependencies,
        model,
    )


def state(
    card,
    section: RepositorySemanticSection,
):
    return next(
        value
        for value
        in card.semantic_sections
        if value.section
        is section
    )


def assertion_bundle(
    model,
    assertion_id: str,
):
    snapshot = model.snapshot

    assertion = next(
        value
        for value
        in snapshot.assertions
        if value.assertion_id
        == assertion_id
    )

    claim = next(
        value
        for value
        in snapshot.claims
        if value.claim_id
        == assertion.claim_id
    )

    assessment = next(
        value
        for value
        in snapshot.assessments
        if value.assessment_id
        == assertion.assessment_id
    )

    return (
        assertion,
        claim,
        assessment,
    )


def raw_basis_evidence_ids(
    claim,
    assessment,
) -> tuple[str, ...]:
    basis = set(
        assessment.basis_reference_ids
    )

    return tuple(
        sorted(
            {
                reference.evidence_id
                for reference
                in claim.evidence
                if reference.reference_id
                in basis
            }
        )
    )


def test_plain_card_has_no_repository_semantic_truth(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        _,
        _,
        _,
        _,
    ) = prepare(
        tmp_path
    )

    card = build_repository_card(
        index
    )

    assert all(
        value.status
        is EpistemicStatus.UNKNOWN
        for value
        in card.semantic_sections
    )


def test_card_builder_no_longer_accepts_raw_repository_evidence(
    tmp_path: Path,
) -> None:
    parameters = (
        inspect.signature(
            build_repository_card
        ).parameters
    )

    assert set(
        parameters
    ) == {
        "index",
        "world_model",
    }

    assert (
        "package_layout"
        not in parameters
    )

    assert (
        "project_dependencies"
        not in parameters
    )


def test_where_it_sits_is_projected_from_canonical_claim(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        _,
        _,
        _,
        model,
    ) = prepare(
        tmp_path
    )

    card = build_repository_card(
        index,
        world_model=model,
    )

    where = state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    (
        _,
        claim,
        assessment,
    ) = assertion_bundle(
        model,
        model.where_it_sits_assertion_ids[0],
    )

    assert (
        where.status
        is assessment.status
    )

    assert (
        where.reason
        == claim.proposition
    )

    assert (
        where.evidence_ids
        == raw_basis_evidence_ids(
            claim,
            assessment,
        )
    )


def test_dependencies_are_projected_from_canonical_claim(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        _,
        _,
        _,
        model,
    ) = prepare(
        tmp_path
    )

    card = build_repository_card(
        index,
        world_model=model,
    )

    depends = state(
        card,
        RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
    )

    (
        _,
        claim,
        assessment,
    ) = assertion_bundle(
        model,
        model.what_it_depends_on_assertion_ids[0],
    )

    assert (
        depends.status
        is assessment.status
    )

    assert (
        depends.reason
        == claim.proposition
    )

    assert (
        depends.evidence_ids
        == raw_basis_evidence_ids(
            claim,
            assessment,
        )
    )


def test_unselected_sections_remain_unknown(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        _,
        _,
        _,
        model,
    ) = prepare(
        tmp_path
    )

    card = build_repository_card(
        index,
        world_model=model,
    )

    for section in (
        RepositorySemanticSection.WHAT_IT_IS,
        RepositorySemanticSection.WHAT_IT_OWNS,
        RepositorySemanticSection.WHAT_MUST_REMAIN_TRUE,
    ):
        assert (
            state(
                card,
                section,
            ).status
            is EpistemicStatus.UNKNOWN
        )


def test_card_rejects_world_model_from_different_repository_snapshot(
    tmp_path: Path,
) -> None:
    (
        repository,
        _,
        _,
        _,
        _,
        _,
        model,
    ) = prepare(
        tmp_path
    )

    (
        repository
        / "second.py"
    ).write_text(
        "value = 2\n",
        encoding="utf-8",
    )

    second_commit = commit_all(
        repository,
        "second",
    )

    _, second_index = make_index(
        repository,
        second_commit,
        tmp_path
        / "cache-second",
    )

    with pytest.raises(
        RepositoryCardError,
        match="snapshot",
    ):
        build_repository_card(
            second_index,
            world_model=model,
        )


def test_automatic_card_materializes_world_model_before_projection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (
        repository,
        observation,
        index,
        _,
        _,
        _,
        _,
    ) = prepare(
        tmp_path
    )

    original = (
        repository_auto_module
        .build_repository_deterministic_world_model
    )

    calls = 0

    def counted(
        *args,
        **kwargs,
    ):
        nonlocal calls

        calls += 1

        return original(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        repository_auto_module,
        "build_repository_deterministic_world_model",
        counted,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    assert calls == 1

    assert (
        state(
            card,
            RepositorySemanticSection.WHERE_IT_SITS,
        ).status
        is EpistemicStatus.PROVEN
    )

    assert (
        state(
            card,
            RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
        ).status
        is EpistemicStatus.PROVEN
    )


def test_card_identity_stays_stable_when_world_model_is_projected(
    tmp_path: Path,
) -> None:
    (
        _,
        _,
        index,
        _,
        _,
        _,
        model,
    ) = prepare(
        tmp_path
    )

    plain = build_repository_card(
        index
    )

    projected = build_repository_card(
        index,
        world_model=model,
    )

    assert (
        plain.card_id
        == projected.card_id
    )

    assert (
        plain.revision_id
        != projected.revision_id
    )
