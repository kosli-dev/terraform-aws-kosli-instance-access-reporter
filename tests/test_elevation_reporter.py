from datetime import timedelta

import pytest

import elevation_reporter
from kosli_access import config, elevation, runtime

from .fakes import (
    GRANT_ENTRY,
    REVOKE_ENTRY,
    FakeKosliClient,
    FakeS3Client,
    fake_boto3_clients,
    s3_object_created_event,
)

BUCKET = "sso-elevator-audit-7f6d93c4cf4a8a0fa6ffaddfd70817782bddd202"
KEY = "946eeb73-678c-479d-b4fc-016c67198b28.json"

PROD_FLOW = "instance-access-prod"

SETTINGS = config.ElevationSettings(
    kosli_binary="/opt/kosli",
    kosli_host="https://app.kosli.com",
    kosli_org="kosli",
    kosli_api_token_secret_arn="arn:aws:secretsmanager:eu-north-1:933561452000:secret:x",
    instance_flows={
        "358426185766": PROD_FLOW,
        "545238427212": "instance-access-prod-us",
    },
    trail_window=timedelta(hours=3),
    trail_list_page_limit=30,
    trail_list_max_pages=3,
)


@pytest.fixture
def kosli(monkeypatch):
    """Wire the handler to fakes and hand back the client and the bucket."""
    clients = {}

    def client_for(flow):
        return clients.setdefault(flow, FakeKosliClient(flow=flow))

    s3 = FakeS3Client()
    monkeypatch.setattr(runtime, "elevation_settings", lambda: SETTINGS)
    monkeypatch.setattr(runtime, "kosli_client_for_flow", client_for)
    monkeypatch.setattr(runtime, "client", fake_boto3_clients(s3=s3))
    yield clients, s3, client_for
    runtime.reset()


def report(entry, kosli, key=KEY, bucket=BUCKET):
    _, s3, _ = kosli
    s3.put(bucket, key, entry)
    return elevation_reporter.lambda_handler(
        s3_object_created_event(bucket=bucket, key=key), None
    )


def test_a_grant_begins_the_trail_it_will_share_with_the_session(kosli):
    clients, _, client_for = kosli

    result = report(GRANT_ENTRY, kosli)

    client = client_for(PROD_FLOW)
    # The grant lands 90 minutes before any session, so the elevation reporter
    # is the half that opens the trail. The session reporters join it when the
    # shell is opened.
    assert result["trail_created"] is True
    assert result["trail"] == "graham-2026-08-03-1238"
    assert client.begun[0]["description"] == "Instance access by graham@kosli.com"


def test_the_grant_goes_to_the_flow_for_the_account_it_was_granted_into(kosli):
    clients, _, _ = kosli

    result = report(GRANT_ENTRY, kosli)

    assert result["flow"] == PROD_FLOW
    assert set(clients) == {PROD_FLOW}


def test_the_whole_audit_entry_is_forwarded(kosli):
    _, _, client_for = kosli

    report(GRANT_ENTRY, kosli)

    attestation = client_for(PROD_FLOW).attestation("elevated-aws-permissions")
    user_data = attestation["user_data"]
    # The old pipeline dropped exactly these, which are what tie the grant back
    # to the Slack conversation that approved it.
    assert user_data["audit_entry"] == GRANT_ENTRY
    assert user_data["audit_entry"]["request_id"] == (
        "1a998d38-075c-498a-94cf-ee6f5c5bcad5"
    )
    assert user_data["audit_entry"]["requester_slack_id"] == "U090MLZ8BPE"
    assert user_data["audit_entry"]["approver_slack_id"] == "U05KR8NS07Q"
    assert user_data["audit_entry"]["sso_user_principal_id"] == (
        "602c699c-e0a1-7077-7186-601dd22c8864"
    )


def test_the_approved_reason_is_readable_without_digging_into_the_blob(kosli):
    _, _, client_for = kosli

    report(GRANT_ENTRY, kosli)

    attestation = client_for(PROD_FLOW).attestation("elevated-aws-permissions")
    assert attestation["user_data"]["elevation_reason"] == (
        "Setup SCIM for Sunlife in prod, as part of their testing"
    )
    assert attestation["description"] == (
        "Elevation to AdministratorAccess in 358426185766, approved by faye@kosli.com"
    )
    assert attestation["compliant"] is True


def test_a_self_approved_grant_is_reported_non_compliant(kosli):
    _, _, client_for = kosli

    report(dict(GRANT_ENTRY, approver_email="graham@kosli.com"), kosli)

    attestation = client_for(PROD_FLOW).attestation("elevated-aws-permissions")
    assert attestation["compliant"] is False
    assert attestation["user_data"]["self_approved"] is True


def test_the_revoke_joins_the_trail_the_grant_opened(kosli):
    _, s3, client_for = kosli

    report(GRANT_ENTRY, kosli, key="grant.json")
    result = report(REVOKE_ENTRY, kosli, key="revoke.json")

    client = client_for(PROD_FLOW)
    assert result["trail_created"] is False
    assert result["trail"] == "graham-2026-08-03-1238"
    assert len(client.begun) == 1
    assert client.attestation_names() == [
        "elevated-aws-permissions",
        "elevated-aws-permissions-revoked",
    ]


def test_a_revoke_after_a_long_elevation_still_finds_its_trail(kosli):
    # Eight hours is well outside the three hour base window. Anchoring on the
    # revoke alone would strand it on a trail of its own.
    _, _, client_for = kosli
    long_grant = dict(GRANT_ENTRY, permission_duration="28800")
    long_revoke = dict(
        REVOKE_ENTRY,
        permission_duration="28800",
        time="2026-08-03 20:38:35.000000+00:00",
        timestamp=1785789515000,
    )

    report(long_grant, kosli, key="grant.json")
    result = report(long_revoke, kosli, key="revoke.json")

    assert result["trail_created"] is False
    assert result["trail"] == "graham-2026-08-03-1238"
    assert len(client_for(PROD_FLOW).begun) == 1


def test_a_scheduled_revocation_is_not_reported_as_a_reason(kosli):
    _, _, client_for = kosli

    report(REVOKE_ENTRY, kosli)

    client = client_for(PROD_FLOW)
    user_data = client.attestation("elevated-aws-permissions-revoked")["user_data"]
    assert user_data["revocation_trigger"] == "scheduled_revocation"
    assert user_data["scheduled"] is True
    assert "elevation_reason" not in user_data


def test_an_elevation_into_an_unmapped_account_is_skipped(kosli):
    # accounts in the elevator config but that are not Kosli
    # instances, so there is no trail to attach to, are skipped
    clients, _, _ = kosli

    result = report(dict(GRANT_ENTRY, account_id="628389144512"), kosli)

    assert result["status"] == "skipped"
    assert clients == {}


def test_a_group_entry_carries_no_account_and_is_skipped(kosli):
    clients, _, _ = kosli

    result = report(
        dict(GRANT_ENTRY, audit_entry_type="group", account_id="NA"), kosli
    )

    assert result["status"] == "skipped"
    assert clients == {}


def test_the_object_is_read_from_the_key_in_the_event(kosli):
    _, s3, _ = kosli

    report(GRANT_ENTRY, kosli, key="946eeb73-678c-479d-b4fc-016c67198b28.json")

    assert s3.reads == [(BUCKET, "946eeb73-678c-479d-b4fc-016c67198b28.json")]


def test_an_object_that_is_not_json_fails_loudly(kosli):
    _, s3, _ = kosli
    s3.put(BUCKET, KEY, b"<html>not an audit entry</html>")

    with pytest.raises(elevation.MalformedAuditEntryError):
        elevation_reporter.lambda_handler(
            s3_object_created_event(bucket=BUCKET, key=KEY), None
        )
