from datetime import timedelta

import pytest

from kosli_access import config, runtime

SETTINGS = config.ElevationSettings(
    kosli_binary="/opt/kosli",
    kosli_host="https://app.kosli.com",
    kosli_org="kosli",
    kosli_api_token_secret_arn="arn:aws:secretsmanager:eu-north-1:1:secret:x",
    trail_window=timedelta(hours=3),
    trail_list_page_limit=30,
    trail_list_max_pages=3,
    instance_flows={"358426185766": "instance-access-prod"},
)


@pytest.fixture(autouse=True)
def clean_process_cache():
    """Nothing cached here may leak into another test."""
    runtime.reset()
    yield
    runtime.reset()


def test_a_boto3_client_is_built_once_per_service(monkeypatch):
    built = []

    def build(service):
        built.append(service)
        return f"{service}-client"

    monkeypatch.setattr(runtime.boto3, "client", build)

    first = runtime.client("s3")
    again = runtime.client("s3")
    other = runtime.client("cloudtrail")

    assert first is again
    assert other == "cloudtrail-client"
    assert built == ["s3", "cloudtrail"]


def test_the_api_token_is_fetched_once_however_many_flows_are_written_to(monkeypatch):
    # The elevation reporter writes to one flow per instance account. Fetching
    # the token per flow would be a Secrets Manager call per elevation.
    fetches = []

    def fetch(secret_arn, client):
        fetches.append(secret_arn)
        return "a-token"

    monkeypatch.setattr(runtime, "fetch_api_token", fetch)
    monkeypatch.setattr(runtime, "client", lambda service: object())
    monkeypatch.setattr(runtime, "elevation_settings", lambda: SETTINGS)

    prod = runtime.kosli_client_for_flow("instance-access-prod")
    prod_us = runtime.kosli_client_for_flow("instance-access-prod-us")

    assert len(fetches) == 1
    assert prod is runtime.kosli_client_for_flow("instance-access-prod")
    assert prod is not prod_us
    assert (prod.flow, prod_us.flow) == (
        "instance-access-prod",
        "instance-access-prod-us",
    )


def test_a_reset_discards_the_token_so_a_rotated_one_is_picked_up(monkeypatch):
    tokens = iter(["first", "second"])
    monkeypatch.setattr(runtime, "fetch_api_token", lambda arn, client: next(tokens))
    monkeypatch.setattr(runtime, "client", lambda service: object())
    monkeypatch.setattr(runtime, "elevation_settings", lambda: SETTINGS)

    assert runtime.api_token(SETTINGS) == "first"
    assert runtime.api_token(SETTINGS) == "first"

    runtime.reset()

    assert runtime.api_token(SETTINGS) == "second"


def test_failures_are_collected_so_one_cannot_hide_the_rest():
    errors = runtime.AttestationErrors()

    errors.attempt("first", lambda: None)
    errors.attempt("second", lambda: 1 / 0)
    assert errors.attempt("third", lambda: "reported") == "reported"

    with pytest.raises(RuntimeError, match="second") as raised:
        errors.raise_if_any()

    assert "first" not in str(raised.value)
    assert "third" not in str(raised.value)
