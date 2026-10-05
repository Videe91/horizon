from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess

from horizon.repository.git_observation import (
    GitCommitObservation,
)


class GitSearchError(Exception):
    """Base error for observed repository search."""


class EmptySearchQueryError(GitSearchError):
    """A repository search query may not be empty."""


@dataclass(frozen=True, slots=True)
class GitTextMatch:
    path: str
    object_id: str
    line_number: int
    line: bytes
    byte_start: int
    byte_end: int
    evidence_id: str


@dataclass(frozen=True, slots=True)
class GitTextSearchResult:
    query: str
    commit_sha: str
    repository_observation_id: str
    matches: tuple[GitTextMatch, ...]
    search_id: str


@dataclass(frozen=True, slots=True)
class _MatchTemplate:
    line_number: int
    line: bytes
    byte_start: int
    byte_end: int


def _read_blob_batch(
    repository: Path,
    object_ids: tuple[str, ...],
) -> dict[str, bytes]:
    if not object_ids:
        return {}

    request = b"".join(
        object_id.encode("ascii") + b"\n"
        for object_id in object_ids
    )

    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "cat-file",
            "--batch",
        ],
        input=request,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    output = completed.stdout
    position = 0
    result: dict[str, bytes] = {}

    for requested_object_id in object_ids:
        header_end = output.find(
            b"\n",
            position,
        )

        if header_end < 0:
            raise GitSearchError(
                "unexpected end of git cat-file batch output"
            )

        header = output[
            position:header_end
        ].decode("ascii")

        parts = header.split(" ")

        if len(parts) != 3:
            raise GitSearchError(
                "unexpected git cat-file batch header: "
                f"{header!r}"
            )

        returned_object_id, object_type, size_text = parts

        if object_type != "blob":
            raise GitSearchError(
                "search requested a non-blob Git object: "
                f"{requested_object_id!r}"
            )

        if returned_object_id != requested_object_id:
            raise GitSearchError(
                "git returned an unexpected object identity"
            )

        try:
            size = int(size_text)
        except ValueError as exc:
            raise GitSearchError(
                "invalid Git object size"
            ) from exc

        content_start = header_end + 1
        content_end = content_start + size

        if content_end > len(output):
            raise GitSearchError(
                "truncated Git blob content"
            )

        content = output[
            content_start:content_end
        ]

        if output[
            content_end:content_end + 1
        ] != b"\n":
            raise GitSearchError(
                "malformed git cat-file batch framing"
            )

        result[
            requested_object_id
        ] = content

        position = content_end + 1

    if position != len(output):
        raise GitSearchError(
            "unexpected trailing git cat-file batch output"
        )

    return result


def _find_matches(
    content: bytes,
    needle: bytes,
) -> tuple[_MatchTemplate, ...]:
    newline_offsets = [
        index
        for index, value in enumerate(content)
        if value == 10
    ]

    matches: list[_MatchTemplate] = []

    search_from = 0

    while True:
        byte_start = content.find(
            needle,
            search_from,
        )

        if byte_start < 0:
            break

        byte_end = (
            byte_start
            + len(needle)
        )

        line_index = bisect_left(
            newline_offsets,
            byte_start,
        )

        line_number = line_index + 1

        if line_index == 0:
            line_start = 0
        else:
            line_start = (
                newline_offsets[
                    line_index - 1
                ]
                + 1
            )

        if line_index < len(
            newline_offsets
        ):
            line_end = newline_offsets[
                line_index
            ]
        else:
            line_end = len(content)

        matches.append(
            _MatchTemplate(
                line_number=line_number,
                line=content[
                    line_start:line_end
                ],
                byte_start=byte_start,
                byte_end=byte_end,
            )
        )

        search_from = byte_end

    return tuple(matches)


def _match_evidence_identity(
    *,
    observation_id: str,
    commit_sha: str,
    path: str,
    object_id: str,
    query: bytes,
    byte_start: int,
    byte_end: int,
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.git-search-match.v1\0"
    )

    for value in (
        observation_id,
        commit_sha,
        object_id,
        path,
        str(byte_start),
        str(byte_end),
    ):
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(b"\0")

    digest.update(query)
    digest.update(b"\0")

    return (
        "git-search-match:"
        + digest.hexdigest()
    )


def _search_identity(
    *,
    observation_id: str,
    commit_sha: str,
    query: bytes,
    matches: tuple[GitTextMatch, ...],
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.git-text-search.v1\0"
    )

    digest.update(
        observation_id.encode("utf-8")
    )
    digest.update(b"\0")

    digest.update(
        commit_sha.encode("ascii")
    )
    digest.update(b"\0")

    digest.update(query)
    digest.update(b"\0")

    for match in matches:
        digest.update(
            match.evidence_id.encode(
                "ascii"
            )
        )
        digest.update(b"\0")

    return (
        "git-text-search:"
        + digest.hexdigest()
    )


def search_observed_text(
    repository: Path,
    observation: GitCommitObservation,
    query: str,
) -> GitTextSearchResult:
    if query == "":
        raise EmptySearchQueryError(
            "repository search query may not be empty"
        )

    repository = Path(repository)

    needle = query.encode(
        "utf-8",
        errors="surrogateescape",
    )

    blob_entries = tuple(
        sorted(
            (
                entry
                for entry in observation.entries
                if entry.object_type == "blob"
            ),
            key=lambda entry: entry.path,
        )
    )

    unique_object_ids = tuple(
        sorted(
            {
                entry.object_id
                for entry in blob_entries
            }
        )
    )

    templates_by_object_id: dict[
        str,
        tuple[_MatchTemplate, ...],
    ] = {}

    batch_size = 256

    for start in range(
        0,
        len(unique_object_ids),
        batch_size,
    ):
        batch = unique_object_ids[
            start:start + batch_size
        ]

        contents = _read_blob_batch(
            repository,
            batch,
        )

        for object_id in batch:
            templates_by_object_id[
                object_id
            ] = _find_matches(
                contents[object_id],
                needle,
            )

    matches: list[GitTextMatch] = []

    for entry in blob_entries:
        templates = (
            templates_by_object_id[
                entry.object_id
            ]
        )

        for template in templates:
            evidence_id = (
                _match_evidence_identity(
                    observation_id=(
                        observation.observation_id
                    ),
                    commit_sha=(
                        observation.commit_sha
                    ),
                    path=entry.path,
                    object_id=(
                        entry.object_id
                    ),
                    query=needle,
                    byte_start=(
                        template.byte_start
                    ),
                    byte_end=(
                        template.byte_end
                    ),
                )
            )

            matches.append(
                GitTextMatch(
                    path=entry.path,
                    object_id=(
                        entry.object_id
                    ),
                    line_number=(
                        template.line_number
                    ),
                    line=template.line,
                    byte_start=(
                        template.byte_start
                    ),
                    byte_end=(
                        template.byte_end
                    ),
                    evidence_id=evidence_id,
                )
            )

    frozen_matches = tuple(matches)

    return GitTextSearchResult(
        query=query,
        commit_sha=observation.commit_sha,
        repository_observation_id=(
            observation.observation_id
        ),
        matches=frozen_matches,
        search_id=_search_identity(
            observation_id=(
                observation.observation_id
            ),
            commit_sha=(
                observation.commit_sha
            ),
            query=needle,
            matches=frozen_matches,
        ),
    )
