from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def bootstrap_repository_src() -> tuple[
    Path,
    Path,
]:
    """
    Establish the runner's own repository and src import
    authority without depending on cwd, PYTHONPATH, an
    editable install, or shell launch configuration.

    This executes at module load, before any horizon.*
    import in the live runner can execute.
    """

    runner_path = Path(
        __file__
    ).resolve()

    investigator_directory = (
        runner_path.parent
    )

    artifacts_directory = (
        investigator_directory.parent
    )

    repository = (
        artifacts_directory.parent
    ).resolve()

    if (
        investigator_directory.name
        != "investigator"
        or artifacts_directory.name
        != "artifacts"
    ):
        raise RuntimeError(
            "live runner is outside the certified "
            "artifacts/investigator repository layout"
        )

    src = (
        repository
        / "src"
    ).resolve()

    horizon_package = (
        src
        / "horizon"
    )

    if not src.is_dir():
        raise RuntimeError(
            "certified repository src directory is absent"
        )

    if not horizon_package.is_dir():
        raise RuntimeError(
            "certified Horizon source package is absent"
        )

    if not (
        repository
        / "pyproject.toml"
    ).is_file():
        raise RuntimeError(
            "certified repository pyproject.toml is absent"
        )

    src_text = str(
        src
    )

    #
    # Do not trust an externally supplied PYTHONPATH.
    # The certified repository src path wins deterministically.
    #
    sys.path[:] = [
        item
        for item
        in sys.path
        if item != src_text
    ]

    sys.path.insert(
        0,
        src_text,
    )

    return (
        repository,
        src,
    )


(
    BOOTSTRAP_REPOSITORY_ROOT,
    BOOTSTRAP_REPOSITORY_SRC,
) = bootstrap_repository_src()


EXPECTED_SEAL_STAGE = (
    "025ZZE-3F-R60"
)

EXPECTED_SEAL_ID = (
    "fresh-autonomous-semantic-self-test-seal:"
    "f060b397c9fb7039b483d4954164049c6ac7f068e0e0f1799f7d96ddf9b690ac"
)

EXPECTED_R59_COMMIT = (
    "6bc0cb3d7635159593d4a4e2d6b283e1039bce02"
)

EXPECTED_R60_COMMIT = (
    "6126dfca4ee1d21d71989337da919e882a1648ab"
)

EXPECTED_R45_PRODUCT_COMMIT = (
    "2b948e6e41850c6f36ed2735cfb3b17bbf8b2a69"
)

EXPECTED_R46_REPAIR_COMMIT = (
    "f275083cd56c734abf0dd23b0d34113ef1b849de"
)

EXPECTED_R49_CLOSURE_COMMIT = (
    "2674ca4b8d0d97f8c9419fef5a36c938186195de"
)

EXPECTED_R50_BOOTSTRAP_COMMIT = (
    "664dec86d1dfe067b846017801449a745a598492"
)

EXPECTED_R50_BOOTSTRAP_CERTIFICATION_ID = (
    "live-runner-import-bootstrap-certification:"
    "1a1ce4d8eace0424440635f7ae55be386ad6bce73569dda7b346d5da4f63e1b2"
)

EXPECTED_R50_REFERENCE_SHA256 = (
    "sha256:"
    "afa03c1ca3f128fd8e2580e5283dd2d4384f1e0d35232fe2aaca2680e68c725b"
)

EXPECTED_R58_CLOSURE_ID = (
    "fresh-autonomous-semantic-self-test-closure:"
    "c6cce9ca07cef80fd7be3e16db47211e7d34f06107a3799994f74565c5157f19"
)

EXPECTED_R59_CERTIFICATION_ID = (
    "prelock-provider-access-gate-certification:"
    "1c98dac5bf0f3da7a265d7871911403b48d29d4e6c6460085cf7b964a0375d2f"
)

EXPECTED_R59_REFERENCE_SHA256 = (
    "sha256:"
    "23bc03a9b63855647773c81eca0beb036f6ee6a39e10a0ba5a6c689226bd9a4c"
)

DEFAULT_SEAL = (
    "artifacts/investigator/"
    "025zze3f-r60-fresh-horizon-self-test-preregistration.json"
)

DEFAULT_CERTIFICATE = (
    "artifacts/investigator/"
    "025zze3f-r61-live-harness-certification.json"
)

LIVE_EXTRACTION_CACHE = Path(
    "/tmp/horizon-025zze3f-extraction-cache"
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
    return BOOTSTRAP_REPOSITORY_ROOT


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

    certification = seal.get(
        "certification",
        {},
    )

    if (
        certification.get(
            "stage"
        )
        != EXPECTED_SEAL_STAGE
        or certification.get(
            "status"
        )
        != "PASS"
    ):
        raise LiveHarnessError(
            "R60 seal stage/status mismatch"
        )

    if (
        seal.get(
            "seal_id"
        )
        != EXPECTED_SEAL_ID
    ):
        raise LiveHarnessError(
            "R60 seal id mismatch"
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
            "R60 seal canonical hash mismatch"
        )

    boundary = seal[
        "boundary"
    ]

    if (
        boundary[
            "provider_network_calls_this_stage"
        ]
        != 0
        or boundary[
            "provider_model_calls_this_stage"
        ]
        != 0
        or boundary[
            "paid_calls_this_stage"
        ]
        != 0
        or boundary[
            "3f_live_namespace_created"
        ]
        is not False
        or boundary[
            "live_execution_performed"
        ]
        is not False
        or boundary[
            "live_execution_authorized_inside_r60"
        ]
        is not False
    ):
        raise LiveHarnessError(
            "R60 boundary is inconsistent"
        )

    attempt = seal[
        "attempt"
    ]

    if (
        attempt[
            "attempt_id"
        ]
        != "horizon-self-025zze3f"
        or attempt[
            "local_provider_call_ordinal_starts_at"
        ]
        != 1
        or attempt[
            "historical_call_9_reuse_forbidden"
        ]
        is not True
        or attempt[
            "continuation_of_025zze3e"
        ]
        is not False
    ):
        raise LiveHarnessError(
            "fresh 3F attempt authority mismatch"
        )

    for key in (
        "closed_3a_namespace_reuse_forbidden",
        "closed_3b_namespace_reuse_forbidden",
        "closed_3c_namespace_reuse_forbidden",
        "closed_3d_namespace_reuse_forbidden",
        "closed_3e_namespace_reuse_forbidden",
    ):
        if attempt[
            key
        ] is not True:
            raise LiveHarnessError(
                "historical namespace prohibition is absent"
            )

    limits = seal[
        "coordinator_limits"
    ]

    if (
        limits[
            "max_hypothesis_rounds"
        ]
        != 2
        or limits[
            "max_plan_steps"
        ]
        != 6
        or limits[
            "max_plan_total_seconds"
        ]
        != 120
        or limits[
            "max_provider_calls"
        ]
        != 9
        or limits[
            "max_total_model_cost_usd"
        ]
        != "2.700000"
    ):
        raise LiveHarnessError(
            "R60 coordinator limits mismatch"
        )

    model = seal[
        "model"
    ]

    if (
        model[
            "model_id"
        ]
        != "gpt-6-astra"
        or model[
            "reasoning_effort"
        ]
        != "high"
        or model[
            "sdk_max_retries"
        ]
        != 0
        or model[
            "wrapper_retries"
        ]
        != 0
    ):
        raise LiveHarnessError(
            "R60 model authority mismatch"
        )

    combined = seal[
        "combined_offline_authority"
    ]

    if (
        combined[
            "r55_certification_id"
        ]
        != (
            "final-round-addressability-budget-composition-certification:"
            "51fa0b496db02b9a445d9713558d293049c6c44699b9dadb01c925e131989d60"
        )
        or combined[
            "reference_plan_step_count"
        ]
        != 6
        or combined[
            "reference_plan_total_seconds"
        ]
        != 120
        or combined[
            "sealed_plan_total_seconds"
        ]
        != 120
        or combined[
            "reference_plan_is_live_requirement"
        ]
        is not False
    ):
        raise LiveHarnessError(
            "R55 combined authority mismatch"
        )

    typed_instruction = seal[
        "instructions"
    ][
        "typed_planner"
    ][
        "utf8"
    ]

    if (
        "plan_budget.max_total_seconds"
        not in typed_instruction
        or "sum of max_seconds"
        not in typed_instruction
        or "MUST NOT exceed"
        not in typed_instruction
        or (
            "Repository address hints are navigation authority only."
            not in typed_instruction
        )
    ):
        raise LiveHarnessError(
            "R60 typed-planner instruction contract mismatch"
        )

    runner_authority = seal[
        "runner_authority"
    ]

    if (
        runner_authority[
            "preregistration_parent_head"
        ]
        != EXPECTED_R59_COMMIT
        or runner_authority[
            "production_src_tree"
        ]
        != (
            "a3a3fb351e35e1292a3afefd6ef6365c532d936d"
        )
        or runner_authority[
            "new_runner_required"
        ]
        is not True
        or runner_authority[
            "new_runner_must_be_committed_before_live"
        ]
        is not True
        or runner_authority[
            "new_runner_must_be_offline_certified_before_live"
        ]
        is not True
        or runner_authority[
            "r50_self_bootstrap_required"
        ]
        is not True
        or runner_authority[
            "r59_prelock_provider_access_required"
        ]
        is not True
        or runner_authority[
            "shell_pythonpath_dependency_forbidden"
        ]
        is not True
        or runner_authority[
            "launch_cwd_dependency_forbidden"
        ]
        is not True
        or runner_authority[
            "new_runner_path"
        ]
        != (
            "artifacts/investigator/"
            "025zze3f-live-runner.py"
        )
        or runner_authority[
            "new_harness_certificate_path"
        ]
        != (
            "artifacts/investigator/"
            "025zze3f-r61-live-harness-certification.json"
        )
    ):
        raise LiveHarnessError(
            "R60 runner authority mismatch"
        )

    repository = repository_root()

    historical = seal[
        "historical_authority"
    ]

    #
    # Exact closed 3E authority.
    #
    r58_authority = historical[
        "closed_attempt_025zze3e_r58"
    ]

    r58_path = (
        _repository_authority_path(
            repository,
            r58_authority[
                "path"
            ],
            name="3E R58 closure",
        )
    )

    _verify_preserved_file(
        path=r58_path,
        expected_sha256=(
            r58_authority[
                "sha256"
            ]
        ),
        name="3E R58 closure",
    )

    r58 = load_json(
        r58_path
    )

    if (
        r58[
            "closure_id"
        ]
        != EXPECTED_R58_CLOSURE_ID
        or r58[
            "closure_id"
        ]
        != r58_authority[
            "closure_id"
        ]
        or r58[
            "attempt"
        ][
            "state"
        ]
        != "PERMANENTLY_CLOSED"
        or r58[
            "attempt"
        ][
            "rerun_allowed"
        ]
        is not False
        or r58[
            "attempt"
        ][
            "namespace_reuse_allowed"
        ]
        is not False
    ):
        raise LiveHarnessError(
            "3E R58 closure authority mismatch"
        )

    preserved_3e = r58[
        "preserved_live_authority"
    ]

    historical_runner = (
        _repository_authority_path(
            repository,
            runner_authority[
                "historical_3e_runner_path"
            ],
            name="historical 3E runner",
        )
    )

    _verify_preserved_file(
        path=historical_runner,
        expected_sha256=(
            runner_authority[
                "historical_3e_runner_sha256"
            ]
        ),
        name="historical 3E runner",
    )

    if (
        runner_authority[
            "historical_3e_runner_sha256"
        ]
        != preserved_3e[
            "runner_sha256"
        ]
    ):
        raise LiveHarnessError(
            "historical 3E runner chain mismatch"
        )

    historical_certificate_path = (
        _repository_authority_path(
            repository,
            runner_authority[
                "historical_3e_harness_certificate_path"
            ],
            name="historical 3E harness certificate",
        )
    )

    _verify_preserved_file(
        path=historical_certificate_path,
        expected_sha256=(
            runner_authority[
                "historical_3e_harness_certificate_sha256"
            ]
        ),
        name="historical 3E harness certificate",
    )

    historical_certificate = load_json(
        historical_certificate_path
    )

    if (
        historical_certificate.get(
            "certification"
        )
        != "R57_EXACT_3E_LIVE_HARNESS_OFFLINE_CERTIFICATION"
        or historical_certificate.get(
            "status"
        )
        != "PASS"
        or historical_certificate.get(
            "runner_sha256"
        )
        != preserved_3e[
            "runner_sha256"
        ]
    ):
        raise LiveHarnessError(
            "historical 3E harness authority mismatch"
        )

    #
    # R59 must be exact.
    #
    prelock = seal[
        "prelock_provider_access_contract"
    ]

    if (
        prelock[
            "certification_id"
        ]
        != EXPECTED_R59_CERTIFICATION_ID
        or prelock[
            "reference_sha256"
        ]
        != EXPECTED_R59_REFERENCE_SHA256
        or prelock[
            "required_model_id"
        ]
        != "gpt-6-astra"
        or prelock[
            "must_run_before_live_lock"
        ]
        is not True
        or prelock[
            "success_required_before_live_lock"
        ]
        is not True
        or prelock[
            "failure_must_leave_3f_namespace_pristine"
        ]
        is not True
    ):
        raise LiveHarnessError(
            "R59 pre-lock authority mismatch"
        )

    #
    # Reconstruct immutable runtime target identities
    # from the historically exercised R51/R52 chain.
    #
    r53_authority = historical[
        "closed_attempt_025zze3d_r53"
    ]

    r53_path = (
        _repository_authority_path(
            repository,
            r53_authority[
                "path"
            ],
            name="3D closure",
        )
    )

    _verify_preserved_file(
        path=r53_path,
        expected_sha256=(
            r53_authority[
                "sha256"
            ]
        ),
        name="3D closure",
    )

    r53 = load_json(
        r53_path
    )

    if (
        r53[
            "closure_id"
        ]
        != r53_authority[
            "closure_id"
        ]
        or r53[
            "attempt"
        ][
            "state"
        ]
        != "PERMANENTLY_CLOSED"
    ):
        raise LiveHarnessError(
            "3D closure authority mismatch"
        )

    legacy_seal_path = Path(
        r53[
            "preserved_live_authority"
        ][
            "seal_path"
        ]
    ).expanduser().resolve()

    _verify_preserved_file(
        path=legacy_seal_path,
        expected_sha256=(
            r53[
                "preserved_live_authority"
            ][
                "seal_sha256"
            ]
        ),
        name="historical 3D R51 seal",
    )

    legacy_seal = load_json(
        legacy_seal_path
    )

    legacy_without_id = dict(
        legacy_seal
    )

    legacy_id = legacy_without_id.pop(
        "seal_id"
    )

    legacy_recomputed = (
        "fresh-autonomous-semantic-self-test-seal:"
        + hashlib.sha256(
            canonical_bytes(
                legacy_without_id
            )
        ).hexdigest()
    )

    if (
        legacy_recomputed
        != legacy_id
    ):
        raise LiveHarnessError(
            "historical R51 seal canonical hash mismatch"
        )

    new_target = seal[
        "target_repository"
    ]

    semantic_target = seal[
        "semantic_target"
    ]

    legacy_target = legacy_seal[
        "target"
    ]

    if (
        legacy_target[
            "commit"
        ]
        != new_target[
            "commit"
        ]
        or legacy_target[
            "tree"
        ]
        != new_target[
            "tree"
        ]
        or Path(
            legacy_target[
                "path"
            ]
        ).expanduser().resolve()
        != Path(
            new_target[
                "path"
            ]
        ).expanduser().resolve()
        or legacy_target[
            "what_it_is_gap_id"
        ]
        != semantic_target[
            "semantic_gap_id"
        ]
        or legacy_target[
            "what_it_is_question_id"
        ]
        != semantic_target[
            "question_id"
        ]
        or Path(
            legacy_target[
                "semantic_overlay_path"
            ]
        ).expanduser().resolve()
        != Path(
            semantic_target[
                "semantic_overlay_path"
            ]
        ).expanduser().resolve()
    ):
        raise LiveHarnessError(
            "R60 target differs from frozen historical target"
        )

    if (
        historical_certificate[
            "target"
        ][
            "repository_observation_id"
        ]
        != legacy_target[
            "repository_observation_id"
        ]
        or historical_certificate[
            "target"
        ][
            "base_world_model_snapshot_id"
        ]
        != legacy_target[
            "base_world_model_snapshot_id"
        ]
    ):
        raise LiveHarnessError(
            "historical target identity chain mismatch"
        )

    runtime_target = dict(
        legacy_target
    )

    runtime_target[
        "name"
    ] = new_target[
        "name"
    ]

    runtime_target[
        "path"
    ] = new_target[
        "path"
    ]

    runtime_target[
        "commit"
    ] = new_target[
        "commit"
    ]

    runtime_target[
        "tree"
    ] = new_target[
        "tree"
    ]

    runtime_target[
        "remote_free"
    ] = new_target[
        "remote_free"
    ]

    runtime_target[
        "semantic_overlay_path"
    ] = semantic_target[
        "semantic_overlay_path"
    ]

    runtime_target[
        "what_it_is_gap_id"
    ] = semantic_target[
        "semantic_gap_id"
    ]

    runtime_target[
        "what_it_is_question_id"
    ] = semantic_target[
        "question_id"
    ]

    seal[
        "target"
    ] = runtime_target

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
        (
            "closed_attempt_025zze3c_r49",
            "horizon-self-025zze3c",
            "3C",
        ),
        (
            "closed_attempt_025zze3d_r53",
            "horizon-self-025zze3d",
            "3D",
        ),
        (
            "closed_attempt_025zze3e_r58",
            "horizon-self-025zze3e",
            "3E",
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
            spool_value = preserved.get(
                "response_spool_directory",
                preserved.get(
                    "response_spool_path"
                ),
            )

            if (
                not isinstance(
                    spool_value,
                    str,
                )
                or not spool_value
            ):
                raise LiveHarnessError(
                    label
                    + " response spool authority is absent"
                )

            spool = Path(
                spool_value
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
            "planner_addressability_r45",
            "R45",
        ),
        (
            "final_round_consumption_r46",
            "R46",
        ),
        (
            "planner_budget_contract_r54",
            "R54",
        ),
        (
            "combined_final_round_r55",
            "R55",
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

    r54 = loaded[
        "R54"
    ]

    if (
        r54[
            "authority"
        ][
            "sealed_plan_seconds"
        ]
        != 120
        or r54[
            "repair"
        ][
            "provider_neutral_invocation_carries_exact_plan_time_budget"
        ]
        is not True
        or r54[
            "repair"
        ][
            "model_facing_input_contains_plan_budget"
        ]
        is not True
        or r54[
            "repair"
        ][
            "over_budget_typed_planner_output_rejected_before_plan_compilation"
        ]
        is not True
        or r54[
            "repair"
        ][
            "compiler_limit_raised"
        ]
        is not False
        or r54[
            "repair"
        ][
            "compiler_guard_weakened"
        ]
        is not False
        or r54[
            "boundary"
        ][
            "provider_network_calls"
        ]
        != 0
    ):
        raise LiveHarnessError(
            "R54 plan-budget authority is inconsistent"
        )

    r55 = loaded[
        "R55"
    ]

    if (
        r55[
            "authority"
        ][
            "r54_certification_id"
        ]
        != r54[
            "certification_id"
        ]
        or r55[
            "exact_final_round"
        ][
            "plan_step_count"
        ]
        != 6
        or r55[
            "exact_final_round"
        ][
            "aggregate_plan_seconds"
        ]
        != 120
        or r55[
            "exact_final_round"
        ][
            "sealed_max_total_seconds"
        ]
        != 120
        or r55[
            "budget_contract"
        ][
            "provider_payload_plan_budget"
        ]
        != {
            "max_total_seconds": 120,
        }
        or r55[
            "proved"
        ][
            "r54_budget_visible_in_exact_planner_invocation"
        ]
        is not True
        or r55[
            "proved"
        ][
            "r54_budget_visible_in_provider_facing_payload"
        ]
        is not True
        or r55[
            "proved"
        ][
            "six_step_final_round_fits_exact_120_second_budget"
        ]
        is not True
        or r55[
            "proved"
        ][
            "over_budget_plan_rejected_at_typed_planner_boundary"
        ]
        is not True
        or r55[
            "safety"
        ][
            "provider_network_calls"
        ]
        != 0
        or r55[
            "safety"
        ][
            "paid_calls"
        ]
        != 0
    ):
        raise LiveHarnessError(
            "R55 combined authority is inconsistent"
        )

    if (
        seal[
            "combined_offline_authority"
        ][
            "r55_certification_id"
        ]
        != r55[
            "certification_id"
        ]
    ):
        raise LiveHarnessError(
            "R56/R55 combined authority mismatch"
        )




def validate_prelock_provider_access_authority(
    *,
    repository: Path,
    seal: dict[str, Any],
) -> dict[str, Any]:
    contract = seal[
        "prelock_provider_access_contract"
    ]

    certificate_path = (
        _repository_authority_path(
            repository,
            contract[
                "certificate_path"
            ],
            name="R59 pre-lock certificate",
        )
    )

    _verify_preserved_file(
        path=certificate_path,
        expected_sha256=(
            contract[
                "certificate_sha256"
            ]
        ),
        name="R59 pre-lock certificate",
    )

    certificate = load_json(
        certificate_path
    )

    if (
        certificate[
            "certification_id"
        ]
        != EXPECTED_R59_CERTIFICATION_ID
        or certificate[
            "certification_id"
        ]
        != contract[
            "certification_id"
        ]
        or certificate[
            "certification"
        ][
            "stage"
        ]
        != "025ZZE-3F-R59"
        or certificate[
            "certification"
        ][
            "status"
        ]
        != "PASS"
    ):
        raise LiveHarnessError(
            "R59 pre-lock certificate mismatch"
        )

    reference_path = (
        _repository_authority_path(
            repository,
            contract[
                "reference_path"
            ],
            name="R59 pre-lock reference",
        )
    )

    _verify_preserved_file(
        path=reference_path,
        expected_sha256=(
            EXPECTED_R59_REFERENCE_SHA256
        ),
        name="R59 pre-lock reference",
    )

    if (
        contract[
            "reference_sha256"
        ]
        != EXPECTED_R59_REFERENCE_SHA256
        or certificate[
            "authority"
        ][
            "reference_sha256"
        ]
        != EXPECTED_R59_REFERENCE_SHA256
    ):
        raise LiveHarnessError(
            "R59 reference hash mismatch"
        )

    repair = certificate[
        "repair"
    ]

    if (
        repair[
            "classification"
        ]
        != (
            "AUTHENTICATED_MODEL_ACCESS_"
            "BEFORE_IRREVERSIBLE_NAMESPACE"
        )
        or repair[
            "required_model_id"
        ]
        != "gpt-6-astra"
        or repair[
            "metadata_endpoint"
        ]
        != (
            "https://api.openai.com/"
            "v1/models/gpt-6-astra"
        )
        or repair[
            "request_method"
        ]
        != "GET"
        or repair[
            "must_execute_before_live_lock"
        ]
        is not True
        or repair[
            "success_required_before_live_lock"
        ]
        is not True
        or repair[
            "failure_must_leave_fresh_namespace_unconsumed"
        ]
        is not True
        or repair[
            "credential_persisted"
        ]
        is not False
        or repair[
            "credential_hashed"
        ]
        is not False
        or repair[
            "credential_fingerprinted"
        ]
        is not False
        or repair[
            "credential_emitted"
        ]
        is not False
        or repair[
            "provider_error_body_persisted"
        ]
        is not False
        or repair[
            "provider_error_body_emitted"
        ]
        is not False
        or repair[
            "model_generation_request"
        ]
        is not False
        or repair[
            "responses_api_request"
        ]
        is not False
    ):
        raise LiveHarnessError(
            "R59 pre-lock contract mismatch"
        )

    return certificate


def load_r59_prelock_module(
    *,
    repository: Path,
    seal: dict[str, Any],
):
    validate_prelock_provider_access_authority(
        repository=repository,
        seal=seal,
    )

    reference_path = (
        _repository_authority_path(
            repository,
            seal[
                "prelock_provider_access_contract"
            ][
                "reference_path"
            ],
            name="R59 pre-lock reference",
        )
    )

    specification = (
        importlib.util
        .spec_from_file_location(
            "horizon_r59_prelock_provider_gate",
            reference_path,
        )
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise LiveHarnessError(
            "R59 pre-lock reference cannot be imported"
        )

    module = (
        importlib.util
        .module_from_spec(
            specification
        )
    )

    specification.loader.exec_module(
        module
    )

    return module


def invoke_prelock_provider_access(
    *,
    repository: Path,
    seal: dict[str, Any],
    api_key: str,
    opener: object = None,
) -> dict[str, object]:
    module = load_r59_prelock_module(
        repository=repository,
        seal=seal,
    )

    validate = getattr(
        module,
        "validate_openai_model_access",
        None,
    )

    error_type = getattr(
        module,
        "ProviderAccessPreflightError",
        None,
    )

    if (
        not callable(
            validate
        )
        or not isinstance(
            error_type,
            type,
        )
    ):
        raise LiveHarnessError(
            "R59 pre-lock reference API mismatch"
        )

    kwargs = {
        "api_key": api_key,
        "model_id": "gpt-6-astra",
        "timeout_seconds": 30,
    }

    if opener is not None:
        kwargs[
            "opener"
        ] = opener

    try:
        result = validate(
            **kwargs
        )

    except error_type as exc:
        classification = getattr(
            exc,
            "classification",
            None,
        )

        allowed = set(
            seal[
                "prelock_provider_access_contract"
            ][
                "safe_failure_classifications"
            ]
        )

        if (
            not isinstance(
                classification,
                str,
            )
            or classification
            not in allowed
        ):
            raise LiveHarnessError(
                "R59 pre-lock gate emitted unknown classification"
            ) from None

        raise LiveHarnessError(
            "pre-lock provider access failed: "
            + classification
        ) from None

    except BaseException:
        raise LiveHarnessError(
            "pre-lock provider access gate failed unexpectedly"
        ) from None

    expected = {
        "http_status": 200,
        "credential_accepted": True,
        "model_accessible": True,
        "model_id": "gpt-6-astra",
        "object": "model",
        "model_generation_calls": 0,
        "responses_api_calls": 0,
    }

    if result != expected:
        raise LiveHarnessError(
            "R59 pre-lock success identity mismatch"
        )

    return result


def validate_import_bootstrap_authority(
    *,
    repository: Path,
    seal: dict[str, Any],
) -> None:
    historical = seal[
        "historical_authority"
    ]

    authority = historical[
        "live_runner_import_bootstrap_r50"
    ]

    certificate_path = (
        _repository_authority_path(
            repository,
            authority[
                "path"
            ],
            name="R50 bootstrap certification",
        )
    )

    _verify_preserved_file(
        path=certificate_path,
        expected_sha256=(
            authority[
                "sha256"
            ]
        ),
        name="R50 bootstrap certification",
    )

    certificate = load_json(
        certificate_path
    )

    if (
        certificate[
            "certification_id"
        ]
        != EXPECTED_R50_BOOTSTRAP_CERTIFICATION_ID
        or certificate[
            "certification_id"
        ]
        != authority[
            "certification_id"
        ]
        or certificate[
            "certification"
        ][
            "status"
        ]
        != "PASS"
    ):
        raise LiveHarnessError(
            "R50 bootstrap certification mismatch"
        )

    reference_path = (
        _repository_authority_path(
            repository,
            authority[
                "reference_runner_path"
            ],
            name="R50 reference runner",
        )
    )

    _verify_preserved_file(
        path=reference_path,
        expected_sha256=(
            EXPECTED_R50_REFERENCE_SHA256
        ),
        name="R50 reference runner",
    )

    repair = certificate[
        "repair"
    ]

    if (
        authority[
            "reference_runner_sha256"
        ]
        != EXPECTED_R50_REFERENCE_SHA256
        or repair[
            "reference_runner_sha256"
        ]
        != EXPECTED_R50_REFERENCE_SHA256
        or repair[
            "src_inserted_at_sys_path_index_zero"
        ]
        is not True
        or repair[
            "depends_on_shell_pythonpath"
        ]
        is not False
        or repair[
            "depends_on_current_working_directory"
        ]
        is not False
        or repair[
            "depends_on_git_toplevel_discovery"
        ]
        is not False
    ):
        raise LiveHarnessError(
            "R50 self-bootstrap contract mismatch"
        )

    runner_authority = seal[
        "runner_authority"
    ]

    if (
        runner_authority[
            "r50_self_bootstrap_required"
        ]
        is not True
        or runner_authority[
            "shell_pythonpath_dependency_forbidden"
        ]
        is not True
        or runner_authority[
            "launch_cwd_dependency_forbidden"
        ]
        is not True
        or (
            "runner __file__"
            not in runner_authority[
                "required_repository_bootstrap"
            ]
        )
        or (
            "src first on sys.path"
            not in runner_authority[
                "required_repository_bootstrap"
            ]
        )
    ):
        raise LiveHarnessError(
            "R56 bootstrap authority mismatch"
        )

    expected_root = repository.resolve()

    expected_src = (
        expected_root
        / "src"
    ).resolve()

    if (
        BOOTSTRAP_REPOSITORY_ROOT
        != expected_root
        or BOOTSTRAP_REPOSITORY_SRC
        != expected_src
    ):
        raise LiveHarnessError(
            "runtime bootstrap repository authority mismatch"
        )

    if (
        not sys.path
        or Path(
            sys.path[
                0
            ]
        ).resolve()
        != expected_src
    ):
        raise LiveHarnessError(
            "runtime bootstrap src is not first on sys.path"
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
            "certification"
        )
        != "R61_EXACT_3F_LIVE_HARNESS_OFFLINE_CERTIFICATION"
        or certificate.get(
            "status"
        )
        != "PASS"
    ):
        raise LiveHarnessError(
            "R61 harness certificate is not PASS"
        )

    certificate_id = certificate.get(
        "certification_id"
    )

    without_id = dict(
        certificate
    )

    without_id.pop(
        "certification_id",
        None,
    )

    expected_certificate_id = (
        "live-harness-certification:"
        + hashlib.sha256(
            canonical_bytes(
                without_id
            )
        ).hexdigest()
    )

    if (
        certificate_id
        != expected_certificate_id
    ):
        raise LiveHarnessError(
            "R61 certificate canonical identity mismatch"
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
            "live runner bytes differ from R61 certificate"
        )

    if (
        certificate.get(
            "r60_seal_id"
        )
        != seal[
            "seal_id"
        ]
        or certificate.get(
            "r60_seal_sha256"
        )
        != sha256_file(
            seal_path
        )
        or certificate.get(
            "r60_head"
        )
        != EXPECTED_R60_COMMIT
    ):
        raise LiveHarnessError(
            "R60 seal authority differs from R61 certificate"
        )

    if (
        certificate.get(
            "production_src_tree"
        )
        != seal[
            "runner_authority"
        ][
            "production_src_tree"
        ]
    ):
        raise LiveHarnessError(
            "R61 production src authority mismatch"
        )

    prelock_proof = certificate[
        "prelock_provider_access_proof"
    ]

    if (
        prelock_proof[
            "r59_certification_revalidated"
        ]
        is not True
        or prelock_proof[
            "r59_certification_id"
        ]
        != EXPECTED_R59_CERTIFICATION_ID
        or prelock_proof[
            "r59_reference_sha256"
        ]
        != EXPECTED_R59_REFERENCE_SHA256
        or prelock_proof[
            "authenticated_access_before_live_lock"
        ]
        is not True
    ):
        raise LiveHarnessError(
            "R61 pre-lock provider proof mismatch"
        )

    repair_proof = certificate[
        "repair_authority_proof"
    ]

    if (
        repair_proof[
            "r54_budget_contract_revalidated"
        ]
        is not True
        or repair_proof[
            "r55_combined_offline_gate_revalidated"
        ]
        is not True
    ):
        raise LiveHarnessError(
            "R61 semantic repair authority mismatch"
        )

    branch = git(
        repository,
        "branch",
        "--show-current",
    )

    expected_branch = seal[
        "runner_authority"
    ][
        "branch"
    ]

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
            "R61 runner+certificate authority"
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
            "R61 live authority has not been pushed exactly"
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

    subprocess.run(
        [
            "git",
            "-C",
            str(
                repository
            ),
            "merge-base",
            "--is-ancestor",
            EXPECTED_R60_COMMIT,
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

    validate_prelock_provider_access_authority(
        repository=repository,
        seal=seal,
    )

    validate_import_bootstrap_authority(
        repository=repository,
        seal=seal,
    )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )


    #
    # R60/R59 irreversible-boundary rule:
    #
    # 1. credential must exist locally;
    # 2. exact R59 authenticated model-metadata
    #    access to gpt-6-astra must succeed;
    # 3. fresh namespace must still be empty;
    # 4. only then may the 3F live lock be created.
    #
    require_local_api_key_presence()

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
            "OPENAI_API_KEY local presence preflight failed"
        )

    invoke_prelock_provider_access(
        repository=repository,
        seal=seal,
        api_key=api_key,
    )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

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

        validate_prelock_provider_access_authority(
            repository=repository,
            seal=seal,
        )

        validate_import_bootstrap_authority(
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
        # The exact credential already passed the R59
        # authenticated access gate before namespace
        # entry. Reuse the same in-memory value. Do
        # not re-read, print, persist, hash or
        # fingerprint it after the lock.
        #
        if (
            not isinstance(
                api_key,
                str,
            )
            or not api_key.strip()
        ):
            raise LiveHarnessError(
                "pre-lock credential authority disappeared"
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



def offline_certify_prelock_provider_gate(
    *,
    repository: Path,
    seal: dict[str, Any],
) -> dict[str, bool]:
    sentinel = (
        "r61-offline-provider-access-sentinel"
    )

    class MetadataResponse:
        def __init__(
            self,
            *,
            body: bytes,
        ) -> None:
            self.status = 200
            self.body = body
            self.closed = False

        def read(
            self,
            amount: int = -1,
        ) -> bytes:
            if amount < 0:
                return self.body

            return self.body[
                :amount
            ]

        def close(
            self,
        ) -> None:
            self.closed = True

    calls = []

    success_response = MetadataResponse(
        body=json.dumps(
            {
                "id": "gpt-6-astra",
                "object": "model",
            }
        ).encode(
            "utf-8"
        )
    )

    def success_opener(
        request,
        *,
        timeout,
    ):
        calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "authorization": (
                    request.get_header(
                        "Authorization"
                    )
                ),
                "accept": request.get_header(
                    "Accept"
                ),
                "timeout": timeout,
            }
        )

        return success_response

    result = invoke_prelock_provider_access(
        repository=repository,
        seal=seal,
        api_key=sentinel,
        opener=success_opener,
    )

    if (
        result[
            "model_id"
        ]
        != "gpt-6-astra"
        or len(
            calls
        )
        != 1
        or calls[
            0
        ][
            "url"
        ]
        != (
            "https://api.openai.com/"
            "v1/models/gpt-6-astra"
        )
        or calls[
            0
        ][
            "method"
        ]
        != "GET"
        or calls[
            0
        ][
            "authorization"
        ]
        != (
            "Bearer "
            + sentinel
        )
        or calls[
            0
        ][
            "accept"
        ]
        != "application/json"
        or calls[
            0
        ][
            "timeout"
        ]
        != 30.0
        or success_response.closed
        is not True
    ):
        raise LiveHarnessError(
            "offline R59 success proof failed"
        )

    module = load_r59_prelock_module(
        repository=repository,
        seal=seal,
    )

    def expect_http_failure(
        *,
        status: int,
        classification: str,
    ) -> None:
        def opener(
            request,
            *,
            timeout,
        ):
            raise module.urllib.error.HTTPError(
                request.full_url,
                status,
                "offline simulated provider error",
                None,
                None,
            )

        try:
            invoke_prelock_provider_access(
                repository=repository,
                seal=seal,
                api_key=sentinel,
                opener=opener,
            )

        except LiveHarnessError as exc:
            expected = (
                "pre-lock provider access failed: "
                + classification
            )

            if str(
                exc
            ) != expected:
                raise

        else:
            raise LiveHarnessError(
                "offline provider failure did not fail closed"
            )

    expect_http_failure(
        status=401,
        classification=(
            "AUTHENTICATION_REJECTED"
        ),
    )

    expect_http_failure(
        status=403,
        classification=(
            "MODEL_ACCESS_REJECTED"
        ),
    )

    expect_http_failure(
        status=404,
        classification=(
            "MODEL_ACCESS_REJECTED"
        ),
    )

    def network_opener(
        request,
        *,
        timeout,
    ):
        raise module.urllib.error.URLError(
            "offline simulated network failure"
        )

    try:
        invoke_prelock_provider_access(
            repository=repository,
            seal=seal,
            api_key=sentinel,
            opener=network_opener,
        )

    except LiveHarnessError as exc:
        if (
            str(
                exc
            )
            != (
                "pre-lock provider access failed: "
                "NETWORK_PREFLIGHT_FAILED"
            )
        ):
            raise

    else:
        raise LiveHarnessError(
            "offline network failure did not fail closed"
        )

    wrong_response = MetadataResponse(
        body=json.dumps(
            {
                "id": "wrong-model",
                "object": "model",
            }
        ).encode(
            "utf-8"
        )
    )

    def wrong_identity_opener(
        request,
        *,
        timeout,
    ):
        return wrong_response

    try:
        invoke_prelock_provider_access(
            repository=repository,
            seal=seal,
            api_key=sentinel,
            opener=wrong_identity_opener,
        )

    except LiveHarnessError as exc:
        if (
            str(
                exc
            )
            != (
                "pre-lock provider access failed: "
                "MODEL_ACCESS_IDENTITY_MISMATCH"
            )
        ):
            raise

    else:
        raise LiveHarnessError(
            "wrong-model preflight did not fail closed"
        )

    return {
        "fake_success": True,
        "fake_401": True,
        "fake_403": True,
        "fake_404": True,
        "fake_network_failure": True,
        "fake_identity_mismatch": True,
    }



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
        != EXPECTED_R60_COMMIT
    ):
        raise LiveHarnessError(
            "offline certification is not running at R60 HEAD"
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

    validate_prelock_provider_access_authority(
        repository=repository,
        seal=seal,
    )

    validate_import_bootstrap_authority(
        repository=repository,
        seal=seal,
    )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    if "OPENAI_API_KEY" in os.environ:
        raise LiveHarnessError(
            "offline certification requires OPENAI_API_KEY absent"
        )

    #
    # Presence-only boundary still fails before
    # namespace entry.
    #
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
            "missing credential presence gate did not fail"
        )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    #
    # Exact R59 authenticated model-access gate is
    # exercised entirely with injected fake openers.
    #
    gate_proof = (
        offline_certify_prelock_provider_gate(
            repository=repository,
            seal=seal,
        )
    )

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="horizon-r61-"
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
        # Preserve R57's proven durable provider
        # response boundary with an offline fake SDK
        # response. This is not a network/provider call.
        #
        fake_ledger = (
            temporary
            / "attempt.jsonl"
        )

        fake_spool = (
            temporary
            / "spool"
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
                    "type": "json_schema",
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
                "durable fake boundary returned no response"
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

        spooled = ledger_lines[
            -1
        ]

        if (
            spooled[
                "response_sha256"
            ]
            != sha256_file(
                response_path
            )
            or spooled[
                "cost_meter_valid"
            ]
            is not True
        ):
            raise LiveHarnessError(
                "durable spool/cost proof failed"
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

    validate_fresh_namespace(
        seal,
        include_cache=True,
    )

    runner_path = Path(
        __file__
    ).resolve()

    certificate = {
        "certification": (
            "R61_EXACT_3F_LIVE_HARNESS_OFFLINE_CERTIFICATION"
        ),

        "status": "PASS",

        "r60_seal_id": (
            seal[
                "seal_id"
            ]
        ),

        "r60_seal_sha256": (
            sha256_file(
                seal_path
            )
        ),

        "r60_head": (
            EXPECTED_R60_COMMIT
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
            "closed_3c_revalidated": True,
            "closed_3d_revalidated": True,
            "closed_3e_revalidated": True,
            "historical_live_bytes_revalidated": True,
        },

        "repair_authority_proof": {
            "r45_certification_revalidated": True,
            "r46_certification_revalidated": True,
            "r50_bootstrap_certification_revalidated": True,
            "r54_budget_contract_revalidated": True,
            "r55_combined_offline_gate_revalidated": True,

            "r54_certification_id": (
                seal[
                    "historical_authority"
                ][
                    "planner_budget_contract_r54"
                ][
                    "certification_id"
                ]
            ),

            "r55_certification_id": (
                seal[
                    "combined_offline_authority"
                ][
                    "r55_certification_id"
                ]
            ),

            "planner_aggregate_budget_visible": True,
            "planner_over_budget_precompile_rejection_certified": True,
            "address_hints_non_evidentiary": True,
            "final_round_hint_consumption_certified": True,
        },

        "prelock_provider_access_proof": {
            "r59_certification_revalidated": True,

            "r59_certification_id": (
                EXPECTED_R59_CERTIFICATION_ID
            ),

            "r59_reference_sha256": (
                EXPECTED_R59_REFERENCE_SHA256
            ),

            "required_model_id": (
                "gpt-6-astra"
            ),

            "authenticated_access_before_live_lock": True,

            "success_case_offline_injected": (
                gate_proof[
                    "fake_success"
                ]
            ),

            "authentication_401_fails_before_lock": (
                gate_proof[
                    "fake_401"
                ]
            ),

            "model_access_403_fails_before_lock": (
                gate_proof[
                    "fake_403"
                ]
            ),

            "model_access_404_fails_before_lock": (
                gate_proof[
                    "fake_404"
                ]
            ),

            "network_failure_fails_before_lock": (
                gate_proof[
                    "fake_network_failure"
                ]
            ),

            "identity_mismatch_fails_before_lock": (
                gate_proof[
                    "fake_identity_mismatch"
                ]
            ),

            "provider_error_body_emitted": False,
            "provider_error_body_persisted": False,
            "credential_emitted": False,
            "credential_persisted": False,
            "credential_hashed": False,
            "credential_fingerprinted": False,
        },

        "harness_contract": {
            "credential_presence_before_live_namespace": True,

            "authenticated_model_access_preflight_before_live_lock": True,

            "exact_required_model": "gpt-6-astra",

            "prelock_failure_burns_no_namespace": True,

            "same_in_memory_credential_used_for_sdk_after_lock": True,

            "fresh_local_provider_ordinal_starts_at_1": True,

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

            "planner_max_plan_total_seconds": 120,

            "attempt_event_fsynced_before_provider_dispatch": True,

            "response_spooled_before_adapter_validation": True,

            "response_spool_fsynced": True,

            "response_spool_hash_ledgered": True,

            "provider_exception_has_no_automatic_retry": True,

            "final_result_exclusive_spool": True,

            "current_committed_runner_required_for_live": True,

            "current_committed_certificate_required_for_live": True,

            "remote_exact_current_head_required_for_live": True,

            "production_src_tree_immutable": True,

            "self_bootstrap_before_horizon_import": True,

            "repository_root_from_runner_file_location": True,

            "exact_repository_src_first_on_sys_path": True,

            "shell_pythonpath_dependency": False,

            "launch_cwd_dependency": False,

            "git_toplevel_bootstrap_dependency": False,

            "r50_bootstrap_authority_revalidated": True,

            "r59_prelock_provider_access_revalidated": True,

            "planner_provider_payload_budget_certified": True,

            "planner_over_budget_precompile_rejection_certified": True,
        },

        "offline_boundary_proof": {
            "real_OPENAI_API_KEY_read": False,

            "provider_network_calls": 0,

            "model_generation_calls": 0,

            "responses_api_calls": 0,

            "paid_calls": 0,

            "fake_metadata_provider_calls": 0,

            "fake_sdk_responses": 1,

            "credential_presence_missing_fails_without_live_state": True,

            "r59_success_case_injected": True,

            "r59_401_case_injected": True,

            "r59_403_case_injected": True,

            "r59_404_case_injected": True,

            "r59_network_failure_injected": True,

            "r59_identity_mismatch_injected": True,

            "ledger_event_order": [
                "ATTEMPT_STARTED",
                "ATTEMPT",
                "RESPONSE_SPOOLED",
            ],

            "response_spool_hash_verified": True,

            "cost_meter_valid": True,

            "target_identity_reconstructed": True,

            "semantic_store_mutations": 0,

            "target_repository_mutations": 0,

            "prefect_repository_mutations": 0,

            "3f_namespace_created": False,

            "3f_namespace_consumed": False,
        },

        "boundary": {
            "real_OPENAI_API_KEY_read": False,

            "provider_network_calls": 0,

            "model_generation_calls": 0,

            "responses_api_calls": 0,

            "paid_calls": 0,

            "paid_spend_usd": "0",

            "live_lock_created": False,

            "live_attempt_ledger_created": False,

            "live_response_spool_created": False,

            "live_result_spool_created": False,

            "live_extraction_cache_created": False,

            "live_world_model_mutations": 0,
        },

        "next_authorized_stage": (
            "Commit and push this exact R61 3F runner and certificate. "
            "Only while that exact commit remains current, clean, "
            "remote-exact, R60-descended, production-src-identical, "
            "and the fresh 3F namespace remains pristine may a later "
            "separate explicit live-execution stage enter --live. "
            "Before create_live_lock the exact R59 authenticated "
            "gpt-6-astra access gate must succeed."
        ),
    }

    canonical_without_id = canonical_bytes(
        certificate
    )

    certificate[
        "certification_id"
    ] = (
        "live-harness-certification:"
        + hashlib.sha256(
            canonical_without_id
        ).hexdigest()
    )

    write_exclusive_json(
        certificate_path,
        certificate,
    )

    print("R60_SEAL_VALID=PASS")
    print("R59_PRELOCK_AUTHORITY=PASS")
    print("R59_FAKE_SUCCESS=PASS")
    print("R59_FAKE_401_FAILS_SAFE=PASS")
    print("R59_FAKE_403_FAILS_SAFE=PASS")
    print("R59_FAKE_404_FAILS_SAFE=PASS")
    print("R59_FAKE_NETWORK_FAILS_SAFE=PASS")
    print("R59_FAKE_IDENTITY_MISMATCH_FAILS_SAFE=PASS")
    print("PRELOCK_FAILURE_CREATES_3F_STATE=NO")
    print("FROZEN_TARGET_RECONSTRUCTED=PASS")
    print("BASE_WORLD_MODEL_IDENTITY=PASS")
    print("INITIAL_EVIDENCE_IDENTITY=PASS")
    print("WHAT_IT_IS_GAP_IDENTITY=PASS")
    print("DURABLE_ATTEMPT_BEFORE_DISPATCH=PASS")
    print("RESPONSE_SPOOLED_BEFORE_ADAPTER_RETURN=PASS")
    print("RESPONSE_HASH_LEDGERED=PASS")
    print("OFFLINE_COST_METER=PASS")
    print("LIVE_API_KEY_READ=NO")
    print("NETWORK_PROVIDER_CALLS=0")
    print("MODEL_GENERATION_CALLS=0")
    print("RESPONSES_API_CALLS=0")
    print("WORLD_MODEL_MUTATIONS=0")
    print("HISTORICAL_3A_REVALIDATED=PASS")
    print("HISTORICAL_3B_REVALIDATED=PASS")
    print("HISTORICAL_3C_REVALIDATED=PASS")
    print("HISTORICAL_3D_REVALIDATED=PASS")
    print("HISTORICAL_3E_REVALIDATED=PASS")
    print("R50_IMPORT_BOOTSTRAP_REVALIDATED=PASS")
    print("R54_BUDGET_CONTRACT_REVALIDATED=PASS")
    print("R55_COMBINED_OFFLINE_GATE_REVALIDATED=PASS")
    print("R61_CERTIFICATE_WRITTEN=PASS")

    return 0



def bootstrap_probe() -> int:
    if "PYTHONPATH" in os.environ:
        raise LiveHarnessError(
            "bootstrap probe requires PYTHONPATH absent"
        )

    cwd = Path.cwd().resolve()

    try:
        cwd.relative_to(
            BOOTSTRAP_REPOSITORY_ROOT
        )
    except ValueError:
        pass
    else:
        raise LiveHarnessError(
            "bootstrap probe must run outside repository"
        )

    import horizon.cache.content as content

    module_path = Path(
        content.__file__
    ).resolve()

    expected_module = (
        BOOTSTRAP_REPOSITORY_SRC
        / "horizon"
        / "cache"
        / "content.py"
    ).resolve()

    if module_path != expected_module:
        raise LiveHarnessError(
            "Horizon module resolved outside certified src"
        )

    if (
        not sys.path
        or Path(
            sys.path[0]
        ).resolve()
        != BOOTSTRAP_REPOSITORY_SRC
    ):
        raise LiveHarnessError(
            "certified repository src is not first on sys.path"
        )

    print(
        "BOOTSTRAP_REPOSITORY_ROOT="
        + str(
            BOOTSTRAP_REPOSITORY_ROOT
        )
    )

    print(
        "BOOTSTRAP_REPOSITORY_SRC="
        + str(
            BOOTSTRAP_REPOSITORY_SRC
        )
    )

    print(
        "HORIZON_CACHE_CONTENT="
        + str(
            module_path
        )
    )

    print(
        "PYTHONPATH_ENV_PRESENT=NO"
    )

    print(
        "CERTIFIED_SRC_FIRST_ON_SYS_PATH=PASS"
    )

    print(
        "BOOTSTRAP_PROBE=PASS"
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

    mode.add_argument(
        "--bootstrap-probe",
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

    if arguments.bootstrap_probe:
        return bootstrap_probe()

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
