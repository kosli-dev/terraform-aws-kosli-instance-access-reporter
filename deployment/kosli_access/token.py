"""Kosli API token retrieval.

The token is fetched from Secrets Manager at runtime rather than being passed
in as a lambda environment variable. That keeps the secret out of Terraform
state and out of the function configuration, and means a rotated token is
picked up by the next cold start instead of requiring a redeploy.
"""

import logging

logger = logging.getLogger(__name__)


class TokenError(RuntimeError):
    """The Kosli API token could not be retrieved."""


def fetch_api_token(secret_arn, client):
    """Return the Kosli API token held in ``secret_arn``.

    A secret container created by Terraform but never populated raises
    ``ResourceNotFoundException`` here. That is deliberately fatal: it is the
    one prerequisite an account can be stood up without.
    """
    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except Exception as exc:  # noqa: BLE001 - re-raised with context below
        raise TokenError(
            f"Could not read the Kosli API token from {secret_arn}. "
            "If the secret exists but has no version, it has not been "
            "populated yet."
        ) from exc

    token = (response.get("SecretString") or "").strip()
    if not token:
        raise TokenError(f"The secret {secret_arn} holds no string value")
    return token
