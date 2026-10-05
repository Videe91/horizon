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
