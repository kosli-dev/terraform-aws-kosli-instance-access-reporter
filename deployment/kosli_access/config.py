"""Environment-driven configuration.

Every failure here is fatal by design. A misconfigured reporter must fail
loudly, at the first event, rather than silently dropping audit evidence.
"""

import json
import os
from dataclasses import dataclass
from datetime import timedelta

DEFAULT_KOSLI_BINARY = "/opt/kosli"


class ConfigurationError(RuntimeError):
    """The lambda is misconfigured and cannot produce evidence."""


def required_env(name, environ=None):
    """Return the value of ``name``, raising if it is unset or empty."""
    environ = os.environ if environ is None else environ
    value = (environ.get(name) or "").strip()
    if not value:
        raise ConfigurationError(
            f"Required environment variable {name} is not set"
        )
    return value


def optional_env(name, default, environ=None):
    environ = os.environ if environ is None else environ
    value = (environ.get(name) or "").strip()
    return value or default


def numeric_env(name, default, environ=None):
    environ = os.environ if environ is None else environ
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"Environment variable {name} must be a number, got {raw!r}"
        ) from exc


def int_env(name, default, environ=None):
    """Return ``name`` as an int, for the settings that count things."""
    return int(numeric_env(name, default, environ))


@dataclass(frozen=True)
class KosliSettings:
    """What every reporter needs to talk to Kosli and to name a trail.

    The trail settings live here, on the shared base, because the reporters have
    to agree about which events belong to one piece of work. A window read from
    two places is a window that can differ, and two halves of a trail that
    disagree about it land in different places.

    Anything that takes one of these works for any reporter, which is what lets
    :mod:`kosli_access.runtime` build a client from either subclass.
    """

    kosli_binary: str
    kosli_host: str
    kosli_org: str
    kosli_api_token_secret_arn: str
    trail_window: timedelta
    trail_list_page_limit: int
    trail_list_max_pages: int


def _shared_settings(environ):
    """Read the :class:`KosliSettings` fields, and their defaults, just once."""
    return {
        "kosli_binary": optional_env("KOSLI_BINARY", DEFAULT_KOSLI_BINARY, environ),
        "kosli_host": optional_env("KOSLI_HOST", "https://app.kosli.com", environ),
        "kosli_org": required_env("KOSLI_ORG", environ),
        "kosli_api_token_secret_arn": required_env(
            "KOSLI_API_TOKEN_SECRET_ARN", environ
        ),
        "trail_window": timedelta(
            hours=numeric_env("TRAIL_WINDOW_HOURS", 3.0, environ)
        ),
        "trail_list_page_limit": int_env("TRAIL_LIST_PAGE_LIMIT", 30, environ),
        "trail_list_max_pages": int_env("TRAIL_LIST_MAX_PAGES", 3, environ),
    }


@dataclass(frozen=True)
class Settings(KosliSettings):
    """Configuration for the session reporters, which serve one instance.

    Deployed once per instance account, so the flow is known at deploy time and
    named in the environment.
    """

    kosli_flow_name: str
    identity_lookup_timeout: float


def load_settings(environ=None):
    """Build :class:`Settings` from the lambda's environment."""
    environ = os.environ if environ is None else environ
    return Settings(
        **_shared_settings(environ),
        kosli_flow_name=required_env("KOSLI_FLOW_NAME", environ),
        # Only the transcript reporter resolves an identity from CloudTrail, so
        # only it has a polling budget; the exec session reporter reads this and
        # ignores it.
        identity_lookup_timeout=numeric_env(
            "IDENTITY_LOOKUP_TIMEOUT_SECONDS", 840.0, environ
        ),
    )


@dataclass(frozen=True)
class ElevationSettings(KosliSettings):
    """Configuration for the elevation reporter in the SSO account.

    It differs from :class:`Settings` in one structural way: there is no single
    flow. The session reporters are deployed once per instance account and so
    know their own flow, while this one lambda serves every instance and has to
    look the flow up from the account the elevation was granted into.
    """

    instance_flows: dict


def load_instance_flows(environ=None):
    """Return the account-id to flow-name map from ``INSTANCE_FLOWS``.

    A JSON object, supplied by the caller. There is deliberately no derivation
    from the account id: guessing would write real evidence to the wrong
    instance's flow, which is worse than not writing it at all.
    """
    environ = os.environ if environ is None else environ
    raw = (environ.get("INSTANCE_FLOWS") or "").strip()
    if not raw:
        raise ConfigurationError(
            "Required environment variable INSTANCE_FLOWS is not set, so no "
            "elevation can be matched to an instance flow"
        )
    try:
        flows = json.loads(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"Environment variable INSTANCE_FLOWS must be JSON, got {raw!r}"
        ) from exc
    if not isinstance(flows, dict) or not flows:
        raise ConfigurationError(
            "INSTANCE_FLOWS must be a non-empty object mapping AWS account id "
            f"to Kosli flow name, got {flows!r}"
        )
    return {str(account): str(flow) for account, flow in flows.items()}


def load_elevation_settings(environ=None):
    """Build :class:`ElevationSettings` from the lambda's environment."""
    environ = os.environ if environ is None else environ
    return ElevationSettings(
        **_shared_settings(environ),
        instance_flows=load_instance_flows(environ),
    )
