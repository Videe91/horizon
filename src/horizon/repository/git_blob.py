from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess

from horizon.repository.git_observation import (
    GitCommitObservation,
    GitTreeEntry,
)


class GitBlobError(Exception):
    """Base error for observed Git blob access."""


class GitBlobNotFoundError(GitBlobError):
    """The requested path was not present in the observation."""


class GitObjectIsNotBlobError(GitBlobError):
    """The observed path exists but does not identify a Git blob."""


@dataclass(frozen=True, slots=True)
class GitBlobEvidence:
    path: str
    commit_sha: str
    repository_observation_id: str
    object_id: str
    content: bytes
    evidence_id: str


def _run_git(
    repository: Path,
    *args: str,
) -> bytes:
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
    )

    return completed.stdout


def _find_entry(
    observation: GitCommitObservation,
    path: str,
) -> GitTreeEntry:
    for entry in observation.entries:
        if entry.path == path:
            return entry

    raise GitBlobNotFoundError(
        f"path not present in repository observation: {path!r}"
    )


def _evidence_identity(
    *,
    observation_id: str,
    commit_sha: str,
    path: str,
    object_id: str,
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.git-blob-evidence.v1\0"
    )

    for value in (
        observation_id,
        commit_sha,
        object_id,
        path,
    ):
        digest.update(
            value.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(b"\0")

    return (
        "git-blob-evidence:"
        + digest.hexdigest()
    )


def read_observed_blob(
    repository: Path,
    observation: GitCommitObservation,
    path: str,
) -> GitBlobEvidence:
    repository = Path(repository)

    entry = _find_entry(
        observation,
        path,
    )

    if entry.object_type != "blob":
        raise GitObjectIsNotBlobError(
            "observed path does not identify a Git blob: "
            f"{path!r} "
            f"(object type: {entry.object_type!r})"
        )

    content = _run_git(
        repository,
        "cat-file",
        "blob",
        entry.object_id,
    )

    return GitBlobEvidence(
        path=entry.path,
        commit_sha=observation.commit_sha,
        repository_observation_id=(
            observation.observation_id
        ),
        object_id=entry.object_id,
        content=content,
        evidence_id=_evidence_identity(
            observation_id=(
                observation.observation_id
            ),
            commit_sha=observation.commit_sha,
            path=entry.path,
            object_id=entry.object_id,
        ),
    )


def _read_git_blob_batch(
    repository: Path,
    object_ids: tuple[
        str,
        ...,
    ],
) -> dict[
    str,
    bytes,
]:
    if not object_ids:
        return {}

    process = subprocess.Popen(
        [
            "git",
            "-C",
            str(
                repository
            ),
            "cat-file",
            "--batch",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    request = b"".join(
        (
            object_id.encode(
                "ascii"
            )
            + b"\n"
        )
        for object_id
        in object_ids
    )

    stdout, stderr = (
        process.communicate(
            input=request
        )
    )

    if (
        process.returncode
        != 0
    ):
        raise GitBlobError(
            "Git batch blob read failed: "
            + stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()
        )

    offset = 0

    contents: dict[
        str,
        bytes,
    ] = {}

    for expected_object_id in object_ids:
        header_end = stdout.find(
            b"\n",
            offset,
        )

        if header_end < 0:
            raise GitBlobError(
                "Git batch blob response ended before object header"
            )

        header = stdout[
            offset:
            header_end
        ]

        parts = header.split(
            b" "
        )

        if len(
            parts
        ) != 3:
            raise GitBlobError(
                "Git batch blob response header is invalid"
            )

        (
            returned_object_id_raw,
            object_type_raw,
            size_raw,
        ) = parts

        try:
            returned_object_id = (
                returned_object_id_raw.decode(
                    "ascii"
                )
            )

            object_type = (
                object_type_raw.decode(
                    "ascii"
                )
            )

            size = int(
                size_raw.decode(
                    "ascii"
                )
            )

        except (
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise GitBlobError(
                "Git batch blob response metadata is invalid"
            ) from exc

        if (
            returned_object_id
            != expected_object_id
        ):
            raise GitBlobError(
                "Git batch blob response object identity mismatch"
            )

        if object_type != "blob":
            raise GitObjectIsNotBlobError(
                "Git batch object is not a blob: "
                f"{expected_object_id!r} "
                f"(object type: {object_type!r})"
            )

        if size < 0:
            raise GitBlobError(
                "Git batch blob response size is invalid"
            )

        content_start = (
            header_end
            + 1
        )

        content_end = (
            content_start
            + size
        )

        if (
            content_end
            > len(
                stdout
            )
        ):
            raise GitBlobError(
                "Git batch blob response ended before blob content"
            )

        content = stdout[
            content_start:
            content_end
        ]

        terminator_end = (
            content_end
            + 1
        )

        if (
            stdout[
                content_end:
                terminator_end
            ]
            != b"\n"
        ):
            raise GitBlobError(
                "Git batch blob response is missing content terminator"
            )

        contents[
            expected_object_id
        ] = content

        offset = (
            terminator_end
        )

    if (
        offset
        != len(
            stdout
        )
    ):
        raise GitBlobError(
            "Git batch blob response contains unexpected trailing bytes"
        )

    return contents


def read_observed_blobs(
    repository: Path,
    observation: GitCommitObservation,
    paths: tuple[
        str,
        ...,
    ],
) -> tuple[
    GitBlobEvidence,
    ...,
]:
    """Read many observed Git blobs through one Git batch process.

    Returned evidence is path- and observation-specific exactly like
    read_observed_blob. Only raw object retrieval is shared.
    """

    repository = Path(
        repository
    )

    entries = tuple(
        _find_entry(
            observation,
            path,
        )
        for path
        in paths
    )

    for entry in entries:
        if (
            entry.object_type
            != "blob"
        ):
            raise GitObjectIsNotBlobError(
                "observed path does not identify a Git blob: "
                f"{entry.path!r} "
                f"(object type: {entry.object_type!r})"
            )

    unique_object_ids = tuple(
        dict.fromkeys(
            entry.object_id
            for entry
            in entries
        )
    )

    contents = _read_git_blob_batch(
        repository,
        unique_object_ids,
    )

    return tuple(
        GitBlobEvidence(
            path=entry.path,
            commit_sha=(
                observation.commit_sha
            ),
            repository_observation_id=(
                observation.observation_id
            ),
            object_id=(
                entry.object_id
            ),
            content=contents[
                entry.object_id
            ],
            evidence_id=(
                _evidence_identity(
                    observation_id=(
                        observation.observation_id
                    ),
                    commit_sha=(
                        observation.commit_sha
                    ),
                    path=(
                        entry.path
                    ),
                    object_id=(
                        entry.object_id
                    ),
                )
            ),
        )
        for entry
        in entries
    )
