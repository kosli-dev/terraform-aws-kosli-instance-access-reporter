import dataclasses
from datetime import timedelta

import pytest

from kosli_access import config

#: The minimum an instance account and the SSO account both have to supply.
ENVIRON = {
    "KOSLI_ORG": "kosli",
    "KOSLI_FLOW_NAME": "instance-access-prod",
    "KOSLI_API_TOKEN_SECRET_ARN": "arn:aws:secretsmanager:eu-central-1:1:secret:x",
    "INSTANCE_FLOWS": '{"358426185766": "instance-access-prod"}',
}


def test_the_two_loaders_agree_about_every_shared_setting():
    # The contract between the two halves of a trail. If these ever read a
    # different window, an elevation and the session it authorised land on
    # different trails and the correlation fails silently.
    session = config.load_settings(ENVIRON)
    elevation = config.load_elevation_settings(ENVIRON)

    shared = [field.name for field in dataclasses.fields(config.KosliSettings)]
    assert shared, "KosliSettings has lost its fields, so this proves nothing"
    for name in shared:
        assert getattr(session, name) == getattr(elevation, name), name


def test_the_defaults_do_not_have_to_be_configured():
    settings = config.load_settings(ENVIRON)

    assert settings.kosli_binary == "/opt/kosli"
    assert settings.kosli_host == "https://app.kosli.com"
    assert settings.trail_window == timedelta(hours=3)


def test_the_trail_window_is_read_in_hours_and_may_be_fractional():
    environ = dict(ENVIRON, TRAIL_WINDOW_HOURS="0.5")

    assert config.load_settings(environ).trail_window == timedelta(minutes=30)


def test_the_page_settings_are_integers_though_the_environment_is_text():
    environ = dict(ENVIRON, TRAIL_LIST_PAGE_LIMIT="50", TRAIL_LIST_MAX_PAGES="2")

    settings = config.load_settings(environ)

    assert (settings.trail_list_page_limit, settings.trail_list_max_pages) == (50, 2)
    assert isinstance(settings.trail_list_page_limit, int)


@pytest.mark.parametrize("name", ["KOSLI_ORG", "KOSLI_API_TOKEN_SECRET_ARN"])
def test_a_missing_shared_setting_is_fatal_for_both_reporters(name):
    environ = {key: value for key, value in ENVIRON.items() if key != name}

    with pytest.raises(config.ConfigurationError, match=name):
        config.load_settings(environ)
    with pytest.raises(config.ConfigurationError, match=name):
        config.load_elevation_settings(environ)


def test_the_session_reporters_cannot_start_without_a_flow():
    environ = {k: v for k, v in ENVIRON.items() if k != "KOSLI_FLOW_NAME"}

    with pytest.raises(config.ConfigurationError, match="KOSLI_FLOW_NAME"):
        config.load_settings(environ)


def test_the_elevation_reporter_cannot_start_without_a_flow_map():
    environ = {k: v for k, v in ENVIRON.items() if k != "INSTANCE_FLOWS"}

    with pytest.raises(config.ConfigurationError, match="INSTANCE_FLOWS"):
        config.load_elevation_settings(environ)


def test_a_window_that_is_not_a_number_is_fatal_rather_than_defaulted():
    # Silently falling back to three hours would be worse than not starting: the
    # window would differ from the other half's and nothing would say so.
    environ = dict(ENVIRON, TRAIL_WINDOW_HOURS="soon")

    with pytest.raises(config.ConfigurationError, match="TRAIL_WINDOW_HOURS"):
        config.load_settings(environ)


@pytest.mark.parametrize("raw", ["not json", "[]", "{}", '"a flow"'])
def test_a_flow_map_that_is_not_a_populated_object_is_fatal(raw):
    environ = dict(ENVIRON, INSTANCE_FLOWS=raw)

    with pytest.raises(config.ConfigurationError):
        config.load_elevation_settings(environ)


def test_account_ids_are_strings_so_they_match_the_elevator_audit_entry():
    environ = dict(
        ENVIRON,
        INSTANCE_FLOWS='{"358426185766": "prod", "545238427212": "prod-us"}',
    )

    flows = config.load_elevation_settings(environ).instance_flows

    assert flows == {"358426185766": "prod", "545238427212": "prod-us"}
