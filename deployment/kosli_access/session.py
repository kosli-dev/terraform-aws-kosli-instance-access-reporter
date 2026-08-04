"""A normalised view of a CloudTrail ``ExecuteCommand`` record.

Both reporter lambdas read the same record shape: the EventBridge envelope's
``detail`` and a record returned by ``cloudtrail:LookupEvents`` are identical,
so both paths derive identity, session start and trail name the same way and
cannot disagree about which trail a session belongs to.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import trail as trail_naming


class MalformedEventError(ValueError):
    """The CloudTrail record is not a usable ExecuteCommand event."""


def parse_event_time(value):
    """Parse a CloudTrail ``eventTime`` into an aware UTC datetime."""
    if not value:
        raise MalformedEventError("The CloudTrail record has no eventTime")
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MalformedEventError(f"Unparseable eventTime {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class ExecSession:
    """Everything the session reporters need, from the CloudTrail record alone."""

    event_id: str
    event_time: datetime
    email: str
    user: str
    user_identity: dict
    aws_account_id: str
    aws_region: str
    cluster: str
    container: str
    task_arn: str
    command: str
    interactive: bool
    dry_run: bool
    session_id: str = None
    error_code: str = None
    error_message: str = None
    request_parameters: dict = field(default_factory=dict)

    @property
    def denied(self):
        """True when the call was refused, so no transcript will ever arrive."""
        return bool(self.error_code) or not self.session_id

    @property
    def session_start(self):
        """The API call *is* the session start; the two align to the second."""
        return self.event_time


def from_cloudtrail_record(record):
    """Build an :class:`ExecSession` from a CloudTrail ``ExecuteCommand`` record."""
    if not isinstance(record, dict):
        raise MalformedEventError("The CloudTrail record is not an object")

    event_name = record.get("eventName")
    if event_name != "ExecuteCommand":
        raise MalformedEventError(
            f"Expected an ExecuteCommand event, got {event_name!r}"
        )

    identity = record.get("userIdentity") or {}
    email = trail_naming.email_from_principal_id(identity.get("principalId"))
    request = record.get("requestParameters") or {}
    response = record.get("responseElements") or {}
    session = (response or {}).get("session") or {}

    return ExecSession(
        event_id=record.get("eventID"),
        event_time=parse_event_time(record.get("eventTime")),
        email=email,
        user=trail_naming.trail_user(email),
        user_identity=identity,
        aws_account_id=record.get("recipientAccountId") or identity.get("accountId"),
        aws_region=record.get("awsRegion"),
        cluster=request.get("cluster"),
        container=request.get("container"),
        task_arn=response.get("taskArn") or request.get("task"),
        command=request.get("command"),
        interactive=bool(request.get("interactive")),
        dry_run=bool(request.get("dryrun")),
        session_id=session.get("sessionId"),
        error_code=record.get("errorCode"),
        error_message=record.get("errorMessage"),
        request_parameters=request,
    )
