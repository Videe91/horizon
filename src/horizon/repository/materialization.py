"""Evidence-backed repository materialization witness.

The filesystem is the witness, not Git status.

Horizon does not decide what command materializes a project.
The caller supplies the command; Horizon runs it in a disposable
exact-source worktree and records what actually happened.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from horizon.repository.git_observation import (
    observe_git_commit,
)


class MaterializationEvidenceError(
    RuntimeError
):
    pass


class MaterializationTermination(
    str,
    Enum,
):
    EXITED = "EXITED"
    TIMED_OUT = "TIMED_OUT"
    DISK_LIMIT_EXCEEDED = (
        "DISK_LIMIT_EXCEEDED"
    )


class MaterializationFetchStatus(
    str,
    Enum,
):
    REPORTED = "REPORTED"
    UNKNOWN = "UNKNOWN"


@dataclass(
    frozen=True,
    slots=True,
)
class MaterializationLimits:
    timeout_seconds: float
    disk_growth_limit_bytes: int

    def __post_init__(
        self,
    ) -> None:
        if self.timeout_seconds <= 0:
            raise MaterializationEvidenceError(
                "timeout_seconds must be positive"
            )

        if (
            self.disk_growth_limit_bytes
            <= 0
        ):
            raise MaterializationEvidenceError(
                "disk_growth_limit_bytes "
                "must be positive"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class MaterializationGeneratedFile:
    path: str
    kind: str
    size: int
    sha256: str


@dataclass(
    frozen=True,
    slots=True,
)
class MaterializationModifiedFile:
    path: str
    kind: str
    before_size: int
    before_sha256: str
    after_size: int
    after_sha256: str


@dataclass(
    frozen=True,
    slots=True,
)
class MaterializationDeletedFile:
    path: str
    kind: str
    size: int
    sha256: str


@dataclass(
    frozen=True,
    slots=True,
)
class MaterializationEvidence:
    evidence_id: str

    source_observation_id: str
    source_commit: str

    command: tuple[str, ...]
    limits: MaterializationLimits

    termination: MaterializationTermination
    return_code: int | None

    stdout_size: int
    stdout_sha256: str

    stderr_size: int
    stderr_sha256: str

    fetch_status: MaterializationFetchStatus
    reported_fetch_lines: tuple[str, ...]

    generated: tuple[
        MaterializationGeneratedFile,
        ...,
    ]

    modified: tuple[
        MaterializationModifiedFile,
        ...,
    ]

    deleted: tuple[
        MaterializationDeletedFile,
        ...,
    ]

    observed_peak_disk_growth_bytes: int


@dataclass(
    frozen=True,
    slots=True,
)
class _FileState:
    kind: str
    size: int
    sha256: str


def _sha256_bytes(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


def _git(
    repository: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> str:
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
        text=True,
        env=env,
    )

    return completed.stdout.strip()


def _git_status(
    repository: Path,
) -> str:
    return _git(
        repository,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )


def _candidate_observation_commits(
    observation: Any,
) -> tuple[str, ...]:
    values: list[str] = []

    for attribute in (
        "commit_sha",
        "commit",
        "commit_id",
        "commit_oid",
        "commit_hash",
        "resolved_commit",
        "resolved_revision",
    ):
        value = getattr(
            observation,
            attribute,
            None,
        )

        if isinstance(
            value,
            str,
        ):
            if value and value not in values:
                values.append(
                    value
                )

    return tuple(
        values
    )


def _resolve_observed_commit(
    repository: Path,
    observation: Any,
) -> str:
    observation_id = getattr(
        observation,
        "observation_id",
        None,
    )

    if not isinstance(
        observation_id,
        str,
    ):
        raise MaterializationEvidenceError(
            "observation has no observation_id"
        )

    candidates = list(
        _candidate_observation_commits(
            observation
        )
    )

    head = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    if head not in candidates:
        candidates.append(
            head
        )

    for candidate in candidates:
        try:
            resolved = _git(
                repository,
                "rev-parse",
                f"{candidate}^{{commit}}",
            )
        except subprocess.CalledProcessError:
            continue

        try:
            fresh = observe_git_commit(
                repository,
                resolved,
            )
        except Exception:
            continue

        if (
            fresh.observation_id
            == observation_id
        ):
            return resolved

    raise MaterializationEvidenceError(
        "cannot resolve the exact commit "
        "represented by the supplied observation"
    )


def _snapshot(
    root: Path,
) -> dict[str, _FileState]:
    result: dict[
        str,
        _FileState,
    ] = {}

    for path in sorted(
        root.rglob("*")
    ):
        relative = path.relative_to(
            root
        )

        if (
            relative.parts
            and relative.parts[0]
            == ".git"
        ):
            continue

        key = relative.as_posix()

        if path.is_symlink():
            target = os.readlink(
                path
            )

            content = target.encode(
                "utf-8",
                errors="surrogateescape",
            )

            result[key] = _FileState(
                kind="symlink",
                size=len(content),
                sha256=_sha256_bytes(
                    content
                ),
            )

            continue

        if path.is_dir():
            continue

        if not path.is_file():
            continue

        content = path.read_bytes()

        result[key] = _FileState(
            kind="file",
            size=len(content),
            sha256=_sha256_bytes(
                content
            ),
        )

    return result


def _disk_usage_bytes(
    root: Path,
) -> int:
    total = 0

    for directory, _, filenames in os.walk(
        root,
        followlinks=False,
    ):
        directory_path = Path(
            directory
        )

        for filename in filenames:
            path = (
                directory_path
                / filename
            )

            try:
                stat_result = path.lstat()
            except FileNotFoundError:
                continue

            total += stat_result.st_size

    return total


def _kill_process_tree(
    process: subprocess.Popen[bytes],
) -> None:
    if process.poll() is not None:
        return

    try:
        os.killpg(
            process.pid,
            signal.SIGKILL,
        )
    except (
        AttributeError,
        ProcessLookupError,
        PermissionError,
    ):
        try:
            process.kill()
        except ProcessLookupError:
            pass

    try:
        process.wait(
            timeout=5
        )
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass

        process.wait()


def _run_command(
    command: tuple[str, ...],
    worktree: Path,
    lab: Path,
    limits: MaterializationLimits,
) -> tuple[
    MaterializationTermination,
    int | None,
    int,
]:
    stdout_path = (
        lab / "stdout.bin"
    )

    stderr_path = (
        lab / "stderr.bin"
    )

    temp_path = (
        lab / "tmp"
    )

    temp_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    stdout_path.write_bytes(
        b""
    )

    stderr_path.write_bytes(
        b""
    )

    baseline_bytes = (
        _disk_usage_bytes(
            lab
        )
    )

    environment = (
        os.environ.copy()
    )

    environment[
        "TMPDIR"
    ] = str(
        temp_path
    )

    environment[
        "TMP"
    ] = str(
        temp_path
    )

    environment[
        "TEMP"
    ] = str(
        temp_path
    )

    started = time.monotonic()

    peak_growth = 0

    with stdout_path.open(
        "wb"
    ) as stdout_handle, stderr_path.open(
        "wb"
    ) as stderr_handle:
        try:
            process = subprocess.Popen(
                command,
                cwd=worktree,
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=environment,
                start_new_session=True,
            )
        except OSError as exc:
            raise MaterializationEvidenceError(
                "could not start materialization "
                f"command: {exc}"
            ) from exc

        termination = (
            MaterializationTermination.EXITED
        )

        return_code: int | None = None

        while True:
            current_bytes = (
                _disk_usage_bytes(
                    lab
                )
            )

            growth = max(
                0,
                current_bytes
                - baseline_bytes,
            )

            peak_growth = max(
                peak_growth,
                growth,
            )

            if (
                growth
                >= limits.disk_growth_limit_bytes
            ):
                termination = (
                    MaterializationTermination
                    .DISK_LIMIT_EXCEEDED
                )

                _kill_process_tree(
                    process
                )

                return_code = None
                break

            elapsed = (
                time.monotonic()
                - started
            )

            if (
                elapsed
                >= limits.timeout_seconds
            ):
                termination = (
                    MaterializationTermination
                    .TIMED_OUT
                )

                _kill_process_tree(
                    process
                )

                return_code = None
                break

            polled = process.poll()

            if polled is not None:
                return_code = polled
                break

            time.sleep(
                0.05
            )

        final_bytes = (
            _disk_usage_bytes(
                lab
            )
        )

        final_growth = max(
            0,
            final_bytes
            - baseline_bytes,
        )

        peak_growth = max(
            peak_growth,
            final_growth,
        )

    return (
        termination,
        return_code,
        peak_growth,
    )


def _reported_fetch_lines(
    stdout: bytes,
    stderr: bytes,
) -> tuple[str, ...]:
    reported: list[str] = []

    for content in (
        stdout,
        stderr,
    ):
        text = content.decode(
            "utf-8",
            errors="replace",
        )

        for line in text.splitlines():
            lowered = line.lower()

            explicit_fetch = (
                "downloading " in lowered
                or "downloaded " in lowered
                or "fetching " in lowered
                or "fetched " in lowered
                or " from https://" in lowered
                or " from http://" in lowered
            )

            if (
                explicit_fetch
                and line not in reported
            ):
                reported.append(
                    line
                )

    return tuple(
        reported
    )


def _diff_snapshots(
    before: dict[
        str,
        _FileState,
    ],
    after: dict[
        str,
        _FileState,
    ],
) -> tuple[
    tuple[
        MaterializationGeneratedFile,
        ...,
    ],
    tuple[
        MaterializationModifiedFile,
        ...,
    ],
    tuple[
        MaterializationDeletedFile,
        ...,
    ],
]:
    before_paths = set(
        before
    )

    after_paths = set(
        after
    )

    generated: list[
        MaterializationGeneratedFile
    ] = []

    modified: list[
        MaterializationModifiedFile
    ] = []

    deleted: list[
        MaterializationDeletedFile
    ] = []

    for path in sorted(
        after_paths
        - before_paths
    ):
        state = after[
            path
        ]

        generated.append(
            MaterializationGeneratedFile(
                path=path,
                kind=state.kind,
                size=state.size,
                sha256=state.sha256,
            )
        )

    for path in sorted(
        before_paths
        & after_paths
    ):
        old = before[
            path
        ]

        new = after[
            path
        ]

        if old == new:
            continue

        modified.append(
            MaterializationModifiedFile(
                path=path,
                kind=new.kind,
                before_size=old.size,
                before_sha256=(
                    old.sha256
                ),
                after_size=new.size,
                after_sha256=(
                    new.sha256
                ),
            )
        )

    for path in sorted(
        before_paths
        - after_paths
    ):
        state = before[
            path
        ]

        deleted.append(
            MaterializationDeletedFile(
                path=path,
                kind=state.kind,
                size=state.size,
                sha256=state.sha256,
            )
        )

    return (
        tuple(
            generated
        ),
        tuple(
            modified
        ),
        tuple(
            deleted
        ),
    )


def _generated_payload(
    generated: tuple[
        MaterializationGeneratedFile,
        ...,
    ],
) -> list[
    dict[str, object]
]:
    return [
        {
            "path": item.path,
            "kind": item.kind,
            "size": item.size,
            "sha256": item.sha256,
        }
        for item in generated
    ]


def _modified_payload(
    modified: tuple[
        MaterializationModifiedFile,
        ...,
    ],
) -> list[
    dict[str, object]
]:
    return [
        {
            "path": item.path,
            "kind": item.kind,
            "before_size": (
                item.before_size
            ),
            "before_sha256": (
                item.before_sha256
            ),
            "after_size": (
                item.after_size
            ),
            "after_sha256": (
                item.after_sha256
            ),
        }
        for item in modified
    ]


def _deleted_payload(
    deleted: tuple[
        MaterializationDeletedFile,
        ...,
    ],
) -> list[
    dict[str, object]
]:
    return [
        {
            "path": item.path,
            "kind": item.kind,
            "size": item.size,
            "sha256": item.sha256,
        }
        for item in deleted
    ]


def _evidence_id(
    *,
    source_observation_id: str,
    source_commit: str,
    command: tuple[str, ...],
    limits: MaterializationLimits,
    termination: MaterializationTermination,
    return_code: int | None,
    stdout_size: int,
    stdout_sha256: str,
    stderr_size: int,
    stderr_sha256: str,
    fetch_status: MaterializationFetchStatus,
    reported_fetch_lines: tuple[
        str,
        ...,
    ],
    generated: tuple[
        MaterializationGeneratedFile,
        ...,
    ],
    modified: tuple[
        MaterializationModifiedFile,
        ...,
    ],
    deleted: tuple[
        MaterializationDeletedFile,
        ...,
    ],
) -> str:
    payload = {
        "source_observation_id": (
            source_observation_id
        ),
        "source_commit": (
            source_commit
        ),
        "command": list(
            command
        ),
        "limits": {
            "timeout_seconds": (
                limits.timeout_seconds
            ),
            "disk_growth_limit_bytes": (
                limits.disk_growth_limit_bytes
            ),
        },
        "termination": (
            termination.value
        ),
        "return_code": (
            return_code
        ),
        "stdout_size": (
            stdout_size
        ),
        "stdout_sha256": (
            stdout_sha256
        ),
        "stderr_size": (
            stderr_size
        ),
        "stderr_sha256": (
            stderr_sha256
        ),
        "fetch_status": (
            fetch_status.value
        ),
        "reported_fetch_lines": list(
            reported_fetch_lines
        ),
        "generated": (
            _generated_payload(
                generated
            )
        ),
        "modified": (
            _modified_payload(
                modified
            )
        ),
        "deleted": (
            _deleted_payload(
                deleted
            )
        ),
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    digest = hashlib.sha256(
        canonical
    ).hexdigest()

    return (
        "materialization-evidence:"
        f"{digest}"
    )


def observe_materialization(
    repository: str | Path,
    observation: Any,
    command: Sequence[str],
    *,
    limits: MaterializationLimits,
) -> MaterializationEvidence:
    repository_path = Path(
        repository
    ).resolve()

    normalized_command = tuple(
        command
    )

    if not normalized_command:
        raise MaterializationEvidenceError(
            "command must not be empty"
        )

    if not all(
        isinstance(
            argument,
            str,
        )
        and argument
        for argument in normalized_command
    ):
        raise MaterializationEvidenceError(
            "command arguments must be "
            "non-empty strings"
        )

    source_observation_id = getattr(
        observation,
        "observation_id",
        None,
    )

    if not isinstance(
        source_observation_id,
        str,
    ):
        raise MaterializationEvidenceError(
            "observation has no observation_id"
        )

    source_commit = (
        _resolve_observed_commit(
            repository_path,
            observation,
        )
    )

    source_head_before = _git(
        repository_path,
        "rev-parse",
        "HEAD",
    )

    source_status_before = (
        _git_status(
            repository_path
        )
    )

    lab = Path(
        tempfile.mkdtemp(
            prefix=(
                "horizon-materialization-"
            )
        )
    )

    worktree = (
        lab / "source"
    )

    worktree_registered = False

    try:
        git_environment = (
            os.environ.copy()
        )

        git_environment[
            "GIT_NO_LAZY_FETCH"
        ] = "1"

        completed = subprocess.run(
            [
                "git",
                "-C",
                str(
                    repository_path
                ),
                "worktree",
                "add",
                "--detach",
                str(
                    worktree
                ),
                source_commit,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=git_environment,
            check=False,
        )

        if completed.returncode != 0:
            raise MaterializationEvidenceError(
                "could not materialize exact "
                "source commit as a worktree: "
                f"{completed.stderr.strip()}"
            )

        worktree_registered = True

        derived_commit = _git(
            worktree,
            "rev-parse",
            "HEAD",
        )

        if (
            derived_commit
            != source_commit
        ):
            raise MaterializationEvidenceError(
                "derived worktree does not "
                "match source commit"
            )

        before = _snapshot(
            worktree
        )

        (
            termination,
            return_code,
            peak_disk_growth,
        ) = _run_command(
            normalized_command,
            worktree,
            lab,
            limits,
        )

        after = _snapshot(
            worktree
        )

        stdout = (
            lab / "stdout.bin"
        ).read_bytes()

        stderr = (
            lab / "stderr.bin"
        ).read_bytes()

        (
            generated,
            modified,
            deleted,
        ) = _diff_snapshots(
            before,
            after,
        )

        fetch_lines = (
            _reported_fetch_lines(
                stdout,
                stderr,
            )
        )

        if fetch_lines:
            fetch_status = (
                MaterializationFetchStatus
                .REPORTED
            )
        else:
            fetch_status = (
                MaterializationFetchStatus
                .UNKNOWN
            )

        stdout_sha256 = (
            _sha256_bytes(
                stdout
            )
        )

        stderr_sha256 = (
            _sha256_bytes(
                stderr
            )
        )

        evidence_id = _evidence_id(
            source_observation_id=(
                source_observation_id
            ),
            source_commit=source_commit,
            command=normalized_command,
            limits=limits,
            termination=termination,
            return_code=return_code,
            stdout_size=len(
                stdout
            ),
            stdout_sha256=(
                stdout_sha256
            ),
            stderr_size=len(
                stderr
            ),
            stderr_sha256=(
                stderr_sha256
            ),
            fetch_status=fetch_status,
            reported_fetch_lines=(
                fetch_lines
            ),
            generated=generated,
            modified=modified,
            deleted=deleted,
        )

        evidence = (
            MaterializationEvidence(
                evidence_id=evidence_id,
                source_observation_id=(
                    source_observation_id
                ),
                source_commit=source_commit,
                command=normalized_command,
                limits=limits,
                termination=termination,
                return_code=return_code,
                stdout_size=len(
                    stdout
                ),
                stdout_sha256=(
                    stdout_sha256
                ),
                stderr_size=len(
                    stderr
                ),
                stderr_sha256=(
                    stderr_sha256
                ),
                fetch_status=(
                    fetch_status
                ),
                reported_fetch_lines=(
                    fetch_lines
                ),
                generated=generated,
                modified=modified,
                deleted=deleted,
                observed_peak_disk_growth_bytes=(
                    peak_disk_growth
                ),
            )
        )

    finally:
        if worktree_registered:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(
                        repository_path
                    ),
                    "worktree",
                    "remove",
                    "--force",
                    str(
                        worktree
                    ),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(
                        repository_path
                    ),
                    "worktree",
                    "prune",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

        shutil.rmtree(
            lab,
            ignore_errors=True,
        )

    source_head_after = _git(
        repository_path,
        "rev-parse",
        "HEAD",
    )

    source_status_after = (
        _git_status(
            repository_path
        )
    )

    if (
        source_head_after
        != source_head_before
    ):
        raise MaterializationEvidenceError(
            "source repository HEAD changed "
            "during materialization"
        )

    if (
        source_status_after
        != source_status_before
    ):
        raise MaterializationEvidenceError(
            "source repository working tree "
            "changed during materialization"
        )

    return evidence
