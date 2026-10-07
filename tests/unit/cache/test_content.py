from __future__ import annotations

import hashlib

from pathlib import Path

import pytest

from horizon.cache.content import (
    ContentAddressedExtractionCache,
    ContentCacheConflictError,
    ContentCacheCorruptionError,
    make_content_cache_key,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)


def _entry_path(
    root: Path,
    key_id: str,
) -> Path:
    digest = key_id.split(
        ":",
        1,
    )[1]

    return (
        root
        / "objects"
        / digest[:2]
        / (
            digest[2:]
            + ".json"
        )
    )


def test_key_is_content_addressed() -> None:
    content = (
        b"def run():\n"
        b"    return 1\n"
    )

    key = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="1",
    )

    assert (
        key.content_sha256
        == hashlib.sha256(
            content
        ).hexdigest()
    )

    assert key.key_id.startswith(
        "content-extraction-key:"
    )


def test_identical_bytes_have_identical_key() -> None:
    content = (
        b"value = 1\n"
    )

    first = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="1",
    )

    second = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="1",
    )

    assert first == second


def test_git_provenance_does_not_change_content_key() -> None:
    content = (
        b"def run():\n"
        b"    return 1\n"
    )

    first_blob = GitBlobEvidence(
        path="src/a.py",
        commit_sha="1" * 40,
        repository_observation_id=(
            "git-observation:first"
        ),
        object_id="a" * 40,
        content=content,
        evidence_id=(
            "git-blob-evidence:first"
        ),
    )

    second_blob = GitBlobEvidence(
        path="different/location.py",
        commit_sha="2" * 40,
        repository_observation_id=(
            "git-observation:second"
        ),
        object_id="b" * 40,
        content=content,
        evidence_id=(
            "git-blob-evidence:second"
        ),
    )

    assert (
        first_blob.evidence_id
        != second_blob.evidence_id
    )

    first_key = make_content_cache_key(
        content=first_blob.content,
        extractor="python.structure",
        extractor_version="1",
    )

    second_key = make_content_cache_key(
        content=second_blob.content,
        extractor="python.structure",
        extractor_version="1",
    )

    assert first_key == second_key


def test_different_content_changes_key() -> None:
    first = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    second = make_content_cache_key(
        content=b"value = 2\n",
        extractor="python.structure",
        extractor_version="1",
    )

    assert first != second


def test_extractor_identity_changes_key() -> None:
    content = b"value = 1\n"

    first = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="1",
    )

    second = make_content_cache_key(
        content=content,
        extractor="python.bindings",
        extractor_version="1",
    )

    assert first != second


def test_extractor_version_changes_key() -> None:
    content = b"value = 1\n"

    first = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="1",
    )

    second = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="2",
    )

    assert first != second


def test_parameters_change_key() -> None:
    content = b"value = 1\n"

    first = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="1",
        parameters=b"mode=one",
    )

    second = make_content_cache_key(
        content=content,
        extractor="python.structure",
        extractor_version="1",
        parameters=b"mode=two",
    )

    assert first != second


def test_missing_entry_returns_none(
    tmp_path: Path,
) -> None:
    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    assert cache.get(
        key
    ) is None


def test_store_and_reuse_payload(
    tmp_path: Path,
) -> None:
    root = (
        tmp_path
        / "cache"
    )

    cache = (
        ContentAddressedExtractionCache(
            root
        )
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    stored = cache.put(
        key,
        b'{"facts":3}',
    )

    loaded = cache.get(
        key
    )

    assert loaded is not None

    assert (
        loaded.key
        == key
    )

    assert (
        loaded.payload
        == b'{"facts":3}'
    )

    assert (
        loaded.payload_sha256
        == stored.payload_sha256
    )


def test_same_store_is_idempotent(
    tmp_path: Path,
) -> None:
    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    first = cache.put(
        key,
        b"facts",
    )

    second = cache.put(
        key,
        b"facts",
    )

    assert first == second


def test_same_key_cannot_be_rewritten_with_different_payload(
    tmp_path: Path,
) -> None:
    cache = (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    cache.put(
        key,
        b"first",
    )

    with pytest.raises(
        ContentCacheConflictError,
    ):
        cache.put(
            key,
            b"second",
        )


def test_corruption_is_detected(
    tmp_path: Path,
) -> None:
    root = (
        tmp_path
        / "cache"
    )

    cache = (
        ContentAddressedExtractionCache(
            root
        )
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    cache.put(
        key,
        b"facts",
    )

    path = _entry_path(
        root,
        key.key_id,
    )

    path.write_bytes(
        b"{}"
    )

    with pytest.raises(
        ContentCacheCorruptionError,
    ):
        cache.get(
            key
        )


def test_get_does_not_create_cache_directory(
    tmp_path: Path,
) -> None:
    root = (
        tmp_path
        / "cache"
    )

    cache = (
        ContentAddressedExtractionCache(
            root
        )
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    assert not root.exists()

    assert cache.get(
        key
    ) is None

    assert not root.exists()
