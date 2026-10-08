"""One-shot replay boundary for a preserved investigator model result.

This module permits a coordinator recovery to consume one exact,
previously obtained InvestigatorModelResult without repeating the
provider request.

The first invocation must match the pre-registered replay invocation
identity exactly. After that single replay, all later invocations are
delegated normally.

This boundary does not parse provider files, perform network I/O,
modify repository state, or change World Model truth.
"""

from __future__ import annotations

from horizon.investigator.model import (
    InvestigatorModel,
    InvestigatorModelInvocation,
    InvestigatorModelResult,
)


class InvestigatorReplayError(
    RuntimeError
):
    """A preserved investigator result cannot be replayed safely."""


class ReplayThenDelegateInvestigatorModel:
    """Replay one exact model result, then delegate all later calls."""

    def __init__(
        self,
        *,
        replay_invocation_id: str,
        replay_result: InvestigatorModelResult,
        delegate: InvestigatorModel,
    ) -> None:
        if (
            not isinstance(
                replay_invocation_id,
                str,
            )
            or not replay_invocation_id.strip()
        ):
            raise InvestigatorReplayError(
                "replay invocation id must be nonempty"
            )

        if not isinstance(
            replay_result,
            InvestigatorModelResult,
        ):
            raise InvestigatorReplayError(
                "replay result must be an InvestigatorModelResult"
            )

        if not callable(
            getattr(
                delegate,
                "invoke",
                None,
            )
        ):
            raise InvestigatorReplayError(
                "delegate must implement investigator model invoke"
            )

        self._replay_invocation_id = (
            replay_invocation_id
        )

        self._replay_result = (
            replay_result
        )

        self._delegate = (
            delegate
        )

        self._replay_consumed = False
        self._replay_count = 0
        self._delegate_count = 0

    @property
    def replay_consumed(
        self,
    ) -> bool:
        return self._replay_consumed

    @property
    def replay_count(
        self,
    ) -> int:
        return self._replay_count

    @property
    def delegate_count(
        self,
    ) -> int:
        return self._delegate_count

    def invoke(
        self,
        invocation: InvestigatorModelInvocation,
    ) -> InvestigatorModelResult:
        if not isinstance(
            invocation,
            InvestigatorModelInvocation,
        ):
            raise InvestigatorReplayError(
                "invocation must be an InvestigatorModelInvocation"
            )

        if not self._replay_consumed:
            if (
                invocation.invocation_id
                != self._replay_invocation_id
            ):
                raise InvestigatorReplayError(
                    "first investigator invocation "
                    "does not match preserved replay authority"
                )

            self._replay_consumed = True
            self._replay_count += 1

            return self._replay_result

        self._delegate_count += 1

        return self._delegate.invoke(
            invocation
        )
