"""Test doubles shared by the reporter tests."""

import json


def fake_boto3_clients(**by_service):
    """Stand in for ``runtime.client``, serving one fake per AWS service.

    Asking for a service the test did not provide is an error rather than a
    silent mock, so a handler that starts making an unexpected AWS call is
    caught by whichever test exercises that path.
    """

    def client(service):
        try:
            return by_service[service]
        except KeyError:
            raise AssertionError(
                f"The handler asked for an unexpected {service!r} client; this "
                f"test provides {sorted(by_service)}"
            ) from None

    return client


class FakeKosliClient:
    """Records what would have been sent to Kosli."""

    def __init__(self, trails=None, flow="infra-dev-instance-access"):
        self._trails = list(trails or [])
        self.flow = flow
        self.begun = []
        self.attestations = []

    def list_trails(self):
        return list(self._trails)

    def begin_trail(self, name, description=None):
        self.begun.append({"name": name, "description": description})
        self._trails.insert(0, {"name": name, "html_url": f"https://kosli/{name}"})
        return name

    def attest_generic(
        self,
        trail,
        name,
        user_data=None,
        attachments=None,
        compliant=True,
        description=None,
    ):
        self.attestations.append(
            {
                "trail": trail,
                "name": name,
                "user_data": user_data,
                "attachments": list(attachments or []),
                "compliant": compliant,
                "description": description,
            }
        )

    def attestation(self, name):
        for attestation in self.attestations:
            if attestation["name"] == name:
                return attestation
        raise AssertionError(
            f"No {name!r} attestation was reported; got "
            f"{[a['name'] for a in self.attestations]}"
        )

    def attestation_names(self):
        return [a["name"] for a in self.attestations]


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    """Stands in for ``subprocess.run``."""

    def __init__(self, responses=None):
        self.calls = []
        self._responses = list(responses or [])

    def __call__(self, command, env=None, capture_output=True, text=True, check=False):
        self.calls.append({"command": list(command), "env": dict(env or {})})
        if self._responses:
            return self._responses.pop(0)
        return FakeCompletedProcess()


def trails_page(names, page, page_count):
    """Build a ``kosli list trails --output json`` payload."""
    return json.dumps(
        {
            "data": [
                {"name": name, "html_url": f"https://kosli/{name}"} for name in names
            ],
            "pagination": {
                "total": len(names),
                "page": page,
                "per_page": len(names),
                "page_count": page_count,
            },
        }
    )


def execute_command_record(
    session_id="ecs-execute-command-s9y89par6quf78pcbnoko32g28",
    email="graham@kosli.com",
    event_time="2026-07-31T12:25:25Z",
    command=None,
    cluster="infra-dev",
    error_code=None,
    dry_run=False,
):
    """A CloudTrail ExecuteCommand record, shaped like the real thing."""
    record = {
        "eventID": "b0a1c2d3-0000-4000-8000-000000000000",
        "eventName": "ExecuteCommand",
        "eventSource": "ecs.amazonaws.com",
        "eventTime": event_time,
        "awsRegion": "eu-central-1",
        "recipientAccountId": "400144346314",
        "userIdentity": {
            "type": "AssumedRole",
            "principalId": f"AROAV2KTWFTFPIQXZGND5:{email}",
            "arn": (
                "arn:aws:sts::400144346314:assumed-role/"
                f"AWSReservedSSO_AdministratorAccess_abc/{email}"
            ),
            "onBehalfOf": {"userId": "602c699c-e0a1-7077-7186-601dd22c8864"},
        },
        "requestParameters": {
            "cluster": cluster,
            "container": "app",
            "task": "arn:aws:ecs:eu-central-1:400144346314:task/infra-dev/abc123",
            "command": command,
            "interactive": True,
            "dryrun": dry_run,
        },
        "responseElements": {
            "taskArn": "arn:aws:ecs:eu-central-1:400144346314:task/infra-dev/abc123",
            "session": {"sessionId": session_id},
        },
    }
    if error_code:
        record["errorCode"] = error_code
        record["errorMessage"] = "User is not authorized to perform ecs:ExecuteCommand"
        record["responseElements"] = None
    return record


class FakeS3Client:
    """Serves audit entry objects to the elevation reporter."""

    def __init__(self, objects=None):
        #: {(bucket, key): bytes}
        self._objects = dict(objects or {})
        self.reads = []

    def put(self, bucket, key, payload):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self._objects[(bucket, key)] = body

    def get_object(self, Bucket, Key):  # noqa: N803 - boto3 signature
        self.reads.append((Bucket, Key))
        try:
            body = self._objects[(Bucket, Key)]
        except KeyError:
            raise AssertionError(f"No object at s3://{Bucket}/{Key}") from None
        return {"Body": _Body(body)}


class _Body:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body


def s3_object_created_event(
    bucket="sso-elevator-audit-7f6d93c4cf4a8a0fa6ffaddfd70817782bddd202",
    key="946eeb73-678c-479d-b4fc-016c67198b28.json",
):
    """The EventBridge envelope for an elevator audit object landing in S3."""
    return {
        "source": "aws.s3",
        "detail-type": "Object Created",
        "detail": {"bucket": {"name": bucket}, "object": {"key": key}},
    }


#: A grant, copied from the entry the elevator wrote when Graham requested
#: access to prod on 2026-08-03 and Faye approved it.
GRANT_ENTRY = {
    "reason": "Setup SCIM for Sunlife in prod, as part of their testing",
    "operation_type": "grant",
    "permission_duration": "5400",
    "sso_user_principal_id": "602c699c-e0a1-7077-7186-601dd22c8864",
    "audit_entry_type": "account",
    "role_name": "AdministratorAccess",
    "account_id": "358426185766",
    "requester_slack_id": "U090MLZ8BPE",
    "requester_email": "graham@kosli.com",
    "request_id": "1a998d38-075c-498a-94cf-ee6f5c5bcad5",
    "approver_slack_id": "U05KR8NS07Q",
    "approver_email": "faye@kosli.com",
    "group_name": "NA",
    "group_id": "NA",
    "group_membership_id": "NA",
    "secondary_domain_was_used": False,
    "time": "2026-08-03 12:38:30.795019+00:00",
    "timestamp": 1785760710795,
}

#: The matching revoke, 90 minutes later, when the elevation timed out. Note
#: the request_id differs from the grant's: they are separate requests.
REVOKE_ENTRY = {
    "reason": "scheduled_revocation",
    "operation_type": "revoke",
    "permission_duration": "5400",
    "sso_user_principal_id": "602c699c-e0a1-7077-7186-601dd22c8864",
    "audit_entry_type": "account",
    "role_name": "AdministratorAccess",
    "account_id": "358426185766",
    "requester_slack_id": "U090MLZ8BPE",
    "requester_email": "graham@kosli.com",
    "request_id": "0f2054ec-c3b9-4c8a-a0f6-bf7fdc5a9b68",
    "approver_slack_id": "U05KR8NS07Q",
    "approver_email": "faye@kosli.com",
    "group_name": "NA",
    "group_id": "NA",
    "group_membership_id": "NA",
    "secondary_domain_was_used": False,
    "time": "2026-08-03 14:08:49.966538+00:00",
    "timestamp": 1785766129966,
}


#: The command string captured verbatim from a real infra-dev session, long
#: runs of spaces and all. They come from the shell line continuations in
#: enter_aws.sh.
REAL_COMMAND = (
    "/bin/bash -c 'echo;                     "
    "echo XXXXXXXX Access reason XXXXXXXX;\n"
    "echo Testing of cloudtrail messages;                     "
    "echo User: graham;\n"
    "echo XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX;                     echo; bash'"
)
