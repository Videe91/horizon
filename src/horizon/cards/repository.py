"""Automatic repository Card derived from the instant Python index.

This Card deliberately distinguishes three different things:

1. deterministic software facts;
2. operational compilation progress;
3. semantic questions Horizon has not yet justified.

Cache presence is operational state, not semantic proof.

Structural extraction progress must never silently become a claim about
purpose, architecture, ownership, dependency, or invariants.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass
from enum import Enum

from horizon.claims.epistemic import (
    EpistemicStatus,
)
from horizon.languages.python.repository_modules import (
    PythonPackageLayoutEvidence,
)
from horizon.repository.python_index import (
    PythonRepositoryIndex,
)


class RepositoryCardError(
    ValueError
):
    """A repository Card could not be represented faithfully."""


class RepositoryCardPhase(
    str,
    Enum,
):
    INDEXED = "INDEXED"

    STRUCTURE_CACHE_PARTIAL = (
        "STRUCTURE_CACHE_PARTIAL"
    )

    STRUCTURE_CACHE_PRESENT = (
        "STRUCTURE_CACHE_PRESENT"
    )


class RepositorySemanticSection(
    str,
    Enum,
):
    WHAT_IT_IS = "WHAT_IT_IS"

    WHERE_IT_SITS = "WHERE_IT_SITS"

    WHAT_IT_OWNS = "WHAT_IT_OWNS"

    WHAT_IT_DEPENDS_ON = (
        "WHAT_IT_DEPENDS_ON"
    )

    WHAT_MUST_REMAIN_TRUE = (
        "WHAT_MUST_REMAIN_TRUE"
    )


_SECTION_HEADINGS = {
    RepositorySemanticSection.WHAT_IT_IS: (
        "WHAT IT IS"
    ),
    RepositorySemanticSection.WHERE_IT_SITS: (
        "WHERE IT SITS"
    ),
    RepositorySemanticSection.WHAT_IT_OWNS: (
        "WHAT IT OWNS"
    ),
    RepositorySemanticSection.WHAT_IT_DEPENDS_ON: (
        "WHAT IT DEPENDS ON"
    ),
    RepositorySemanticSection.WHAT_MUST_REMAIN_TRUE: (
        "WHAT MUST REMAIN TRUE"
    ),
}


_UNKNOWN_REASONS = {
    RepositorySemanticSection.WHAT_IT_IS: (
        "The instant repository index establishes inventory, "
        "not semantic purpose."
    ),
    RepositorySemanticSection.WHERE_IT_SITS: (
        "The instant repository index does not establish an "
        "architectural boundary or placement."
    ),
    RepositorySemanticSection.WHAT_IT_OWNS: (
        "The instant repository index does not establish "
        "responsibility ownership."
    ),
    RepositorySemanticSection.WHAT_IT_DEPENDS_ON: (
        "The instant repository index does not establish "
        "semantic dependency relationships."
    ),
    RepositorySemanticSection.WHAT_MUST_REMAIN_TRUE: (
        "The instant repository index does not establish "
        "behavioral or architectural invariants."
    ),
}


@dataclass(
    frozen=True,
    slots=True,
)
class RepositoryCardStatement:
    status: EpistemicStatus
    text: str

    evidence_ids: tuple[
        str,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class RepositoryCardSemanticState:
    section: RepositorySemanticSection
    status: EpistemicStatus

    reason: str

    evidence_ids: tuple[
        str,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class RepositoryCard:
    title: str

    card_id: str
    revision_id: str

    source_commit: str
    repository_observation_id: str
    repository_index_id: str

    phase: RepositoryCardPhase

    tracked_python_file_count: int

    structure_cache_present_count: int
    structure_cache_missing_count: int

    source_snapshot: RepositoryCardStatement
    python_inventory: RepositoryCardStatement

    semantic_sections: tuple[
        RepositoryCardSemanticState,
        ...,
    ]


def _canonical_json(
    value,
) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )


def _identity(
    prefix: str,
    payload,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            _canonical_json(
                payload
            )
        ).hexdigest()
    )


def _phase(
    index: PythonRepositoryIndex,
) -> RepositoryCardPhase:
    if (
        index.python_file_count
        == 0
        or index.cache_present_count
        == 0
    ):
        return (
            RepositoryCardPhase
            .INDEXED
        )

    if (
        index.cache_missing_count
        == 0
    ):
        return (
            RepositoryCardPhase
            .STRUCTURE_CACHE_PRESENT
        )

    return (
        RepositoryCardPhase
        .STRUCTURE_CACHE_PARTIAL
    )


def _card_identity(
    index: PythonRepositoryIndex,
) -> str:
    return _identity(
        "repository-card:",
        {
            "schema_version": 1,
            "kind": (
                "REPOSITORY_UNDERSTANDING"
            ),
            "repository_observation_id": (
                index.repository_observation_id
            ),
        },
    )


def _revision_identity(
    *,
    card_id: str,
    index: PythonRepositoryIndex,
    phase: RepositoryCardPhase,
    semantic_sections: tuple[
        RepositoryCardSemanticState,
        ...,
    ],
) -> str:
    return _identity(
        "repository-card-revision:",
        {
            "schema_version": 2,
            "card_id": (
                card_id
            ),
            "repository_index_id": (
                index.index_id
            ),
            "phase": (
                phase.value
            ),
            "structure_cache_present_count": (
                index.cache_present_count
            ),
            "structure_cache_missing_count": (
                index.cache_missing_count
            ),
            "semantic_sections": [
                {
                    "section": (
                        state.section.value
                    ),
                    "status": (
                        state.status.value
                    ),
                    "reason": (
                        state.reason
                    ),
                    "evidence_ids": list(
                        state.evidence_ids
                    ),
                }
                for state
                in semantic_sections
            ],
        },
    )


def _package_placement_state(
    layout: PythonPackageLayoutEvidence,
) -> RepositoryCardSemanticState:
    if not isinstance(
        layout,
        PythonPackageLayoutEvidence,
    ):
        raise RepositoryCardError(
            "package_layout must be PythonPackageLayoutEvidence"
        )

    if not layout.import_roots:
        raise RepositoryCardError(
            "package layout contains no import roots"
        )

    placements: list[str] = []

    for root in layout.import_roots:
        import_root = (
            root.root_path
            if root.root_path
            else "<repository-root>"
        )

        placements.append(
            (
                "package path "
                + repr(
                    root.package_path
                )
                + ", import root "
                + repr(
                    import_root
                )
                + ", top-level package "
                + repr(
                    root.top_level_package
                )
            )
        )

    if len(
        placements
    ) == 1:
        prefix = (
            "Declared Python package placement: "
        )
    else:
        prefix = (
            "Declared Python package placements: "
        )

    evidence_ids = tuple(
        dict.fromkeys(
            (
                layout.source_evidence_id,
                layout.layout_id,
                *(
                    root.evidence_id
                    for root
                    in layout.import_roots
                ),
            )
        )
    )

    return RepositoryCardSemanticState(
        section=(
            RepositorySemanticSection
            .WHERE_IT_SITS
        ),
        status=(
            EpistemicStatus.PROVEN
        ),
        reason=(
            prefix
            + "; ".join(
                placements
            )
            + "."
        ),
        evidence_ids=(
            evidence_ids
        ),
    )


def _semantic_states(
    package_layout: PythonPackageLayoutEvidence | None,
) -> tuple[
    RepositoryCardSemanticState,
    ...,
]:
    states: list[
        RepositoryCardSemanticState
    ] = []

    for section in RepositorySemanticSection:
        if (
            section
            is RepositorySemanticSection.WHERE_IT_SITS
            and package_layout
            is not None
        ):
            states.append(
                _package_placement_state(
                    package_layout
                )
            )

            continue

        states.append(
            RepositoryCardSemanticState(
                section=section,
                status=(
                    EpistemicStatus.UNKNOWN
                ),
                reason=(
                    _UNKNOWN_REASONS[
                        section
                    ]
                ),
                evidence_ids=(),
            )
        )

    return tuple(
        states
    )


def build_repository_card(
    index: PythonRepositoryIndex,
    *,
    package_layout: (
        PythonPackageLayoutEvidence
        | None
    ) = None,
) -> RepositoryCard:
    """Build the instant deterministic repository Card."""

    if not isinstance(
        index,
        PythonRepositoryIndex,
    ):
        raise RepositoryCardError(
            "index must be a PythonRepositoryIndex"
        )

    if (
        index.cache_present_count
        + index.cache_missing_count
        != index.python_file_count
    ):
        raise RepositoryCardError(
            "index cache coverage does not match Python inventory"
        )

    phase = _phase(
        index
    )

    card_id = _card_identity(
        index
    )

    source_snapshot = (
        RepositoryCardStatement(
            status=(
                EpistemicStatus.PROVEN
            ),
            text=(
                "Source snapshot: "
                + index.commit_sha
            ),
            evidence_ids=(
                index.repository_observation_id,
            ),
        )
    )

    python_inventory = (
        RepositoryCardStatement(
            status=(
                EpistemicStatus.PROVEN
            ),
            text=(
                "Tracked regular Python source files: "
                + str(
                    index.python_file_count
                )
            ),
            evidence_ids=(
                index.index_id,
            ),
        )
    )

    semantic_sections = _semantic_states(
        package_layout
    )

    return RepositoryCard(
        title=(
            "Repository Understanding"
        ),
        card_id=(
            card_id
        ),
        revision_id=(
            _revision_identity(
                card_id=card_id,
                index=index,
                phase=phase,
                semantic_sections=(
                    semantic_sections
                ),
            )
        ),
        source_commit=(
            index.commit_sha
        ),
        repository_observation_id=(
            index.repository_observation_id
        ),
        repository_index_id=(
            index.index_id
        ),
        phase=phase,
        tracked_python_file_count=(
            index.python_file_count
        ),
        structure_cache_present_count=(
            index.cache_present_count
        ),
        structure_cache_missing_count=(
            index.cache_missing_count
        ),
        source_snapshot=(
            source_snapshot
        ),
        python_inventory=(
            python_inventory
        ),
        semantic_sections=(
            semantic_sections
        ),
    )


def _statement_line(
    statement: RepositoryCardStatement,
) -> str:
    evidence = ",".join(
        statement.evidence_ids
    )

    return (
        "["
        + statement.status.value
        + "] "
        + statement.text
        + " | evidence="
        + evidence
    )


def render_repository_card(
    card: RepositoryCard,
) -> str:
    """Render the repository Card without adding meaning."""

    if not isinstance(
        card,
        RepositoryCard,
    ):
        raise RepositoryCardError(
            "card must be a RepositoryCard"
        )

    lines = [
        "TITLE: "
        + card.title,
        "CARD_ID: "
        + card.card_id,
        "REVISION_ID: "
        + card.revision_id,
        "",
        "DETERMINISTIC KNOWLEDGE",
        _statement_line(
            card.source_snapshot
        ),
        _statement_line(
            card.python_inventory
        ),
        "",
        "COMPILATION PROGRESS",
        "PHASE: "
        + card.phase.value,
        (
            "STRUCTURE CACHE PRESENT: "
            + str(
                card.structure_cache_present_count
            )
        ),
        (
            "STRUCTURE CACHE MISSING: "
            + str(
                card.structure_cache_missing_count
            )
        ),
        (
            "NOTE: cache presence is operational scheduling state; "
            "it is not semantic proof."
        ),
        "",
        "SEMANTIC UNDERSTANDING",
    ]

    states = {
        state.section: state
        for state
        in card.semantic_sections
    }

    if set(
        states
    ) != set(
        RepositorySemanticSection
    ):
        raise RepositoryCardError(
            "card semantic sections are incomplete"
        )

    for section in RepositorySemanticSection:
        state = states[
            section
        ]

        semantic_line = (
            "["
            + state.status.value
            + "] "
            + state.reason
        )

        if state.evidence_ids:
            semantic_line += (
                " | evidence="
                + ",".join(
                    state.evidence_ids
                )
            )

        lines.extend(
            (
                "",
                _SECTION_HEADINGS[
                    section
                ],
                semantic_line,
            )
        )

    return "\n".join(
        lines
    )
