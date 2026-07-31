"""Extraction of the session access reason from the ECS exec command string.

``server/bin/enter_aws.sh -r "<reason>"`` builds a command of the form::

    /bin/bash -c 'echo;   echo XXXXXXXX Access reason XXXXXXXX;
    echo <reason>;   echo User: <login>;   echo XXXXXXXXXXXXXXX;   echo; bash'

and that string lands verbatim in the CloudTrail ``ExecuteCommand`` event as
``requestParameters.command``. So the per-session reason is already available
without modifying the wrapper script, and it is available in the lower
environments where there is no elevation step at all.

The extraction is *derived* evidence. The raw command string is attested
separately as the primary evidence, and stays authoritative.
"""

import re

#: Everything between the two markers. Deliberately not split on ';' —
#: ${REASON} is interpolated unquoted by enter_aws.sh, so a reason containing a
#: semicolon puts one inside the region being extracted.
_REASON_REGION = re.compile(
    r"Access\s+reason\s+X{2,}\s*;(?P<body>.*?)echo\s+User:", re.DOTALL
)
_LEADING_ECHO = re.compile(r"^echo\s+")
_OPERATOR_LOGIN = re.compile(r"echo\s+User:\s*(?P<login>[^;\s]+)")
#: Used only to tell "wrapper bypassed" apart from "wrapper output changed".
_WRAPPER_HINT = re.compile(r"Access\s+reason", re.IGNORECASE)

PARSED = "parsed"
UNPARSEABLE = "unparseable"
ABSENT = "absent"
NO_COMMAND = "no-command"

_NOTES = {
    UNPARSEABLE: (
        "The access reason markers written by enter_aws.sh were present but "
        "could not be parsed. The wrapper script may have changed. See the "
        "access-command attestation for the raw command string."
    ),
    ABSENT: (
        "No reason supplied - the enter_aws.sh wrapper script was bypassed and "
        "aws ecs execute-command was called directly."
    ),
    NO_COMMAND: (
        "The ExecuteCommand event carried no command string, so no reason "
        "could be present."
    ),
}


def extract_access_reason(command):
    """Return a dict describing the session reason found in ``command``.

    Always returns a result. A missing reason is reported as such, on the
    trail, rather than being omitted — an omitted attestation would look like a
    reporting failure, which says something quite different to an auditor.
    """
    result = {
        "status": NO_COMMAND,
        "reason": None,
        "operator_login": None,
        "note": _NOTES[NO_COMMAND],
    }
    if not command:
        return result

    login = _OPERATOR_LOGIN.search(command)
    if login:
        result["operator_login"] = login.group("login")

    match = _REASON_REGION.search(command)
    if match:
        body = _LEADING_ECHO.sub("", match.group("body").strip(), count=1)
        body = body.strip().rstrip(";").strip()
        if body:
            return dict(result, status=PARSED, reason=body, note=None)
        return dict(result, status=UNPARSEABLE, note=_NOTES[UNPARSEABLE])

    if _WRAPPER_HINT.search(command):
        return dict(result, status=UNPARSEABLE, note=_NOTES[UNPARSEABLE])
    return dict(result, status=ABSENT, note=_NOTES[ABSENT])


def is_compliant(extraction):
    """A trail is only compliant on this point if a reason was actually given."""
    return extraction["status"] == PARSED
