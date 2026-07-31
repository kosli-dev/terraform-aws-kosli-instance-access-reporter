"""Resolving an ECS exec session ID back to its CloudTrail event.

The transcript that S3 delivers is named after the session ID and carries no
identity: SSM only ever sees the ECS service-linked role, never the human. So
the transcript path resolves the human identity, and the session start, from
the same CloudTrail ``ExecuteCommand`` event the other path is triggered by.

EventBridge delivery is near-instant, but CloudTrail *Event history*, which is
what ``lookup_events`` reads, can lag by minutes. Hence the polling budget.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: Seconds to wait between lookup attempts, then the last value repeats.
_BACKOFF = (5, 10, 20, 30, 60)


class IdentityNotFound(RuntimeError):
    """The ExecuteCommand event for a session could not be found in time."""


def _session_id_of(record):
    session = (record.get("responseElements") or {}).get("session") or {}
    return session.get("sessionId")


def find_execute_command_event(
    session_id,
    client,
    timeout,
    lookback=timedelta(hours=12),
    sleeper=time.sleep,
    clock=time.monotonic,
    now=None,
):
    """Return the CloudTrail record for ``session_id``.

    Raises :class:`IdentityNotFound` when the budget runs out. That is a hard
    failure on purpose — it alarms, and the daily reconciliation sweep picks up
    what the alarm does not.
    """
    started = clock()
    start_time = (now or datetime.now(timezone.utc)) - lookback
    attempt = 0
    while True:
        record = _lookup_once(session_id, client, start_time)
        if record is not None:
            logger.info(
                "Resolved session %s to CloudTrail event %s after %d attempt(s)",
                session_id,
                record.get("eventID"),
                attempt + 1,
            )
            return record

        elapsed = clock() - started
        delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
        if elapsed + delay >= timeout:
            raise IdentityNotFound(
                f"No CloudTrail ExecuteCommand event for session {session_id} "
                f"after {elapsed:.0f}s. The transcript cannot be attributed to "
                "a person, so no evidence was written for it."
            )
        logger.info(
            "Session %s not yet visible in CloudTrail; retrying in %ds "
            "(%.0fs of %.0fs budget used)",
            session_id,
            delay,
            elapsed,
            timeout,
        )
        sleeper(delay)
        attempt += 1


def _lookup_once(session_id, client, start_time):
    paginator = client.get_paginator("lookup_events")
    pages = paginator.paginate(
        LookupAttributes=[
            {"AttributeKey": "EventName", "AttributeValue": "ExecuteCommand"}
        ],
        StartTime=start_time,
    )
    for page in pages:
        for event in page.get("Events") or []:
            raw = event.get("CloudTrailEvent")
            if not raw:
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Skipping unparseable CloudTrail event payload")
                continue
            if _session_id_of(record) == session_id:
                return record
    return None
