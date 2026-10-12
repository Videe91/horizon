"""Two-speed, file-anchored Component Card from existing Horizon evidence.

A file is only a candidate component boundary. Syntax is never presented as
proof of purpose, ownership, behavioural dependencies, or invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json

from horizon.languages.python.structure import (
    PythonStructureAnalysis,
    PythonStructureFact,
    PythonStructureKind,
)
from horizon.repository.python_index import PythonRepositoryIndex


class ComponentCardError(ValueError):
    pass


class ComponentCardPhase(str, Enum):
    INDEXED = "INDEXED"
    STRUCTURE_AVAILABLE = "STRUCTURE_AVAILABLE"


@dataclass(frozen=True, slots=True)
class ComponentCard:
    repository_key: str
    source_path: str
    card_id: str
    revision_id: str
    source_commit: str
    source_evidence_id: str
    content_sha256: str
    phase: ComponentCardPhase
    facts: tuple[PythonStructureFact, ...]


def _id(prefix: str, data: dict) -> str:
    raw = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return prefix + sha256(raw.encode("utf-8")).hexdigest()


def build_component_card(
    index: PythonRepositoryIndex,
    *,
    repository_key: str,
    source_path: str,
    analysis: PythonStructureAnalysis | None = None,
) -> ComponentCard:
    """Compile source facts only; semantic knowledge comes in a later slice.

    The caller supplies a stable repository key across Git commits. Without
    analysis, a Card is available immediately from the Python index.
    """
    if not isinstance(index, PythonRepositoryIndex):
        raise ComponentCardError("index must be PythonRepositoryIndex")
    if not isinstance(repository_key, str) or not repository_key.strip():
        raise ComponentCardError("repository_key must be nonempty")
    if not isinstance(source_path, str) or not source_path:
        raise ComponentCardError("source_path must be nonempty")

    file = next(
        (f for f in index.files if f.path == source_path),
        None,
    )
    if file is None:
        raise ComponentCardError(
            "source_path is absent from the observed index"
        )

    facts: tuple[PythonStructureFact, ...] = ()
    analysis_id = None

    if analysis is not None:
        if not isinstance(analysis, PythonStructureAnalysis):
            raise ComponentCardError(
                "analysis must be PythonStructureAnalysis"
            )
        if (
            analysis.path != source_path
            or analysis.source_evidence_id != file.source_evidence_id
            or any(
                not isinstance(f, PythonStructureFact)
                or f.source_evidence_id != file.source_evidence_id
                for f in analysis.facts
            )
        ):
            raise ComponentCardError(
                "analysis does not match indexed source"
            )

        facts = analysis.facts
        analysis_id = analysis.analysis_id

    card_id = _id(
        "component-card:",
        {
            "v": 1,
            "repository_key": repository_key,
            "path": source_path,
        },
    )

    return ComponentCard(
        repository_key=repository_key,
        source_path=source_path,
        card_id=card_id,
        revision_id=_id(
            "component-card-revision:",
            {
                "v": 1,
                "card_id": card_id,
                "source_commit": index.commit_sha,
                "observation": index.repository_observation_id,
                "indexed_file": file.handle_id,
                "analysis": analysis_id,
            },
        ),
        source_commit=index.commit_sha,
        source_evidence_id=file.source_evidence_id,
        content_sha256=file.content_sha256,
        phase=(
            ComponentCardPhase.STRUCTURE_AVAILABLE
            if analysis is not None
            else ComponentCardPhase.INDEXED
        ),
        facts=facts,
    )


def _fact_text(fact: PythonStructureFact) -> str:
    if fact.kind is PythonStructureKind.IMPORT:
        name = f"import {fact.name}"
    elif fact.kind is PythonStructureKind.FROM_IMPORT:
        name = f"from {fact.module or ''} import {fact.name}"
    else:
        name = ".".join((*fact.scope, fact.name))

    if fact.alias:
        name += f" as {fact.alias}"

    return (
        f"- {name} [L{fact.line_start}-{fact.line_end}] "
        f"evidence={fact.evidence_id}"
    )


def render_component_card(
    card: ComponentCard,
    *,
    max_facts: int = 12,
) -> str:
    """Bounded projection for agents; omitted facts are counted."""
    if not isinstance(card, ComponentCard):
        raise ComponentCardError("card must be ComponentCard")
    if type(max_facts) is not int or max_facts < 1:
        raise ComponentCardError(
            "max_facts must be a positive integer"
        )

    lines = [
        "KIND: FILE_ANCHORED_COMPONENT_CANDIDATE",
        f"REPOSITORY: {card.repository_key}",
        f"FILE: {card.source_path}",
        f"CARD_ID: {card.card_id}",
        f"REVISION_ID: {card.revision_id}",
        f"COMMIT: {card.source_commit}",
        f"SOURCE_EVIDENCE: {card.source_evidence_id}",
        f"CONTENT_SHA256: {card.content_sha256}",
        f"PHASE: {card.phase.value}",
    ]

    groups = (
        (
            "DEFINITIONS",
            {
                PythonStructureKind.CLASS_DEFINITION,
                PythonStructureKind.FUNCTION_DEFINITION,
                PythonStructureKind.ASYNC_FUNCTION_DEFINITION,
            },
        ),
        (
            "IMPORTS",
            {
                PythonStructureKind.IMPORT,
                PythonStructureKind.FROM_IMPORT,
            },
        ),
        (
            "CALL SYNTAX (NOT RESOLVED TARGETS)",
            {PythonStructureKind.CALL},
        ),
    )

    for title, kinds in groups:
        lines.extend(("", title))

        if card.phase is ComponentCardPhase.INDEXED:
            lines.append("NOT EXTRACTED YET")
            continue

        items = sorted(
            (f for f in card.facts if f.kind in kinds),
            key=lambda f: (
                f.line_start,
                f.line_end,
                f.evidence_id,
            ),
        )

        lines.extend(
            _fact_text(f)
            for f in items[:max_facts]
        )

        if not items:
            lines.append("NONE IN EXTRACTED FACTS")

        if len(items) > max_facts:
            lines.append(
                f"... {len(items) - max_facts} additional facts omitted"
            )

    lines.extend((
        "",
        "ARCHITECTURAL UNDERSTANDING: UNKNOWN (not yet investigated)",
        "REVERSE IMPORTERS / RELATED TESTS: NOT YET COMPUTED",
        "SOURCE CALL SYNTAX DOES NOT PROVE RUNTIME BEHAVIOUR",
    ))

    return "\n".join(lines)
