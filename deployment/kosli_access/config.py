"""Environment-driven configuration.

Every failure here is fatal by design. A misconfigured reporter must fail
loudly, at the first event, rather than silently dropping audit evidence.
"""

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


@dataclass(frozen=True)
class Settings:
    """Configuration shared by all of the reporter lambdas."""

    kosli_binary: str
    kosli_host: str
    kosli_org: str
    kosli_flow_name: str
    kosli_api_token_secret_arn: str
    trail_window: timedelta
    trail_list_page_limit: int
    trail_list_max_pages: int
    identity_lookup_timeout: float


def load_settings(environ=None):
    """Build :class:`Settings` from the lambda's environment."""
    environ = os.environ if environ is None else environ
    return Settings(
        kosli_binary=optional_env("KOSLI_BINARY", DEFAULT_KOSLI_BINARY, environ),
        kosli_host=optional_env("KOSLI_HOST", "https://app.kosli.com", environ),
        kosli_org=required_env("KOSLI_ORG", environ),
        kosli_flow_name=required_env("KOSLI_FLOW_NAME", environ),
        kosli_api_token_secret_arn=required_env(
            "KOSLI_API_TOKEN_SECRET_ARN", environ
        ),
        trail_window=timedelta(
            hours=numeric_env("TRAIL_WINDOW_HOURS", 3.0, environ)
        ),
        trail_list_page_limit=int(
            numeric_env("TRAIL_LIST_PAGE_LIMIT", 30, environ)
        ),
        trail_list_max_pages=int(numeric_env("TRAIL_LIST_MAX_PAGES", 3, environ)),
        identity_lookup_timeout=numeric_env(
            "IDENTITY_LOOKUP_TIMEOUT_SECONDS", 840.0, environ
        ),
    )
