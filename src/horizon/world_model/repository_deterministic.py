"""Deterministic repository evidence materialized into the World Model.

This module adds no new inference.

It converts already-established repository evidence into Horizon's
canonical claim -> assessment -> assertion -> snapshot representation.

Current deterministic mappings:

- explicit Python package placement
      -> DEPENDS_ON import root

- direct PEP 621 project dependency declaration
      -> DEPENDS_ON declared dependency set

No purpose, responsibility ownership, runtime behavior, or invariant
assertion is manufactured here.
"""

from __future__ import annotations

from dataclasses import dataclass

from horizon.claims.evidence_backed import (
    ClaimEvidenceKind,
    ClaimEvidenceRelation,
    EvidenceBackedClaim,
    make_claim_evidence_reference,
    make_evidence_backed_claim,
)
from horizon.claims.epistemic import (
    EpistemicAssessment,
    EpistemicStatus,
    make_epistemic_assessment,
)
from horizon.languages.python.project_dependencies import (
    PythonDeclaredProjectDependenciesEvidence,
)
from horizon.languages.python.repository_modules import (
    PythonImportRootEvidence,
    PythonPackageLayoutEvidence,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)
from horizon.repository.python_index import (
    PythonRepositoryIndex,
)
from horizon.world_model.assertion import (
    WorldModelAssertion,
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.snapshot import (
    WorldModelSnapshot,
    make_world_model_snapshot,
)


class RepositoryDeterministicWorldModelError(
    ValueError
):
    """Repository evidence cannot be bound safely into one World Model."""


@dataclass(
    frozen=True,
    slots=True,
)
class RepositoryDeterministicWorldModel:
    source_commit: str
    repository_observation_id: str

    snapshot: WorldModelSnapshot

    where_it_sits_assertion_ids: tuple[
        str,
        ...,
    ]

    what_it_depends_on_assertion_ids: tuple[
        str,
        ...,
    ]


def _support(
    evidence_id: str,
):
    return make_claim_evidence_reference(
        ClaimEvidenceKind.STATIC,
        ClaimEvidenceRelation.SUPPORTS,
        evidence_id,
    )


def _scope(
    index: PythonRepositoryIndex,
) -> str:
    return (
        "Exact repository observation "
        + index.repository_observation_id
        + " at frozen commit "
        + index.commit_sha
        + "."
    )


def _package_bundle(
    *,
    index: PythonRepositoryIndex,
    pyproject_blob: GitBlobEvidence,
    layout: PythonPackageLayoutEvidence,
    root: PythonImportRootEvidence,
) -> tuple[
    EvidenceBackedClaim,
    EpistemicAssessment,
    WorldModelAssertion,
]:
    import_root = (
        root.root_path
        if root.root_path
        else "<repository-root>"
    )

    evidence = (
        _support(
            pyproject_blob.evidence_id
        ),
        _support(
            layout.layout_id
        ),
        _support(
            root.evidence_id
        ),
    )

    claim = make_evidence_backed_claim(
        (
            "At frozen commit "
            + index.commit_sha
            + ", the declared Python package path is "
            + repr(
                root.package_path
            )
            + ", under import root "
            + repr(
                import_root
            )
            + ", with top-level package "
            + repr(
                root.top_level_package
            )
            + "."
        ),
        scope=_scope(
            index
        ),
        evidence=evidence,
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.PROVEN,
        rationale=(
            "Horizon derived the package layout from the exact observed "
            "pyproject.toml blob at the frozen commit."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        (
            "python-package:"
            + root.top_level_package
        ),
        WorldModelRelationKind.DEPENDS_ON,
        (
            "python-import-root:"
            + import_root
        ),
        claim=claim,
        assessment=assessment,
    )

    return (
        claim,
        assessment,
        assertion,
    )


def _dependency_bundle(
    *,
    index: PythonRepositoryIndex,
    pyproject_blob: GitBlobEvidence,
    dependencies: PythonDeclaredProjectDependenciesEvidence,
) -> tuple[
    EvidenceBackedClaim,
    EpistemicAssessment,
    WorldModelAssertion,
]:
    evidence = (
        _support(
            pyproject_blob.evidence_id
        ),
        _support(
            dependencies.evidence_id
        ),
    )

    claim = make_evidence_backed_claim(
        (
            "At frozen commit "
            + index.commit_sha
            + ", project "
            + repr(
                dependencies.project_name
            )
            + " declares "
            + str(
                dependencies.dependency_count
            )
            + " direct project dependencies in pyproject.toml."
        ),
        scope=_scope(
            index
        ),
        evidence=evidence,
    )

    assessment = make_epistemic_assessment(
        claim,
        EpistemicStatus.PROVEN,
        rationale=(
            "The dependency count and declarations come directly from "
            "Horizon's exact pyproject.toml blob evidence."
        ),
        basis=claim.evidence,
    )

    assertion = make_world_model_assertion(
        (
            "python-project:"
            + dependencies.project_name
        ),
        WorldModelRelationKind.DEPENDS_ON,
        dependencies.evidence_id,
        claim=claim,
        assessment=assessment,
    )

    return (
        claim,
        assessment,
        assertion,
    )


def _validate_blob_snapshot(
    index: PythonRepositoryIndex,
    pyproject_blob: GitBlobEvidence,
) -> None:
    if not isinstance(
        pyproject_blob,
        GitBlobEvidence,
    ):
        raise RepositoryDeterministicWorldModelError(
            "pyproject_blob must be GitBlobEvidence"
        )

    if (
        pyproject_blob.commit_sha
        != index.commit_sha
        or pyproject_blob.repository_observation_id
        != index.repository_observation_id
    ):
        raise RepositoryDeterministicWorldModelError(
            "pyproject evidence does not belong to the repository snapshot"
        )

    if (
        pyproject_blob.path
        != "pyproject.toml"
    ):
        raise RepositoryDeterministicWorldModelError(
            "supplied source evidence is not pyproject.toml"
        )


def build_repository_deterministic_world_model(
    index: PythonRepositoryIndex,
    *,
    pyproject_blob: GitBlobEvidence | None = None,
    package_layout: PythonPackageLayoutEvidence | None = None,
    project_dependencies: (
        PythonDeclaredProjectDependenciesEvidence
        | None
    ) = None,
) -> RepositoryDeterministicWorldModel:
    """Materialize already-proven deterministic repository evidence."""

    if not isinstance(
        index,
        PythonRepositoryIndex,
    ):
        raise RepositoryDeterministicWorldModelError(
            "index must be a PythonRepositoryIndex"
        )

    if (
        package_layout is not None
        or project_dependencies is not None
    ):
        if pyproject_blob is None:
            raise RepositoryDeterministicWorldModelError(
                "derived pyproject evidence requires its exact source blob"
            )

        _validate_blob_snapshot(
            index,
            pyproject_blob,
        )

    if (
        pyproject_blob is not None
        and package_layout is None
        and project_dependencies is None
    ):
        _validate_blob_snapshot(
            index,
            pyproject_blob,
        )

    if package_layout is not None:
        if not isinstance(
            package_layout,
            PythonPackageLayoutEvidence,
        ):
            raise RepositoryDeterministicWorldModelError(
                "package_layout must be PythonPackageLayoutEvidence"
            )

        if (
            pyproject_blob is None
            or package_layout.source_evidence_id
            != pyproject_blob.evidence_id
        ):
            raise RepositoryDeterministicWorldModelError(
                "package layout source does not match pyproject evidence"
            )

        if any(
            root.source_evidence_id
            != pyproject_blob.evidence_id
            for root
            in package_layout.import_roots
        ):
            raise RepositoryDeterministicWorldModelError(
                "package import-root evidence source mismatch"
            )

    if project_dependencies is not None:
        if not isinstance(
            project_dependencies,
            PythonDeclaredProjectDependenciesEvidence,
        ):
            raise RepositoryDeterministicWorldModelError(
                "project_dependencies must be "
                "PythonDeclaredProjectDependenciesEvidence"
            )

        if (
            pyproject_blob is None
            or project_dependencies.source_evidence_id
            != pyproject_blob.evidence_id
        ):
            raise RepositoryDeterministicWorldModelError(
                "dependency evidence source does not match pyproject evidence"
            )

    claims: list[
        EvidenceBackedClaim
    ] = []

    assessments: list[
        EpistemicAssessment
    ] = []

    assertions: list[
        WorldModelAssertion
    ] = []

    where_ids: list[
        str
    ] = []

    dependency_ids: list[
        str
    ] = []

    if package_layout is not None:
        assert (
            pyproject_blob
            is not None
        )

        for root in package_layout.import_roots:
            (
                claim,
                assessment,
                assertion,
            ) = _package_bundle(
                index=index,
                pyproject_blob=pyproject_blob,
                layout=package_layout,
                root=root,
            )

            claims.append(
                claim
            )

            assessments.append(
                assessment
            )

            assertions.append(
                assertion
            )

            where_ids.append(
                assertion.assertion_id
            )

    if project_dependencies is not None:
        assert (
            pyproject_blob
            is not None
        )

        (
            claim,
            assessment,
            assertion,
        ) = _dependency_bundle(
            index=index,
            pyproject_blob=pyproject_blob,
            dependencies=project_dependencies,
        )

        claims.append(
            claim
        )

        assessments.append(
            assessment
        )

        assertions.append(
            assertion
        )

        dependency_ids.append(
            assertion.assertion_id
        )

    snapshot = make_world_model_snapshot(
        claims=claims,
        assessments=assessments,
        assertions=assertions,
    )

    return RepositoryDeterministicWorldModel(
        source_commit=(
            index.commit_sha
        ),
        repository_observation_id=(
            index.repository_observation_id
        ),
        snapshot=snapshot,
        where_it_sits_assertion_ids=tuple(
            sorted(
                where_ids
            )
        ),
        what_it_depends_on_assertion_ids=tuple(
            sorted(
                dependency_ids
            )
        ),
    )
