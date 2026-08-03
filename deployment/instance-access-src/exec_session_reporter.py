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
from dataclasses import dataclass

from kosli_access import reason as reason_parser
from kosli_access import runtime, session as session_model, trail as trail_naming

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@dataclass(frozen=True)
class Attestation:
    """One attestation to report, as data rather than as a call.

    Keeping these as values is what lets :func:`planned_attestations` be read as
    the list of what a session produces, without following any reporting code.
    """

    name: str
    description: str
    user_data: dict
    compliant: bool = True


def describe_service_identity(session, client=None):
    """Return what the ECS API knows about the task the shell was opened in."""
    if not session.cluster or not session.task_arn:
        return {
            "cluster": session.cluster,
            "container": session.container,
            "task_arn": session.task_arn,
            "note": "The event carried no cluster or task ARN to describe.",
        }

    client = client or runtime.client("ecs")
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


def planned_attestations(session, service_identity=None):
    """Return the attestations ``session`` calls for, in reporting order.

    The list in this module's docstring, the table in the README and this
    function are all the same list. Keep them that way.

    ``service_identity`` is passed in rather than looked up here because the ECS
    call can fail on its own, and that failure has to be recorded without
    stopping the evidence already in hand from reaching the trail.
    """
    extraction = reason_parser.extract_access_reason(session.command)

    planned = [
        Attestation(
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
        Attestation(
            name="access-reason",
            description=extraction["reason"] or extraction["note"],
            compliant=reason_parser.is_compliant(extraction),
            user_data=dict(
                extraction,
                session_id=session.session_id,
                cloudtrail_event_id=session.event_id,
            ),
        ),
        Attestation(
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
    ]

    if session.denied:
        planned.append(
            Attestation(
                name="access-denied",
                description=f"ExecuteCommand was refused: {session.error_code}",
                compliant=False,
                user_data={
                    "error_code": session.error_code,
                    "error_message": session.error_message,
                    "cloudtrail_event_id": session.event_id,
                    "note": (
                        "No session was created, so no transcript will be "
                        "uploaded for this attempt."
                    ),
                },
            )
        )
    elif service_identity is not None:
        # None means the lookup failed, and that is already recorded as a
        # failure, so there is nothing left to attest here.
        planned.append(
            Attestation(
                name="service-identity",
                description="The ECS task the shell was opened in",
                user_data=service_identity,
            )
        )

    return planned


def _report(client, trail, planned):
    """Return a thunk that reports ``planned`` against ``trail``."""
    return lambda: client.attest_generic(
        trail=trail,
        name=planned.name,
        description=planned.description,
        compliant=planned.compliant,
        user_data=planned.user_data,
    )


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

    # A refused call created no task to describe, so there is nothing to ask ECS
    # about and asking would only produce a second failure to report.
    service_identity = None
    if not session.denied:
        service_identity = errors.attempt(
            "service-identity lookup", lambda: describe_service_identity(session)
        )

    for planned in planned_attestations(session, service_identity):
        errors.attempt(planned.name, _report(client, rendezvous.name, planned))

    errors.raise_if_any()

    return {
        "status": "reported",
        "trail": rendezvous.name,
        "trail_created": rendezvous.created,
        "flow": client.flow,
        "session_id": session.session_id,
        "denied": session.denied,
    }
