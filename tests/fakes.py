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
        annotations=None,
    ):
        self.attestations.append(
            {
                "trail": trail,
                "name": name,
                "user_data": user_data,
                "attachments": list(attachments or []),
                "compliant": compliant,
                "description": description,
                "annotations": dict(annotations or {}),
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


# The identities the elevation fixtures are built from. All placeholders: this
# repository is public, and nothing here depends on the real values - the tests
# assert on the shape of the evidence, not on who appears in it. Named rather
# than inlined so a grant and its revoke cannot drift apart, which is a real
# failure mode: the two are paired by the trail name derived from the
# requester's email, so scrubbing one side alone silently breaks the pair.
REQUESTER_EMAIL = "requester@example.com"
APPROVER_EMAIL = "approver@example.com"
REQUESTER_SLACK_ID = "U000REQUEST"
APPROVER_SLACK_ID = "U000APPROVE"
SSO_USER_PRINCIPAL_ID = "bf433fa6-06c3-4372-82c1-0b4fa7fc149e"

#: The trail name component derived from :data:`REQUESTER_EMAIL`, by the same
#: rule the reporters use - the local part, before the "@".
REQUESTER_TRAIL_USER = REQUESTER_EMAIL.split("@", 1)[0]

#: An account with an instance flow configured, and one without. The elevator
#: covers accounts that are not Kosli instances, and those are skipped.
ACCOUNT_ID = "958426185778"
SECONDARY_ACCOUNT_ID = "958426185789"
UNMAPPED_ACCOUNT_ID = "958426185790"

AUDIT_BUCKET = "sso-elevator-audit-example"


def s3_object_created_event(
    bucket=AUDIT_BUCKET,
    key="946eeb73-678c-479d-b4fc-016c67198b28.json",
):
    """The EventBridge envelope for an elevator audit object landing in S3."""
    return {
        "source": "aws.s3",
        "detail-type": "Object Created",
        "detail": {"bucket": {"name": bucket}, "object": {"key": key}},
    }


#: A grant, copied from a real entry the elevator wrote on 2026-08-03. Every
#: value that named a person, an account or a customer has been replaced with a
#: placeholder: this repository is public, and the shape is what the tests care
#: about, not the identities.
GRANT_ENTRY = {
    "reason": "Setup SCIM for customer in prod, as part of their testing",
    "operation_type": "grant",
    "permission_duration": "5400",
    "sso_user_principal_id": SSO_USER_PRINCIPAL_ID,
    "audit_entry_type": "account",
    "role_name": "AdministratorAccess",
    "account_id": ACCOUNT_ID,
    "requester_slack_id": REQUESTER_SLACK_ID,
    "requester_email": REQUESTER_EMAIL,
    "request_id": "1a998d38-075c-498a-94cf-ee6f5c5bcad5",
    "approver_slack_id": APPROVER_SLACK_ID,
    "approver_email": APPROVER_EMAIL,
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
    # The same person as the grant, in every field that identifies one. They
    # are one elevation; only request_id differs, because the revoke is a
    # separate request.
    "sso_user_principal_id": SSO_USER_PRINCIPAL_ID,
    "audit_entry_type": "account",
    "role_name": "AdministratorAccess",
    "account_id": ACCOUNT_ID,
    "requester_slack_id": REQUESTER_SLACK_ID,
    "requester_email": REQUESTER_EMAIL,
    "request_id": "0f2054ec-c3b9-4c8a-a0f6-bf7fdc5a9b68",
    "approver_slack_id": APPROVER_SLACK_ID,
    "approver_email": APPROVER_EMAIL,
    "group_name": "NA",
    "group_id": "NA",
    "group_membership_id": "NA",
    "secondary_domain_was_used": False,
    "time": "2026-08-03 14:08:49.966538+00:00",
    "timestamp": 1785766129966,
}


#: What the elevator's nightly sweep writes when it tidies up an elevation
#: whose scheduled revocation failed. Copied from a real entry, with the two
#: ids replaced by fresh uuids - the principal id in the original belongs to a
#: real person and this repository is public. Everything that would name a
#: person - both emails, both Slack ids - is "NA" in the original too, and so
#: is the duration, so there is nothing here to attribute or to find a trail
#: with.
AUTOMATED_REVOCATION_ENTRY = {
    "reason": "automated revocation",
    "operation_type": "revoke",
    "permission_duration": "NA",
    "sso_user_principal_id": "5555fa26-23e2-4da2-8392-edff7481f9de",
    "audit_entry_type": "account",
    "role_name": "AdministratorAccess",
    "account_id": ACCOUNT_ID,
    "requester_slack_id": "NA",
    "requester_email": "NA",
    "request_id": "14c924a1-1ea2-4154-886f-a449c5cf67fe",
    "approver_slack_id": "NA",
    "approver_email": "NA",
    "group_name": "NA",
    "group_id": "NA",
    "group_membership_id": "NA",
    "secondary_domain_was_used": False,
    "sync_operation": "NA",
    "matched_attributes": "NA",
    "sso_user_email": "NA",
    "time": "2026-08-06 23:00:08.954258+00:00",
    "timestamp": 1786057208954,
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
