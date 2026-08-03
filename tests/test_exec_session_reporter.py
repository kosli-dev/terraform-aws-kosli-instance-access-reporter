from datetime import timedelta

import pytest

import exec_session_reporter
from kosli_access import runtime, session as session_model
from kosli_access.config import Settings

from .fakes import (
    REAL_COMMAND,
    FakeKosliClient,
    execute_command_record,
    fake_boto3_clients,
)

SETTINGS = Settings(
    kosli_binary="/opt/kosli",
    kosli_host="https://app.kosli.com",
    kosli_org="kosli",
    kosli_flow_name="infra-dev-instance-access",
    kosli_api_token_secret_arn="arn:aws:secretsmanager:eu-central-1:1:secret:x",
    trail_window=timedelta(hours=3),
    trail_list_page_limit=30,
    trail_list_max_pages=3,
    identity_lookup_timeout=840.0,
)


class FakeEcs:
    def __init__(self, tasks=None):
        self._tasks = tasks

    def describe_tasks(self, cluster, tasks):
        if self._tasks is None:
            return {"tasks": []}
        return {"tasks": self._tasks}


@pytest.fixture
def kosli(monkeypatch):
    client = FakeKosliClient()
    monkeypatch.setattr(runtime, "settings", lambda: SETTINGS)
    monkeypatch.setattr(runtime, "kosli_client", lambda: client)
    monkeypatch.setattr(
        runtime,
        "client",
        fake_boto3_clients(
            ecs=FakeEcs(
                [
                    {
                        "group": "service:app",
                        "taskDefinitionArn": "arn:aws:ecs:eu-central-1:1:task-definition/app:7",
                        "launchType": "FARGATE",
                        "containers": [{"name": "app", "image": "app:1.2.3"}],
                    }
                ]
            )
        ),
    )
    return client


def invoke(record):
    return exec_session_reporter.lambda_handler({"detail": record}, None)


def planned(record, service_identity=None):
    session = session_model.from_cloudtrail_record(record)
    return [
        attestation.name
        for attestation in exec_session_reporter.planned_attestations(
            session, service_identity
        )
    ]


def test_what_a_session_produces_can_be_read_without_reporting_it():
    # This module's docstring, the README's table and planned_attestations are
    # the same list. This is what keeps them so.
    assert planned(
        execute_command_record(command=REAL_COMMAND), {"cluster": "infra-dev"}
    ) == [
        "user-identity",
        "access-reason",
        "access-command",
        "service-identity",
    ]


def test_a_denied_attempt_swaps_service_identity_for_access_denied():
    assert planned(
        execute_command_record(command=REAL_COMMAND, error_code="AccessDeniedException")
    ) == [
        "user-identity",
        "access-reason",
        "access-command",
        "access-denied",
    ]


def test_a_failed_task_lookup_drops_only_its_own_attestation():
    # No service identity means the ECS call failed, and that failure is already
    # recorded, so there is nothing left to attest for it.
    assert planned(execute_command_record(command=REAL_COMMAND)) == [
        "user-identity",
        "access-reason",
        "access-command",
    ]


def test_a_successful_session_produces_the_four_session_attestations(kosli):
    result = invoke(execute_command_record(command=REAL_COMMAND))

    assert result["trail"] == "graham-2026-07-31-1225"
    assert result["trail_created"] is True
    assert sorted(kosli.attestation_names()) == [
        "access-command",
        "access-reason",
        "service-identity",
        "user-identity",
    ]


def test_the_raw_user_identity_block_is_attested(kosli):
    invoke(execute_command_record(command=REAL_COMMAND))

    user_data = kosli.attestation("user-identity")["user_data"]
    assert user_data["email"] == "graham@kosli.com"
    assert user_data["user_identity"]["onBehalfOf"]["userId"] == (
        "602c699c-e0a1-7077-7186-601dd22c8864"
    )


def test_the_session_reason_is_attested_as_its_own_readable_field(kosli):
    invoke(execute_command_record(command=REAL_COMMAND))

    attestation = kosli.attestation("access-reason")
    assert attestation["user_data"]["reason"] == "Testing of cloudtrail messages"
    assert attestation["compliant"] is True


def test_the_raw_command_is_kept_as_primary_evidence(kosli):
    # The reason is derived from this, not a replacement for it.
    invoke(execute_command_record(command=REAL_COMMAND))

    assert kosli.attestation("access-command")["user_data"]["command"] == REAL_COMMAND


def test_a_bypassed_wrapper_is_flagged_on_the_trail_as_non_compliant(kosli):
    invoke(execute_command_record(command="/bin/bash"))

    attestation = kosli.attestation("access-reason")
    assert attestation["compliant"] is False
    assert "bypassed" in attestation["user_data"]["note"]


def test_a_denied_attempt_is_reported_and_no_service_identity_is_looked_up(kosli):
    result = invoke(
        execute_command_record(command=REAL_COMMAND, error_code="AccessDeniedException")
    )

    assert result["denied"] is True
    denied = kosli.attestation("access-denied")
    assert denied["compliant"] is False
    assert denied["user_data"]["error_code"] == "AccessDeniedException"
    assert "service-identity" not in kosli.attestation_names()


def test_dry_runs_are_ignored(kosli):
    result = invoke(execute_command_record(dry_run=True))

    assert result == {"status": "ignored", "reason": "dry-run"}
    assert kosli.attestations == []


def test_a_second_session_in_the_window_joins_the_first_trail(kosli):
    invoke(execute_command_record(command=REAL_COMMAND, event_time="2026-07-31T09:00:00Z"))
    result = invoke(
        execute_command_record(command=REAL_COMMAND, event_time="2026-07-31T11:00:00Z")
    )

    assert result["trail"] == "graham-2026-07-31-0900"
    assert result["trail_created"] is False


def test_a_task_that_has_gone_away_does_not_lose_the_rest_of_the_evidence(
    kosli, monkeypatch
):
    monkeypatch.setattr(
        runtime, "client", fake_boto3_clients(ecs=FakeEcs(tasks=None))
    )

    invoke(execute_command_record(command=REAL_COMMAND))

    assert "no longer describable" in kosli.attestation("service-identity")["user_data"]["note"]


def test_one_failed_attestation_does_not_hide_the_others(kosli, monkeypatch):
    failing = []

    def attest(**kwargs):
        if kwargs["name"] == "user-identity":
            raise RuntimeError("kosli returned 503")
        failing.append(kwargs["name"])

    monkeypatch.setattr(kosli, "attest_generic", attest)

    with pytest.raises(RuntimeError, match="user-identity"):
        invoke(execute_command_record(command=REAL_COMMAND))

    assert sorted(failing) == ["access-command", "access-reason", "service-identity"]
