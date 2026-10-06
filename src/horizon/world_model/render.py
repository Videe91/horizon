"""Pure human-readable rendering of a world-model snapshot.

The renderer formats only assertions explicitly selected by its caller.

Human meaning is presented first. Machine identities remain visible as
trace provenance beneath the human-readable statement.

The renderer does not infer section membership, semantic relations,
epistemic status, ownership, or disagreement resolution.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from enum import Enum

from horizon.world_model.snapshot import (
    WorldModelSnapshot,
)


class WorldModelRenderError(
    ValueError
):
    """A requested world-model view cannot be rendered faithfully."""


class WorldModelCardSection(
    str,
    Enum,
):
    WHAT_IT_IS = "WHAT_IT_IS"
    WHERE_IT_SITS = "WHERE_IT_SITS"
    WHAT_IT_OWNS = "WHAT_IT_OWNS"
    WHAT_IT_DEPENDS_ON = "WHAT_IT_DEPENDS_ON"
    WHAT_MUST_REMAIN_TRUE = "WHAT_MUST_REMAIN_TRUE"


_SECTION_HEADINGS = {
    WorldModelCardSection.WHAT_IT_IS: "WHAT IT IS",
    WorldModelCardSection.WHERE_IT_SITS: "WHERE IT SITS",
    WorldModelCardSection.WHAT_IT_OWNS: "WHAT IT OWNS",
    WorldModelCardSection.WHAT_IT_DEPENDS_ON: "WHAT IT DEPENDS ON",
    WorldModelCardSection.WHAT_MUST_REMAIN_TRUE: "WHAT MUST REMAIN TRUE",
}


def _trace_line(
    assertion,
    claim,
    assessment,
) -> str:
    return (
        "  trace: "
        f"assertion_id={assertion.assertion_id} "
        f"| claim_id={claim.claim_id} "
        f"| assessment_id={assessment.assessment_id}"
    )


def _evidence_text(
    assessment,
) -> str:
    return ",".join(
        assessment.basis_reference_ids
    )


def render_world_model_card(
    snapshot: WorldModelSnapshot,
    *,
    title: str,
    question: str,
    sections: Mapping[
        WorldModelCardSection,
        Iterable[str],
    ],
) -> str:
    if not isinstance(
        snapshot,
        WorldModelSnapshot,
    ):
        raise WorldModelRenderError(
            "snapshot must be a WorldModelSnapshot"
        )

    claims_by_id = {
        claim.claim_id: claim
        for claim in snapshot.claims
    }

    assessments_by_id = {
        assessment.assessment_id: assessment
        for assessment in snapshot.assessments
    }

    assertions_by_id = {
        assertion.assertion_id: assertion
        for assertion in snapshot.assertions
    }

    selected_by_section: dict[
        WorldModelCardSection,
        tuple[str, ...],
    ] = {}

    selected_assertion_ids: set[str] = set()

    for section in WorldModelCardSection:
        assertion_ids = tuple(
            sorted(
                sections.get(
                    section,
                    (),
                )
            )
        )

        for assertion_id in assertion_ids:
            if assertion_id not in assertions_by_id:
                raise WorldModelRenderError(
                    "selected assertion is not present in snapshot"
                )

        selected_by_section[
            section
        ] = assertion_ids

        selected_assertion_ids.update(
            assertion_ids
        )

    lines = [
        f"TITLE: {title}",
        f"QUESTION: {question}",
    ]

    for section in WorldModelCardSection:
        lines.extend(
            (
                "",
                _SECTION_HEADINGS[
                    section
                ],
            )
        )

        assertion_ids = selected_by_section[
            section
        ]

        if not assertion_ids:
            lines.append(
                "NO JUSTIFIED ASSERTION SELECTED"
            )
            continue

        for assertion_id in assertion_ids:
            assertion = assertions_by_id[
                assertion_id
            ]

            claim = claims_by_id[
                assertion.claim_id
            ]

            assessment = assessments_by_id[
                assertion.assessment_id
            ]

            evidence = _evidence_text(
                assessment
            )

            lines.append(
                (
                    f"[{assessment.status.value}] "
                    f"{claim.proposition} "
                    f"| evidence={evidence}"
                )
            )

            lines.append(
                (
                    "  relation: "
                    f"{assertion.subject_id} "
                    f"{assertion.relation.value} "
                    f"{assertion.object_id}"
                )
            )

            lines.append(
                (
                    "  rationale: "
                    f"{assessment.rationale}"
                )
            )

            lines.append(
                _trace_line(
                    assertion,
                    claim,
                    assessment,
                )
            )

            lines.append(
                (
                    "  claim="
                    f"{json.dumps(claim.proposition)}"
                )
            )

    lines.extend(
        (
            "",
            "HOW WE KNOW",
        )
    )

    if not selected_assertion_ids:
        lines.append(
            "NO SELECTED ASSERTION EVIDENCE"
        )
    else:
        for assertion_id in sorted(
            selected_assertion_ids
        ):
            assertion = assertions_by_id[
                assertion_id
            ]

            claim = claims_by_id[
                assertion.claim_id
            ]

            assessment = assessments_by_id[
                assertion.assessment_id
            ]

            evidence = _evidence_text(
                assessment
            )

            lines.append(
                (
                    f"[{assessment.status.value}] "
                    f"{claim.proposition}"
                )
            )

            lines.append(
                (
                    "  rationale: "
                    f"{assessment.rationale}"
                )
            )

            lines.append(
                (
                    "  evidence: "
                    f"{evidence}"
                )
            )

            lines.append(
                _trace_line(
                    assertion,
                    claim,
                    assessment,
                )
            )

    return "\n".join(
        lines
    )
