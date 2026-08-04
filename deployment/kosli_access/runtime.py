"""Process-wide wiring, kept out of the handlers so they stay testable.

Everything a handler needs but should not build for itself: the settings, the
boto3 clients, the Kosli clients, and the collector the handlers report their
attestation failures through. All of it is cached for the life of the lambda
process, so a warm invocation reads no environment and fetches no secret.
"""

import logging

import boto3

from .config import load_elevation_settings, load_settings
from .kosli import KosliClient
from .token import fetch_api_token

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_settings = None
_elevation_settings = None
_api_token = None
_kosli_clients = {}
_boto3_clients = {}


def settings():
    """Return the process-wide :class:`~kosli_access.config.Settings`."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def elevation_settings():
    """Return the process-wide :class:`~kosli_access.config.ElevationSettings`."""
    global _elevation_settings
    if _elevation_settings is None:
        _elevation_settings = load_elevation_settings()
    return _elevation_settings


def client(service):
    """Return a boto3 client for ``service``, built once per process.

    Here rather than in each handler so that the tests have one seam to replace
    instead of a private global per handler per service.
    """
    existing = _boto3_clients.get(service)
    if existing is None:
        existing = boto3.client(service)
        _boto3_clients[service] = existing
    return existing


def api_token(current):
    """Return the Kosli API token, fetched from Secrets Manager on cold start.

    One token serves every flow a reporter writes to, so it is cached here and
    not per client.
    """
    global _api_token
    if _api_token is None:
        _api_token = fetch_api_token(
            current.kosli_api_token_secret_arn, client("secretsmanager")
        )
    return _api_token


def _kosli_client(current, flow):
    """Return the Kosli client for ``flow``, one per flow, cached per process.

    ``current`` is any :class:`~kosli_access.config.KosliSettings`, which is why
    this serves both the session reporters and the elevation reporter.
    """
    existing = _kosli_clients.get(flow)
    if existing is None:
        existing = KosliClient(
            binary=current.kosli_binary,
            host=current.kosli_host,
            org=current.kosli_org,
            flow=flow,
            api_token=api_token(current),
            page_limit=current.trail_list_page_limit,
            max_pages=current.trail_list_max_pages,
        )
        _kosli_clients[flow] = existing
    return existing


def kosli_client():
    """Return the Kosli client for this instance's own flow."""
    current = settings()
    return _kosli_client(current, current.kosli_flow_name)


def kosli_client_for_flow(flow):
    """Return the Kosli client for ``flow``.

    The elevation reporter writes into whichever instance's flow the elevation
    was granted into, so it needs several clients where the session reporters
    need one.
    """
    return _kosli_client(elevation_settings(), flow)


def reset():
    """Discard everything cached above. Used by the tests."""
    global _settings, _elevation_settings, _api_token
    _settings = None
    _elevation_settings = None
    _api_token = None
    _kosli_clients.clear()
    _boto3_clients.clear()


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
