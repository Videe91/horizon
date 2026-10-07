from __future__ import annotations

from pathlib import Path

from horizon.cache.content import (
    ContentAddressedExtractionCache,
    make_content_cache_key,
)


def test_contains_is_false_without_entry(
    tmp_path: Path,
) -> None:
    cache = ContentAddressedExtractionCache(
        tmp_path
        / "cache"
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    assert cache.contains(
        key
    ) is False

    assert not cache.root.exists()


def test_contains_is_true_after_put(
    tmp_path: Path,
) -> None:
    cache = ContentAddressedExtractionCache(
        tmp_path
        / "cache"
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    cache.put(
        key,
        b"payload",
    )

    assert cache.contains(
        key
    ) is True


def test_contains_does_not_decode_payload(
    tmp_path: Path,
) -> None:
    cache = ContentAddressedExtractionCache(
        tmp_path
        / "cache"
    )

    key = make_content_cache_key(
        content=b"value = 1\n",
        extractor="python.structure",
        extractor_version="1",
    )

    cache.put(
        key,
        b"payload",
    )

    digest = key.key_id.split(
        ":",
        1,
    )[1]

    path = (
        cache.root
        / "objects"
        / digest[:2]
        / (
            digest[2:]
            + ".json"
        )
    )

    path.write_bytes(
        b"not valid cache data"
    )

    # Presence is intentionally only a cheap scheduling/index hint.
    # Integrity is still enforced by cache.get when the result is used.
    assert cache.contains(
        key
    ) is True
