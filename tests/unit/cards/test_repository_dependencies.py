from __future__ import annotations

import subprocess

from pathlib import Path

import horizon.cards.repository_auto as repository_auto_module

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.cards.repository import (
    RepositorySemanticSection,
    build_repository_card,
    render_repository_card,
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


def write_project(
    repository: Path,
    *,
    hatch: bool = True,
    include_dependencies: bool = True,
) -> None:
    hatch_text = ""

    if hatch:
        hatch_text = """\

[tool.hatch.build.targets.wheel]
packages = ["src/acme"]
"""

    dependencies_text = ""

    if include_dependencies:
        dependencies_text = """\
dependencies = [
    "httpx>=0.27",
    "pydantic>=2,<3",
]
"""

    (
        repository
        / "pyproject.toml"
    ).write_text(
        (
            "[project]\n"
            'name = "acme"\n'
            'version = "1.0.0"\n'
            + dependencies_text
            + """
[project.optional-dependencies]
aws = [
    "boto3>=1",
    "botocore>=1",
]

[dependency-groups]
dev = [
    "pytest>=9",
    "ruff>=1",
]
"""
            + hatch_text
        ),
        encoding="utf-8",
    )


def prepare(
    repository: Path,
    tmp_path: Path,
):
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

    return observation, index


def state(
    card,
    section: RepositorySemanticSection,
):
    return next(
        item
        for item
        in card.semantic_sections
        if item.section
        is section
    )


def test_direct_dependencies_automatically_prove_dependency_section(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    depends = state(
        card,
        RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
    )

    assert (
        depends.status
        is EpistemicStatus.PROVEN
    )

    assert (
        "project 'acme' declares 2 direct project dependencies"
        in depends.reason
    )


def test_dependency_card_uses_exact_dependency_evidence_ids(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    blob = read_observed_blob(
        repository,
        observation,
        "pyproject.toml",
    )

    evidence = (
        discover_declared_project_dependencies(
            blob
        )
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    depends = state(
        card,
        RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
    )

    assert set(
        depends.evidence_ids
    ) == {
        evidence.source_evidence_id,
        evidence.evidence_id,
    }


def test_optional_and_dev_groups_do_not_inflate_card_count(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    depends = state(
        card,
        RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
    )

    assert (
        "declares 2 direct project dependencies"
        in depends.reason
    )

    assert "4 direct" not in depends.reason
    assert "6 direct" not in depends.reason


def test_dependencies_can_be_proven_without_supported_package_layout(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository,
        hatch=False,
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    where = state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    depends = state(
        card,
        RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
    )

    assert (
        where.status
        is EpistemicStatus.UNKNOWN
    )

    assert (
        depends.status
        is EpistemicStatus.PROVEN
    )


def test_missing_direct_dependency_declaration_remains_unknown(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository,
        include_dependencies=False,
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    where = state(
        card,
        RepositorySemanticSection.WHERE_IT_SITS,
    )

    depends = state(
        card,
        RepositorySemanticSection.WHAT_IT_DEPENDS_ON,
    )

    assert (
        where.status
        is EpistemicStatus.PROVEN
    )

    assert (
        depends.status
        is EpistemicStatus.UNKNOWN
    )

    assert depends.evidence_ids == ()


def test_dependency_enrichment_does_not_promote_purpose_ownership_or_invariants(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
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


def test_dependency_enrichment_changes_revision_not_card_identity(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    observation, index = prepare(
        repository,
        tmp_path,
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

    before = build_repository_card(
        index
    )

    after = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    assert (
        before.card_id
        == after.card_id
    )

    assert (
        before.revision_id
        != after.revision_id
    )


def test_render_exposes_dependency_evidence(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

    rendered = render_repository_card(
        card
    )

    assert (
        "WHAT IT DEPENDS ON"
        in rendered
    )

    assert (
        "project 'acme' declares 2 direct project dependencies"
        in rendered
    )

    assert (
        "declared-python-dependency-set:"
        in rendered
    )


def test_pyproject_is_read_once_for_both_deterministic_enrichments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = create_repository(
        tmp_path
    )

    write_project(
        repository
    )

    (
        repository
        / "src"
        / "acme"
    ).mkdir(
        parents=True
    )

    (
        repository
        / "src"
        / "acme"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    observation, index = prepare(
        repository,
        tmp_path,
    )

    original = (
        repository_auto_module
        .read_observed_blob
    )

    reads = 0

    def counted(
        *args,
        **kwargs,
    ):
        nonlocal reads

        reads += 1

        return original(
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        repository_auto_module,
        "read_observed_blob",
        counted,
    )

    card = (
        build_repository_card_automatically(
            repository,
            observation,
            index,
        )
    )

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

    assert reads == 1
