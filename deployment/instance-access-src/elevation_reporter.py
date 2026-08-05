"""Attaches SSO elevation context to Kosli, triggered by S3 ObjectCreated.

The only reporter that runs in the SSO account. The session reporters record
what happened in a session; this records the elevation it was made under, and
the named person who approved it — which they cannot see, because the approval
happens in Slack before anyone opens a shell.

It runs alongside ``session-saver`` on the same bucket events rather than
replacing it. EventBridge fans out, so the old pipeline is untouched until it
is retired.

Ordering is the thing to understand here. The grant almost always arrives
*first*, before any session exists, so this lambda is usually the one that
begins the trail and the session reporters join it later. That is the
rendezvous design working as intended: the trail is named for when the work
started, and an approved elevation is a perfectly good start.
"""

import json
import logging

from kosli_access import elevation, runtime
from kosli_access import trail as trail_naming

logger = logging.getLogger()
logger.setLevel(logging.INFO)

#: The attestation names this reporter owns. The session reporters own
#: user-identity, access-reason, access-command, service-identity and
#: command-logs.
GRANT_ATTESTATION = "elevated-aws-permissions"
REVOKE_ATTESTATION = "elevated-aws-permissions-revoked"


def read_audit_entry(bucket, key, client=None):
    """Return the elevator's audit entry stored at ``bucket``/``key``.

    The object name is a UUID with no meaning, so unlike the transcript path
    there is nothing to parse out of the key.
    """
    client = client or runtime.client("s3")
    body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise elevation.MalformedAuditEntryError(
            f"s3://{bucket}/{key} is not valid JSON"
        ) from exc
    return elevation.from_object(payload)


def _grant_user_data(entry, bucket, key):
    return {
        # The whole entry, verbatim. The old pipeline forwarded six hand-picked
        # fields and silently dropped request_id, sso_user_principal_id and
        # both Slack IDs - exactly the fields that let an auditor trace the
        # grant back to the Slack conversation that approved it.
        "audit_entry": entry.raw,
        "elevation_reason": entry.elevation_reason,
        "requester_email": entry.requester_email,
        "approver_email": entry.approver_email,
        "account_id": entry.account_id,
        "role_name": entry.role_name,
        "granted_at": entry.entry_time.isoformat(),
        "permission_duration_seconds": (
            entry.permission_duration.total_seconds()
            if entry.permission_duration is not None
            else None
        ),
        "self_approved": entry.self_approved,
        "source_bucket": bucket,
        "source_key": key,
        "note": (
            "The elevation reason is the justification a named approver "
            "agreed to, covering the whole elevation. It is not the same as "
            "the per-session reason the exec session reporter records from "
            "enter_aws.sh -r, and one elevation may cover several sessions "
            "with different reasons."
        ),
    }


def _revoke_user_data(entry, bucket, key):
    return {
        "audit_entry": entry.raw,
        # Deliberately not reported as a reason. On a scheduled revocation this
        # field is the literal string "scheduled_revocation" - a mechanism, not
        # a justification - and labelling it as a reason would put a machine
        # token where an auditor expects prose.
        "revocation_trigger": entry.reason,
        "scheduled": entry.scheduled_revocation,
        "requester_email": entry.requester_email,
        "account_id": entry.account_id,
        "role_name": entry.role_name,
        "revoked_at": entry.entry_time.isoformat(),
        "source_bucket": bucket,
        "source_key": key,
        "note": (
            "The grant and its revoke carry different request_id values - the "
            "revoke is a fresh request raised by the elevator's scheduler - so "
            "the pair is correlated by the trail, not by an id in the entries."
        ),
    }


def lambda_handler(event, context):  # noqa: ARG001 - lambda signature
    settings = runtime.elevation_settings()

    detail = (event or {}).get("detail") or {}
    bucket = (detail.get("bucket") or {}).get("name")
    key = (detail.get("object") or {}).get("key")
    entry = read_audit_entry(bucket, key)

    logger.info(
        "Elevator %s for %s into account %s (%s)",
        entry.operation_type,
        entry.requester_email,
        entry.account_id,
        entry.role_name,
    )

    # The elevator also covers accounts that are not Kosli instances and group-type entries carry no
    # account at all. None of them has access trails to attach anything to, so
    # they are logged and skipped rather than alarmed on. This is a deliberate
    # gap: elevation into the security account produces no Kosli evidence.
    flow = settings.instance_flows.get(entry.account_id or "")
    if flow is None:
        logger.info(
            "Account %s has no instance flow configured; nothing to report for "
            "this %s",
            entry.account_id,
            entry.operation_type,
        )
        return {
            "status": "skipped",
            "reason": "account has no instance flow",
            "account_id": entry.account_id,
            "operation_type": entry.operation_type,
        }

    client = runtime.kosli_client_for_flow(flow)
    rendezvous = trail_naming.find_or_begin_trail(
        client,
        entry.user,
        entry.entry_time,
        entry.rendezvous_window(settings.trail_window),
        # Identical to the description the session reporters use, so a trail
        # reads the same whichever half of the pipeline happened to open it.
        description=f"Instance access by {entry.requester_email}",
    )

    # One attestation either way, so there is nothing for an AttestationErrors
    # collector to protect: a failure here cannot hide evidence that would
    # otherwise have been reportable, and raising is what the alarm watches for.
    # The session reporters collect because they report four.
    if entry.is_grant:
        client.attest_generic(
            trail=rendezvous.name,
            name=GRANT_ATTESTATION,
            description=(
                f"Elevation to {entry.role_name} in {entry.account_id}, "
                f"approved by {entry.approver_email or 'nobody recorded'}"
            ),
            # A grant that nobody else approved is still evidence, but it is
            # not the evidence we intend to produce: the elevator config sets
            # AllowSelfApproval false, so this should be unreachable.
            compliant=not entry.self_approved,
            user_data=_grant_user_data(entry, bucket, key),
        )
    else:
        client.attest_generic(
            trail=rendezvous.name,
            name=REVOKE_ATTESTATION,
            description=(
                f"Elevation to {entry.role_name} in {entry.account_id} removed"
            ),
            user_data=_revoke_user_data(entry, bucket, key),
        )

    return {
        "status": "reported",
        "trail": rendezvous.name,
        "trail_created": rendezvous.created,
        "flow": flow,
        "operation_type": entry.operation_type,
        "account_id": entry.account_id,
        "requester_email": entry.requester_email,
    }
