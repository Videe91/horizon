"""Evidence-backed observation of real program execution.

Runtime evidence is distinct from static source evidence.

Horizon runs a caller-supplied command against an exact disposable
Git source state and records only what was directly observed:

- exact source identity
- command and explicit configuration
- root process identity
- termination and return code
- stdout/stderr provenance
- caller-instrumented ordered events

Structured runtime events are reports emitted by instrumentation.
A reported process id is therefore preserved as reported evidence;
it is not silently promoted to an independently OS-verified fact.
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
from typing import Any, Mapping, Sequence

from horizon.repository.git_observation import (
    GitCommitObservation,
    observe_git_commit,
)


_RUNTIME_EVENT_ENV = (
    "HORIZON_RUNTIME_EVENT_FILE"
)


class RuntimeEvidenceError(
    RuntimeError
):
    """Runtime evidence could not be observed faithfully."""


class RuntimeTermination(
    str,
    Enum,
):
    EXITED = "EXITED"
    TIMED_OUT = "TIMED_OUT"
    DISK_LIMIT_EXCEEDED = (
        "DISK_LIMIT_EXCEEDED"
    )


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeLimits:
    timeout_seconds: float
    disk_growth_limit_bytes: int

    def __post_init__(
        self,
    ) -> None:
        if self.timeout_seconds <= 0:
            raise RuntimeEvidenceError(
                "timeout_seconds must be positive"
            )

        if (
            self.disk_growth_limit_bytes
            <= 0
        ):
            raise RuntimeEvidenceError(
                "disk_growth_limit_bytes "
                "must be positive"
            )


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeEventEvidence:
    observation_evidence_id: str
    sequence: int
    kind: str
    reported_process_id: int | None
    payload_json: str
    evidence_id: str


@dataclass(
    frozen=True,
    slots=True,
)
class RuntimeEvidence:
    evidence_id: str

    source_observation_id: str
    source_commit: str

    command: tuple[str, ...]
    configuration: tuple[
        tuple[str, str],
        ...,
    ]

    root_process_id: int

    termination: RuntimeTermination
    return_code: int | None

    stdout_size: int
    stdout_sha256: str

    stderr_size: int
    stderr_sha256: str

    events: tuple[
        RuntimeEventEvidence,
        ...,
    ]

    experiment_id: str | None
    intervention_id: str | None

    observed_peak_disk_growth_bytes: int


@dataclass(
    frozen=True,
    slots=True,
)
class _ParsedRuntimeEvent:
    sequence: int
    kind: str
    reported_process_id: int | None
    payload_json: str


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


def _resolve_source_commit(
    repository: Path,
    observation: GitCommitObservation,
) -> str:
    commit = getattr(
        observation,
        "commit_sha",
        None,
    )

    if (
        not isinstance(
            commit,
            str,
        )
        or not commit
    ):
        raise RuntimeEvidenceError(
            "observation has no commit_sha"
        )

    try:
        resolved = _git(
            repository,
            "rev-parse",
            f"{commit}^{{commit}}",
        )

        fresh = observe_git_commit(
            repository,
            resolved,
        )

    except (
        subprocess.CalledProcessError,
        Exception,
    ) as exc:
        raise RuntimeEvidenceError(
            "cannot resolve runtime source "
            "observation"
        ) from exc

    if (
        fresh.observation_id
        != observation.observation_id
    ):
        raise RuntimeEvidenceError(
            "runtime source observation "
            "identity does not match commit"
        )

    return resolved


def _disk_usage_bytes(
    root: Path,
) -> int:
    total = 0

    for (
        directory,
        _,
        filenames,
    ) in os.walk(
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


def _normalize_command(
    command: Sequence[str],
) -> tuple[str, ...]:
    normalized = tuple(
        command
    )

    if not normalized:
        raise RuntimeEvidenceError(
            "command must not be empty"
        )

    if not all(
        isinstance(
            argument,
            str,
        )
        and argument
        for argument in normalized
    ):
        raise RuntimeEvidenceError(
            "command arguments must be "
            "non-empty strings"
        )

    return normalized


def _normalize_configuration(
    configuration: Mapping[
        str,
        str,
    ]
    | None,
) -> tuple[
    tuple[str, str],
    ...,
]:
    if configuration is None:
        return ()

    normalized: list[
        tuple[str, str]
    ] = []

    for key, value in configuration.items():
        if (
            not isinstance(
                key,
                str,
            )
            or not key
        ):
            raise RuntimeEvidenceError(
                "configuration keys must be "
                "non-empty strings"
            )

        if not isinstance(
            value,
            str,
        ):
            raise RuntimeEvidenceError(
                "configuration values must "
                "be strings"
            )

        normalized.append(
            (
                key,
                value,
            )
        )

    return tuple(
        sorted(
            normalized
        )
    )


def _normalize_optional_identity(
    value: str | None,
    *,
    description: str,
) -> str | None:
    if value is None:
        return None

    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise RuntimeEvidenceError(
            f"{description} must be a "
            "non-empty string or None"
        )

    return value


def _run_command(
    *,
    command: tuple[str, ...],
    worktree: Path,
    lab: Path,
    event_path: Path,
    configuration: tuple[
        tuple[str, str],
        ...,
    ],
    limits: RuntimeLimits,
) -> tuple[
    RuntimeTermination,
    int | None,
    int,
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

    event_path.write_bytes(
        b""
    )

    environment = (
        os.environ.copy()
    )

    environment.update(
        dict(
            configuration
        )
    )

    environment[
        _RUNTIME_EVENT_ENV
    ] = str(
        event_path
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

    baseline_bytes = (
        _disk_usage_bytes(
            lab
        )
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
            raise RuntimeEvidenceError(
                "could not start runtime "
                f"command: {exc}"
            ) from exc

        root_process_id = process.pid

        termination = (
            RuntimeTermination.EXITED
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
                    RuntimeTermination
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
                    RuntimeTermination
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
        root_process_id,
        peak_growth,
    )


def _parse_runtime_events(
    event_path: Path,
) -> tuple[
    _ParsedRuntimeEvent,
    ...,
]:
    raw = event_path.read_bytes()

    if not raw:
        return ()

    try:
        text = raw.decode(
            "utf-8",
        )

    except UnicodeDecodeError as exc:
        raise RuntimeEvidenceError(
            "runtime event stream is not "
            "valid UTF-8"
        ) from exc

    parsed: list[
        _ParsedRuntimeEvent
    ] = []

    for sequence, line in enumerate(
        text.splitlines()
    ):
        try:
            value = json.loads(
                line
            )

        except json.JSONDecodeError as exc:
            raise RuntimeEvidenceError(
                "malformed runtime event "
                f"at sequence {sequence}"
            ) from exc

        if not isinstance(
            value,
            dict,
        ):
            raise RuntimeEvidenceError(
                "runtime event must be "
                "a JSON object"
            )

        kind = value.get(
            "kind"
        )

        if (
            not isinstance(
                kind,
                str,
            )
            or not kind
        ):
            raise RuntimeEvidenceError(
                "runtime event kind must be "
                "a non-empty string"
            )

        reported_process_id = (
            value.get(
                "process_id"
            )
        )

        if (
            reported_process_id
            is not None
            and (
                not isinstance(
                    reported_process_id,
                    int,
                )
                or isinstance(
                    reported_process_id,
                    bool,
                )
                or reported_process_id
                <= 0
            )
        ):
            raise RuntimeEvidenceError(
                "runtime event process_id "
                "must be a positive integer "
                "or null"
            )

        if "payload" not in value:
            raise RuntimeEvidenceError(
                "runtime event is missing payload"
            )

        payload_json = json.dumps(
            value[
                "payload"
            ],
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )

        parsed.append(
            _ParsedRuntimeEvent(
                sequence=sequence,
                kind=kind,
                reported_process_id=(
                    reported_process_id
                ),
                payload_json=(
                    payload_json
                ),
            )
        )

    return tuple(
        parsed
    )


def _observation_identity(
    *,
    source_observation_id: str,
    source_commit: str,
    command: tuple[str, ...],
    configuration: tuple[
        tuple[str, str],
        ...,
    ],
    root_process_id: int,
    termination: RuntimeTermination,
    return_code: int | None,
    stdout_size: int,
    stdout_sha256: str,
    stderr_size: int,
    stderr_sha256: str,
    events: tuple[
        _ParsedRuntimeEvent,
        ...,
    ],
    experiment_id: str | None,
    intervention_id: str | None,
) -> str:
    payload: dict[
        str,
        Any,
    ] = {
        "source_observation_id": (
            source_observation_id
        ),
        "source_commit": (
            source_commit
        ),
        "command": list(
            command
        ),
        "configuration": [
            [
                key,
                value,
            ]
            for key, value
            in configuration
        ],
        "root_process_id": (
            root_process_id
        ),
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
        "events": [
            {
                "sequence": event.sequence,
                "kind": event.kind,
                "reported_process_id": (
                    event.reported_process_id
                ),
                "payload_json": (
                    event.payload_json
                ),
            }
            for event
            in events
        ],
        "experiment_id": (
            experiment_id
        ),
        "intervention_id": (
            intervention_id
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

    return (
        "runtime-observation:"
        + hashlib.sha256(
            canonical
        ).hexdigest()
    )


def _event_identity(
    *,
    observation_evidence_id: str,
    event: _ParsedRuntimeEvent,
) -> str:
    canonical = json.dumps(
        {
            "observation_evidence_id": (
                observation_evidence_id
            ),
            "sequence": (
                event.sequence
            ),
            "kind": event.kind,
            "reported_process_id": (
                event.reported_process_id
            ),
            "payload_json": (
                event.payload_json
            ),
        },
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    return (
        "runtime-event:"
        + hashlib.sha256(
            canonical
        ).hexdigest()
    )


def observe_runtime(
    repository: str | Path,
    observation: GitCommitObservation,
    command: Sequence[str],
    *,
    limits: RuntimeLimits,
    configuration: Mapping[
        str,
        str,
    ]
    | None = None,
    experiment_id: str | None = None,
    intervention_id: str | None = None,
) -> RuntimeEvidence:
    repository_path = Path(
        repository
    ).resolve()

    normalized_command = (
        _normalize_command(
            command
        )
    )

    normalized_configuration = (
        _normalize_configuration(
            configuration
        )
    )

    normalized_experiment_id = (
        _normalize_optional_identity(
            experiment_id,
            description="experiment_id",
        )
    )

    normalized_intervention_id = (
        _normalize_optional_identity(
            intervention_id,
            description="intervention_id",
        )
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
        raise RuntimeEvidenceError(
            "observation has no observation_id"
        )

    source_commit = (
        _resolve_source_commit(
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
                "horizon-runtime-"
            )
        )
    )

    worktree = (
        lab / "source"
    )

    event_path = (
        lab / "events.jsonl"
    )

    worktree_registered = False

    pending_error: Exception | None = None
    evidence: RuntimeEvidence | None = None

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
            raise RuntimeEvidenceError(
                "could not create exact "
                "runtime source worktree: "
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
            raise RuntimeEvidenceError(
                "runtime worktree does not "
                "match source commit"
            )

        (
            termination,
            return_code,
            root_process_id,
            peak_disk_growth,
        ) = _run_command(
            command=normalized_command,
            worktree=worktree,
            lab=lab,
            event_path=event_path,
            configuration=(
                normalized_configuration
            ),
            limits=limits,
        )

        stdout = (
            lab
            / "stdout.bin"
        ).read_bytes()

        stderr = (
            lab
            / "stderr.bin"
        ).read_bytes()

        parsed_events = (
            _parse_runtime_events(
                event_path
            )
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

        evidence_id = (
            _observation_identity(
                source_observation_id=(
                    source_observation_id
                ),
                source_commit=(
                    source_commit
                ),
                command=(
                    normalized_command
                ),
                configuration=(
                    normalized_configuration
                ),
                root_process_id=(
                    root_process_id
                ),
                termination=(
                    termination
                ),
                return_code=(
                    return_code
                ),
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
                events=(
                    parsed_events
                ),
                experiment_id=(
                    normalized_experiment_id
                ),
                intervention_id=(
                    normalized_intervention_id
                ),
            )
        )

        events = tuple(
            RuntimeEventEvidence(
                observation_evidence_id=(
                    evidence_id
                ),
                sequence=event.sequence,
                kind=event.kind,
                reported_process_id=(
                    event.reported_process_id
                ),
                payload_json=(
                    event.payload_json
                ),
                evidence_id=(
                    _event_identity(
                        observation_evidence_id=(
                            evidence_id
                        ),
                        event=event,
                    )
                ),
            )
            for event
            in parsed_events
        )

        evidence = RuntimeEvidence(
            evidence_id=(
                evidence_id
            ),
            source_observation_id=(
                source_observation_id
            ),
            source_commit=(
                source_commit
            ),
            command=(
                normalized_command
            ),
            configuration=(
                normalized_configuration
            ),
            root_process_id=(
                root_process_id
            ),
            termination=(
                termination
            ),
            return_code=(
                return_code
            ),
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
            events=events,
            experiment_id=(
                normalized_experiment_id
            ),
            intervention_id=(
                normalized_intervention_id
            ),
            observed_peak_disk_growth_bytes=(
                peak_disk_growth
            ),
        )

    except Exception as exc:
        pending_error = exc

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
        raise RuntimeEvidenceError(
            "source repository HEAD changed "
            "during runtime observation"
        )

    if (
        source_status_after
        != source_status_before
    ):
        raise RuntimeEvidenceError(
            "source repository working tree "
            "changed during runtime observation"
        )

    if pending_error is not None:
        if isinstance(
            pending_error,
            RuntimeEvidenceError,
        ):
            raise pending_error

        raise RuntimeEvidenceError(
            "runtime observation failed"
        ) from pending_error

    assert evidence is not None

    return evidence
