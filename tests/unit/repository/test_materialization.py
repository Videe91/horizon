from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from horizon.repository.git_observation import observe_git_commit
from horizon.repository.materialization import (
    MaterializationEvidenceError,
    MaterializationFetchStatus,
    MaterializationLimits,
    MaterializationTermination,
    observe_materialization,
)


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
    files: dict[str, bytes],
    *,
    gitignore: str | None = None,
) -> tuple[Path, str]:
    repository = root / "repository"
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

    for relative_path, content in files.items():
        path = repository / relative_path
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_bytes(content)

    if gitignore is not None:
        (
            repository / ".gitignore"
        ).write_text(
            gitignore,
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

    return repository, commit


def _observation(
    repository: Path,
    commit: str,
):
    return observe_git_commit(
        repository,
        commit,
    )


def _limits(
    *,
    timeout_seconds: float = 5.0,
    disk_growth_limit_bytes: int = 10_000_000,
) -> MaterializationLimits:
    return MaterializationLimits(
        timeout_seconds=timeout_seconds,
        disk_growth_limit_bytes=(
            disk_growth_limit_bytes
        ),
    )


def _generated_by_path(
    evidence,
):
    return {
        item.path: item
        for item in evidence.generated
    }


def _modified_by_path(
    evidence,
):
    return {
        item.path: item
        for item in evidence.modified
    }


def _deleted_by_path(
    evidence,
):
    return {
        item.path: item
        for item in evidence.deleted
    }


def test_materialization_requires_explicit_caller_command(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    with pytest.raises(
        MaterializationEvidenceError,
        match="command",
    ):
        observe_materialization(
            repository,
            observation,
            (),
            limits=_limits(),
        )


def test_generated_file_is_detected_even_when_git_ignores_it(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
        gitignore="generated.txt\n",
    )

    observation = _observation(
        repository,
        commit,
    )

    command = (
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('generated.txt').write_bytes("
            "b'generated\\n'"
            ")"
        ),
    )

    evidence = observe_materialization(
        repository,
        observation,
        command,
        limits=_limits(),
    )

    assert (
        evidence.termination
        == MaterializationTermination.EXITED
    )
    assert evidence.return_code == 0

    generated = _generated_by_path(
        evidence
    )

    assert set(generated) == {
        "generated.txt",
    }

    assert (
        generated["generated.txt"].size
        == len(b"generated\n")
    )

    assert (
        generated["generated.txt"].sha256
        == hashlib.sha256(
            b"generated\n"
        ).hexdigest()
    )


def test_filesystem_diff_records_modified_deleted_and_not_unchanged(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "modified.txt": b"before\n",
            "deleted.txt": b"delete me\n",
            "unchanged.txt": b"same\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    script = (
        "from pathlib import Path\n"
        "Path('modified.txt').write_bytes(b'after\\n')\n"
        "Path('deleted.txt').unlink()\n"
    )

    evidence = observe_materialization(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            script,
        ),
        limits=_limits(),
    )

    assert evidence.return_code == 0

    modified = _modified_by_path(
        evidence
    )
    deleted = _deleted_by_path(
        evidence
    )

    assert set(modified) == {
        "modified.txt",
    }

    assert set(deleted) == {
        "deleted.txt",
    }

    assert not evidence.generated

    assert (
        modified["modified.txt"].before_sha256
        == hashlib.sha256(
            b"before\n"
        ).hexdigest()
    )

    assert (
        modified["modified.txt"].after_sha256
        == hashlib.sha256(
            b"after\n"
        ).hexdigest()
    )

    assert (
        deleted["deleted.txt"].sha256
        == hashlib.sha256(
            b"delete me\n"
        ).hexdigest()
    )


def test_nonzero_exit_still_returns_truthful_after_snapshot(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    script = (
        "from pathlib import Path\n"
        "import sys\n"
        "Path('partial.txt').write_bytes(b'partial\\n')\n"
        "print('build failed intentionally', file=sys.stderr)\n"
        "raise SystemExit(7)\n"
    )

    evidence = observe_materialization(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            script,
        ),
        limits=_limits(),
    )

    assert (
        evidence.termination
        == MaterializationTermination.EXITED
    )
    assert evidence.return_code == 7

    generated = _generated_by_path(
        evidence
    )

    assert "partial.txt" in generated

    assert evidence.stderr_size > 0
    assert (
        evidence.stderr_sha256
        == hashlib.sha256(
            b"build failed intentionally\n"
        ).hexdigest()
    )


def test_timeout_kills_command_and_still_records_partial_after_snapshot(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    script = (
        "from pathlib import Path\n"
        "import time\n"
        "Path('started.txt').write_bytes(b'started\\n')\n"
        "time.sleep(30)\n"
    )

    evidence = observe_materialization(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            script,
        ),
        limits=_limits(
            timeout_seconds=0.25,
        ),
    )

    assert (
        evidence.termination
        == MaterializationTermination.TIMED_OUT
    )

    assert evidence.return_code is None

    generated = _generated_by_path(
        evidence
    )

    assert "started.txt" in generated

    assert (
        generated["started.txt"].sha256
        == hashlib.sha256(
            b"started\n"
        ).hexdigest()
    )


def test_disk_growth_limit_kills_command_and_records_partial_state(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    limit = 128 * 1024

    script = (
        "import os\n"
        "import time\n"
        "from pathlib import Path\n"
        "chunk = b'x' * 65536\n"
        "with Path('growing.bin').open('wb') as handle:\n"
        "    while True:\n"
        "        handle.write(chunk)\n"
        "        handle.flush()\n"
        "        os.fsync(handle.fileno())\n"
        "        time.sleep(0.02)\n"
    )

    evidence = observe_materialization(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            script,
        ),
        limits=_limits(
            timeout_seconds=5.0,
            disk_growth_limit_bytes=limit,
        ),
    )

    assert (
        evidence.termination
        == MaterializationTermination.DISK_LIMIT_EXCEEDED
    )

    assert evidence.return_code is None

    generated = _generated_by_path(
        evidence
    )

    assert "growing.bin" in generated

    assert (
        generated["growing.bin"].size
        >= limit
    )

    assert (
        evidence.observed_peak_disk_growth_bytes
        >= limit
    )


def test_tool_reported_fetch_activity_is_preserved_exactly(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    reported = (
        "Downloading "
        "demo-1.2.3-py3-none-any.whl "
        "from "
        "https://example.invalid/"
        "demo-1.2.3-py3-none-any.whl"
    )

    script = (
        "import sys\n"
        f"print({reported!r}, file=sys.stderr)\n"
    )

    evidence = observe_materialization(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            script,
        ),
        limits=_limits(),
    )

    assert (
        evidence.fetch_status
        == MaterializationFetchStatus.REPORTED
    )

    assert evidence.reported_fetch_lines == (
        reported,
    )


def test_absence_of_reported_fetch_does_not_claim_no_network(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    evidence = observe_materialization(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            "print('quiet build')",
        ),
        limits=_limits(),
    )

    assert (
        evidence.fetch_status
        == MaterializationFetchStatus.UNKNOWN
    )

    assert not evidence.reported_fetch_lines


def test_source_repository_remains_untouched_and_exact_commit_is_preserved(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    evidence = observe_materialization(
        repository,
        observation,
        (
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "Path('generated.txt').write_text("
                "'derived', encoding='utf-8'"
                ")"
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

    assert evidence.source_commit == commit

    assert (
        evidence.source_observation_id
        == observation.observation_id
    )


def test_same_deterministic_observation_has_same_evidence_identity(
    tmp_path: Path,
) -> None:
    repository, commit = _init_repository(
        tmp_path,
        {
            "tracked.txt": b"source\n",
        },
    )

    observation = _observation(
        repository,
        commit,
    )

    command = (
        sys.executable,
        "-c",
        (
            "from pathlib import Path; "
            "Path('generated.txt').write_bytes("
            "b'deterministic\\n'"
            ")"
        ),
    )

    limits = _limits()

    first = observe_materialization(
        repository,
        observation,
        command,
        limits=limits,
    )

    second = observe_materialization(
        repository,
        observation,
        command,
        limits=limits,
    )

    assert (
        first.evidence_id
        == second.evidence_id
    )

    assert (
        first.generated
        == second.generated
    )

    assert (
        first.modified
        == second.modified
    )

    assert (
        first.deleted
        == second.deleted
    )


def test_shallow_promisor_repository_can_materialize_exact_head(
    tmp_path: Path,
) -> None:
    author = tmp_path / "author"

    subprocess.run(
        [
            "git",
            "init",
            "-q",
            "-b",
            "main",
            str(author),
        ],
        check=True,
    )

    _git(
        author,
        "config",
        "user.name",
        "Horizon Test",
    )

    _git(
        author,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    (
        author / "tracked.txt"
    ).write_bytes(
        b"first\n"
    )

    _git(
        author,
        "add",
        ".",
    )

    _git(
        author,
        "commit",
        "-q",
        "-m",
        "first",
    )

    (
        author / "tracked.txt"
    ).write_bytes(
        b"second\n"
    )

    _git(
        author,
        "add",
        ".",
    )

    _git(
        author,
        "commit",
        "-q",
        "-m",
        "second",
    )

    origin = tmp_path / "origin.git"

    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--bare",
            str(author),
            str(origin),
        ],
        check=True,
    )

    subprocess.run(
        [
            "git",
            "--git-dir",
            str(origin),
            "config",
            "uploadpack.allowFilter",
            "true",
        ],
        check=True,
    )

    partial = tmp_path / "partial"

    subprocess.run(
        [
            "git",
            "clone",
            "-q",
            "--depth",
            "1",
            "--filter=blob:none",
            "--branch",
            "main",
            origin.as_uri(),
            str(partial),
        ],
        check=True,
    )

    assert (
        _git(
            partial,
            "rev-parse",
            "--is-shallow-repository",
        )
        == "true"
    )

    assert (
        _git(
            partial,
            "config",
            "--get",
            "remote.origin.promisor",
        )
        == "true"
    )

    commit = _git(
        partial,
        "rev-parse",
        "HEAD",
    )

    observation = _observation(
        partial,
        commit,
    )

    evidence = observe_materialization(
        partial,
        observation,
        (
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "Path('generated.txt').write_bytes("
                "b'generated\\n'"
                ")"
            ),
        ),
        limits=_limits(),
    )

    assert (
        evidence.termination
        == MaterializationTermination.EXITED
    )

    assert evidence.return_code == 0

    assert (
        "generated.txt"
        in _generated_by_path(
            evidence
        )
    )

    assert (
        _git(
            partial,
            "rev-parse",
            "HEAD",
        )
        == commit
    )

    assert (
        _git(
            partial,
            "status",
            "--porcelain",
            "--untracked-files=all",
        )
        == ""
    )
