"""Trail naming and the rendezvous window.

A trail is named ``<user>-<session-start-utc>``, for example
``graham-2026-07-31-1234``. The timestamp in the *name* is the true session
start, taken from the CloudTrail event. A trail's ``created_at`` is when Kosli
first saw a write for it, which can be hours later if the transcript path wins
the race — so the window search matches on the name, never on ``created_at``.

Several sessions inside one window share a trail: request access, open a shell,
run a migration, exit, remember a second migration. That is one piece of work
and belongs on one trail.
"""

import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TRAIL_TIMESTAMP_FORMAT = "%Y-%m-%d-%H%M"

# Kosli trail names must start with a letter or number and may otherwise
# contain only letters, numbers, '.', '-', '_' and '~'.
_DISALLOWED = re.compile(r"[^A-Za-z0-9._~-]")


class TrailNamingError(ValueError):
    """A trail name could not be derived from the identity in the event."""


def email_from_principal_id(principal_id):
    """Extract the Identity Center email from a CloudTrail ``principalId``.

    The value looks like ``AROAV2KTWFTFPIQXZGND5:graham@kosli.com``: the part
    before the colon is the role's unique ID, and the part after is the role
    session name, which Identity Center sets to the identity-store userName.
    """
    if not principal_id or ":" not in principal_id:
        raise TrailNamingError(
            f"principalId {principal_id!r} carries no role session name, so "
            "the human identity cannot be determined"
        )
    session_name = principal_id.split(":", 1)[1].strip()
    if not session_name:
        raise TrailNamingError(
            f"principalId {principal_id!r} has an empty role session name"
        )
    return session_name


def trail_user(email):
    """Return the trail-name-safe user component of ``email``."""
    local_part = email.split("@", 1)[0].strip()
    user = _DISALLOWED.sub("-", local_part)
    if not user or not user[0].isalnum():
        raise TrailNamingError(
            f"Cannot build a valid trail name from identity {email!r}"
        )
    return user


def format_trail_name(user, session_start):
    """Return ``<user>-<session-start-utc>``."""
    return f"{user}-{session_start.astimezone(timezone.utc).strftime(TRAIL_TIMESTAMP_FORMAT)}"


def parse_trail_start(trail_name, user):
    """Return the session start encoded in ``trail_name``, or ``None``.

    ``None`` means the name does not belong to ``user`` or was not written by
    this pipeline — either way it is not a rendezvous candidate.
    """
    prefix = f"{user}-"
    if not trail_name.startswith(prefix):
        return None
    stamp = trail_name[len(prefix) :]
    try:
        parsed = datetime.strptime(stamp, TRAIL_TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


class Rendezvous:
    """The outcome of looking for a trail to attach this event's evidence to."""

    def __init__(self, name, created, html_url=None):
        self.name = name
        self.created = created
        self.html_url = html_url

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Rendezvous(name={self.name!r}, created={self.created!r})"


def find_or_begin_trail(client, user, session_start, window, description=None):
    """Find the trail this session belongs to, beginning one if there is none.

    Takes the newest trail whose name begins ``<user>-`` and whose encoded
    session start is within ``window`` of *this* session's start. Because the
    comparison is against the session start rather than wall-clock now, late
    and out-of-order events resolve to the same trail deterministically.
    """
    best_start = None
    best_trail = None
    for trail in client.list_trails():
        name = trail.get("name") or ""
        start = parse_trail_start(name, user)
        if start is None:
            continue
        if abs(start - session_start) > window:
            continue
        if best_start is None or start > best_start:
            best_start, best_trail = start, trail

    if best_trail is not None:
        name = best_trail["name"]
        html_url = best_trail.get("html_url")
        logger.info(
            "Session at %s joins existing trail %s (%s)",
            session_start.isoformat(),
            name,
            html_url or "no url reported",
        )
        return Rendezvous(name, created=False, html_url=html_url)

    name = format_trail_name(user, session_start)
    logger.info("Beginning trail %s in flow %s", name, client.flow)
    client.begin_trail(name, description=description)
    return Rendezvous(name, created=True)
