"""Content-addressed cache for reusable Horizon extraction work.

The cache is deliberately separate from Horizon evidence identity.

A cache key answers:

    "Have we already performed this exact extractor computation
    over these exact bytes with these exact extractor inputs?"

It does not answer:

    "Where did these bytes come from?"
    "Which commit contains them?"
    "What evidence identity should they have now?"

Repository provenance remains attached when cached computation is
materialized into Horizon evidence.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContentCacheError(
    ValueError
):
    """Base failure for the content-addressed extraction cache."""


class ContentCacheCorruptionError(
    ContentCacheError
):
    """A stored cache entry failed deterministic integrity checks."""


class ContentCacheConflictError(
    ContentCacheError
):
    """One immutable cache key was assigned conflicting payload bytes."""


@dataclass(
    frozen=True,
    slots=True,
)
class ContentCacheKey:
    content_sha256: str
    extractor: str
    extractor_version: str
    parameters_sha256: str
    key_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class ContentCacheEntry:
    key: ContentCacheKey
    payload: bytes
    payload_sha256: str


def _sha256(
    value: bytes,
) -> str:
    return hashlib.sha256(
        value
    ).hexdigest()


def _canonical_json(
    value: Any,
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


def _validate_label(
    value: str,
    *,
    name: str,
) -> None:
    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise ContentCacheError(
            f"{name} must be a non-empty string"
        )

    if "\x00" in value:
        raise ContentCacheError(
            f"{name} may not contain NUL"
        )


def _validate_digest(
    value: str,
    *,
    name: str,
) -> None:
    if (
        not isinstance(
            value,
            str,
        )
        or len(
            value
        )
        != 64
        or any(
            character
            not in "0123456789abcdef"
            for character
            in value
        )
    ):
        raise ContentCacheError(
            f"{name} must be a lowercase SHA-256 digest"
        )


def _key_identity(
    *,
    content_sha256: str,
    extractor: str,
    extractor_version: str,
    parameters_sha256: str,
) -> str:
    payload = {
        "schema_version": 1,
        "content_sha256": (
            content_sha256
        ),
        "extractor": extractor,
        "extractor_version": (
            extractor_version
        ),
        "parameters_sha256": (
            parameters_sha256
        ),
    }

    return (
        "content-extraction-key:"
        + _sha256(
            _canonical_json(
                payload
            )
        )
    )


def make_content_cache_key(
    *,
    content: bytes,
    extractor: str,
    extractor_version: str,
    parameters: bytes = b"",
) -> ContentCacheKey:
    """Build a cache key from semantic computation inputs only."""

    if not isinstance(
        content,
        bytes,
    ):
        raise ContentCacheError(
            "content must be bytes"
        )

    if not isinstance(
        parameters,
        bytes,
    ):
        raise ContentCacheError(
            "parameters must be bytes"
        )

    _validate_label(
        extractor,
        name="extractor",
    )

    _validate_label(
        extractor_version,
        name="extractor_version",
    )

    content_digest = (
        _sha256(
            content
        )
    )

    parameters_digest = (
        _sha256(
            parameters
        )
    )

    return ContentCacheKey(
        content_sha256=(
            content_digest
        ),
        extractor=extractor,
        extractor_version=(
            extractor_version
        ),
        parameters_sha256=(
            parameters_digest
        ),
        key_id=_key_identity(
            content_sha256=(
                content_digest
            ),
            extractor=extractor,
            extractor_version=(
                extractor_version
            ),
            parameters_sha256=(
                parameters_digest
            ),
        ),
    )


def _validate_key(
    key: ContentCacheKey,
) -> None:
    if not isinstance(
        key,
        ContentCacheKey,
    ):
        raise ContentCacheError(
            "key must be a ContentCacheKey"
        )

    _validate_digest(
        key.content_sha256,
        name="content_sha256",
    )

    _validate_label(
        key.extractor,
        name="extractor",
    )

    _validate_label(
        key.extractor_version,
        name="extractor_version",
    )

    _validate_digest(
        key.parameters_sha256,
        name="parameters_sha256",
    )

    expected = _key_identity(
        content_sha256=(
            key.content_sha256
        ),
        extractor=(
            key.extractor
        ),
        extractor_version=(
            key.extractor_version
        ),
        parameters_sha256=(
            key.parameters_sha256
        ),
    )

    if key.key_id != expected:
        raise ContentCacheError(
            "cache key identity does not match its inputs"
        )


class ContentAddressedExtractionCache:
    """Immutable file-backed cache for extractor computation payloads."""

    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self._root = Path(
            root
        ).resolve()

    @property
    def root(
        self,
    ) -> Path:
        return self._root

    def _entry_path(
        self,
        key: ContentCacheKey,
    ) -> Path:
        _validate_key(
            key
        )

        digest = key.key_id.split(
            ":",
            1,
        )[1]

        return (
            self._root
            / "objects"
            / digest[:2]
            / (
                digest[2:]
                + ".json"
            )
        )

    def get(
        self,
        key: ContentCacheKey,
    ) -> ContentCacheEntry | None:
        path = self._entry_path(
            key
        )

        if not path.exists():
            return None

        if not path.is_file():
            raise ContentCacheCorruptionError(
                "cache entry path is not a file"
            )

        try:
            raw = path.read_bytes()

            document = json.loads(
                raw.decode(
                    "utf-8"
                )
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ContentCacheCorruptionError(
                "cache entry is not valid canonical data"
            ) from exc

        if not isinstance(
            document,
            dict,
        ):
            raise ContentCacheCorruptionError(
                "cache entry root must be an object"
            )

        expected_fields = {
            "schema_version",
            "key_id",
            "content_sha256",
            "extractor",
            "extractor_version",
            "parameters_sha256",
            "payload_sha256",
            "payload_base64",
        }

        if set(
            document
        ) != expected_fields:
            raise ContentCacheCorruptionError(
                "cache entry fields are invalid"
            )

        if document[
            "schema_version"
        ] != 1:
            raise ContentCacheCorruptionError(
                "cache entry schema version is unsupported"
            )

        expected_key_values = {
            "key_id": (
                key.key_id
            ),
            "content_sha256": (
                key.content_sha256
            ),
            "extractor": (
                key.extractor
            ),
            "extractor_version": (
                key.extractor_version
            ),
            "parameters_sha256": (
                key.parameters_sha256
            ),
        }

        for (
            field,
            expected,
        ) in expected_key_values.items():
            if document[
                field
            ] != expected:
                raise ContentCacheCorruptionError(
                    "cache entry key metadata does not match lookup key"
                )

        payload_digest = document[
            "payload_sha256"
        ]

        try:
            _validate_digest(
                payload_digest,
                name="payload_sha256",
            )
        except ContentCacheError as exc:
            raise ContentCacheCorruptionError(
                "cache payload digest is invalid"
            ) from exc

        payload_base64 = document[
            "payload_base64"
        ]

        if not isinstance(
            payload_base64,
            str,
        ):
            raise ContentCacheCorruptionError(
                "cache payload encoding is invalid"
            )

        try:
            payload = base64.b64decode(
                payload_base64.encode(
                    "ascii"
                ),
                validate=True,
            )
        except (
            UnicodeEncodeError,
            ValueError,
        ) as exc:
            raise ContentCacheCorruptionError(
                "cache payload is not valid base64"
            ) from exc

        if _sha256(
            payload
        ) != payload_digest:
            raise ContentCacheCorruptionError(
                "cache payload digest does not match payload"
            )

        return ContentCacheEntry(
            key=key,
            payload=payload,
            payload_sha256=(
                payload_digest
            ),
        )

    def put(
        self,
        key: ContentCacheKey,
        payload: bytes,
    ) -> ContentCacheEntry:
        _validate_key(
            key
        )

        if not isinstance(
            payload,
            bytes,
        ):
            raise ContentCacheError(
                "payload must be bytes"
            )

        existing = self.get(
            key
        )

        if existing is not None:
            if (
                existing.payload
                != payload
            ):
                raise ContentCacheConflictError(
                    "immutable cache key already contains different payload"
                )

            return existing

        payload_digest = (
            _sha256(
                payload
            )
        )

        document = {
            "schema_version": 1,
            "key_id": (
                key.key_id
            ),
            "content_sha256": (
                key.content_sha256
            ),
            "extractor": (
                key.extractor
            ),
            "extractor_version": (
                key.extractor_version
            ),
            "parameters_sha256": (
                key.parameters_sha256
            ),
            "payload_sha256": (
                payload_digest
            ),
            "payload_base64": (
                base64.b64encode(
                    payload
                ).decode(
                    "ascii"
                )
            ),
        }

        encoded = (
            _canonical_json(
                document
            )
            + b"\n"
        )

        path = self._entry_path(
            key
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            with path.open(
                "xb"
            ) as handle:
                handle.write(
                    encoded
                )

                handle.flush()

                os.fsync(
                    handle.fileno()
                )

        except FileExistsError:
            existing = self.get(
                key
            )

            if existing is None:
                raise ContentCacheCorruptionError(
                    "cache entry disappeared during concurrent write"
                )

            if (
                existing.payload
                != payload
            ):
                raise ContentCacheConflictError(
                    "concurrent cache writer produced conflicting payload"
                )

            return existing

        return ContentCacheEntry(
            key=key,
            payload=payload,
            payload_sha256=(
                payload_digest
            ),
        )
