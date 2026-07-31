"""Test doubles shared by the reporter tests."""

import json


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
