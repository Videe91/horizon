from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import tempfile

from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any


EXPECTED_SEAL_STAGE = (
    "025ZZE-3C-R47"
)

EXPECTED_SEAL_ID = (
    "fresh-autonomous-semantic-self-test-seal:"
    "d71e7737a5a1d5857b09e29e6653471751d5f764d6f506127980217266bc3c9d"
)

EXPECTED_R47_COMMIT = (
    "574f3eaefc12e4db36d8698754c53785a5f009cb"
)

EXPECTED_R45_PRODUCT_COMMIT = (
    "2b948e6e41850c6f36ed2735cfb3b17bbf8b2a69"
)

EXPECTED_R46_REPAIR_COMMIT = (
    "f275083cd56c734abf0dd23b0d34113ef1b849de"
)

DEFAULT_SEAL = (
    "artifacts/investigator/"
    "025zze3c-r47-fresh-horizon-self-test-preregistration.json"
)

DEFAULT_CERTIFICATE = (
    "artifacts/investigator/"
    "025zze3c-r48-live-harness-certification.json"
)

LIVE_EXTRACTION_CACHE = Path(
    "/tmp/horizon-025zze3c-extraction-cache"
)


class LiveHarnessError(
    RuntimeError
):
    pass


def canonical_value(
    value: Any,
) -> Any:
    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        Decimal,
    ):
        if not value.is_finite():
            raise LiveHarnessError(
                "non-finite Decimal cannot be serialized"
            )

        return str(
            value
        )

    if isinstance(
        value,
        Path,
    ):
        return str(
            value
        )

    if dataclasses.is_dataclass(
        value
    ) and not isinstance(
        value,
        type,
    ):
        return {
            field.name: canonical_value(
                getattr(
                    value,
                    field.name,
                )
            )
            for field
            in dataclasses.fields(
                value
            )
        }

    if isinstance(
        value,
        Mapping,
    ):
        result = {}

        for key, item in value.items():
            if not isinstance(
                key,
                str,
            ):
                raise LiveHarnessError(
                    "canonical mapping keys must be strings"
                )

            result[
                key
            ] = canonical_value(
                item
            )

        return result

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return [
            canonical_value(
                item
            )
            for item
            in value
        ]

    if value is None or isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    model_dump = getattr(
        value,
        "model_dump",
        None,
    )

    if callable(
        model_dump
    ):
        try:
            dumped = model_dump(
                mode="json"
            )
        except TypeError:
            dumped = model_dump()

        return canonical_value(
            dumped
        )

    raise LiveHarnessError(
        "value cannot be serialized canonically: "
        + type(
            value
        ).__name__
    )


def canonical_bytes(
    value: Any,
) -> bytes:
    return json.dumps(
        canonical_value(
            value
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        allow_nan=False,
    ).encode(
        "utf-8"
    )


def sha256_bytes(
    value: bytes,
) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            value
        ).hexdigest()
    )


def sha256_file(
    path: Path,
) -> str:
    return sha256_bytes(
        path.read_bytes()
    )


def fsync_directory(
    directory: Path,
) -> None:
    descriptor = os.open(
        str(
            directory
        ),
        os.O_RDONLY,
    )

    try:
        os.fsync(
            descriptor
        )

    finally:
        os.close(
            descriptor
        )


def write_exclusive_bytes(
    path: Path,
    raw: bytes,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor = os.open(
        str(
            path
        ),
        (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
        ),
        0o600,
    )

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as handle:
            handle.write(
                raw
            )

            handle.flush()

            os.fsync(
                handle.fileno()
            )

    except BaseException:
        try:
            path.unlink(
                missing_ok=True
            )
        finally:
            raise

    fsync_directory(
        path.parent
    )


def write_exclusive_json(
    path: Path,
    value: Any,
) -> None:
    write_exclusive_bytes(
        path,
        (
            json.dumps(
                canonical_value(
                    value
                ),
                sort_keys=True,
                indent=2,
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode(
            "utf-8"
        ),
    )


def append_jsonl_fsync(
    path: Path,
    value: Any,
) -> None:
    raw = (
        canonical_bytes(
            value
        )
        + b"\n"
    )

    with path.open(
        "ab",
    ) as handle:
        handle.write(
            raw
        )

        handle.flush()

        os.fsync(
            handle.fileno()
        )


def git(
    repository: Path,
    *arguments: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(
                repository
            ),
            *arguments,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return completed.stdout.strip()


def repository_root() -> Path:
    completed = subprocess.run(
        [
            "git",
            "rev-parse",
            "--show-toplevel",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return Path(
        completed.stdout.strip()
    ).resolve()


def load_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise LiveHarnessError(
            "JSON authority cannot be loaded: "
            + str(
                path
            )
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise LiveHarnessError(
            "JSON authority root must be an object"
        )

    return value


def validate_seal(
    seal_path: Path,
) -> dict[str, Any]:
    seal = load_json(
        seal_path
    )

    if (
        seal.get(
            "certification",
            {},
        ).get(
            "stage"
        )
        != EXPECTED_SEAL_STAGE
    ):
        raise LiveHarnessError(
            "R47 stage identity mismatch"
        )

    if (
        seal.get(
            "certification",
            {},
        ).get(
            "status"
        )
        != "PASS"
    ):
        raise LiveHarnessError(
            "R47 seal is not PASS"
        )

    if (
        seal.get(
            "seal_id"
        )
        != EXPECTED_SEAL_ID
    ):
        raise LiveHarnessError(
            "R47 seal id mismatch"
        )

    without_seal = dict(
        seal
    )

    without_seal.pop(
        "seal_id",
        None,
    )

    recomputed = (
        "fresh-autonomous-semantic-self-test-seal:"
        + hashlib.sha256(
            canonical_bytes(
                without_seal
            )
        ).hexdigest()
    )

    if recomputed != EXPECTED_SEAL_ID:
        raise LiveHarnessError(
            "R47 seal canonical hash mismatch"
        )

    if (
        seal[
            "boundary"
        ][
            "provider_calls_this_stage"
        ]
        != 0
    ):
        raise LiveHarnessError(
            "R47 boundary is inconsistent"
        )

    if (
        seal[
            "attempt"
        ][
            "local_provider_call_ordinal_starts_at"
        ]
        != 1
    ):
        raise LiveHarnessError(
            "fresh attempt does not start at call 1"
        )

    if (
        seal[
            "attempt"
        ][
            "historical_call_9_reuse_forbidden"
        ]
        is not True
    ):
        raise LiveHarnessError(
            "old call-9 prohibition is absent"
        )

    runner_authority = seal[
        "runner_authority"
    ]

    if (
        runner_authority[
            "certified_production_head"
        ]
        != EXPECTED_R45_PRODUCT_COMMIT
    ):
        raise LiveHarnessError(
            "R45 product authority mismatch"
        )

    if (
        runner_authority[
            "preregistration_host_head"
        ]
        != EXPECTED_R46_REPAIR_COMMIT
    ):
        raise LiveHarnessError(
            "R46 repair authority mismatch"
        )

    if (
        seal[
            "attempt"
        ][
            "closed_3a_namespace_reuse_forbidden"
        ]
        is not True
        or seal[
            "attempt"
        ][
            "closed_3b_namespace_reuse_forbidden"
        ]
        is not True
    ):
        raise LiveHarnessError(
            "historical namespace prohibition is absent"
        )

    return seal


def path_from_seal(
    value: object,
    *,
    name: str,
) -> Path:
    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise LiveHarnessError(
            name
            + " path is invalid"
        )

    return Path(
        value
    ).expanduser().resolve()


def validate_frozen_repository(
    path: Path,
    *,
    expected_head: str,
    expected_tree: str,
    require_remote_free: bool,
) -> None:
    if not path.is_dir():
        raise LiveHarnessError(
            "frozen repository is absent: "
            + str(
                path
            )
        )

    if (
        git(
            path,
            "rev-parse",
            "HEAD",
        )
        != expected_head
    ):
        raise LiveHarnessError(
            "frozen repository HEAD mismatch: "
            + str(
                path
            )
        )

    if git(
        path,
        "status",
        "--short",
    ):
        raise LiveHarnessError(
            "frozen repository is dirty: "
            + str(
                path
            )
        )

    tree = git(
        path,
        "rev-parse",
        "HEAD^{tree}",
    )

    if tree != expected_tree:
        raise LiveHarnessError(
            "frozen repository tree mismatch: "
            + str(
                path
            )
        )

    if (
        require_remote_free
        and git(
            path,
            "remote",
        )
    ):
        raise LiveHarnessError(
            "frozen repository unexpectedly has a remote"
        )


def validate_target_and_control(
    seal: dict[str, Any],
) -> tuple[
    Path,
    Path,
    Path,
]:
    target_value = seal[
        "target"
    ]

    control_value = seal[
        "control_repository"
    ]

    target = path_from_seal(
        target_value[
            "path"
        ],
        name="target",
    )

    prefect = path_from_seal(
        control_value[
            "path"
        ],
        name="Prefect",
    )

    overlay = path_from_seal(
        target_value[
            "semantic_overlay_path"
        ],
        name="semantic overlay",
    )

    validate_frozen_repository(
        target,
        expected_head=(
            target_value[
                "commit"
            ]
        ),
        expected_tree=(
            target_value[
                "tree"
            ]
        ),
        require_remote_free=True,
    )

    validate_frozen_repository(
        prefect,
        expected_head=(
            control_value[
                "commit"
            ]
        ),
        expected_tree=(
            control_value[
                "tree"
            ]
        ),
        require_remote_free=False,
    )

    if overlay.exists():
        raise LiveHarnessError(
            "semantic overlay already exists"
        )

    return (
        target,
        prefect,
        overlay,
    )


\
def _repository_authority_path(
    repository: Path,
    value: object,
    *,
    name: str,
) -> Path:
    if (
        not isinstance(
            value,
            str,
        )
        or not value
    ):
        raise LiveHarnessError(
            name
            + " authority path is invalid"
        )

    path = Path(
        value
    ).expanduser()

    if not path.is_absolute():
        path = (
            repository
            / path
        )

    return path.resolve()


def _verify_preserved_file(
    *,
    path: Path,
    expected_sha256: object,
    name: str,
) -> None:
    if not path.is_file():
        raise LiveHarnessError(
            name
            + " preserved file is absent"
        )

    if (
        not isinstance(
            expected_sha256,
            str,
        )
        or expected_sha256
        != sha256_file(
            path
        )
    ):
        raise LiveHarnessError(
            name
            + " preserved file hash mismatch"
        )


def validate_historical_closed_attempts(
    *,
    repository: Path,
    seal: dict[str, Any],
) -> None:
    historical = seal[
        "historical_authority"
    ]

    specifications = (
        (
            "closed_attempt_025zze3a_r41",
            "horizon-self-025zze3a",
            "3A",
        ),
        (
            "closed_attempt_025zze3b_r44",
            "horizon-self-025zze3b",
            "3B",
        ),
    )

    for key, attempt_id, label in specifications:
        authority = historical[
            key
        ]

        closure_path = (
            _repository_authority_path(
                repository,
                authority[
                    "path"
                ],
                name=(
                    label
                    + " closure"
                ),
            )
        )

        _verify_preserved_file(
            path=closure_path,
            expected_sha256=(
                authority[
                    "sha256"
                ]
            ),
            name=(
                label
                + " closure authority"
            ),
        )

        closure = load_json(
            closure_path
        )

        if (
            closure[
                "closure_id"
            ]
            != authority[
                "closure_id"
            ]
        ):
            raise LiveHarnessError(
                label
                + " closure identity mismatch"
            )

        attempt = closure[
            "attempt"
        ]

        if (
            attempt[
                "attempt_id"
            ]
            != attempt_id
            or attempt[
                "state"
            ]
            != "PERMANENTLY_CLOSED"
            or attempt[
                "rerun_allowed"
            ]
            is not False
            or attempt[
                "namespace_reuse_allowed"
            ]
            is not False
        ):
            raise LiveHarnessError(
                label
                + " is not permanently closed"
            )

        preserved = closure[
            "preserved_live_authority"
        ]

        for hash_key, path_key, suffix in (
            (
                "live_lock_sha256",
                "live_lock_path",
                "live lock",
            ),
            (
                "attempt_ledger_sha256",
                "attempt_ledger_path",
                "attempt ledger",
            ),
            (
                "final_result_sha256",
                "final_result_path",
                "final result",
            ),
        ):
            preserved_path = Path(
                preserved[
                    path_key
                ]
            ).expanduser().resolve()

            _verify_preserved_file(
                path=preserved_path,
                expected_sha256=(
                    preserved[
                        hash_key
                    ]
                ),
                name=(
                    label
                    + " "
                    + suffix
                ),
            )

        if (
            "response_spool_manifest"
            in preserved
        ):
            spool = Path(
                preserved[
                    "response_spool_directory"
                ]
            ).expanduser().resolve()

            if not spool.is_dir():
                raise LiveHarnessError(
                    label
                    + " response spool is absent"
                )

            manifest = preserved[
                "response_spool_manifest"
            ]

            for item in manifest:
                response = (
                    spool
                    / (
                        "response-"
                        + f"{item['ordinal']:04d}"
                        + ".json"
                    )
                )

                _verify_preserved_file(
                    path=response,
                    expected_sha256=(
                        item[
                            "response_sha256"
                        ]
                    ),
                    name=(
                        label
                        + " response "
                        + str(
                            item[
                                "ordinal"
                            ]
                        )
                    ),
                )

        else:
            spool = Path(
                preserved[
                    "response_spool_path"
                ]
            ).expanduser().resolve()

            if not spool.is_dir():
                raise LiveHarnessError(
                    label
                    + " response spool is absent"
                )

            expected_count = preserved[
                "response_spool_file_count"
            ]

            actual_count = len(
                tuple(
                    spool.iterdir()
                )
            )

            if (
                actual_count
                != expected_count
            ):
                raise LiveHarnessError(
                    label
                    + " response spool count mismatch"
                )


def validate_repair_certifications(
    *,
    repository: Path,
    seal: dict[str, Any],
) -> None:
    historical = seal[
        "historical_authority"
    ]

    specifications = (
        (
            "planner_addressability_repair_r45",
            "R45",
        ),
        (
            "final_round_consumption_certification_r46",
            "R46",
        ),
    )

    loaded = {}

    for key, label in specifications:
        authority = historical[
            key
        ]

        authority_path = (
            _repository_authority_path(
                repository,
                authority[
                    "path"
                ],
                name=(
                    label
                    + " certification"
                ),
            )
        )

        _verify_preserved_file(
            path=authority_path,
            expected_sha256=(
                authority[
                    "sha256"
                ]
            ),
            name=(
                label
                + " certification"
            ),
        )

        value = load_json(
            authority_path
        )

        if (
            value.get(
                "certification_id"
            )
            != authority[
                "certification_id"
            ]
        ):
            raise LiveHarnessError(
                label
                + " certification identity mismatch"
            )

        if (
            value.get(
                "certification",
                {},
            ).get(
                "status"
            )
            != "PASS"
        ):
            raise LiveHarnessError(
                label
                + " certification is not PASS"
            )

        loaded[
            label
        ] = value

    r45 = loaded[
        "R45"
    ]

    if (
        r45[
            "repair"
        ][
            "creates_evidence"
        ]
        is not False
        or r45[
            "repair"
        ][
            "may_support_hypothesis"
        ]
        is not False
        or r45[
            "repair"
        ][
            "may_contradict_hypothesis"
        ]
        is not False
    ):
        raise LiveHarnessError(
            "R45 address hints crossed semantic authority"
        )

    r46 = loaded[
        "R46"
    ]

    if (
        r46[
            "proved"
        ][
            "address_hints_present_in_real_planner_instruction"
        ]
        is not True
        or r46[
            "proved"
        ][
            "real_investigation_executor_materialized_reads"
        ]
        is not True
        or r46[
            "safety"
        ][
            "provider_calls"
        ]
        != 0
    ):
        raise LiveHarnessError(
            "R46 consumption authority is inconsistent"
        )


def validate_fresh_namespace(
    seal: dict[str, Any],
    *,
    include_cache: bool,
) -> None:
    protocol = seal[
        "attempt_spool_protocol"
    ]

    paths = [
        Path(
            protocol[
                "live_lock_path"
            ]
        ),
        Path(
            protocol[
                "attempt_ledger_path"
            ]
        ),
        Path(
            protocol[
                "response_spool_directory"
            ]
        ),
        Path(
            protocol[
                "final_result_spool_path"
            ]
        ),
    ]

    if include_cache:
        paths.append(
            LIVE_EXTRACTION_CACHE
        )

    existing = [
        str(
            path
        )
        for path
        in paths
        if path.exists()
    ]

    if existing:
        raise LiveHarnessError(
            "fresh attempt namespace is not empty: "
            + ", ".join(
                existing
            )
        )


def prepare_target_authority(
    seal: dict[str, Any],
    *,
    cache_root: Path,
):
    from horizon.cache.content import (
        ContentAddressedExtractionCache,
    )
    from horizon.investigation.deterministic_evidence_records import (
        canonical_declared_dependencies_evidence_record,
        canonical_git_blob_evidence_record,
    )
    from horizon.investigation.semantic_gap import (
        RepositorySemanticGapSection,
        discover_repository_semantic_gaps,
    )
    from horizon.languages.python.project_dependencies import (
        discover_declared_project_dependencies,
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
    from horizon.world_model.repository_deterministic import (
        build_repository_deterministic_world_model,
    )
    from horizon.world_model.repository_semantic_store import (
        RepositorySemanticWorldModelStore,
    )

    target_value = seal[
        "target"
    ]

    target = path_from_seal(
        target_value[
            "path"
        ],
        name="target",
    )

    observation = observe_git_commit(
        target,
        target_value[
            "commit"
        ],
    )

    if (
        observation.observation_id
        != target_value[
            "repository_observation_id"
        ]
    ):
        raise LiveHarnessError(
            "repository observation identity mismatch"
        )

    cache = ContentAddressedExtractionCache(
        cache_root
    )

    index = index_python_repository(
        target,
        observation,
        cache,
    )

    pyproject_blob = read_observed_blob(
        target,
        observation,
        "pyproject.toml",
    )

    dependencies = (
        discover_declared_project_dependencies(
            pyproject_blob
        )
    )

    base_model = (
        build_repository_deterministic_world_model(
            index,
            pyproject_blob=(
                pyproject_blob
            ),
            project_dependencies=(
                dependencies
            ),
        )
    )

    if (
        base_model.snapshot.snapshot_id
        != target_value[
            "base_world_model_snapshot_id"
        ]
    ):
        raise LiveHarnessError(
            "base World Model snapshot mismatch"
        )

    initial_evidence = (
        canonical_declared_dependencies_evidence_record(
            dependencies
        ),
        canonical_git_blob_evidence_record(
            pyproject_blob
        ),
    )

    evidence_ids = [
        record.evidence_id
        for record
        in initial_evidence
    ]

    if (
        evidence_ids
        != target_value[
            "initial_evidence_ids"
        ]
    ):
        raise LiveHarnessError(
            "initial evidence identity mismatch"
        )

    gaps = discover_repository_semantic_gaps(
        index,
        base_model,
    )

    matches = [
        question
        for question
        in gaps.questions
        if (
            question.section
            is RepositorySemanticGapSection
            .WHAT_IT_IS
        )
    ]

    if len(
        matches
    ) != 1:
        raise LiveHarnessError(
            "WHAT_IT_IS gap cardinality mismatch"
        )

    question = matches[
        0
    ]

    if (
        question.gap_id
        != target_value[
            "what_it_is_gap_id"
        ]
    ):
        raise LiveHarnessError(
            "WHAT_IT_IS gap identity mismatch"
        )

    if (
        question.question_id
        != target_value[
            "what_it_is_question_id"
        ]
    ):
        raise LiveHarnessError(
            "WHAT_IT_IS question identity mismatch"
        )

    overlay = path_from_seal(
        target_value[
            "semantic_overlay_path"
        ],
        name="semantic overlay",
    )

    store = RepositorySemanticWorldModelStore(
        overlay.parent
    )

    if (
        store.path_for(
            base_model
        ).resolve()
        != overlay
    ):
        raise LiveHarnessError(
            "semantic overlay derivation mismatch"
        )

    return (
        observation,
        index,
        base_model,
        initial_evidence,
        store,
    )


def response_field(
    value: object,
    name: str,
    default: object = None,
) -> object:
    if isinstance(
        value,
        Mapping,
    ):
        return value.get(
            name,
            default,
        )

    return getattr(
        value,
        name,
        default,
    )


def token_count(
    value: object,
    *,
    name: str,
) -> int:
    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            int,
        )
        or value < 0
    ):
        raise LiveHarnessError(
            name
            + " must be a nonnegative integer"
        )

    return value


def response_usage_cost(
    response: object,
    *,
    seal: dict[str, Any],
) -> tuple[
    int,
    int,
    Decimal,
]:
    usage = response_field(
        response,
        "usage",
    )

    if usage is None:
        raise LiveHarnessError(
            "provider response usage is missing"
        )

    input_tokens = token_count(
        response_field(
            usage,
            "input_tokens",
        ),
        name="input tokens",
    )

    output_tokens = token_count(
        response_field(
            usage,
            "output_tokens",
        ),
        name="output tokens",
    )

    details = response_field(
        usage,
        "input_tokens_details",
    )

    if details is None:
        cached_tokens = 0
        cache_write_tokens = 0

    else:
        cached_raw = response_field(
            details,
            "cached_tokens",
            0,
        )

        cache_write_raw = response_field(
            details,
            "cache_write_tokens",
            0,
        )

        if cached_raw is None:
            cached_raw = 0

        if cache_write_raw is None:
            cache_write_raw = 0

        cached_tokens = token_count(
            cached_raw,
            name="cached input tokens",
        )

        cache_write_tokens = token_count(
            cache_write_raw,
            name="cache-write input tokens",
        )

    if (
        cached_tokens
        + cache_write_tokens
        > input_tokens
    ):
        raise LiveHarnessError(
            "cached plus cache-write tokens exceed input tokens"
        )

    pricing = seal[
        "cost_authority"
    ][
        "pricing_usd_per_million_tokens"
    ]

    uncached_tokens = (
        input_tokens
        - cached_tokens
        - cache_write_tokens
    )

    million = Decimal(
        "1000000"
    )

    cost = (
        (
            Decimal(
                uncached_tokens
            )
            * Decimal(
                pricing[
                    "input_per_million"
                ]
            )
        )
        + (
            Decimal(
                cached_tokens
            )
            * Decimal(
                pricing[
                    "cached_input_per_million"
                ]
            )
        )
        + (
            Decimal(
                cache_write_tokens
            )
            * Decimal(
                pricing[
                    "cache_write_per_million"
                ]
            )
        )
        + (
            Decimal(
                output_tokens
            )
            * Decimal(
                pricing[
                    "output_per_million"
                ]
            )
        )
    ) / million

    return (
        input_tokens,
        output_tokens,
        cost,
    )


def serialized_provider_response(
    response: object,
) -> dict[str, Any]:
    model_dump = getattr(
        response,
        "model_dump",
        None,
    )

    full_response = None

    if callable(
        model_dump
    ):
        try:
            full_response = model_dump(
                mode="json"
            )

        except TypeError:
            full_response = model_dump()

    return {
        "status": response_field(
            response,
            "status",
        ),
        "returned_model": response_field(
            response,
            "model",
        ),
        "api_request_id": response_field(
            response,
            "_request_id",
        ),
        "output_text": response_field(
            response,
            "output_text",
        ),
        "usage": canonical_value(
            response_field(
                response,
                "usage",
            )
        ),
        "sdk_response": (
            None
            if full_response is None
            else canonical_value(
                full_response
            )
        ),
    }


class DurableAttemptState:
    def __init__(
        self,
        *,
        seal: dict[str, Any],
        ledger: Path,
        spool: Path,
    ) -> None:
        self.seal = seal
        self.ledger = ledger
        self.spool = spool

        self.next_ordinal = 1

        self.cumulative_cost = Decimal(
            "0"
        )

    @property
    def max_provider_calls(
        self,
    ) -> int:
        return int(
            self.seal[
                "coordinator_limits"
            ][
                "max_provider_calls"
            ]
        )

    @property
    def aggregate_cap(
        self,
    ) -> Decimal:
        return Decimal(
            self.seal[
                "cost_authority"
            ][
                "aggregate_exam_cap_usd"
            ]
        )

    def initialize(
        self,
    ) -> None:
        if self.ledger.exists():
            raise LiveHarnessError(
                "attempt ledger already exists"
            )

        if self.spool.exists():
            raise LiveHarnessError(
                "response spool already exists"
            )

        self.spool.mkdir(
            parents=True,
            mode=0o700,
            exist_ok=False,
        )

        fsync_directory(
            self.spool.parent
        )

        write_exclusive_bytes(
            self.ledger,
            (
                canonical_bytes(
                    {
                        "event": (
                            "ATTEMPT_STARTED"
                        ),
                        "attempt_id": (
                            self.seal[
                                "attempt"
                            ][
                                "attempt_id"
                            ]
                        ),
                        "seal_id": (
                            self.seal[
                                "seal_id"
                            ]
                        ),
                        "local_provider_call_ordinal_starts_at": (
                            1
                        ),
                    }
                )
                + b"\n"
            ),
        )

    def append_event(
        self,
        value: dict[str, Any],
    ) -> None:
        append_jsonl_fsync(
            self.ledger,
            value,
        )

    def before_call(
        self,
        *,
        role: str,
        call_kwargs: dict[str, object],
    ) -> int:
        ordinal = (
            self.next_ordinal
        )

        if ordinal > self.max_provider_calls:
            raise LiveHarnessError(
                "provider-call count authority exhausted"
            )

        if (
            self.cumulative_cost
            >= self.aggregate_cap
        ):
            raise LiveHarnessError(
                "aggregate model-cost authority exhausted"
            )

        configured_model = (
            call_kwargs.get(
                "model"
            )
        )

        if (
            configured_model
            != self.seal[
                "model"
            ][
                "model_id"
            ]
        ):
            raise LiveHarnessError(
                "provider model differs from R47 seal"
            )

        request_hash = sha256_bytes(
            canonical_bytes(
                call_kwargs
            )
        )

        self.append_event(
            {
                "event": "ATTEMPT",
                "ordinal": ordinal,
                "provider_role": role,
                "model": configured_model,
                "reasoning_effort": (
                    self.seal[
                        "model"
                    ][
                        "reasoning_effort"
                    ]
                ),
                "max_output_tokens": (
                    self.seal[
                        "model"
                    ][
                        "max_output_tokens"
                    ]
                ),
                "request_call_sha256": (
                    request_hash
                ),
                "cumulative_cost_before_usd": (
                    str(
                        self.cumulative_cost
                    )
                ),
                "aggregate_cost_cap_usd": (
                    str(
                        self.aggregate_cap
                    )
                ),
            }
        )

        self.next_ordinal += 1

        return ordinal

    def provider_failed(
        self,
        *,
        ordinal: int,
        role: str,
        exc: BaseException,
    ) -> None:
        self.append_event(
            {
                "event": "FAILED",
                "ordinal": ordinal,
                "provider_role": role,
                "exception_class": (
                    type(
                        exc
                    ).__name__
                ),
                "message": str(
                    exc
                ),
                "automatic_retry": False,
            }
        )

    def spool_response(
        self,
        *,
        ordinal: int,
        role: str,
        response: object,
    ) -> Path:
        response_path = (
            self.spool
            / (
                "response-"
                + f"{ordinal:04d}"
                + ".json"
            )
        )

        payload = {
            "ordinal": ordinal,
            "provider_role": role,
            "response": (
                serialized_provider_response(
                    response
                )
            ),
        }

        write_exclusive_json(
            response_path,
            payload,
        )

        response_sha = sha256_file(
            response_path
        )

        try:
            (
                input_tokens,
                output_tokens,
                cost,
            ) = response_usage_cost(
                response,
                seal=self.seal,
            )

        except BaseException as exc:
            self.append_event(
                {
                    "event": (
                        "RESPONSE_SPOOLED"
                    ),
                    "ordinal": ordinal,
                    "provider_role": role,
                    "response_path": str(
                        response_path
                    ),
                    "response_sha256": (
                        response_sha
                    ),
                    "cost_meter_valid": False,
                    "cost_meter_error": (
                        type(
                            exc
                        ).__name__
                        + ": "
                        + str(
                            exc
                        )
                    ),
                }
            )

            raise

        self.cumulative_cost += (
            cost
        )

        self.append_event(
            {
                "event": (
                    "RESPONSE_SPOOLED"
                ),
                "ordinal": ordinal,
                "provider_role": role,
                "response_path": str(
                    response_path
                ),
                "response_sha256": (
                    response_sha
                ),
                "status": response_field(
                    response,
                    "status",
                ),
                "returned_model": (
                    response_field(
                        response,
                        "model",
                    )
                ),
                "api_request_id": (
                    response_field(
                        response,
                        "_request_id",
                    )
                ),
                "input_tokens": (
                    input_tokens
                ),
                "output_tokens": (
                    output_tokens
                ),
                "conservative_cost_usd": (
                    str(
                        cost
                    )
                ),
                "cumulative_cost_usd": (
                    str(
                        self.cumulative_cost
                    )
                ),
                "cost_meter_valid": True,
            }
        )

        if (
            self.cumulative_cost
            > self.aggregate_cap
        ):
            raise LiveHarnessError(
                "completed provider response exceeds "
                "aggregate model-cost authority"
            )

        return response_path


class DurableResponses:
    def __init__(
        self,
        *,
        inner: object,
        state: DurableAttemptState,
        role: str,
    ) -> None:
        create = getattr(
            inner,
            "create",
            None,
        )

        if not callable(
            create
        ):
            raise LiveHarnessError(
                "inner responses object does not expose create"
            )

        self.inner = inner
        self.state = state
        self.role = role

    def create(
        self,
        **kwargs,
    ):
        ordinal = (
            self.state
            .before_call(
                role=self.role,
                call_kwargs=kwargs,
            )
        )

        try:
            response = (
                self.inner
                .create(
                    **kwargs
                )
            )

        except BaseException as exc:
            self.state.provider_failed(
                ordinal=ordinal,
                role=self.role,
                exc=exc,
            )

            raise

        #
        # Critical durability boundary:
        #
        # The SDK response is persisted + fsynced and
        # RESPONSE_SPOOLED is fsynced to the ledger
        # BEFORE the production Horizon adapter receives
        # this response and begins parsing/semantic validation.
        #
        self.state.spool_response(
            ordinal=ordinal,
            role=self.role,
            response=response,
        )

        return response


class DurableClient:
    def __init__(
        self,
        *,
        inner_client: object,
        state: DurableAttemptState,
        role: str,
    ) -> None:
        responses = getattr(
            inner_client,
            "responses",
            None,
        )

        if responses is None:
            raise LiveHarnessError(
                "OpenAI client has no responses boundary"
            )

        self.responses = DurableResponses(
            inner=responses,
            state=state,
            role=role,
        )


def create_live_lock(
    lock: Path,
    *,
    seal: dict[str, Any],
    runner_sha256: str,
    certificate_sha256: str,
) -> None:
    write_exclusive_json(
        lock,
        {
            "attempt_id": (
                seal[
                    "attempt"
                ][
                    "attempt_id"
                ]
            ),
            "seal_id": (
                seal[
                    "seal_id"
                ]
            ),
            "runner_sha256": (
                runner_sha256
            ),
            "certificate_sha256": (
                certificate_sha256
            ),
            "provider_calls_before_lock": 0,
        },
    )


def live_paths(
    seal: dict[str, Any],
) -> tuple[
    Path,
    Path,
    Path,
    Path,
]:
    protocol = seal[
        "attempt_spool_protocol"
    ]

    return (
        Path(
            protocol[
                "live_lock_path"
            ]
        ),
        Path(
            protocol[
                "attempt_ledger_path"
            ]
        ),
        Path(
            protocol[
                "response_spool_directory"
            ]
        ),
        Path(
            protocol[
                "final_result_spool_path"
            ]
        ),
    )


def validate_committed_live_authority(
    *,
    repository: Path,
    seal: dict[str, Any],
    seal_path: Path,
    certificate_path: Path,
) -> dict[str, Any]:
    certificate = load_json(
        certificate_path
    )

    if (
        certificate.get(
            "status"
        )
        != "PASS"
    ):
        raise LiveHarnessError(
            "R48 harness certificate is not PASS"
        )

    runner_path = Path(
        __file__
    ).resolve()

    runner_sha = sha256_file(
        runner_path
    )

    if (
        certificate.get(
            "runner_sha256"
        )
        != runner_sha
    ):
        raise LiveHarnessError(
            "live runner bytes differ from R48 certificate"
        )

    seal_sha = sha256_file(
        seal_path
    )

    if (
        certificate.get(
            "r47_seal_sha256"
        )
        != seal_sha
    ):
        raise LiveHarnessError(
            "R47 seal bytes differ from R48 certificate"
        )

    branch = git(
        repository,
        "branch",
        "--show-current",
    )

    expected_branch = (
        seal[
            "runner_authority"
        ][
            "branch"
        ]
    )

    if branch != expected_branch:
        raise LiveHarnessError(
            "live host branch mismatch"
        )

    if git(
        repository,
        "status",
        "--short",
    ):
        raise LiveHarnessError(
            "live host working tree is not clean"
        )

    current_head = git(
        repository,
        "rev-parse",
        "HEAD",
    )

    runner_relative = str(
        runner_path.relative_to(
            repository
        )
    )

    certificate_relative = str(
        certificate_path.resolve().relative_to(
            repository
        )
    )

    runner_commit = git(
        repository,
        "log",
        "-1",
        "--format=%H",
        "--",
        runner_relative,
    )

    certificate_commit = git(
        repository,
        "log",
        "-1",
        "--format=%H",
        "--",
        certificate_relative,
    )

    if (
        not runner_commit
        or runner_commit
        != certificate_commit
        or current_head
        != runner_commit
    ):
        raise LiveHarnessError(
            "current HEAD is not the exact committed "
            "R48 runner+certificate authority"
        )

    remote = subprocess.run(
        [
            "git",
            "-C",
            str(
                repository
            ),
            "ls-remote",
            "origin",
            (
                "refs/heads/"
                + expected_branch
            ),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()

    if not remote:
        raise LiveHarnessError(
            "remote branch authority is absent"
        )

    remote_head = remote.split(
        None,
        1,
    )[
        0
    ]

    if remote_head != current_head:
        raise LiveHarnessError(
            "R48 live authority has not been pushed exactly"
        )

    src_tree = git(
        repository,
        "rev-parse",
        "HEAD:src",
    )

    if (
        src_tree
        != seal[
            "runner_authority"
        ][
            "production_src_tree"
        ]
    ):
        raise LiveHarnessError(
            "production src tree changed after certification"
        )

    r47_head = (
        EXPECTED_R47_COMMIT
    )

    subprocess.run(
        [
            "git",
            "-C",
            str(
                repository
            ),
            "merge-base",
            "--is-ancestor",
            r47_head,
            current_head,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return certificate


def model_pricing(
    seal: dict[str, Any],
):
    pricing = seal[
        "cost_authority"
    ][
        "pricing_usd_per_million_tokens"
    ]

    values = {
        "input_per_million": Decimal(
            pricing[
                "input_per_million"
            ]
        ),
        "cached_input_per_million": Decimal(
            pricing[
                "cached_input_per_million"
            ]
        ),
        "cache_write_per_million": Decimal(
            pricing[
                "cache_write_per_million"
            ]
        ),
        "output_per_million": Decimal(
            pricing[
                "output_per_million"
            ]
        ),
    }

    return values


def result_payload(
    execution,
    *,
    seal: dict[str, Any],
    attempt_state: DurableAttemptState,
) -> dict[str, Any]:
    evaluation = (
        execution.evaluation
    )

    proposal = (
        execution.proposal
    )

    return {
        "status": "COMPLETED",
        "attempt_id": (
            seal[
                "attempt"
            ][
                "attempt_id"
            ]
        ),
        "seal_id": (
            seal[
                "seal_id"
            ]
        ),
        "disposition": (
            execution.disposition.value
        ),
        "investigator_rounds_completed": (
            execution.investigator_rounds_completed
        ),
        "hypothesis_rounds_completed": (
            execution.hypothesis_rounds_completed
        ),
        "total_model_cost_usd": (
            str(
                execution.total_model_cost_usd
            )
        ),
        "independent_spool_meter_cost_usd": (
            str(
                attempt_state.cumulative_cost
            )
        ),
        "provider_calls_completed": (
            attempt_state.next_ordinal
            - 1
        ),
        "investigator_run_ids": list(
            execution.investigator_run_ids
        ),
        "planner_run_ids": list(
            execution.planner_run_ids
        ),
        "evaluation_run_ids": list(
            execution.evaluation_run_ids
        ),
        "operation_observation_ids": list(
            execution.operation_observation_ids
        ),
        "evidence_record_ids": list(
            execution.evidence_record_ids
        ),
        "persisted_overlay_path": (
            execution.persisted_overlay_path
        ),
        "proposal": (
            None
            if proposal is None
            else canonical_value(
                proposal
            )
        ),
        "evaluation": (
            None
            if evaluation is None
            else canonical_value(
                evaluation
            )
        ),
    }



def require_local_api_key_presence() -> None:
    """
    Presence-only preflight.

    This deliberately does not return, print, hash,
    persist, transmit, or validate the credential.
    It exists only to avoid consuming a fresh live
    namespace when the environment variable is absent
    or empty.
    """
    value = os.environ.get(
        "OPENAI_API_KEY"
    )

    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise LiveHarnessError(
            "OPENAI_API_KEY local presence preflight failed"
        )


def run_live(
    *,
    seal_path: Path,
    certificate_path: Path,
) -> int:
    repository = repository_root()

    seal = validate_seal(
        seal_path
    )

    certificate = (
        validate_committed_live_authority(
            repository=repository,
            seal=seal,
            seal_path=seal_path,
            certificate_path=(
                certificate_path
            ),
        )
    )

    (
        target,
        prefect,
        overlay,
    ) = validate_target_and_control(
        seal
    )

    validate_historical_closed_attempts(
        repository=repository,
        seal=seal,
    )

    validate_repair_certifications(
        repository=repository,
        seal=seal,
    )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    #
    # R47 credential-preflight authority:
    # fail BEFORE entering the irreversible 3C
    # namespace when the variable is absent/empty.
    #
    require_local_api_key_presence()

    (
        lock,
        ledger,
        spool,
        final_result,
    ) = live_paths(
        seal
    )

    runner_sha = sha256_file(
        Path(
            __file__
        ).resolve()
    )

    certificate_sha = sha256_file(
        certificate_path
    )

    #
    # R47/R48 credential boundary:
    #
    # A presence/nonempty-only check has already
    # succeeded before namespace entry.
    #
    # The irreversible lock is now created.
    # The provider credential used for SDK
    # construction is re-read only AFTER this lock
    # and after all post-lock authority checks.
    #
    create_live_lock(
        lock,
        seal=seal,
        runner_sha256=runner_sha,
        certificate_sha256=(
            certificate_sha
        ),
    )

    attempt_state = DurableAttemptState(
        seal=seal,
        ledger=ledger,
        spool=spool,
    )

    attempt_state.initialize()

    try:
        #
        # Re-check every repository authority after
        # the lock and before credential access.
        #
        validate_committed_live_authority(
            repository=repository,
            seal=seal,
            seal_path=seal_path,
            certificate_path=(
                certificate_path
            ),
        )

        (
            target,
            prefect,
            overlay,
        ) = validate_target_and_control(
            seal
        )

        validate_historical_closed_attempts(
            repository=repository,
            seal=seal,
        )

        validate_repair_certifications(
            repository=repository,
            seal=seal,
        )

        if LIVE_EXTRACTION_CACHE.exists():
            raise LiveHarnessError(
                "live extraction cache appeared before target preparation"
            )

        (
            observation,
            index,
            base_model,
            initial_evidence,
            semantic_store,
        ) = prepare_target_authority(
            seal,
            cache_root=(
                LIVE_EXTRACTION_CACHE
            ),
        )

        #
        # Only now may the credential be read.
        #
        api_key = os.environ.get(
            "OPENAI_API_KEY"
        )

        if (
            not isinstance(
                api_key,
                str,
            )
            or not api_key.strip()
        ):
            raise LiveHarnessError(
                "OPENAI_API_KEY is absent after live lock creation"
            )

        from openai import OpenAI

        from horizon.investigation.providers.openai_hypothesis_evaluation import (
            OpenAIHypothesisEvaluationTokenPricing,
            OpenAIResponsesHypothesisEvaluationModel,
        )
        from horizon.investigation.providers.openai_responses import (
            OpenAIResponsesTypedPlannerModel,
            OpenAITypedPlannerTokenPricing,
        )
        from horizon.investigation.semantic_understanding_coordinator import (
            RepositorySemanticUnderstandingDisposition,
            RepositorySemanticUnderstandingLimits,
            run_repository_what_it_is_semantic_understanding,
        )
        from horizon.investigator.providers.openai_responses import (
            OpenAIResponsesInvestigatorModel,
            OpenAITokenPricing,
        )

        model = seal[
            "model"
        ]

        inner_client = OpenAI(
            api_key=api_key,
            max_retries=0,
            timeout=float(
                model[
                    "timeout_seconds"
                ]
            ),
        )

        pricing_values = (
            model_pricing(
                seal
            )
        )

        investigator_model = (
            OpenAIResponsesInvestigatorModel(
                client=DurableClient(
                    inner_client=(
                        inner_client
                    ),
                    state=attempt_state,
                    role="INVESTIGATOR",
                ),
                model_id=(
                    model[
                        "model_id"
                    ]
                ),
                reasoning_effort=(
                    model[
                        "reasoning_effort"
                    ]
                ),
                max_output_tokens=(
                    model[
                        "max_output_tokens"
                    ]
                ),
                pricing=OpenAITokenPricing(
                    **pricing_values
                ),
            )
        )

        planner_model = (
            OpenAIResponsesTypedPlannerModel(
                client=DurableClient(
                    inner_client=(
                        inner_client
                    ),
                    state=attempt_state,
                    role="TYPED_PLANNER",
                ),
                model_id=(
                    model[
                        "model_id"
                    ]
                ),
                reasoning_effort=(
                    model[
                        "reasoning_effort"
                    ]
                ),
                max_output_tokens=(
                    model[
                        "max_output_tokens"
                    ]
                ),
                pricing=(
                    OpenAITypedPlannerTokenPricing(
                        **pricing_values
                    )
                ),
            )
        )

        evaluator_model = (
            OpenAIResponsesHypothesisEvaluationModel(
                client=DurableClient(
                    inner_client=(
                        inner_client
                    ),
                    state=attempt_state,
                    role="HYPOTHESIS_EVALUATOR",
                ),
                model_id=(
                    model[
                        "model_id"
                    ]
                ),
                reasoning_effort=(
                    model[
                        "reasoning_effort"
                    ]
                ),
                max_output_tokens=(
                    model[
                        "max_output_tokens"
                    ]
                ),
                pricing=(
                    OpenAIHypothesisEvaluationTokenPricing(
                        **pricing_values
                    )
                ),
            )
        )

        limits_value = seal[
            "coordinator_limits"
        ]

        limits = (
            RepositorySemanticUnderstandingLimits(
                max_investigator_rounds=(
                    limits_value[
                        "max_investigator_rounds"
                    ]
                ),
                max_hypothesis_rounds=(
                    limits_value[
                        "max_hypothesis_rounds"
                    ]
                ),
                max_plan_steps=(
                    limits_value[
                        "max_plan_steps"
                    ]
                ),
                max_plan_total_seconds=(
                    limits_value[
                        "max_plan_total_seconds"
                    ]
                ),
                max_evidence_record_bytes=(
                    limits_value[
                        "max_evidence_record_bytes"
                    ]
                ),
                max_total_evidence_bytes=(
                    limits_value[
                        "max_total_evidence_bytes"
                    ]
                ),
                max_total_model_cost_usd=Decimal(
                    limits_value[
                        "max_total_model_cost_usd"
                    ]
                ),
            )
        )

        aggregate_cap = Decimal(
            seal[
                "cost_authority"
            ][
                "aggregate_exam_cap_usd"
            ]
        )

        instructions = seal[
            "instructions"
        ]

        execution = (
            run_repository_what_it_is_semantic_understanding(
                repository=target,
                observation=observation,
                index=index,
                base_model=base_model,
                initial_evidence_records=(
                    initial_evidence
                ),
                semantic_store=(
                    semantic_store
                ),
                investigator_model=(
                    investigator_model
                ),
                typed_planner_model=(
                    planner_model
                ),
                evaluation_model=(
                    evaluator_model
                ),
                investigator_instruction=(
                    instructions[
                        "investigator"
                    ][
                        "utf8"
                    ].encode(
                        "utf-8"
                    )
                ),
                investigator_temperature=(
                    model[
                        "temperature"
                    ]
                ),
                investigator_cost_cap_usd=(
                    aggregate_cap
                ),
                typed_planner_instruction=(
                    instructions[
                        "typed_planner"
                    ][
                        "utf8"
                    ].encode(
                        "utf-8"
                    )
                ),
                typed_planner_temperature=(
                    model[
                        "temperature"
                    ]
                ),
                typed_planner_cost_cap_usd=(
                    aggregate_cap
                ),
                evaluation_instruction=(
                    instructions[
                        "hypothesis_evaluator"
                    ][
                        "utf8"
                    ].encode(
                        "utf-8"
                    )
                ),
                evaluation_temperature=(
                    model[
                        "temperature"
                    ]
                ),
                evaluation_cost_cap_usd=(
                    aggregate_cap
                ),
                limits=limits,
            )
        )

        #
        # Repository post-guards.
        #
        validate_frozen_repository(
            target,
            expected_head=(
                seal[
                    "target"
                ][
                    "commit"
                ]
            ),
            expected_tree=(
                seal[
                    "target"
                ][
                    "tree"
                ]
            ),
            require_remote_free=True,
        )

        validate_frozen_repository(
            prefect,
            expected_head=(
                seal[
                    "control_repository"
                ][
                    "commit"
                ]
            ),
            expected_tree=(
                seal[
                    "control_repository"
                ][
                    "tree"
                ]
            ),
            require_remote_free=False,
        )

        if (
            execution.disposition
            is RepositorySemanticUnderstandingDisposition
            .PROMOTED
        ):
            if not overlay.is_file():
                raise LiveHarnessError(
                    "PROMOTED result did not persist semantic overlay"
                )

            if (
                execution.persisted_overlay_path
                is None
                or Path(
                    execution.persisted_overlay_path
                ).resolve()
                != overlay
            ):
                raise LiveHarnessError(
                    "PROMOTED result persisted unexpected overlay"
                )

        else:
            if overlay.exists():
                raise LiveHarnessError(
                    "non-PROMOTED execution created semantic overlay"
                )

        payload = result_payload(
            execution,
            seal=seal,
            attempt_state=(
                attempt_state
            ),
        )

        write_exclusive_json(
            final_result,
            payload,
        )

        attempt_state.append_event(
            {
                "event": "RUN_COMPLETED",
                "disposition": (
                    execution.disposition.value
                ),
                "provider_calls_completed": (
                    attempt_state.next_ordinal
                    - 1
                ),
                "coordinator_cost_usd": (
                    str(
                        execution
                        .total_model_cost_usd
                    )
                ),
                "independent_spool_meter_cost_usd": (
                    str(
                        attempt_state
                        .cumulative_cost
                    )
                ),
                "final_result_path": str(
                    final_result
                ),
                "final_result_sha256": (
                    sha256_file(
                        final_result
                    )
                ),
            }
        )

        print(
            "LIVE_EXECUTION_COMPLETED"
        )

        print(
            "DISPOSITION="
            + execution.disposition.value
        )

        print(
            "PROVIDER_CALLS="
            + str(
                attempt_state.next_ordinal
                - 1
            )
        )

        print(
            "TOTAL_MODEL_COST_USD="
            + str(
                execution.total_model_cost_usd
            )
        )

        print(
            "RESULT_SPOOL="
            + str(
                final_result
            )
        )

        return 0

    except BaseException as exc:
        if attempt_state.ledger.exists():
            attempt_state.append_event(
                {
                    "event": "RUN_FAILED",
                    "exception_class": (
                        type(
                            exc
                        ).__name__
                    ),
                    "message": str(
                        exc
                    ),
                    "automatic_retry": False,
                    "provider_calls_completed": (
                        attempt_state.next_ordinal
                        - 1
                    ),
                    "independent_spool_meter_cost_usd": (
                        str(
                            attempt_state
                            .cumulative_cost
                        )
                    ),
                }
            )

        if not final_result.exists():
            write_exclusive_json(
                final_result,
                {
                    "status": "FAILED",
                    "attempt_id": (
                        seal[
                            "attempt"
                        ][
                            "attempt_id"
                        ]
                    ),
                    "seal_id": (
                        seal[
                            "seal_id"
                        ]
                    ),
                    "exception_class": (
                        type(
                            exc
                        ).__name__
                    ),
                    "message": str(
                        exc
                    ),
                    "automatic_retry": False,
                    "provider_calls_completed": (
                        attempt_state.next_ordinal
                        - 1
                    ),
                    "independent_spool_meter_cost_usd": (
                        str(
                            attempt_state
                            .cumulative_cost
                        )
                    ),
                },
            )

        raise


class FakeResponse:
    def __init__(
        self,
    ) -> None:
        self.status = "completed"

        self.model = (
            "gpt-6-astra"
        )

        self._request_id = (
            "req_r48_offline_fake"
        )

        self.output_text = (
            '{"offline":"certification"}'
        )

        self.usage = {
            "input_tokens": 100,
            "output_tokens": 10,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 0,
            },
        }

    def model_dump(
        self,
        *,
        mode: str = "json",
    ):
        return {
            "status": self.status,
            "model": self.model,
            "output_text": (
                self.output_text
            ),
            "usage": {
                "input_tokens": 100,
                "output_tokens": 10,
                "input_tokens_details": {
                    "cached_tokens": 0,
                    "cache_write_tokens": 0,
                },
            },
        }


class FakeResponses:
    def __init__(
        self,
    ) -> None:
        self.calls = 0

    def create(
        self,
        **kwargs,
    ):
        self.calls += 1

        return FakeResponse()


def offline_certify(
    *,
    seal_path: Path,
    certificate_path: Path,
) -> int:
    repository = repository_root()

    seal = validate_seal(
        seal_path
    )

    if (
        git(
            repository,
            "branch",
            "--show-current",
        )
        != seal[
            "runner_authority"
        ][
            "branch"
        ]
    ):
        raise LiveHarnessError(
            "offline-certification branch mismatch"
        )

    if (
        git(
            repository,
            "rev-parse",
            "HEAD",
        )
        != EXPECTED_R47_COMMIT
    ):
        raise LiveHarnessError(
            "offline certification is not running at R47 HEAD"
        )

    if (
        git(
            repository,
            "rev-parse",
            "HEAD:src",
        )
        != seal[
            "runner_authority"
        ][
            "production_src_tree"
        ]
    ):
        raise LiveHarnessError(
            "production source authority changed"
        )

    (
        target,
        prefect,
        overlay,
    ) = validate_target_and_control(
        seal
    )

    validate_historical_closed_attempts(
        repository=repository,
        seal=seal,
    )

    validate_repair_certifications(
        repository=repository,
        seal=seal,
    )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    #
    # Prove the new credential preflight offline.
    #
    # The real OPENAI_API_KEY must be absent during
    # certification. We first prove absence fails
    # without creating any 3C live state, then use
    # a local fake sentinel solely to prove that a
    # nonempty value passes. No SDK is constructed.
    #
    if "OPENAI_API_KEY" in os.environ:
        raise LiveHarnessError(
            "offline certification requires OPENAI_API_KEY absent"
        )

    missing_preflight_failed = False

    try:
        require_local_api_key_presence()
    except LiveHarnessError as exc:
        if (
            str(
                exc
            )
            != "OPENAI_API_KEY local presence preflight failed"
        ):
            raise

        missing_preflight_failed = True

    if not missing_preflight_failed:
        raise LiveHarnessError(
            "missing credential preflight did not fail closed"
        )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    os.environ[
        "OPENAI_API_KEY"
    ] = "horizon-r48-offline-presence-sentinel"

    try:
        require_local_api_key_presence()
    finally:
        os.environ.pop(
            "OPENAI_API_KEY",
            None,
        )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="horizon-r48-"
    ) as temporary_raw:
        temporary = Path(
            temporary_raw
        )

        (
            observation,
            index,
            base_model,
            initial_evidence,
            semantic_store,
        ) = prepare_target_authority(
            seal,
            cache_root=(
                temporary
                / "target-cache"
            ),
        )

        #
        # Exercise the exact durable response boundary
        # with a fake SDK response. This is NOT a
        # provider/network call.
        #
        fake_lock = (
            temporary
            / "live.lock"
        )

        fake_ledger = (
            temporary
            / "attempt.jsonl"
        )

        fake_spool = (
            temporary
            / "spool"
        )

        write_exclusive_json(
            fake_lock,
            {
                "offline": True,
            },
        )

        state = DurableAttemptState(
            seal=seal,
            ledger=fake_ledger,
            spool=fake_spool,
        )

        state.initialize()

        fake_inner = FakeResponses()

        durable = DurableResponses(
            inner=fake_inner,
            state=state,
            role=(
                "OFFLINE_FAKE_PROVIDER"
            ),
        )

        returned = durable.create(
            model=(
                seal[
                    "model"
                ][
                    "model_id"
                ]
            ),
            instructions=(
                "offline-certification"
            ),
            input="{}",
            text={
                "format": {
                    "type": (
                        "json_schema"
                    )
                }
            },
            max_output_tokens=(
                seal[
                    "model"
                ][
                    "max_output_tokens"
                ]
            ),
            store=False,
            reasoning={
                "effort": (
                    seal[
                        "model"
                    ][
                        "reasoning_effort"
                    ]
                )
            },
        )

        if returned is None:
            raise LiveHarnessError(
                "durable fake boundary did not return response"
            )

        if fake_inner.calls != 1:
            raise LiveHarnessError(
                "fake provider call count mismatch"
            )

        response_path = (
            fake_spool
            / "response-0001.json"
        )

        if not response_path.is_file():
            raise LiveHarnessError(
                "durable response spool was not created"
            )

        ledger_lines = [
            json.loads(
                line
            )
            for line
            in fake_ledger.read_text(
                encoding="utf-8"
            ).splitlines()
            if line
        ]

        events = [
            item[
                "event"
            ]
            for item
            in ledger_lines
        ]

        if events != [
            "ATTEMPT_STARTED",
            "ATTEMPT",
            "RESPONSE_SPOOLED",
        ]:
            raise LiveHarnessError(
                "durable ledger event order mismatch"
            )

        spooled_event = (
            ledger_lines[
                -1
            ]
        )

        if (
            spooled_event[
                "response_sha256"
            ]
            != sha256_file(
                response_path
            )
        ):
            raise LiveHarnessError(
                "response spool hash mismatch"
            )

        if (
            spooled_event[
                "cost_meter_valid"
            ]
            is not True
        ):
            raise LiveHarnessError(
                "offline response cost meter failed"
            )

        if overlay.exists():
            raise LiveHarnessError(
                "offline certification mutated semantic store"
            )

        validate_frozen_repository(
            target,
            expected_head=(
                seal[
                    "target"
                ][
                    "commit"
                ]
            ),
            expected_tree=(
                seal[
                    "target"
                ][
                    "tree"
                ]
            ),
            require_remote_free=True,
        )

        validate_frozen_repository(
            prefect,
            expected_head=(
                seal[
                    "control_repository"
                ][
                    "commit"
                ]
            ),
            expected_tree=(
                seal[
                    "control_repository"
                ][
                    "tree"
                ]
            ),
            require_remote_free=False,
        )

    runner_path = Path(
        __file__
    ).resolve()

    certificate = {
        "certification": (
            "R48_EXACT_LIVE_HARNESS_OFFLINE_CERTIFICATION"
        ),
        "status": "PASS",

        "r47_seal_id": (
            seal[
                "seal_id"
            ]
        ),

        "r47_seal_sha256": (
            sha256_file(
                seal_path
            )
        ),

        "r47_head": (
            EXPECTED_R47_COMMIT
        ),

        "runner_path": str(
            runner_path.relative_to(
                repository
            )
        ),

        "runner_sha256": (
            sha256_file(
                runner_path
            )
        ),

        "production_src_tree": (
            seal[
                "runner_authority"
            ][
                "production_src_tree"
            ]
        ),

        "target": {
            "commit": (
                seal[
                    "target"
                ][
                    "commit"
                ]
            ),
            "tree": (
                seal[
                    "target"
                ][
                    "tree"
                ]
            ),
            "repository_observation_id": (
                seal[
                    "target"
                ][
                    "repository_observation_id"
                ]
            ),
            "base_world_model_snapshot_id": (
                seal[
                    "target"
                ][
                    "base_world_model_snapshot_id"
                ]
            ),
            "what_it_is_gap_id": (
                seal[
                    "target"
                ][
                    "what_it_is_gap_id"
                ]
            ),
            "what_it_is_question_id": (
                seal[
                    "target"
                ][
                    "what_it_is_question_id"
                ]
            ),
        },

        "historical_authority_proof": {
            "closed_3a_revalidated": True,
            "closed_3b_revalidated": True,
            "historical_live_bytes_revalidated": True,
            "revalidated_before_live_namespace_entry": True,
            "revalidated_after_live_lock_before_credential": True,
        },

        "repair_authority_proof": {
            "r45_certification_revalidated": True,
            "r46_certification_revalidated": True,
            "r45_product_commit": (
                EXPECTED_R45_PRODUCT_COMMIT
            ),
            "r46_repair_commit": (
                EXPECTED_R46_REPAIR_COMMIT
            ),
            "address_hints_non_evidentiary": True,
            "final_round_hint_consumption_certified": True,
        },

        "harness_contract": {
            "credential_presence_preflight_before_live_namespace": (
                True
            ),
            "missing_credential_preflight_burns_no_namespace": (
                True
            ),
            "provider_api_key_reloaded_after_live_lock": (
                True
            ),
            "fresh_local_provider_ordinal_starts_at_1": (
                True
            ),
            "max_provider_calls_enforced": (
                seal[
                    "coordinator_limits"
                ][
                    "max_provider_calls"
                ]
            ),
            "aggregate_cost_cap_usd": (
                seal[
                    "cost_authority"
                ][
                    "aggregate_exam_cap_usd"
                ]
            ),
            "attempt_event_fsynced_before_provider_dispatch": (
                True
            ),
            "response_spooled_before_adapter_validation": (
                True
            ),
            "response_spool_fsynced": (
                True
            ),
            "response_spool_hash_ledgered": (
                True
            ),
            "provider_exception_has_no_automatic_retry": (
                True
            ),
            "final_result_exclusive_spool": (
                True
            ),
            "current_committed_runner_required_for_live": (
                True
            ),
            "current_committed_certificate_required_for_live": (
                True
            ),
            "remote_exact_current_head_required_for_live": (
                True
            ),
            "production_src_tree_immutable": (
                True
            ),
            "frozen_target_rechecked_before_credential": (
                True
            ),
            "prefect_rechecked_before_credential": (
                True
            ),
            "semantic_overlay_absent_before_credential": (
                True
            ),
        },

        "offline_boundary_proof": {
            "fake_sdk_responses": 1,
            "network_provider_calls": 0,
            "credential_preflight_missing_fails_without_live_state": (
                True
            ),
            "credential_preflight_nonempty_passes": (
                True
            ),
            "credential_preflight_sdk_construction": (
                False
            ),
            "ledger_event_order": [
                "ATTEMPT_STARTED",
                "ATTEMPT",
                "RESPONSE_SPOOLED",
            ],
            "response_spool_hash_verified": (
                True
            ),
            "cost_meter_valid": (
                True
            ),
            "target_identity_reconstructed": (
                True
            ),
            "semantic_store_mutations": 0,
            "target_repository_mutations": 0,
            "prefect_repository_mutations": 0,
            "historical_3a_revalidated": True,
            "historical_3b_revalidated": True,
            "r45_repair_certification_revalidated": True,
            "r46_consumption_certification_revalidated": True,
        },

        "boundary": {
            "real_OPENAI_API_KEY_read": False,
            "offline_sentinel_presence_preflight": True,
            "provider_network_calls": 0,
            "paid_calls": 0,
            "live_lock_created": False,
            "live_attempt_ledger_created": False,
            "live_response_spool_created": False,
            "live_result_spool_created": False,
            "live_world_model_mutations": 0,
        },

        "next_authorized_stage": (
            "Commit and push this exact R48 runner and certificate. "
            "Only while that exact commit remains current, clean, "
            "remote-exact, R47-descended, and production-src-identical "
            "may a later explicit live-execution command enter --live."
        ),
    }

    write_exclusive_json(
        certificate_path,
        certificate,
    )

    print(
        "R47_SEAL_VALID=PASS"
    )

    print(
        "CREDENTIAL_PREFLIGHT_MISSING_FAILS_SAFE=PASS"
    )

    print(
        "CREDENTIAL_PREFLIGHT_NONEMPTY=PASS"
    )

    print(
        "CREDENTIAL_PREFLIGHT_PROVIDER_CALLS=0"
    )

    print(
        "FROZEN_TARGET_RECONSTRUCTED=PASS"
    )

    print(
        "BASE_WORLD_MODEL_IDENTITY=PASS"
    )

    print(
        "INITIAL_EVIDENCE_IDENTITY=PASS"
    )

    print(
        "WHAT_IT_IS_GAP_IDENTITY=PASS"
    )

    print(
        "DURABLE_ATTEMPT_BEFORE_DISPATCH=PASS"
    )

    print(
        "RESPONSE_SPOOLED_BEFORE_ADAPTER_RETURN=PASS"
    )

    print(
        "RESPONSE_SPOOL_FSYNC=PASS"
    )

    print(
        "RESPONSE_HASH_LEDGERED=PASS"
    )

    print(
        "OFFLINE_COST_METER=PASS"
    )

    print(
        "LIVE_API_KEY_READ=NO"
    )

    print(
        "NETWORK_PROVIDER_CALLS=0"
    )

    print(
        "WORLD_MODEL_MUTATIONS=0"
    )

    print(
        "HISTORICAL_3A_REVALIDATED=PASS"
    )

    print(
        "HISTORICAL_3B_REVALIDATED=PASS"
    )

    print(
        "R45_REPAIR_AUTHORITY_REVALIDATED=PASS"
    )

    print(
        "R46_CONSUMPTION_AUTHORITY_REVALIDATED=PASS"
    )

    print(
        "R48_CERTIFICATE_WRITTEN=PASS"
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()

    mode = parser.add_mutually_exclusive_group(
        required=True
    )

    mode.add_argument(
        "--offline-certify",
        action="store_true",
    )

    mode.add_argument(
        "--live",
        action="store_true",
    )

    parser.add_argument(
        "--seal",
        default=DEFAULT_SEAL,
    )

    parser.add_argument(
        "--certificate",
        default=DEFAULT_CERTIFICATE,
    )

    arguments = parser.parse_args()

    repository = repository_root()

    seal_path = (
        repository
        / arguments.seal
    ).resolve()

    certificate_path = (
        repository
        / arguments.certificate
    ).resolve()

    if arguments.offline_certify:
        return offline_certify(
            seal_path=seal_path,
            certificate_path=(
                certificate_path
            ),
        )

    return run_live(
        seal_path=seal_path,
        certificate_path=(
            certificate_path
        ),
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
