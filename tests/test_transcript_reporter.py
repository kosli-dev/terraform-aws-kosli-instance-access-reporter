import dataclasses
import json
import os

import pytest

import transcript_reporter
from kosli_access import cloudtrail, runtime

from .fakes import FakeKosliClient, execute_command_record, fake_boto3_clients
from .test_exec_session_reporter import SETTINGS

SESSION_ID = "ecs-execute-command-s9y89par6quf78pcbnoko32g28"
KEY = f"infra-dev/{SESSION_ID}.log"
TRANSCRIPT = b"Script started\r\n\x1b[0m$ ls\r\napp\r\n"


class FakeS3:
    def __init__(self, body=TRANSCRIPT):
        self._body = body
        self.downloads = []

    def download_file(self, bucket, key, path):
        self.downloads.append((bucket, key, path))
        with open(path, "wb") as handle:
            handle.write(self._body)


class FakeCloudTrail:
    def __init__(self, record):
        self._record = record

    def get_paginator(self, name):
        return self

    def paginate(self, **kwargs):
        if self._record is None:
            return [{"Events": []}]
        return [{"Events": [{"CloudTrailEvent": json.dumps(self._record)}]}]


@pytest.fixture
def kosli(monkeypatch):
    client = FakeKosliClient()
    monkeypatch.setattr(runtime, "settings", lambda: SETTINGS)
    monkeypatch.setattr(runtime, "kosli_client", lambda: client)
    monkeypatch.setattr(
        runtime,
        "client",
        fake_boto3_clients(
            s3=FakeS3(),
            cloudtrail=FakeCloudTrail(execute_command_record(session_id=SESSION_ID)),
        ),
    )
    return client


def invoke(key=KEY, bucket="ecs-exec-logs-abc123"):
    return transcript_reporter.lambda_handler(
        {"detail": {"bucket": {"name": bucket}, "object": {"key": key}}}, None
    )


def test_the_session_id_is_the_object_name_and_the_prefix_is_the_cluster():
    assert transcript_reporter.parse_log_key(KEY) == ("infra-dev", SESSION_ID)


@pytest.mark.parametrize("key", ["", "no-prefix.log", f"infra-dev/{SESSION_ID}.txt"])
def test_an_unexpected_key_shape_fails_loudly(key):
    with pytest.raises(transcript_reporter.MalformedKeyError):
        transcript_reporter.parse_log_key(key)


def test_the_transcript_is_attached_to_the_trail_for_that_session(kosli):
    result = invoke()

    assert result["trail"] == "graham-2026-07-31-1225"
    attestation = kosli.attestation("terminal-session-log")
    assert attestation["attachments"] == [f"/tmp/{SESSION_ID}.log"]
    assert attestation["user_data"]["transcript_bytes"] == len(TRANSCRIPT)
    assert attestation["user_data"]["cluster"] == "infra-dev"


def test_the_downloaded_transcript_is_cleaned_up(kosli):
    invoke()

    assert not os.path.exists(f"/tmp/{SESSION_ID}.log")


def test_the_transcript_joins_the_trail_the_exec_event_created(kosli):
    # Both paths derive the name from the same CloudTrail eventTime, so they
    # cannot disagree about which trail the session belongs to.
    kosli.begin_trail("graham-2026-07-31-1225")
    kosli.begun.clear()

    result = invoke()

    assert result["trail"] == "graham-2026-07-31-1225"
    assert result["trail_created"] is False
    assert kosli.begun == []


def test_an_unattributable_transcript_fails_rather_than_being_attested(
    kosli, monkeypatch
):
    # No identity means no defensible trail name. Failing here alarms rather
    # than attesting a transcript that cannot be attributed to anyone.
    impatient = dataclasses.replace(SETTINGS, identity_lookup_timeout=1.0)
    monkeypatch.setattr(runtime, "settings", lambda: impatient)
    monkeypatch.setattr(
        runtime,
        "client",
        fake_boto3_clients(s3=FakeS3(), cloudtrail=FakeCloudTrail(None)),
    )

    with pytest.raises(cloudtrail.IdentityNotFound):
        invoke()

    assert kosli.attestations == []
