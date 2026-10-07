from __future__ import annotations

from pathlib import Path

import pytest

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.languages.python.structure import (
    PythonStructureKind,
    PythonSyntaxEvidenceError,
    analyze_python_blob,
)
from horizon.languages.python.structure_cache import (
    PythonStructureCacheError,
    analyze_python_blob_cached,
    make_python_structure_cache_key,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)


def _blob(
    *,
    path: str,
    content: bytes,
    marker: str,
) -> GitBlobEvidence:
    return GitBlobEvidence(
        path=path,
        commit_sha=(
            marker * 40
        )[:40],
        repository_observation_id=(
            "git-observation:"
            + marker
        ),
        object_id=(
            marker * 40
        )[:40],
        content=content,
        evidence_id=(
            "git-blob-evidence:"
            + marker
        ),
    )


def _cache(
    tmp_path: Path,
) -> ContentAddressedExtractionCache:
    return (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )


def test_first_analysis_is_cache_miss(
    tmp_path: Path,
) -> None:
    blob = _blob(
        path="src/a.py",
        content=b"""\
def run():
    helper()
""",
        marker="a",
    )

    result = analyze_python_blob_cached(
        blob,
        _cache(
            tmp_path
        ),
    )

    assert result.cache_hit is False

    assert (
        result.analysis
        == analyze_python_blob(
            blob
        )
    )


def test_second_analysis_is_cache_hit(
    tmp_path: Path,
) -> None:
    blob = _blob(
        path="src/a.py",
        content=b"""\
def run():
    helper()
""",
        marker="a",
    )

    cache = _cache(
        tmp_path
    )

    first = analyze_python_blob_cached(
        blob,
        cache,
    )

    second = analyze_python_blob_cached(
        blob,
        cache,
    )

    assert first.cache_hit is False
    assert second.cache_hit is True

    assert (
        second.analysis
        == first.analysis
    )


def test_same_bytes_share_structure_cache_key() -> None:
    content = b"""\
class Worker:
    def run(self):
        return helper()
"""

    first = make_python_structure_cache_key(
        content
    )

    second = make_python_structure_cache_key(
        content
    )

    assert first == second


def test_same_bytes_at_different_paths_reuse_computation_but_not_provenance(
    tmp_path: Path,
) -> None:
    content = b"""\
class Worker:
    def run(self):
        return helper()
"""

    first_blob = _blob(
        path="src/a.py",
        content=content,
        marker="a",
    )

    second_blob = _blob(
        path="fork/src/b.py",
        content=content,
        marker="b",
    )

    assert (
        first_blob.evidence_id
        != second_blob.evidence_id
    )

    cache = _cache(
        tmp_path
    )

    first = analyze_python_blob_cached(
        first_blob,
        cache,
    )

    second = analyze_python_blob_cached(
        second_blob,
        cache,
    )

    assert first.cache_hit is False
    assert second.cache_hit is True

    assert (
        first.cache_key
        == second.cache_key
    )

    expected_first = analyze_python_blob(
        first_blob
    )

    expected_second = analyze_python_blob(
        second_blob
    )

    assert (
        first.analysis
        == expected_first
    )

    assert (
        second.analysis
        == expected_second
    )

    assert (
        first.analysis.analysis_id
        != second.analysis.analysis_id
    )

    assert (
        first.analysis.source_evidence_id
        == first_blob.evidence_id
    )

    assert (
        second.analysis.source_evidence_id
        == second_blob.evidence_id
    )

    assert all(
        fact.source_evidence_id
        == second_blob.evidence_id
        for fact
        in second.analysis.facts
    )

    first_module = next(
        fact
        for fact
        in first.analysis.facts
        if fact.kind
        is PythonStructureKind.MODULE
    )

    second_module = next(
        fact
        for fact
        in second.analysis.facts
        if fact.kind
        is PythonStructureKind.MODULE
    )

    assert (
        first_module.name
        == "src/a.py"
    )

    assert (
        second_module.name
        == "fork/src/b.py"
    )


def test_cached_parent_ids_are_rematerialized_for_current_blob(
    tmp_path: Path,
) -> None:
    content = b"""\
class Worker:
    def run(self):
        helper()
"""

    first_blob = _blob(
        path="a.py",
        content=content,
        marker="a",
    )

    second_blob = _blob(
        path="b.py",
        content=content,
        marker="b",
    )

    cache = _cache(
        tmp_path
    )

    first = analyze_python_blob_cached(
        first_blob,
        cache,
    )

    second = analyze_python_blob_cached(
        second_blob,
        cache,
    )

    assert second.cache_hit is True

    assert (
        second.analysis
        == analyze_python_blob(
            second_blob
        )
    )

    first_ids = {
        fact.evidence_id
        for fact
        in first.analysis.facts
    }

    second_ids = {
        fact.evidence_id
        for fact
        in second.analysis.facts
    }

    assert first_ids.isdisjoint(
        second_ids
    )


def test_cached_callee_identity_is_rematerialized(
    tmp_path: Path,
) -> None:
    content = b"""\
def run():
    service.execute()
"""

    first_blob = _blob(
        path="one.py",
        content=content,
        marker="a",
    )

    second_blob = _blob(
        path="two.py",
        content=content,
        marker="b",
    )

    cache = _cache(
        tmp_path
    )

    first = analyze_python_blob_cached(
        first_blob,
        cache,
    )

    second = analyze_python_blob_cached(
        second_blob,
        cache,
    )

    first_call = next(
        fact
        for fact
        in first.analysis.facts
        if fact.kind
        is PythonStructureKind.CALL
    )

    second_call = next(
        fact
        for fact
        in second.analysis.facts
        if fact.kind
        is PythonStructureKind.CALL
    )

    assert (
        first_call.callee_expression
        == second_call.callee_expression
        == "service.execute"
    )

    assert (
        first_call.callee_evidence_id
        != second_call.callee_evidence_id
    )

    assert (
        second.analysis
        == analyze_python_blob(
            second_blob
        )
    )


def test_changed_content_is_cache_miss(
    tmp_path: Path,
) -> None:
    cache = _cache(
        tmp_path
    )

    first = _blob(
        path="app.py",
        content=b"value = 1\n",
        marker="a",
    )

    second = _blob(
        path="app.py",
        content=b"value = 2\n",
        marker="b",
    )

    first_result = (
        analyze_python_blob_cached(
            first,
            cache,
        )
    )

    second_result = (
        analyze_python_blob_cached(
            second,
            cache,
        )
    )

    assert (
        first_result.cache_hit
        is False
    )

    assert (
        second_result.cache_hit
        is False
    )

    assert (
        first_result.cache_key
        != second_result.cache_key
    )


def test_invalid_python_is_not_cached(
    tmp_path: Path,
) -> None:
    content = b"def broken(:\n"

    blob = _blob(
        path="broken.py",
        content=content,
        marker="a",
    )

    cache = _cache(
        tmp_path
    )

    key = (
        make_python_structure_cache_key(
            content
        )
    )

    with pytest.raises(
        PythonSyntaxEvidenceError,
    ):
        analyze_python_blob_cached(
            blob,
            cache,
        )

    assert cache.get(
        key
    ) is None


def test_invalid_portable_payload_is_explicit(
    tmp_path: Path,
) -> None:
    content = b"value = 1\n"

    blob = _blob(
        path="app.py",
        content=content,
        marker="a",
    )

    cache = _cache(
        tmp_path
    )

    key = (
        make_python_structure_cache_key(
            content
        )
    )

    cache.put(
        key,
        b"{}",
    )

    with pytest.raises(
        PythonStructureCacheError,
    ):
        analyze_python_blob_cached(
            blob,
            cache,
        )


def test_cached_result_contains_no_old_source_identity(
    tmp_path: Path,
) -> None:
    content = b"""\
def run():
    helper()
"""

    old_blob = _blob(
        path="old.py",
        content=content,
        marker="a",
    )

    new_blob = _blob(
        path="new.py",
        content=content,
        marker="b",
    )

    cache = _cache(
        tmp_path
    )

    analyze_python_blob_cached(
        old_blob,
        cache,
    )

    current = (
        analyze_python_blob_cached(
            new_blob,
            cache,
        )
    )

    assert current.cache_hit is True

    assert (
        current.analysis.source_evidence_id
        == new_blob.evidence_id
    )

    assert all(
        old_blob.evidence_id
        not in fact.evidence_id
        for fact
        in current.analysis.facts
    )

    assert all(
        fact.source_evidence_id
        == new_blob.evidence_id
        for fact
        in current.analysis.facts
    )
