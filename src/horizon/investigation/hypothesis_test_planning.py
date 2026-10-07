"""Deterministic bridge from hypothesis tests into typed planning.

PROPOSE_HYPOTHESIS is deliberately not directly executable.

A validated hypothesis proposal may, however, contain test questions
which request further evidence. Those questions need to enter Horizon's
existing typed-planning authority boundary without changing the source
proposal into truth and without weakening the existing rule that only a
PROPOSE_INVESTIGATION proposal can compile into an execution plan.

This module creates a deterministic derived planning proposal whose
investigation questions are exactly the source hypothesis test questions.

The source hypothesis proposal remains the provenance authority.
The derived proposal is a planning envelope only.
"""

from __future__ import annotations

import hashlib
import json

from dataclasses import dataclass

from horizon.investigator.middleware import (
    InvestigationRequest,
    InvestigationRequestOrigin,
)
from horizon.investigator.proposal import (
    InvestigationProposal,
    parse_investigation_proposal,
)


class HypothesisTestPlanningBridgeError(
    ValueError
):
    """A hypothesis proposal cannot be bridged safely into planning."""


@dataclass(
    frozen=True,
    slots=True,
)
class HypothesisTestPlanningBridge:
    source_proposal_id: str
    source_hypothesis: str
    test_questions: tuple[
        str,
        ...,
    ]

    planning_proposal: InvestigationProposal

    bridge_id: str


def _identity(
    prefix: str,
    payload: object,
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        prefix
        + hashlib.sha256(
            encoded
        ).hexdigest()
    )


def bridge_hypothesis_tests_to_typed_planning(
    *,
    request: InvestigationRequest,
    proposal: InvestigationProposal,
) -> HypothesisTestPlanningBridge:
    """Derive an executable-planning envelope from exact test questions."""

    if not isinstance(
        request,
        InvestigationRequest,
    ):
        raise HypothesisTestPlanningBridgeError(
            "request must be an InvestigationRequest"
        )

    if (
        request.origin
        is not
        InvestigationRequestOrigin.REPOSITORY_SEMANTIC_GAP
    ):
        raise HypothesisTestPlanningBridgeError(
            "request must be a repository semantic-gap request"
        )

    if not isinstance(
        proposal,
        InvestigationProposal,
    ):
        raise HypothesisTestPlanningBridgeError(
            "proposal must be an InvestigationProposal"
        )

    if (
        proposal.kind.value
        != "PROPOSE_HYPOTHESIS"
    ):
        raise HypothesisTestPlanningBridgeError(
            "proposal must be PROPOSE_HYPOTHESIS"
        )

    if (
        proposal.question_id
        != request.question_id
    ):
        raise HypothesisTestPlanningBridgeError(
            "proposal question does not match request"
        )

    if (
        proposal.relationship_id
        != request.relationship_id
    ):
        raise HypothesisTestPlanningBridgeError(
            "proposal relationship does not match request"
        )

    if (
        not isinstance(
            proposal.hypothesis,
            str,
        )
        or not proposal.hypothesis.strip()
    ):
        raise HypothesisTestPlanningBridgeError(
            "hypothesis must be nonempty"
        )

    if not proposal.test_questions:
        raise HypothesisTestPlanningBridgeError(
            "hypothesis proposal must contain test questions"
        )

    if any(
        (
            not isinstance(
                question,
                str,
            )
            or not question.strip()
        )
        for question
        in proposal.test_questions
    ):
        raise HypothesisTestPlanningBridgeError(
            "test questions must be nonempty text"
        )

    planning_proposal = (
        parse_investigation_proposal(
            request,
            {
                "type": (
                    "PROPOSE_INVESTIGATION"
                ),
                "question_id": (
                    proposal.question_id
                ),
                "relationship_id": (
                    proposal.relationship_id
                ),
                "assertion_ids": list(
                    proposal.assertion_ids
                ),
                "claim_ids": list(
                    proposal.claim_ids
                ),
                "assessment_ids": list(
                    proposal.assessment_ids
                ),
                "evidence_reference_ids": list(
                    proposal.evidence_reference_ids
                ),
                "investigation_questions": list(
                    proposal.test_questions
                ),
            },
        )
    )

    if (
        planning_proposal
        .investigation_questions
        != proposal.test_questions
    ):
        raise HypothesisTestPlanningBridgeError(
            "derived planning questions do not exactly match test questions"
        )

    bridge_id = _identity(
        "hypothesis-test-planning-bridge:",
        {
            "request_id": (
                request.request_id
            ),
            "source_proposal_id": (
                proposal.proposal_id
            ),
            "source_hypothesis": (
                proposal.hypothesis
            ),
            "test_questions": list(
                proposal.test_questions
            ),
            "planning_proposal_id": (
                planning_proposal.proposal_id
            ),
        },
    )

    return HypothesisTestPlanningBridge(
        source_proposal_id=(
            proposal.proposal_id
        ),
        source_hypothesis=(
            proposal.hypothesis
        ),
        test_questions=(
            proposal.test_questions
        ),
        planning_proposal=(
            planning_proposal
        ),
        bridge_id=bridge_id,
    )
