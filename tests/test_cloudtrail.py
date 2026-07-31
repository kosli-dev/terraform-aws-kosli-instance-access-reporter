import json

import pytest

from kosli_access import cloudtrail

from .fakes import execute_command_record

SESSION_ID = "ecs-execute-command-s9y89par6quf78pcbnoko32g28"


class FakeCloudTrail:
    """Returns nothing until ``visible_after`` calls, then the record."""

    def __init__(self, record=None, visible_after=0):
        self._record = record
        self._visible_after = visible_after
        self.calls = 0

    def get_paginator(self, name):
        assert name == "lookup_events"
        return self

    def paginate(self, **kwargs):
        self.calls += 1
        if self._record is None or self.calls <= self._visible_after:
            return [{"Events": []}]
        return [{"Events": [{"CloudTrailEvent": json.dumps(self._record)}]}]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_the_event_is_returned_as_soon_as_it_is_visible():
    record = execute_command_record(session_id=SESSION_ID)
    client = FakeCloudTrail(record)
    clock = FakeClock()

    found = cloudtrail.find_execute_command_event(
        SESSION_ID, client=client, timeout=600, sleeper=clock.sleep, clock=clock
    )

    assert found["eventID"] == record["eventID"]
    assert client.calls == 1


def test_it_keeps_polling_while_cloudtrail_event_history_lags():
    # EventBridge delivery is near-instant, but lookup-events can lag by
    # minutes, which is why this path has a long budget rather than 300s.
    client = FakeCloudTrail(execute_command_record(session_id=SESSION_ID), visible_after=4)
    clock = FakeClock()

    found = cloudtrail.find_execute_command_event(
        SESSION_ID, client=client, timeout=600, sleeper=clock.sleep, clock=clock
    )

    assert found is not None
    assert client.calls == 5
    assert clock.now == pytest.approx(5 + 10 + 20 + 30)


def test_giving_up_raises_rather_than_returning_none():
    # The old pipeline returned None here and the caller did None.split(),
    # producing an AttributeError, a 500, and silent evidence loss.
    client = FakeCloudTrail(record=None)
    clock = FakeClock()

    with pytest.raises(cloudtrail.IdentityNotFound, match=SESSION_ID):
        cloudtrail.find_execute_command_event(
            SESSION_ID, client=client, timeout=60, sleeper=clock.sleep, clock=clock
        )


def test_an_event_for_a_different_session_is_not_mistaken_for_this_one():
    client = FakeCloudTrail(execute_command_record(session_id="ecs-execute-command-other"))
    clock = FakeClock()

    with pytest.raises(cloudtrail.IdentityNotFound):
        cloudtrail.find_execute_command_event(
            SESSION_ID, client=client, timeout=10, sleeper=clock.sleep, clock=clock
        )
