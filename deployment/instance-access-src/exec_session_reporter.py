"""Reports an ECS exec session to Kosli, triggered by CloudTrail ExecuteCommand.

This path is self-sufficient. The human identity and the session start both
come from the CloudTrail event, with no store to consult, so it works in the
lower environments where there is no elevation step and it keeps working when
an elevation grant is revoked before the evidence is written.

Attestations reported here:

``user-identity``    the raw CloudTrail userIdentity block
``access-reason``    the session reason from ``enter_aws.sh -r``, or a marker
                     saying explicitly that none was supplied
``access-command``   the raw requestParameters.command, primary evidence
``service-identity`` the ECS task and service the shell was opened in
``access-denied``    only when the call was refused
"""

import logging

import boto3

from kosli_access import reason as reason_parser
from kosli_access import runtime, session as session_model, trail as trail_naming

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ecs = None


def _ecs_client():
    global _ecs
    if _ecs is None:
        _ecs = boto3.client("ecs")
    return _ecs


def describe_service_identity(session, client=None):
    """Return what the ECS API knows about the task the shell was opened in."""
    if not session.cluster or not session.task_arn:
        return {
            "cluster": session.cluster,
            "container": session.container,
            "task_arn": session.task_arn,
            "note": "The event carried no cluster or task ARN to describe.",
        }

    client = client or _ecs_client()
    described = client.describe_tasks(
        cluster=session.cluster, tasks=[session.task_arn]
    )
    tasks = described.get("tasks") or []
    if not tasks:
        return {
            "cluster": session.cluster,
            "container": session.container,
            "task_arn": session.task_arn,
            "note": "The task was no longer describable when the event was processed.",
        }

    task = tasks[0]
    return {
        "cluster": session.cluster,
        "container": session.container,
        "task_arn": session.task_arn,
        "group": task.get("group"),
        "task_definition_arn": task.get("taskDefinitionArn"),
        "launch_type": task.get("launchType"),
        "availability_zone": task.get("availabilityZone"),
        "started_at": task.get("startedAt"),
        "containers": [
            {"name": c.get("name"), "image": c.get("image")}
            for c in task.get("containers") or []
        ],
    }


def lambda_handler(event, context):  # noqa: ARG001 - lambda signature
    settings = runtime.settings()
    client = runtime.kosli_client()

    detail = (event or {}).get("detail") or {}
    session = session_model.from_cloudtrail_record(detail)

    if session.dry_run:
        logger.info(
            "Ignoring dry-run ExecuteCommand %s by %s", session.event_id, session.email
        )
        return {"status": "ignored", "reason": "dry-run"}

    rendezvous = trail_naming.find_or_begin_trail(
        client,
        session.user,
        session.session_start,
        settings.trail_window,
        description=f"Instance access by {session.email}",
    )

    errors = runtime.AttestationErrors()

    errors.attempt(
        "user-identity",
        lambda: client.attest_generic(
            trail=rendezvous.name,
            name="user-identity",
            description=f"AWS identity that opened the session: {session.email}",
            user_data={
                "email": session.email,
                "aws_account_id": session.aws_account_id,
                "aws_region": session.aws_region,
                "cloudtrail_event_id": session.event_id,
                "session_id": session.session_id,
                "session_start": session.session_start.isoformat(),
                "user_identity": session.user_identity,
            },
        ),
    )

    extraction = reason_parser.extract_access_reason(session.command)
    errors.attempt(
        "access-reason",
        lambda: client.attest_generic(
            trail=rendezvous.name,
            name="access-reason",
            compliant=reason_parser.is_compliant(extraction),
            description=extraction["reason"] or extraction["note"],
            user_data=dict(
                extraction,
                session_id=session.session_id,
                cloudtrail_event_id=session.event_id,
            ),
        ),
    )

    errors.attempt(
        "access-command",
        lambda: client.attest_generic(
            trail=rendezvous.name,
            name="access-command",
            description="The command ECS was asked to run, verbatim",
            user_data={
                "command": session.command,
                "interactive": session.interactive,
                "session_id": session.session_id,
                "cloudtrail_event_id": session.event_id,
                "request_parameters": session.request_parameters,
            },
        ),
    )

    if session.denied:
        errors.attempt(
            "access-denied",
            lambda: client.attest_generic(
                trail=rendezvous.name,
                name="access-denied",
                compliant=False,
                description=f"ExecuteCommand was refused: {session.error_code}",
                user_data={
                    "error_code": session.error_code,
                    "error_message": session.error_message,
                    "cloudtrail_event_id": session.event_id,
                    "note": (
                        "No session was created, so no transcript will be "
                        "uploaded for this attempt."
                    ),
                },
            ),
        )
    else:
        service_identity = errors.attempt(
            "service-identity lookup", lambda: describe_service_identity(session)
        )
        if service_identity is not None:
            errors.attempt(
                "service-identity",
                lambda: client.attest_generic(
                    trail=rendezvous.name,
                    name="service-identity",
                    description="The ECS task the shell was opened in",
                    user_data=service_identity,
                ),
            )

    errors.raise_if_any()

    return {
        "status": "reported",
        "trail": rendezvous.name,
        "trail_created": rendezvous.created,
        "flow": client.flow,
        "session_id": session.session_id,
        "denied": session.denied,
    }
