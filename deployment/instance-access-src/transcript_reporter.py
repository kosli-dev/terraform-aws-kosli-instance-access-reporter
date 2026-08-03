"""Attaches an ECS exec transcript to Kosli, triggered by S3 ObjectCreated.

Kosli is the definitive record. The transcript is attached to the trail in
full, raw, control characters and all: a trail that merely points at an S3
object stops being evidence when the object ages out, and the exec-logs bucket
expires objects after 397 days.

The S3 event carries only the cluster and the session ID — SSM never sees the
human — so this path resolves identity and session start from the CloudTrail
ExecuteCommand event, exactly as the other reporter does. When it cannot, it
fails loudly rather than writing evidence that is not attributable.
"""

import logging
import os
import re

from kosli_access import cloudtrail, runtime, session as session_model
from kosli_access import trail as trail_naming

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#: The exec log key is flat: <cluster>/<sessionId>.log, where the prefix is the
#: cluster name and the object name is the session ID verbatim.
_LOG_KEY = re.compile(r"^(?P<cluster>[^/]+)/(?P<session_id>[A-Za-z0-9_.:-]+)\.log$")


class MalformedKeyError(ValueError):
    """The S3 object key is not an ECS exec transcript."""


def parse_log_key(key):
    """Return ``(cluster, session_id)`` for an exec transcript key."""
    match = _LOG_KEY.match(key or "")
    if not match:
        raise MalformedKeyError(
            f"S3 key {key!r} is not of the form <cluster>/<sessionId>.log"
        )
    return match.group("cluster"), match.group("session_id")


def lambda_handler(event, context):  # noqa: ARG001 - lambda signature
    settings = runtime.settings()
    client = runtime.kosli_client()

    detail = (event or {}).get("detail") or {}
    bucket = (detail.get("bucket") or {}).get("name")
    key = (detail.get("object") or {}).get("key")
    cluster, session_id = parse_log_key(key)
    logger.info("Transcript for session %s in cluster %s", session_id, cluster)

    record = cloudtrail.find_execute_command_event(
        session_id,
        client=runtime.client("cloudtrail"),
        timeout=settings.identity_lookup_timeout,
    )
    session = session_model.from_cloudtrail_record(record)

    rendezvous = trail_naming.find_or_begin_trail(
        client,
        session.user,
        session.session_start,
        settings.trail_window,
        description=f"Instance access by {session.email}",
    )

    local_path = os.path.join("/tmp", f"{session_id}.log")
    runtime.client("s3").download_file(bucket, key, local_path)
    size = os.path.getsize(local_path)
    logger.info("Downloaded %d bytes of transcript to %s", size, local_path)

    try:
        client.attest_generic(
            trail=rendezvous.name,
            name="command-logs",
            description=f"Full terminal transcript of session {session_id}",
            attachments=[local_path],
            user_data={
                "session_id": session_id,
                "cluster": cluster,
                "email": session.email,
                "session_start": session.session_start.isoformat(),
                "cloudtrail_event_id": session.event_id,
                "source_bucket": bucket,
                "source_key": key,
                "transcript_bytes": size,
                "note": (
                    "Attached raw, control characters included. It is a "
                    "verbatim capture; cleaning it up would make it more "
                    "readable but less defensible as evidence."
                ),
            },
        )
    finally:
        os.unlink(local_path)

    return {
        "status": "reported",
        "trail": rendezvous.name,
        "trail_created": rendezvous.created,
        "flow": client.flow,
        "session_id": session_id,
        "transcript_bytes": size,
    }
