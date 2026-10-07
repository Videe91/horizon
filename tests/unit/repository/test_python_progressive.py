from __future__ import annotations

import subprocess

from pathlib import Path

from horizon.cache.content import (
    ContentAddressedExtractionCache,
)
from horizon.languages.python.structure_cache import (
    analyze_python_blob_cached,
)
from horizon.repository.git_blob import (
    read_observed_blob,
)
from horizon.repository.git_observation import (
    observe_git_commit,
)
from horizon.repository.python_index import (
    index_python_repository,
)
from horizon.repository.python_progressive import (
    execute_python_structure_batch,
    plan_python_structure_extraction,
)


def git(
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


def create_repository(
    tmp_path: Path,
) -> Path:
    repository = (
        tmp_path
        / "repo"
    )

    repository.mkdir()

    git(
        repository,
        "init",
        "-q",
        "-b",
        "main",
    )

    git(
        repository,
        "config",
        "user.name",
        "Horizon Test",
    )

    git(
        repository,
        "config",
        "user.email",
        "horizon@example.invalid",
    )

    return repository


def commit_all(
    repository: Path,
) -> str:
    git(
        repository,
        "add",
        "-A",
    )

    git(
        repository,
        "commit",
        "-q",
        "-m",
        "fixture",
    )

    return git(
        repository,
        "rev-parse",
        "HEAD",
    )


def cache(
    tmp_path: Path,
) -> ContentAddressedExtractionCache:
    return (
        ContentAddressedExtractionCache(
            tmp_path
            / "cache"
        )
    )


def test_plan_contains_only_missing_structure_work(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "cached.py"
    ).write_text(
        "def cached():\n"
        "    return 1\n"
    )

    (
        repository
        / "missing.py"
    ).write_text(
        "def missing():\n"
        "    return 2\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    cached_blob = read_observed_blob(
        repository,
        observation,
        "cached.py",
    )

    analyze_python_blob_cached(
        cached_blob,
        extraction_cache,
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    assert plan.missing_file_count == 1

    assert (
        plan.unique_work_item_count
        == 1
    )

    assert (
        plan.items[0].representative_path
        == "missing.py"
    )


def test_plan_deduplicates_identical_content(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    content = (
        "def same():\n"
        "    helper()\n"
    )

    (
        repository
        / "a.py"
    ).write_text(
        content
    )

    (
        repository
        / "b.py"
    ).write_text(
        content
    )

    (
        repository
        / "c.py"
    ).write_text(
        "value = 3\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    assert plan.missing_file_count == 3

    assert (
        plan.unique_work_item_count
        == 2
    )

    duplicated = next(
        item
        for item
        in plan.items
        if len(
            item.covered_paths
        )
        == 2
    )

    assert duplicated.covered_paths == (
        "a.py",
        "b.py",
    )


def test_one_batch_processes_only_requested_limit(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    for index_number in range(
        5
    ):
        (
            repository
            / f"{index_number}.py"
        ).write_text(
            (
                f"def f_{index_number}():\n"
                f"    return {index_number}\n"
            )
        )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    result = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=2,
    )

    assert result.start_offset == 0
    assert result.end_offset == 2

    assert (
        result.attempted_unique_items
        == 2
    )

    assert (
        result.completed_unique_items
        == 2
    )

    assert result.failed_unique_items == 0

    assert (
        result.remaining_unique_items
        == 3
    )

    assert result.done is False


def test_second_batch_continues_from_previous_cursor(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    for index_number in range(
        4
    ):
        (
            repository
            / f"{index_number}.py"
        ).write_text(
            f"value = {index_number}\n"
        )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    first = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=2,
    )

    second = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=(
            first.end_offset
        ),
        limit=2,
    )

    assert first.end_offset == 2

    assert second.start_offset == 2
    assert second.end_offset == 4

    assert second.done is True

    assert (
        second.remaining_unique_items
        == 0
    )


def test_successful_batch_populates_structure_cache(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "def app():\n"
        "    helper()\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    before = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    assert before.cache_present_count == 0

    plan = plan_python_structure_extraction(
        before
    )

    result = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=1,
    )

    assert (
        result.completed_unique_items
        == 1
    )

    after = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    assert after.cache_present_count == 1
    assert after.cache_missing_count == 0


def test_duplicate_content_completion_covers_all_paths(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    content = (
        "def same():\n"
        "    helper()\n"
    )

    (
        repository
        / "first.py"
    ).write_text(
        content
    )

    (
        repository
        / "second.py"
    ).write_text(
        content
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    assert (
        plan.unique_work_item_count
        == 1
    )

    result = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=1,
    )

    assert (
        result.completed_unique_items
        == 1
    )

    assert (
        result.completed_file_count
        == 2
    )

    assert (
        result.completions[0].covered_paths
        == (
            "first.py",
            "second.py",
        )
    )

    after = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    assert after.cache_present_count == 2


def test_syntax_failure_is_explicit_and_cursor_advances(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "broken.py"
    ).write_text(
        "def broken(:\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    result = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=1,
    )

    assert result.completed_unique_items == 0
    assert result.failed_unique_items == 1

    assert result.end_offset == 1
    assert result.done is True

    assert (
        result.failures[0].path
        == "broken.py"
    )

    assert (
        result.failures[0].failure_id.startswith(
            "python-progressive-syntax-failure:"
        )
    )


def test_batch_result_does_not_retain_analysis_objects(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "def app():\n"
        "    helper()\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    result = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=0,
        limit=1,
    )

    completion = (
        result.completions[0]
    )

    assert not hasattr(
        completion,
        "analysis",
    )

    assert (
        completion.fact_count
        > 0
    )


def test_completed_plan_executes_empty_batch(
    tmp_path: Path,
) -> None:
    repository = create_repository(
        tmp_path
    )

    (
        repository
        / "app.py"
    ).write_text(
        "value = 1\n"
    )

    commit = commit_all(
        repository
    )

    observation = observe_git_commit(
        repository,
        commit,
    )

    extraction_cache = cache(
        tmp_path
    )

    index = index_python_repository(
        repository,
        observation,
        extraction_cache,
    )

    plan = plan_python_structure_extraction(
        index
    )

    completed = execute_python_structure_batch(
        repository,
        observation,
        plan,
        extraction_cache,
        offset=(
            plan.unique_work_item_count
        ),
        limit=10,
    )

    assert (
        completed.attempted_unique_items
        == 0
    )

    assert completed.done is True
    assert completed.remaining_unique_items == 0
