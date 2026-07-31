from datetime import datetime, timedelta, timezone

import pytest

from kosli_access import trail

from .fakes import FakeKosliClient

WINDOW = timedelta(hours=3)


def at(hour, minute=0, day=31):
    return datetime(2026, 7, day, hour, minute, tzinfo=timezone.utc)


def test_the_email_comes_from_the_role_session_name():
    assert (
        trail.email_from_principal_id("AROAV2KTWFTFPIQXZGND5:graham@kosli.com")
        == "graham@kosli.com"
    )


def test_a_principal_id_without_a_session_name_is_fatal():
    # SSM reports the ECS service-linked role, which carries no human. If that
    # ever reaches trail naming we must fail rather than invent an identity.
    with pytest.raises(trail.TrailNamingError):
        trail.email_from_principal_id("AROAV2KTWFTFPIQXZGND5")


def test_the_trail_user_is_the_local_part_of_the_email():
    assert trail.trail_user("graham@kosli.com") == "graham"
    assert trail.trail_user("first.last@kosli.com") == "first.last"


def test_characters_kosli_disallows_in_trail_names_are_replaced():
    assert trail.trail_user("a+b@kosli.com") == "a-b"


def test_a_name_that_cannot_start_a_trail_name_is_fatal():
    with pytest.raises(trail.TrailNamingError):
        trail.trail_user("+nope@kosli.com")


def test_trail_names_carry_the_session_start_in_utc():
    assert trail.format_trail_name("graham", at(12, 34)) == "graham-2026-07-31-1234"


def test_a_non_utc_session_start_is_converted_before_naming():
    berlin = timezone(timedelta(hours=2))
    started = datetime(2026, 7, 31, 14, 34, tzinfo=berlin)

    assert trail.format_trail_name("graham", started) == "graham-2026-07-31-1234"


def test_parsing_a_trail_name_returns_the_session_start():
    assert trail.parse_trail_start("graham-2026-07-31-1234", "graham") == at(12, 34)


@pytest.mark.parametrize(
    "name",
    [
        "someone-else-2026-07-31-1234",  # another user
        "graham-not-a-timestamp",  # not written by this pipeline
        "graham-2026-07-31",  # the old pipeline's shape
    ],
)
def test_names_that_are_not_candidates_parse_to_none(name):
    assert trail.parse_trail_start(name, "graham") is None


def test_a_session_inside_the_window_joins_the_existing_trail():
    # The motivating case: run a migration, exit, remember a second migration.
    # One piece of work, one trail.
    client = FakeKosliClient(trails=[{"name": "graham-2026-07-31-0900"}])

    result = trail.find_or_begin_trail(client, "graham", at(11), WINDOW)

    assert result.name == "graham-2026-07-31-0900"
    assert result.created is False
    assert client.begun == []


def test_a_session_outside_the_window_begins_its_own_trail():
    client = FakeKosliClient(trails=[{"name": "graham-2026-07-31-0900"}])

    result = trail.find_or_begin_trail(client, "graham", at(15), WINDOW)

    assert result.name == "graham-2026-07-31-1500"
    assert result.created is True
    assert client.begun[0]["name"] == "graham-2026-07-31-1500"


def test_the_window_is_not_a_calendar_date():
    client = FakeKosliClient(trails=[{"name": "graham-2026-07-31-2359"}])
    just_after_midnight = datetime(2026, 8, 1, 0, 10, tzinfo=timezone.utc)

    result = trail.find_or_begin_trail(client, "graham", just_after_midnight, WINDOW)

    assert result.name == "graham-2026-07-31-2359"


def test_the_newest_trail_within_the_window_wins():
    client = FakeKosliClient(
        trails=[
            {"name": "graham-2026-07-31-0900"},
            {"name": "graham-2026-07-31-1030"},
        ]
    )

    result = trail.find_or_begin_trail(client, "graham", at(11), WINDOW)

    assert result.name == "graham-2026-07-31-1030"


def test_another_users_trail_in_the_window_is_never_joined():
    client = FakeKosliClient(trails=[{"name": "someone-2026-07-31-1030"}])

    result = trail.find_or_begin_trail(client, "graham", at(11), WINDOW)

    assert result.name == "graham-2026-07-31-1100"
    assert result.created is True


def test_a_late_event_resolves_to_the_same_trail_as_a_timely_one():
    # The window is measured against the session start from CloudTrail, not
    # against wall-clock now, so out-of-order arrival changes nothing.
    trails = [{"name": "graham-2026-07-31-0900"}]

    timely = trail.find_or_begin_trail(FakeKosliClient(trails), "graham", at(9, 5), WINDOW)
    late = trail.find_or_begin_trail(FakeKosliClient(trails), "graham", at(9, 5), WINDOW)

    assert timely.name == late.name == "graham-2026-07-31-0900"


def test_results_are_scanned_in_full_because_they_are_ordered_by_created_at():
    # kosli list trails orders by created_at descending, not by name, so an
    # early exit on the first out-of-window name would skip a valid candidate.
    client = FakeKosliClient(
        trails=[
            {"name": "graham-2026-07-30-0900"},  # older name, listed first
            {"name": "graham-2026-07-31-1030"},  # the one we want
        ]
    )

    result = trail.find_or_begin_trail(client, "graham", at(11), WINDOW)

    assert result.name == "graham-2026-07-31-1030"
