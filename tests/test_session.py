from datetime import datetime, timezone

import pytest

from kosli_access import session as session_model

from .fakes import REAL_COMMAND, execute_command_record


def test_a_successful_call_yields_everything_phase_1_needs():
    session = session_model.from_cloudtrail_record(
        execute_command_record(command=REAL_COMMAND)
    )

    assert session.email == "graham@kosli.com"
    assert session.user == "graham"
    assert session.cluster == "infra-dev"
    assert session.container == "app"
    assert session.session_id.startswith("ecs-execute-command-")
    assert session.denied is False


def test_the_api_call_is_the_session_start():
    # describe-sessions StartDate and CloudTrail eventTime align to the second.
    session = session_model.from_cloudtrail_record(
        execute_command_record(event_time="2026-07-31T12:25:25Z")
    )

    assert session.session_start == datetime(
        2026, 7, 31, 12, 25, 25, tzinfo=timezone.utc
    )


def test_a_refused_call_is_recognised_as_denied():
    session = session_model.from_cloudtrail_record(
        execute_command_record(error_code="AccessDeniedException")
    )

    assert session.denied is True
    assert session.session_id is None
    assert session.error_code == "AccessDeniedException"


def test_dry_runs_are_identifiable_without_a_further_api_call():
    session = session_model.from_cloudtrail_record(
        execute_command_record(dry_run=True)
    )

    assert session.dry_run is True


def test_a_record_for_another_api_call_is_rejected():
    record = execute_command_record()
    record["eventName"] = "RunTask"

    with pytest.raises(session_model.MalformedEventError):
        session_model.from_cloudtrail_record(record)


def test_an_unparseable_event_time_is_rejected():
    with pytest.raises(session_model.MalformedEventError):
        session_model.parse_event_time("not a time")
