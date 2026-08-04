from datetime import datetime, timedelta, timezone

import pytest

from kosli_access import elevation

from .fakes import GRANT_ENTRY, REVOKE_ENTRY

WINDOW = timedelta(hours=3)


def test_a_grant_is_parsed_from_the_real_entry():
    entry = elevation.from_object(GRANT_ENTRY)

    assert entry.is_grant
    assert not entry.is_revoke
    assert entry.requester_email == "graham@kosli.com"
    assert entry.approver_email == "faye@kosli.com"
    assert entry.account_id == "358426185766"
    assert entry.role_name == "AdministratorAccess"
    assert entry.permission_duration == timedelta(minutes=90)


def test_the_trail_user_matches_what_the_session_reporters_derive():
    # They get "graham" from the CloudTrail role session name; this gets it
    # from requester_email. If these ever disagree the two halves of a trail
    # land in different places, so the agreement is the whole contract.
    assert elevation.from_object(GRANT_ENTRY).user == "graham"


def test_the_entry_time_is_read_from_the_python_style_timestamp():
    # "2026-08-03 12:38:30.795019+00:00" - a space where ISO 8601 puts a T.
    assert elevation.from_object(GRANT_ENTRY).entry_time == datetime(
        2026, 8, 3, 12, 38, 30, 795019, tzinfo=timezone.utc
    )


def test_the_epoch_millisecond_timestamp_is_used_when_time_is_missing():
    payload = dict(GRANT_ENTRY)
    del payload["time"]

    assert elevation.from_object(payload).entry_time == datetime(
        2026, 8, 3, 12, 38, 30, 795000, tzinfo=timezone.utc
    )


def test_an_entry_with_no_usable_time_at_all_is_fatal():
    payload = {k: v for k, v in GRANT_ENTRY.items() if k not in ("time", "timestamp")}

    with pytest.raises(elevation.MalformedAuditEntryError):
        elevation.from_object(payload)


def test_a_naive_time_is_assumed_to_be_utc():
    payload = dict(GRANT_ENTRY, time="2026-08-03 12:38:30.795019")

    assert elevation.from_object(payload).entry_time == datetime(
        2026, 8, 3, 12, 38, 30, 795019, tzinfo=timezone.utc
    )


def test_a_grant_carries_the_human_reason():
    entry = elevation.from_object(GRANT_ENTRY)

    assert entry.elevation_reason == (
        "Setup SCIM for Sunlife in prod, as part of their testing"
    )


def test_a_scheduled_revocation_is_not_a_reason():
    # The elevator writes "scheduled_revocation" into the same field a grant
    # uses for prose. Reporting that as a justification would be a lie.
    entry = elevation.from_object(REVOKE_ENTRY)

    assert entry.is_revoke
    assert entry.scheduled_revocation
    assert entry.elevation_reason is None
    assert entry.reason == "scheduled_revocation"


def test_a_revoke_handed_back_early_is_not_flagged_as_scheduled():
    entry = elevation.from_object(dict(REVOKE_ENTRY, reason="no longer needed"))

    assert not entry.scheduled_revocation


def test_the_revoke_search_window_covers_the_whole_elevation():
    # The grant opened the trail 90 minutes before this revoke. Searching only
    # the base window either side of the revoke would still find it here, but
    # would not for an elevation longer than the window - so the window grows
    # by the elevation's own duration.
    revoke = elevation.from_object(REVOKE_ENTRY)

    assert revoke.rendezvous_window(WINDOW) == WINDOW + timedelta(minutes=90)


def test_a_grant_uses_the_ordinary_window():
    assert elevation.from_object(GRANT_ENTRY).rendezvous_window(WINDOW) == WINDOW


def test_a_revoke_with_no_stated_duration_falls_back_to_the_base_window():
    payload = dict(REVOKE_ENTRY, permission_duration="NA")

    assert elevation.from_object(payload).rendezvous_window(WINDOW) == WINDOW


def test_the_elevator_writes_na_rather_than_omitting_fields():
    entry = elevation.from_object(GRANT_ENTRY)

    assert entry.raw["group_name"] == "NA"
    # ...but a caller asking the model gets None, not the string.
    assert elevation.from_object(dict(GRANT_ENTRY, role_name="NA")).role_name is None


def test_self_approval_is_visible():
    payload = dict(GRANT_ENTRY, approver_email="GRAHAM@kosli.com")

    assert elevation.from_object(payload).self_approved


def test_an_approved_grant_is_not_self_approved():
    assert not elevation.from_object(GRANT_ENTRY).self_approved


def test_a_grant_with_no_approver_is_not_treated_as_self_approved():
    payload = dict(GRANT_ENTRY, approver_email="NA")

    entry = elevation.from_object(payload)
    assert entry.approver_email is None
    assert not entry.self_approved


@pytest.mark.parametrize("operation", ["", "NA", "modify", None])
def test_an_unknown_operation_type_is_fatal(operation):
    with pytest.raises(elevation.MalformedAuditEntryError):
        elevation.from_object(dict(GRANT_ENTRY, operation_type=operation))


def test_an_entry_without_a_requester_cannot_be_attributed():
    payload = dict(GRANT_ENTRY, requester_email="NA")

    with pytest.raises(elevation.MalformedAuditEntryError):
        elevation.from_object(payload)


def test_something_that_is_not_an_object_is_fatal():
    with pytest.raises(elevation.MalformedAuditEntryError):
        elevation.from_object(["not", "an", "entry"])
