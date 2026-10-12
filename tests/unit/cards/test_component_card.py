"""The first Component Card uses exact observed Git evidence."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from horizon.cache.content import ContentAddressedExtractionCache
from horizon.cards.component import (
    ComponentCardError,
    ComponentCardPhase,
    build_component_card,
    render_component_card,
)
from horizon.languages.python.structure import PythonSyntaxEvidenceError
from horizon.languages.python.structure_cache import (
    analyze_python_blob_cached,
)
from horizon.repository.git_blob import read_observed_blob
from horizon.repository.git_observation import observe_git_commit
from horizon.repository.python_index import index_python_repository


def _git(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Horizon Test")
    _git(root, "config", "user.email", "horizon@example.invalid")
    return root


def _commit(root: Path) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


def _snapshot(root: Path, cache: ContentAddressedExtractionCache):
    observation = observe_git_commit(root, "HEAD")
    index = index_python_repository(root, observation, cache)
    return observation, index


def _example(root: Path) -> None:
    (root / "engine.py").write_text(
        "import os\n"
        "from typing import Iterable as Rows\n"
        "\n"
        "class Engine:\n"
        "    def run(self):\n"
        "        return os.getcwd()\n"
    )


def test_instant_card_survives_invalid_python(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    (root / "broken.py").write_text("def broken(:\n")
    _commit(root)

    cache = ContentAddressedExtractionCache(tmp_path / "cache")
    observation, index = _snapshot(root, cache)

    card = build_component_card(
        index,
        repository_key="example/repo",
        source_path="broken.py",
    )

    assert card.phase is ComponentCardPhase.INDEXED
    assert card.facts == ()
    assert "NOT EXTRACTED YET" in render_component_card(card)
    assert "ARCHITECTURAL UNDERSTANDING: UNKNOWN" in (
        render_component_card(card)
    )

    with pytest.raises(PythonSyntaxEvidenceError):
        analyze_python_blob_cached(
            read_observed_blob(root, observation, "broken.py"),
            cache,
        )


def test_structure_enriches_card_without_inventing_architecture(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    _example(root)
    _commit(root)

    cache = ContentAddressedExtractionCache(tmp_path / "cache")
    observation, index = _snapshot(root, cache)

    instant = build_component_card(
        index,
        repository_key="example/repo",
        source_path="engine.py",
    )

    analysis = analyze_python_blob_cached(
        read_observed_blob(root, observation, "engine.py"),
        cache,
    ).analysis

    enriched = build_component_card(
        index,
        repository_key="example/repo",
        source_path="engine.py",
        analysis=analysis,
    )

    assert instant.card_id == enriched.card_id
    assert instant.revision_id != enriched.revision_id
    assert enriched.phase is ComponentCardPhase.STRUCTURE_AVAILABLE

    assert {
        f.name
        for f in enriched.facts
        if f.kind.name.endswith("DEFINITION")
    } == {"Engine", "run"}

    assert any(
        f.name == "Iterable" and f.alias == "Rows"
        for f in enriched.facts
    )
    assert any(
        f.name in {"getcwd", "os.getcwd"}
        for f in enriched.facts
    )
    assert all(f.evidence_id for f in enriched.facts)

    rendered = render_component_card(enriched)

    assert "Engine.run" in rendered
    assert "from typing import Iterable as Rows" in rendered
    assert "CALL SYNTAX (NOT RESOLVED TARGETS)" in rendered
    assert "ARCHITECTURAL UNDERSTANDING: UNKNOWN" in rendered


def test_card_identity_survives_commit_and_rebinds_provenance(
    tmp_path: Path,
) -> None:
    root = _repository(tmp_path)
    _example(root)
    _commit(root)

    cache = ContentAddressedExtractionCache(tmp_path / "cache")
    observation1, index1 = _snapshot(root, cache)

    initial = build_component_card(
        index1,
        repository_key="example/repo",
        source_path="engine.py",
    )

    old_analysis = analyze_python_blob_cached(
        read_observed_blob(root, observation1, "engine.py"),
        cache,
    ).analysis

    (root / "README.md").write_text(
        "Unrelated documentation change.\n"
    )
    _commit(root)

    observation2, index2 = _snapshot(root, cache)

    latest = build_component_card(
        index2,
        repository_key="example/repo",
        source_path="engine.py",
    )

    assert latest.card_id == initial.card_id
    assert latest.revision_id != initial.revision_id
    assert latest.content_sha256 == initial.content_sha256

    with pytest.raises(
        ComponentCardError,
        match="analysis does not match",
    ):
        build_component_card(
            index2,
            repository_key="example/repo",
            source_path="engine.py",
            analysis=old_analysis,
        )

    recovered = analyze_python_blob_cached(
        read_observed_blob(root, observation2, "engine.py"),
        cache,
    )

    assert recovered.cache_hit

    card = build_component_card(
        index2,
        repository_key="example/repo",
        source_path="engine.py",
        analysis=recovered.analysis,
    )

    assert card.card_id == initial.card_id
    assert (
        card.source_evidence_id
        == recovered.analysis.source_evidence_id
    )


def test_invalid_inputs_are_rejected(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    _example(root)
    _commit(root)

    _, index = _snapshot(
        root,
        ContentAddressedExtractionCache(tmp_path / "cache"),
    )

    with pytest.raises(ComponentCardError, match="absent"):
        build_component_card(
            index,
            repository_key="example/repo",
            source_path="absent.py",
        )

    with pytest.raises(ComponentCardError, match="repository_key"):
        build_component_card(
            index,
            repository_key=" ",
            source_path="engine.py",
        )


def test_card_render_is_bounded(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    _example(root)
    _commit(root)

    cache = ContentAddressedExtractionCache(tmp_path / "cache")
    observation, index = _snapshot(root, cache)

    analysis = analyze_python_blob_cached(
        read_observed_blob(root, observation, "engine.py"),
        cache,
    ).analysis

    card = build_component_card(
        index,
        repository_key="example/repo",
        source_path="engine.py",
        analysis=analysis,
    )

    rendered = render_component_card(card, max_facts=1)
    assert "additional facts omitted" in rendered

    with pytest.raises(ComponentCardError, match="max_facts"):
        render_component_card(card, max_facts=0)
