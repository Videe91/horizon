from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.runtime.observation import (
    RuntimeEvidenceError,
    RuntimeLimits,
    RuntimeTermination,
    observe_runtime,
)


EVENT_ENV = "HORIZON_RUNTIME_EVENT_FILE"


def _git(
    repository: Path,
    *args: str,
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
    )

    return completed.stdout.strip()


def _init_repository(
    root: Path,
) -> tuple[Path, str]:
    repository = (
        root
        / "repository"
    )

    repository.mkdir()

    subprocess.run(
        [
            "git",
            "init",
            "-q",
            "-b",
            "main",
            str(repository),
        ],
        check=True,
    )

    _git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    _git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    (
        repository
        / "tracked.txt"
    ).write_text(
        "source\n",
        encoding="utf-8",
    )

    _git(
        repository,
        "add",
        ".",
    )

    _git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    commit = _git(
        repository,
        "rev-parse",
        "HEAD",
    )

    return (
        repository,
        commit,
    )


def _limits() -> RuntimeLimits:
    return RuntimeLimits(
        timeout_seconds=5.0,
        disk_growth_limit_bytes=(
            10_000_000
        ),
    )


def _observation(
    repository: Path,
    commit: str,
):
    return observe_git_commit(
        repository,
        commit,
    )


def _event_writer_script(
    events: list[
        dict[str, object]
    ],
    *,
    stdout: str = "",
    stderr: str = "",
) -> str:
    encoded = repr(
        events
    )

    return (
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        f"events = {encoded}\n"
        f"path = Path(os.environ[{EVENT_ENV!r}])\n"
        "with path.open('w', encoding='utf-8') as handle:\n"
        "    for event in events:\n"
        "        if event.get('process_id') == '__SELF__':\n"
        "            event = dict(event)\n"
        "            event['process_id'] = os.getpid()\n"
        "        handle.write(json.dumps(event, sort_keys=True))\n"
        "        handle.write('\\n')\n"
        f"print({stdout!r})\n"
        f"print({stderr!r}, file=__import__('sys').stderr)\n"
    )


def test_runtime_observation_requires_explicit_command(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    with pytest.raises(
        RuntimeEvidenceError,
        match="command",
    ):
        observe_runtime(
            repository,
            observation,
            (),
            limits=_limits(),
        )


def test_runtime_observation_preserves_exact_source_and_command(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    command = (
        sys.executable,
        "-c",
        "print('runtime')",
    )

    evidence = observe_runtime(
        repository,
        observation,
        command,
        limits=_limits(),
    )

    assert (
        evidence.source_observation_id
        == observation.observation_id
    )

    assert (
        evidence.source_commit
        == commit
    )

    assert evidence.command == command

    assert (
        evidence.termination
        == RuntimeTermination.EXITED
    )

    assert evidence.return_code == 0

    assert (
        isinstance(
            evidence.root_process_id,
            int,
        )
        and evidence.root_process_id > 0
    )


def test_runtime_observation_preserves_explicit_configuration(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    evidence = observe_runtime(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            (
                "import os; "
                "print(os.environ['MODE'])"
            ),
        ),
        limits=_limits(),
        configuration={
            "MODE": "baseline",
            "FEATURE_FLAG": "enabled",
        },
    )

    assert evidence.configuration == (
        (
            "FEATURE_FLAG",
            "enabled",
        ),
        (
            "MODE",
            "baseline",
        ),
    )


def test_runtime_events_are_preserved_in_observed_order(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    events = [
        {
            "kind": "state_response",
            "process_id": "__SELF__",
            "payload": {
                "status": "REJECT",
                "state": "AwaitingRetry",
            },
        },
        {
            "kind": "state_response",
            "process_id": "__SELF__",
            "payload": {
                "status": "ACCEPT",
                "state": "Running",
            },
        },
    ]

    evidence = observe_runtime(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            _event_writer_script(
                events
            ),
        ),
        limits=_limits(),
    )

    assert len(
        evidence.events
    ) == 2

    first, second = (
        evidence.events
    )

    assert first.sequence == 0
    assert second.sequence == 1

    assert (
        first.kind
        == "state_response"
    )

    assert (
        second.kind
        == "state_response"
    )

    assert (
        first.reported_process_id
        == evidence.root_process_id
    )

    assert (
        second.reported_process_id
        == evidence.root_process_id
    )

    assert json.loads(
        first.payload_json
    ) == {
        "state": "AwaitingRetry",
        "status": "REJECT",
    }

    assert json.loads(
        second.payload_json
    ) == {
        "state": "Running",
        "status": "ACCEPT",
    }

    assert (
        first.evidence_id
        != second.evidence_id
    )


def test_runtime_stdout_and_stderr_provenance_is_preserved(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    stdout = (
        "HORIZON_RUNTIME_STDOUT"
    )

    stderr = (
        "HORIZON_RUNTIME_STDERR"
    )

    evidence = observe_runtime(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            _event_writer_script(
                [],
                stdout=stdout,
                stderr=stderr,
            ),
        ),
        limits=_limits(),
    )

    expected_stdout = (
        stdout
        + "\n"
    ).encode()

    expected_stderr = (
        stderr
        + "\n"
    ).encode()

    assert (
        evidence.stdout_size
        == len(
            expected_stdout
        )
    )

    assert (
        evidence.stdout_sha256
        == hashlib.sha256(
            expected_stdout
        ).hexdigest()
    )

    assert (
        evidence.stderr_size
        == len(
            expected_stderr
        )
    )

    assert (
        evidence.stderr_sha256
        == hashlib.sha256(
            expected_stderr
        ).hexdigest()
    )


def test_runtime_observation_preserves_experiment_and_intervention_identity(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    evidence = observe_runtime(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            "print('experiment')",
        ),
        limits=_limits(),
        experiment_id=(
            "retry-policy-experiment-v1"
        ),
        intervention_id=(
            "remove-retry-rule"
        ),
    )

    assert (
        evidence.experiment_id
        == "retry-policy-experiment-v1"
    )

    assert (
        evidence.intervention_id
        == "remove-retry-rule"
    )


def test_malformed_runtime_event_fails_closed(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    script = (
        "import os\n"
        "from pathlib import Path\n"
        f"path = Path(os.environ[{EVENT_ENV!r}])\n"
        "path.write_text("
        "'not-json\\n', "
        "encoding='utf-8'"
        ")\n"
    )

    with pytest.raises(
        RuntimeEvidenceError,
        match="runtime event",
    ):
        observe_runtime(
            repository,
            observation,
            (
                sys.executable,
                "-c",
                script,
            ),
            limits=_limits(),
        )


def test_source_repository_remains_untouched(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    evidence = observe_runtime(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "Path('runtime-generated.txt')"
                ".write_text('derived')"
            ),
        ),
        limits=_limits(),
    )

    assert (
        _git(
            repository,
            "rev-parse",
            "HEAD",
        )
        == commit
    )

    assert (
        _git(
            repository,
            "status",
            "--porcelain",
            "--untracked-files=all",
        )
        == ""
    )

    assert (
        evidence.source_commit
        == commit
    )


def test_runtime_evidence_has_first_class_identity(
    tmp_path: Path,
) -> None:
    repository, commit = (
        _init_repository(
            tmp_path
        )
    )

    observation = _observation(
        repository,
        commit,
    )

    evidence = observe_runtime(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            _event_writer_script(
                [
                    {
                        "kind": "attempt",
                        "process_id": "__SELF__",
                        "payload": {
                            "number": 1,
                        },
                    }
                ]
            ),
        ),
        limits=_limits(),
    )

    assert evidence.evidence_id.startswith(
        "runtime-observation:"
    )

    assert len(
        evidence.events
    ) == 1

    assert (
        evidence.events[
            0
        ].evidence_id.startswith(
            "runtime-event:"
        )
    )

    assert (
        evidence.events[
            0
        ].observation_evidence_id
        == evidence.evidence_id
    )
