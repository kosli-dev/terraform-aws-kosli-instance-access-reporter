"""A normalised view of an SSO Elevator ``AuditEntry``.

The elevator writes one JSON object to S3 per grant and per revoke, named with
a UUID that carries no meaning. Everything the reporter needs is inside the
object.

Two things the real entries taught us, both of which shape the code below:

* **``request_id`` is not a join key.** A grant and its matching revoke carry
  *different* request IDs — the revoke is a new request, raised by the
  elevator's scheduler. Nothing in the pair links them explicitly, so the
  revoke finds its trail the same way every other event does: the
  ``<user>-<start>`` rendezvous window in :mod:`kosli_access.trail`.
* **``reason`` means different things either side.** On a grant it is the human
  justification a named approver agreed to. On a scheduled revoke it is the
  literal string ``scheduled_revocation``. Presenting the second as if it were
  the first would put a machine token where an auditor expects prose.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import trail as trail_naming

GRANT = "grant"
REVOKE = "revoke"

#: The elevator writes "NA" rather than omitting fields that do not apply to
#: this entry type, so an absent value has to be recognised by its content.
_NOT_APPLICABLE = {"NA", "N/A", ""}

#: The reason the elevator records when an elevation expires on its own rather
#: than being handed back. Not a human justification.
SCHEDULED_REVOCATION = "scheduled_revocation"


class MalformedAuditEntryError(ValueError):
    """The S3 object is not a usable elevator audit entry."""


def _clean(value):
    """Return ``value`` stripped, or ``None`` if the elevator meant "absent"."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in _NOT_APPLICABLE else text


def parse_entry_time(entry):
    """Return when the elevator recorded this entry, as an aware UTC datetime.

    ``time`` is a Python ``str(datetime)`` — ``2026-08-03 12:38:30.795019+00:00``
    — with a space where ISO 8601 puts a ``T``. ``datetime.fromisoformat``
    accepts that. ``timestamp`` carries the same instant in epoch milliseconds
    and is the fallback, so a change to either field alone cannot blind us.
    """
    text = _clean(entry.get("time"))
    if text:
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

    raw = entry.get("timestamp")
    if raw not in (None, ""):
        try:
            return datetime.fromtimestamp(float(raw) / 1000.0, tz=timezone.utc)
        except (TypeError, ValueError, OSError) as exc:
            raise MalformedAuditEntryError(
                f"Unparseable timestamp {raw!r} in audit entry"
            ) from exc

    raise MalformedAuditEntryError(
        "The audit entry carries neither a usable time nor a timestamp"
    )


def parse_permission_duration(value):
    """Return the elevation's length, or ``None`` if it is not stated.

    The elevator writes seconds as a string — ``"5400"`` for 90 minutes.
    """
    text = _clean(value)
    if text is None:
        return None
    try:
        return timedelta(seconds=float(text))
    except ValueError:
        return None


@dataclass(frozen=True)
class AuditEntry:
    """Everything the elevation reporter needs, from the elevator's object alone."""

    operation_type: str
    entry_time: datetime
    requester_email: str
    user: str
    account_id: str
    role_name: str
    reason: str
    approver_email: str
    permission_duration: timedelta
    audit_entry_type: str
    raw: dict

    @property
    def is_grant(self):
        return self.operation_type == GRANT

    @property
    def is_revoke(self):
        return self.operation_type == REVOKE

    @property
    def scheduled_revocation(self):
        """True when the elevation expired rather than being handed back."""
        return self.is_revoke and (self.reason or "") == SCHEDULED_REVOCATION

    @property
    def elevation_reason(self):
        """The human justification, or ``None`` when there is not one.

        Only a grant has one. A revoke's ``reason`` describes the mechanism
        that removed the access, which is a different thing entirely.
        """
        return self.reason if self.is_grant else None

    @property
    def self_approved(self):
        """True when requester and approver are the same person.

        The elevator config sets ``AllowSelfApproval: false``, so this should
        never be true. If it ever is, the trail should say so rather than the
        evidence looking like any other approved grant.
        """
        if not self.approver_email or not self.requester_email:
            return False
        return self.approver_email.casefold() == self.requester_email.casefold()

    def rendezvous_window(self, base_window):
        """Return how far to search for the trail this entry belongs to.

        A grant is the start of the work, so the ordinary window applies. A
        revoke lands a whole ``permission_duration`` after the grant that
        opened the trail — 90 minutes in the entries we have — so searching
        only ``base_window`` either side of it would miss the trail on any
        elevation longer than the window and strand the revoke on a trail of
        its own. Widening by the duration makes the search hold for an
        elevation of any length, including one handed back early.
        """
        if self.is_revoke and self.permission_duration is not None:
            return base_window + self.permission_duration
        return base_window


def from_object(payload):
    """Build an :class:`AuditEntry` from the elevator's JSON object."""
    if not isinstance(payload, dict):
        raise MalformedAuditEntryError("The audit entry is not an object")

    operation = _clean(payload.get("operation_type"))
    if operation not in (GRANT, REVOKE):
        raise MalformedAuditEntryError(
            f"Unknown operation_type {operation!r}; expected {GRANT!r} or {REVOKE!r}"
        )

    email = _clean(payload.get("requester_email"))
    if not email:
        raise MalformedAuditEntryError(
            "The audit entry carries no requester_email, so the elevation "
            "cannot be attributed to a person"
        )

    return AuditEntry(
        operation_type=operation,
        entry_time=parse_entry_time(payload),
        requester_email=email,
        # The same derivation the session reporters apply to the CloudTrail
        # role session name. Both must agree or the two halves of a trail land
        # in different places.
        user=trail_naming.trail_user(email),
        account_id=_clean(payload.get("account_id")),
        role_name=_clean(payload.get("role_name")),
        reason=_clean(payload.get("reason")),
        approver_email=_clean(payload.get("approver_email")),
        permission_duration=parse_permission_duration(
            payload.get("permission_duration")
        ),
        audit_entry_type=_clean(payload.get("audit_entry_type")),
        raw=payload,
    )
