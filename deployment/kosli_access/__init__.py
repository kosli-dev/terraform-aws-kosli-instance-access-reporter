"""Shared implementation for the Kosli instance access reporter lambdas.

Every lambda in this repository — the ECS exec session reporter, the transcript
reporter, and the elevation reporter in the SSO account — computes trail names
and performs the rendezvous window search through this package. That is
deliberate: if those implementations diverged, one lambda would write evidence
to a trail the other never created, and the correlation would fail silently.
"""

__all__ = [
    "cloudtrail",
    "config",
    "elevation",
    "kosli",
    "reason",
    "token",
    "trail",
]
