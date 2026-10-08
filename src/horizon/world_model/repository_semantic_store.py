"""Durable, fail-closed repository semantic World Model overlays.

The deterministic repository World Model is rebuilt from frozen source
evidence. Semantic promotions are persisted separately as an overlay tied to
that exact deterministic snapshot.

A persisted overlay is accepted only when every claim, assessment, assertion,
selection, identity, and snapshot can be reconstructed through Horizon's
canonical factories.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from horizon.claims.epistemic import (
    EpistemicStatus,
    make_epistemic_assessment,
)
from horizon.claims.evidence_backed import (
    ClaimEvidenceKind,
    ClaimEvidenceRelation,
    make_claim_evidence_reference,
    make_evidence_backed_claim,
)
from horizon.world_model.assertion import (
    WorldModelRelationKind,
    make_world_model_assertion,
)
from horizon.world_model.repository_deterministic import (
    RepositoryDeterministicWorldModel,
)
from horizon.world_model.snapshot import (
    WorldModelSnapshot,
    make_world_model_snapshot,
)


class RepositorySemanticWorldModelStoreError(
    ValueError
):
    """Persisted semantic World Model state is absent from canonical authority."""


_SCHEMA_VERSION = 1

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "source_commit",
    "repository_observation_id",
    "base_snapshot_id",
    "promoted_snapshot_id",
    "what_it_is_assertion_ids",
    "claims",
    "assessments",
    "assertions",
    "overlay_id",
}

_SNAPSHOT_FIELDS = {
    "claims",
    "assessments",
    "assertions",
    "snapshot_id",
}

_REFERENCE_FIELDS = {
    "evidence_kind",
    "relation",
    "evidence_id",
    "reference_id",
}

_CLAIM_FIELDS = {
    "proposition",
    "scope",
    "evidence",
    "claim_id",
}

_ASSESSMENT_FIELDS = {
    "claim_id",
    "status",
    "rationale",
    "basis_reference_ids",
    "assessment_id",
}

_ASSERTION_FIELDS = {
    "subject_id",
    "relation",
    "object_id",
    "claim_id",
    "assessment_id",
    "assertion_id",
}


def _canonical_json(
    value: object,
) -> bytes:
    return json.dumps(
        value,
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


def _identity(
    prefix: str,
    value: object,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            _canonical_json(
                value
            )
        ).hexdigest()
    )


def _require_mapping(
    value: object,
    *,
    name: str,
    fields: set[str],
) -> Mapping[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise RepositorySemanticWorldModelStoreError(
            f"{name} must be an object"
        )

    if set(
        value
    ) != fields:
        raise RepositorySemanticWorldModelStoreError(
            f"{name} fields do not exactly match the schema"
        )

    return value


def _require_text(
    value: object,
    *,
    name: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise RepositorySemanticWorldModelStoreError(
            f"{name} must be a nonempty string"
        )

    return value


def _require_text_list(
    value: object,
    *,
    name: str,
) -> tuple[str, ...]:
    if not isinstance(
        value,
        list,
    ):
        raise RepositorySemanticWorldModelStoreError(
            f"{name} must be a list"
        )

    values = tuple(
        _require_text(
            item,
            name=name,
        )
        for item
        in value
    )

    if len(
        values
    ) != len(
        set(
            values
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            f"{name} contains duplicates"
        )

    return values


def _reference_payload(
    reference,
) -> dict[str, object]:
    return {
        "evidence_kind": (
            reference.evidence_kind.value
        ),
        "relation": (
            reference.relation.value
        ),
        "evidence_id": (
            reference.evidence_id
        ),
        "reference_id": (
            reference.reference_id
        ),
    }


def _claim_payload(
    claim,
) -> dict[str, object]:
    return {
        "proposition": (
            claim.proposition
        ),
        "scope": (
            claim.scope
        ),
        "evidence": [
            _reference_payload(
                reference
            )
            for reference
            in claim.evidence
        ],
        "claim_id": (
            claim.claim_id
        ),
    }


def _assessment_payload(
    assessment,
) -> dict[str, object]:
    return {
        "claim_id": (
            assessment.claim_id
        ),
        "status": (
            assessment.status.value
        ),
        "rationale": (
            assessment.rationale
        ),
        "basis_reference_ids": list(
            assessment.basis_reference_ids
        ),
        "assessment_id": (
            assessment.assessment_id
        ),
    }


def _assertion_payload(
    assertion,
) -> dict[str, object]:
    return {
        "subject_id": (
            assertion.subject_id
        ),
        "relation": (
            assertion.relation.value
        ),
        "object_id": (
            assertion.object_id
        ),
        "claim_id": (
            assertion.claim_id
        ),
        "assessment_id": (
            assertion.assessment_id
        ),
        "assertion_id": (
            assertion.assertion_id
        ),
    }


def repository_world_model_snapshot_payload(
    snapshot: WorldModelSnapshot,
) -> dict[str, object]:
    if not isinstance(
        snapshot,
        WorldModelSnapshot,
    ):
        raise RepositorySemanticWorldModelStoreError(
            "snapshot must be a WorldModelSnapshot"
        )

    return {
        "claims": [
            _claim_payload(
                claim
            )
            for claim
            in sorted(
                snapshot.claims,
                key=lambda item: (
                    item.claim_id
                ),
            )
        ],
        "assessments": [
            _assessment_payload(
                assessment
            )
            for assessment
            in sorted(
                snapshot.assessments,
                key=lambda item: (
                    item.assessment_id
                ),
            )
        ],
        "assertions": [
            _assertion_payload(
                assertion
            )
            for assertion
            in sorted(
                snapshot.assertions,
                key=lambda item: (
                    item.assertion_id
                ),
            )
        ],
        "snapshot_id": (
            snapshot.snapshot_id
        ),
    }


def _decode_reference(
    value: object,
):
    raw = _require_mapping(
        value,
        name="evidence reference",
        fields=_REFERENCE_FIELDS,
    )

    try:
        evidence_kind = (
            ClaimEvidenceKind(
                raw[
                    "evidence_kind"
                ]
            )
        )

        relation = (
            ClaimEvidenceRelation(
                raw[
                    "relation"
                ]
            )
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise RepositorySemanticWorldModelStoreError(
            "evidence reference enum is invalid"
        ) from exc

    reference = (
        make_claim_evidence_reference(
            evidence_kind,
            relation,
            _require_text(
                raw[
                    "evidence_id"
                ],
                name="evidence id",
            ),
        )
    )

    if (
        reference.reference_id
        != raw[
            "reference_id"
        ]
    ):
        raise RepositorySemanticWorldModelStoreError(
            "evidence reference identity is invalid"
        )

    return reference


def _decode_claim(
    value: object,
):
    raw = _require_mapping(
        value,
        name="claim",
        fields=_CLAIM_FIELDS,
    )

    evidence_raw = raw[
        "evidence"
    ]

    if not isinstance(
        evidence_raw,
        list,
    ):
        raise RepositorySemanticWorldModelStoreError(
            "claim evidence must be a list"
        )

    claim = make_evidence_backed_claim(
        _require_text(
            raw[
                "proposition"
            ],
            name="claim proposition",
        ),
        scope=_require_text(
            raw[
                "scope"
            ],
            name="claim scope",
        ),
        evidence=tuple(
            _decode_reference(
                reference
            )
            for reference
            in evidence_raw
        ),
    )

    if (
        claim.claim_id
        != raw[
            "claim_id"
        ]
    ):
        raise RepositorySemanticWorldModelStoreError(
            "claim identity is invalid"
        )

    return claim


def _decode_assessment(
    value: object,
    *,
    claims_by_id,
):
    raw = _require_mapping(
        value,
        name="assessment",
        fields=_ASSESSMENT_FIELDS,
    )

    claim_id = _require_text(
        raw[
            "claim_id"
        ],
        name="assessment claim id",
    )

    claim = claims_by_id.get(
        claim_id
    )

    if claim is None:
        raise RepositorySemanticWorldModelStoreError(
            "assessment claim is absent"
        )

    try:
        status = EpistemicStatus(
            raw[
                "status"
            ]
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise RepositorySemanticWorldModelStoreError(
            "assessment status is invalid"
        ) from exc

    basis_ids = _require_text_list(
        raw[
            "basis_reference_ids"
        ],
        name="assessment basis reference ids",
    )

    references_by_id = {
        reference.reference_id: (
            reference
        )
        for reference
        in claim.evidence
    }

    try:
        basis = tuple(
            references_by_id[
                reference_id
            ]
            for reference_id
            in basis_ids
        )
    except KeyError as exc:
        raise RepositorySemanticWorldModelStoreError(
            "assessment basis is outside its claim"
        ) from exc

    assessment = make_epistemic_assessment(
        claim,
        status,
        rationale=_require_text(
            raw[
                "rationale"
            ],
            name="assessment rationale",
        ),
        basis=basis,
    )

    if (
        assessment.assessment_id
        != raw[
            "assessment_id"
        ]
    ):
        raise RepositorySemanticWorldModelStoreError(
            "assessment identity is invalid"
        )

    return assessment


def _decode_assertion(
    value: object,
    *,
    claims_by_id,
    assessments_by_id,
):
    raw = _require_mapping(
        value,
        name="assertion",
        fields=_ASSERTION_FIELDS,
    )

    claim_id = _require_text(
        raw[
            "claim_id"
        ],
        name="assertion claim id",
    )

    assessment_id = _require_text(
        raw[
            "assessment_id"
        ],
        name="assertion assessment id",
    )

    claim = claims_by_id.get(
        claim_id
    )

    assessment = assessments_by_id.get(
        assessment_id
    )

    if (
        claim is None
        or assessment is None
    ):
        raise RepositorySemanticWorldModelStoreError(
            "assertion authority chain is incomplete"
        )

    try:
        relation = (
            WorldModelRelationKind(
                raw[
                    "relation"
                ]
            )
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise RepositorySemanticWorldModelStoreError(
            "assertion relation is invalid"
        ) from exc

    assertion = make_world_model_assertion(
        _require_text(
            raw[
                "subject_id"
            ],
            name="assertion subject id",
        ),
        relation,
        _require_text(
            raw[
                "object_id"
            ],
            name="assertion object id",
        ),
        claim=claim,
        assessment=assessment,
    )

    if (
        assertion.assertion_id
        != raw[
            "assertion_id"
        ]
    ):
        raise RepositorySemanticWorldModelStoreError(
            "assertion identity is invalid"
        )

    return assertion


def _decode_snapshot(
    value: object,
) -> WorldModelSnapshot:
    raw = _require_mapping(
        value,
        name="World Model snapshot",
        fields=_SNAPSHOT_FIELDS,
    )

    raw_claims = raw[
        "claims"
    ]

    raw_assessments = raw[
        "assessments"
    ]

    raw_assertions = raw[
        "assertions"
    ]

    if not all(
        isinstance(
            item,
            list,
        )
        for item
        in (
            raw_claims,
            raw_assessments,
            raw_assertions,
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "snapshot collections must be lists"
        )

    claims = tuple(
        _decode_claim(
            value
        )
        for value
        in raw_claims
    )

    claims_by_id = {
        claim.claim_id: claim
        for claim
        in claims
    }

    if len(
        claims_by_id
    ) != len(
        claims
    ):
        raise RepositorySemanticWorldModelStoreError(
            "snapshot contains duplicate claims"
        )

    assessments = tuple(
        _decode_assessment(
            value,
            claims_by_id=claims_by_id,
        )
        for value
        in raw_assessments
    )

    assessments_by_id = {
        assessment.assessment_id: (
            assessment
        )
        for assessment
        in assessments
    }

    if len(
        assessments_by_id
    ) != len(
        assessments
    ):
        raise RepositorySemanticWorldModelStoreError(
            "snapshot contains duplicate assessments"
        )

    assertions = tuple(
        _decode_assertion(
            value,
            claims_by_id=claims_by_id,
            assessments_by_id=(
                assessments_by_id
            ),
        )
        for value
        in raw_assertions
    )

    assertions_by_id = {
        assertion.assertion_id: assertion
        for assertion
        in assertions
    }

    if len(
        assertions_by_id
    ) != len(
        assertions
    ):
        raise RepositorySemanticWorldModelStoreError(
            "snapshot contains duplicate assertions"
        )

    snapshot = make_world_model_snapshot(
        claims=claims,
        assessments=assessments,
        assertions=assertions,
    )

    if (
        snapshot.snapshot_id
        != raw[
            "snapshot_id"
        ]
    ):
        raise RepositorySemanticWorldModelStoreError(
            "snapshot identity is invalid"
        )

    if (
        repository_world_model_snapshot_payload(
            snapshot
        )
        != dict(
            raw
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "snapshot payload is not canonical"
        )

    return snapshot


def _validate_model(
    model: RepositoryDeterministicWorldModel,
    *,
    name: str,
) -> None:
    if not isinstance(
        model,
        RepositoryDeterministicWorldModel,
    ):
        raise RepositorySemanticWorldModelStoreError(
            f"{name} must be a RepositoryDeterministicWorldModel"
        )


def serialize_repository_semantic_overlay(
    base_model: RepositoryDeterministicWorldModel,
    promoted_model: RepositoryDeterministicWorldModel,
) -> dict[str, object]:
    _validate_model(
        base_model,
        name="base model",
    )

    _validate_model(
        promoted_model,
        name="promoted model",
    )

    if (
        base_model.source_commit
        != promoted_model.source_commit
        or (
            base_model.repository_observation_id
            != promoted_model.repository_observation_id
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "base and promoted models represent different repository snapshots"
        )

    if (
        base_model.where_it_sits_assertion_ids
        != promoted_model.where_it_sits_assertion_ids
        or (
            base_model.what_it_depends_on_assertion_ids
            != promoted_model.what_it_depends_on_assertion_ids
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay may not alter deterministic section selections"
        )

    if (
        base_model.what_it_is_assertion_ids
    ):
        raise RepositorySemanticWorldModelStoreError(
            "base model already contains WHAT_IT_IS semantic state"
        )

    if len(
        promoted_model.what_it_is_assertion_ids
    ) != 1:
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay requires exactly one WHAT_IT_IS assertion"
        )

    base_claims = {
        item.claim_id: item
        for item
        in base_model.snapshot.claims
    }

    base_assessments = {
        item.assessment_id: item
        for item
        in base_model.snapshot.assessments
    }

    base_assertions = {
        item.assertion_id: item
        for item
        in base_model.snapshot.assertions
    }

    promoted_claims = {
        item.claim_id: item
        for item
        in promoted_model.snapshot.claims
    }

    promoted_assessments = {
        item.assessment_id: item
        for item
        in promoted_model.snapshot.assessments
    }

    promoted_assertions = {
        item.assertion_id: item
        for item
        in promoted_model.snapshot.assertions
    }

    for identity, item in base_claims.items():
        if (
            promoted_claims.get(
                identity
            )
            != item
        ):
            raise RepositorySemanticWorldModelStoreError(
                "promoted model altered or removed a base claim"
            )

    for identity, item in base_assessments.items():
        if (
            promoted_assessments.get(
                identity
            )
            != item
        ):
            raise RepositorySemanticWorldModelStoreError(
                "promoted model altered or removed a base assessment"
            )

    for identity, item in base_assertions.items():
        if (
            promoted_assertions.get(
                identity
            )
            != item
        ):
            raise RepositorySemanticWorldModelStoreError(
                "promoted model altered or removed a base assertion"
            )

    added_claims = tuple(
        item
        for identity, item
        in promoted_claims.items()
        if identity
        not in base_claims
    )

    added_assessments = tuple(
        item
        for identity, item
        in promoted_assessments.items()
        if identity
        not in base_assessments
    )

    added_assertions = tuple(
        item
        for identity, item
        in promoted_assertions.items()
        if identity
        not in base_assertions
    )

    if not (
        len(
            added_claims
        )
        == len(
            added_assessments
        )
        == len(
            added_assertions
        )
        == 1
    ):
        raise RepositorySemanticWorldModelStoreError(
            "WHAT_IT_IS overlay must add exactly one claim, assessment, and assertion"
        )

    claim = added_claims[
        0
    ]

    assessment = added_assessments[
        0
    ]

    assertion = added_assertions[
        0
    ]

    if (
        promoted_model.what_it_is_assertion_ids
        != (
            assertion.assertion_id,
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "WHAT_IT_IS selection does not identify the added assertion"
        )

    if (
        assertion.relation
        is not WorldModelRelationKind.IMPLEMENTS
    ):
        raise RepositorySemanticWorldModelStoreError(
            "WHAT_IT_IS assertion must use IMPLEMENTS"
        )

    if (
        assertion.claim_id
        != claim.claim_id
        or (
            assertion.assessment_id
            != assessment.assessment_id
        )
        or assessment.claim_id
        != claim.claim_id
    ):
        raise RepositorySemanticWorldModelStoreError(
            "WHAT_IT_IS authority chain is inconsistent"
        )

    if (
        assessment.status
        is not EpistemicStatus
        .SUPPORTED_HYPOTHESIS
    ):
        raise RepositorySemanticWorldModelStoreError(
            "persisted WHAT_IT_IS must remain SUPPORTED_HYPOTHESIS"
        )

    if (
        not claim.evidence
        or any(
            (
                reference.evidence_kind
                is not ClaimEvidenceKind.STATIC
                or (
                    reference.relation
                    is not ClaimEvidenceRelation
                    .SUPPORTS
                )
            )
            for reference
            in claim.evidence
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "persisted WHAT_IT_IS claim requires static supporting evidence"
        )

    core = {
        "schema_version": (
            _SCHEMA_VERSION
        ),
        "source_commit": (
            base_model.source_commit
        ),
        "repository_observation_id": (
            base_model.repository_observation_id
        ),
        "base_snapshot_id": (
            base_model.snapshot.snapshot_id
        ),
        "promoted_snapshot_id": (
            promoted_model.snapshot.snapshot_id
        ),
        "what_it_is_assertion_ids": list(
            promoted_model.what_it_is_assertion_ids
        ),
        "claims": [
            _claim_payload(
                claim
            )
        ],
        "assessments": [
            _assessment_payload(
                assessment
            )
        ],
        "assertions": [
            _assertion_payload(
                assertion
            )
        ],
    }

    return {
        **core,
        "overlay_id": _identity(
            "repository-semantic-overlay:",
            core,
        ),
    }


def apply_repository_semantic_overlay_payload(
    base_model: RepositoryDeterministicWorldModel,
    payload: object,
) -> RepositoryDeterministicWorldModel:
    _validate_model(
        base_model,
        name="base model",
    )

    raw = _require_mapping(
        payload,
        name="semantic overlay",
        fields=_TOP_LEVEL_FIELDS,
    )

    if (
        raw[
            "schema_version"
        ]
        != _SCHEMA_VERSION
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay schema version is unsupported"
        )

    source_commit = _require_text(
        raw[
            "source_commit"
        ],
        name="source commit",
    )

    observation_id = _require_text(
        raw[
            "repository_observation_id"
        ],
        name="repository observation id",
    )

    base_snapshot_id = _require_text(
        raw[
            "base_snapshot_id"
        ],
        name="base snapshot id",
    )

    if (
        source_commit
        != base_model.source_commit
        or observation_id
        != base_model.repository_observation_id
        or (
            base_snapshot_id
            != base_model.snapshot.snapshot_id
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay does not belong to the current deterministic snapshot"
        )

    core = {
        key: raw[
            key
        ]
        for key
        in _TOP_LEVEL_FIELDS
        if key
        != "overlay_id"
    }

    expected_overlay_id = _identity(
        "repository-semantic-overlay:",
        core,
    )

    if (
        raw[
            "overlay_id"
        ]
        != expected_overlay_id
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay identity is invalid"
        )

    raw_claims = raw[
        "claims"
    ]

    raw_assessments = raw[
        "assessments"
    ]

    raw_assertions = raw[
        "assertions"
    ]

    if not (
        isinstance(
            raw_claims,
            list,
        )
        and isinstance(
            raw_assessments,
            list,
        )
        and isinstance(
            raw_assertions,
            list,
        )
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay collections must be lists"
        )

    added_claims = tuple(
        _decode_claim(
            item
        )
        for item
        in raw_claims
    )

    claims = (
        *base_model.snapshot.claims,
        *added_claims,
    )

    claims_by_id = {
        claim.claim_id: claim
        for claim
        in claims
    }

    if len(
        claims_by_id
    ) != len(
        claims
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay collides with an existing claim"
        )

    added_assessments = tuple(
        _decode_assessment(
            item,
            claims_by_id=claims_by_id,
        )
        for item
        in raw_assessments
    )

    assessments = (
        *base_model.snapshot.assessments,
        *added_assessments,
    )

    assessments_by_id = {
        assessment.assessment_id: (
            assessment
        )
        for assessment
        in assessments
    }

    if len(
        assessments_by_id
    ) != len(
        assessments
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay collides with an existing assessment"
        )

    added_assertions = tuple(
        _decode_assertion(
            item,
            claims_by_id=claims_by_id,
            assessments_by_id=(
                assessments_by_id
            ),
        )
        for item
        in raw_assertions
    )

    assertions = (
        *base_model.snapshot.assertions,
        *added_assertions,
    )

    if len(
        {
            assertion.assertion_id
            for assertion
            in assertions
        }
    ) != len(
        assertions
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay collides with an existing assertion"
        )

    snapshot = make_world_model_snapshot(
        claims=claims,
        assessments=assessments,
        assertions=assertions,
    )

    if (
        snapshot.snapshot_id
        != raw[
            "promoted_snapshot_id"
        ]
    ):
        raise RepositorySemanticWorldModelStoreError(
            "promoted snapshot identity is invalid"
        )

    what_it_is_ids = (
        _require_text_list(
            raw[
                "what_it_is_assertion_ids"
            ],
            name="WHAT_IT_IS assertion ids",
        )
    )

    promoted = replace(
        base_model,
        snapshot=snapshot,
        what_it_is_assertion_ids=(
            what_it_is_ids
        ),
    )

    canonical = (
        serialize_repository_semantic_overlay(
            base_model,
            promoted,
        )
    )

    if canonical != dict(
        raw
    ):
        raise RepositorySemanticWorldModelStoreError(
            "semantic overlay payload is not canonical"
        )

    return promoted


def restore_repository_world_model_from_promotion_payload(
    *,
    base_model: RepositoryDeterministicWorldModel,
    promoted_snapshot_payload: object,
    what_it_is_assertion_ids: object,
) -> RepositoryDeterministicWorldModel:
    _validate_model(
        base_model,
        name="base model",
    )

    snapshot = _decode_snapshot(
        promoted_snapshot_payload
    )

    ids = _require_text_list(
        (
            list(
                what_it_is_assertion_ids
            )
            if isinstance(
                what_it_is_assertion_ids,
                tuple,
            )
            else what_it_is_assertion_ids
        ),
        name="WHAT_IT_IS assertion ids",
    )

    promoted = replace(
        base_model,
        snapshot=snapshot,
        what_it_is_assertion_ids=ids,
    )

    serialize_repository_semantic_overlay(
        base_model,
        promoted,
    )

    return promoted


def default_repository_semantic_world_model_store_root() -> Path:
    configured = os.environ.get(
        "HORIZON_STATE_HOME"
    )

    if configured is not None:
        if not configured.strip():
            raise RepositorySemanticWorldModelStoreError(
                "HORIZON_STATE_HOME may not be empty"
            )

        state_home = Path(
            configured
        ).expanduser()

    else:
        state_home = (
            Path.home()
            / ".horizon"
            / "state"
        )

    return (
        state_home
        / "repository-semantic-world-model"
    )


def _store_key(
    base_model: RepositoryDeterministicWorldModel,
) -> str:
    _validate_model(
        base_model,
        name="base model",
    )

    return hashlib.sha256(
        _canonical_json(
            {
                "schema_version": (
                    _SCHEMA_VERSION
                ),
                "source_commit": (
                    base_model.source_commit
                ),
                "repository_observation_id": (
                    base_model.repository_observation_id
                ),
                "base_snapshot_id": (
                    base_model.snapshot.snapshot_id
                ),
            }
        )
    ).hexdigest()


class RepositorySemanticWorldModelStore:
    def __init__(
        self,
        root: str | Path,
    ) -> None:
        self.root = Path(
            root
        ).expanduser()

    def path_for(
        self,
        base_model: RepositoryDeterministicWorldModel,
    ) -> Path:
        return (
            self.root
            / (
                "repository-semantic-overlay-"
                + _store_key(
                    base_model
                )
                + ".json"
            )
        )

    def save(
        self,
        base_model: RepositoryDeterministicWorldModel,
        promoted_model: RepositoryDeterministicWorldModel,
    ) -> Path:
        payload = (
            serialize_repository_semantic_overlay(
                base_model,
                promoted_model,
            )
        )

        raw = (
            _canonical_json(
                payload
            )
            + b"\n"
        )

        target = self.path_for(
            base_model
        )

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        if target.exists():
            existing = target.read_bytes()

            if existing != raw:
                raise RepositorySemanticWorldModelStoreError(
                    "a different semantic overlay already exists for this base snapshot"
                )

            return target

        descriptor, temporary_name = (
            tempfile.mkstemp(
                prefix=(
                    ".repository-semantic-overlay-"
                ),
                suffix=".tmp",
                dir=str(
                    self.root
                ),
            )
        )

        temporary = Path(
            temporary_name
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

            os.chmod(
                temporary,
                0o600,
            )

            if target.exists():
                existing = target.read_bytes()

                if existing != raw:
                    raise RepositorySemanticWorldModelStoreError(
                        "a different semantic overlay appeared during persistence"
                    )

                temporary.unlink(
                    missing_ok=True
                )

                return target

            os.replace(
                temporary,
                target,
            )

            os.chmod(
                target,
                0o600,
            )

        finally:
            temporary.unlink(
                missing_ok=True
            )

        if target.read_bytes() != raw:
            raise RepositorySemanticWorldModelStoreError(
                "persisted semantic overlay failed read-back verification"
            )

        return target

    def load(
        self,
        base_model: RepositoryDeterministicWorldModel,
    ) -> RepositoryDeterministicWorldModel:
        path = self.path_for(
            base_model
        )

        if not path.exists():
            return base_model

        if not path.is_file():
            raise RepositorySemanticWorldModelStoreError(
                "semantic overlay path is not a regular file"
            )

        try:
            raw = path.read_bytes()

            payload = json.loads(
                raw.decode(
                    "utf-8"
                )
            )

        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise RepositorySemanticWorldModelStoreError(
                "semantic overlay cannot be read"
            ) from exc

        return (
            apply_repository_semantic_overlay_payload(
                base_model,
                payload,
            )
        )
