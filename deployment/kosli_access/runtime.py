"""Lambda cold-start wiring, kept out of the handlers so they stay testable."""

import logging

import boto3

from .config import load_settings
from .kosli import KosliClient
from .token import fetch_api_token

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_settings = None
_client = None


def settings():
    """Return the process-wide :class:`~kosli_access.config.Settings`."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def kosli_client():
    """Return the process-wide Kosli client, fetching the token on cold start."""
    global _client
    if _client is None:
        current = settings()
        token = fetch_api_token(
            current.kosli_api_token_secret_arn, boto3.client("secretsmanager")
        )
        _client = KosliClient(
            binary=current.kosli_binary,
            host=current.kosli_host,
            org=current.kosli_org,
            flow=current.kosli_flow_name,
            api_token=token,
            page_limit=current.trail_list_page_limit,
            max_pages=current.trail_list_max_pages,
        )
    return _client


def reset():
    """Discard the cached settings and client. Used by the tests."""
    global _settings, _client
    _settings = None
    _client = None


class AttestationErrors:
    """Collects per-attestation failures so one failure cannot hide the rest.

    Every attestation is attempted, then the handler raises if any of them
    failed. The alternative — bailing out on the first error — loses the
    evidence that would still have been reportable.
    """

    def __init__(self):
        self.failures = []

    def attempt(self, description, action):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - recorded and re-raised below
            logger.exception("Failed to report %s", description)
            self.failures.append(f"{description}: {exc}")
            return None

    def raise_if_any(self):
        if self.failures:
            raise RuntimeError(
                "Some evidence could not be reported to Kosli: "
                + "; ".join(self.failures)
            )
