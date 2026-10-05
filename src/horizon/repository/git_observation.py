from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import subprocess


@dataclass(frozen=True, slots=True)
class GitTreeEntry:
    path: str
    mode: str
    object_type: str
    object_id: str


@dataclass(frozen=True, slots=True)
class GitCommitObservation:
    commit_sha: str
    entries: tuple[GitTreeEntry, ...]
    observation_id: str


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


def _resolve_commit(
    repository: Path,
    commit: str,
) -> str:
    output = _run_git(
        repository,
        "rev-parse",
        "--verify",
        f"{commit}^{{commit}}",
    )

    return output.decode("ascii").strip()


def _read_tree(
    repository: Path,
    commit_sha: str,
) -> tuple[GitTreeEntry, ...]:
    output = _run_git(
        repository,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        commit_sha,
    )

    entries: list[GitTreeEntry] = []

    for record in output.split(b"\0"):
        if not record:
            continue

        metadata, raw_path = record.split(
            b"\t",
            1,
        )

        mode, object_type, object_id = (
            metadata.decode("ascii").split(
                " ",
                2,
            )
        )

        entries.append(
            GitTreeEntry(
                path=raw_path.decode(
                    "utf-8",
                    errors="surrogateescape",
                ),
                mode=mode,
                object_type=object_type,
                object_id=object_id,
            )
        )

    return tuple(
        sorted(
            entries,
            key=lambda entry: entry.path,
        )
    )


def _observation_identity(
    commit_sha: str,
    entries: tuple[GitTreeEntry, ...],
) -> str:
    digest = sha256()

    digest.update(
        b"horizon.git-commit-observation.v1\0"
    )
    digest.update(
        commit_sha.encode("ascii")
    )
    digest.update(b"\0")

    for entry in entries:
        digest.update(
            entry.mode.encode("ascii")
        )
        digest.update(b"\0")
        digest.update(
            entry.object_type.encode("ascii")
        )
        digest.update(b"\0")
        digest.update(
            entry.object_id.encode("ascii")
        )
        digest.update(b"\0")
        digest.update(
            entry.path.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(b"\0")

    return (
        "git-observation:"
        + digest.hexdigest()
    )


def observe_git_commit(
    repository: Path,
    commit: str,
) -> GitCommitObservation:
    repository = Path(repository)

    commit_sha = _resolve_commit(
        repository,
        commit,
    )

    entries = _read_tree(
        repository,
        commit_sha,
    )

    return GitCommitObservation(
        commit_sha=commit_sha,
        entries=entries,
        observation_id=_observation_identity(
            commit_sha,
            entries,
        ),
    )
