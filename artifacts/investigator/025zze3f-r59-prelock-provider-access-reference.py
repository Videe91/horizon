from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


MODEL_ENDPOINT_ROOT = (
    "https://api.openai.com/v1/models/"
)

DEFAULT_TIMEOUT_SECONDS = 30.0

MAX_RESPONSE_BYTES = 2_000_000


class ProviderAccessPreflightError(
    RuntimeError
):
    """
    Safe pre-lock provider-access failure.

    `classification` is deliberately bounded and safe
    to persist. Raw provider response bodies and raw
    credential values must never enter this exception.
    """

    def __init__(
        self,
        classification: str,
    ) -> None:
        super().__init__(
            classification
        )

        self.classification = (
            classification
        )


def _require_nonempty_string(
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
        raise ProviderAccessPreflightError(
            name
            + "_ABSENT"
        )

    return value


def _safe_close(
    value: object,
) -> None:
    close = getattr(
        value,
        "close",
        None,
    )

    if callable(
        close
    ):
        try:
            close()
        except Exception:
            pass


def _read_bounded_response(
    response: object,
) -> bytes:
    read = getattr(
        response,
        "read",
        None,
    )

    if not callable(
        read
    ):
        raise ProviderAccessPreflightError(
            "PROVIDER_PREFLIGHT_INVALID_RESPONSE"
        )

    body = read(
        MAX_RESPONSE_BYTES
        + 1
    )

    if not isinstance(
        body,
        bytes,
    ):
        raise ProviderAccessPreflightError(
            "PROVIDER_PREFLIGHT_INVALID_RESPONSE"
        )

    if (
        len(body)
        > MAX_RESPONSE_BYTES
    ):
        raise ProviderAccessPreflightError(
            "PROVIDER_PREFLIGHT_RESPONSE_TOO_LARGE"
        )

    return body


def validate_openai_model_access(
    *,
    api_key: str,
    model_id: str,
    opener: Callable[..., Any] = (
        urllib.request.urlopen
    ),
    timeout_seconds: float = (
        DEFAULT_TIMEOUT_SECONDS
    ),
) -> dict[str, object]:
    """
    Authenticate and verify exact model visibility.

    This gate is designed to run BEFORE an irreversible
    Horizon live-attempt lock is created.

    It performs one authenticated model-metadata GET.
    It does not call the Responses API and does not
    generate model output.

    The caller supplies the credential directly.
    This function does not read environment variables,
    persist the credential, fingerprint it, or return it.
    """

    credential = (
        _require_nonempty_string(
            api_key,
            name="CREDENTIAL",
        )
    )

    model = (
        _require_nonempty_string(
            model_id,
            name="MODEL_ID",
        )
    )

    if (
        not isinstance(
            timeout_seconds,
            (
                int,
                float,
            ),
        )
        or isinstance(
            timeout_seconds,
            bool,
        )
        or timeout_seconds <= 0
    ):
        raise ProviderAccessPreflightError(
            "INVALID_TIMEOUT"
        )

    encoded_model = (
        urllib.parse.quote(
            model,
            safe="",
        )
    )

    url = (
        MODEL_ENDPOINT_ROOT
        + encoded_model
    )

    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": (
                "Bearer "
                + credential
            ),
            "Accept": (
                "application/json"
            ),
        },
    )

    response = None

    try:
        try:
            response = opener(
                request,
                timeout=float(
                    timeout_seconds
                ),
            )

        except urllib.error.HTTPError as exc:
            #
            # Never read or expose the provider body.
            # Authentication error bodies may contain
            # masked credential fingerprints.
            #
            status = int(
                exc.code
            )

            _safe_close(
                exc
            )

            if status == 401:
                raise ProviderAccessPreflightError(
                    "AUTHENTICATION_REJECTED"
                ) from None

            if status in (
                403,
                404,
            ):
                raise ProviderAccessPreflightError(
                    "MODEL_ACCESS_REJECTED"
                ) from None

            raise ProviderAccessPreflightError(
                "PROVIDER_PREFLIGHT_FAILED"
            ) from None

        except (
            urllib.error.URLError,
            TimeoutError,
        ):
            raise ProviderAccessPreflightError(
                "NETWORK_PREFLIGHT_FAILED"
            ) from None

        status = getattr(
            response,
            "status",
            None,
        )

        if status is None:
            getcode = getattr(
                response,
                "getcode",
                None,
            )

            if callable(
                getcode
            ):
                status = getcode()

        if status != 200:
            raise ProviderAccessPreflightError(
                "PROVIDER_PREFLIGHT_FAILED"
            )

        body = _read_bounded_response(
            response
        )

    finally:
        if response is not None:
            _safe_close(
                response
            )

    try:
        decoded = body.decode(
            "utf-8"
        )

        payload = json.loads(
            decoded
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        raise ProviderAccessPreflightError(
            "PROVIDER_PREFLIGHT_INVALID_RESPONSE"
        ) from None

    if not isinstance(
        payload,
        dict,
    ):
        raise ProviderAccessPreflightError(
            "PROVIDER_PREFLIGHT_INVALID_RESPONSE"
        )

    if (
        payload.get(
            "id"
        )
        != model
        or payload.get(
            "object"
        )
        != "model"
    ):
        raise ProviderAccessPreflightError(
            "MODEL_ACCESS_IDENTITY_MISMATCH"
        )

    return {
        "http_status": 200,
        "credential_accepted": True,
        "model_accessible": True,
        "model_id": model,
        "object": "model",
        "model_generation_calls": 0,
        "responses_api_calls": 0,
    }


def main() -> int:
    raise SystemExit(
        "R59 provider-access reference is "
        "offline-certification authority only; "
        "direct execution is forbidden"
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
