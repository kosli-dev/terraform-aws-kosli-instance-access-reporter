# Elevation reporter

The only part of the instance access audit trail that runs in the SSO account.

The **session reporters** — the root module of this repository, deployed into every instance
account — record what happened in a session: who, on which instance, why, and the full transcript.
This module records the **elevation the session was made under, and the named person who approved
it**, which the session reporters cannot see because the approval happens in Slack before anyone
opens a shell.

Both halves land on the same Kosli trail. That is the whole point, and it is why the two modules
share one repository: they are packaged from the same source by the same internal module, so they
run the same `kosli_access.trail` implementation and cannot disagree about which trail a piece of
work belongs to.

## What it does

Triggered by an SSO Elevator audit entry landing in S3, via EventBridge:

- `operation_type: grant` attests **`sso-session-data`** — the whole `AuditEntry`, plus the
  elevation reason and the approver lifted out where an auditor will read them.
- `operation_type: revoke` attests **`sso-session-revoked`** — the whole `AuditEntry`, plus whether
  the elevation expired on its own or was handed back.

It runs *alongside* `session-saver` on the same bucket events rather than replacing it. The bucket
already sets `eventbridge = true`, and EventBridge fans out, so nothing the old pipeline depends on
is modified.

## Usage

```hcl
module "elevation_reporter" {
  source = "github.com/kosli-dev/terraform-aws-kosli-instance-access-reporter//modules/elevation-reporter?ref=v0.1.0"

  kosli_org  = "kosli"
  kosli_host = "https://app.kosli.com"

  instance_flows = {
    "358426185766" = "instance-access-prod"
    "545238427212" = "instance-access-prod-us"
  }

  kosli_api_token_secret_arn = aws_secretsmanager_secret.kosli_api_token_instance_access.arn
  sso_elevator_bucket_name   = module.aws_sso_elevator.sso_elevator_bucket_id
  alarm_sns_topic_arns       = [aws_sns_topic.elevation_reporter_alarms.arn]

  tags = module.tags.result
}
```

The Kosli API token secret is created by the caller with no version and populated out of band, the
same pattern the root module uses: the token is in neither Terraform state nor the function
configuration, and rotating it needs no apply. The SSO account has never held Kosli credentials
before, so this is the one genuinely new prerequisite this module introduces.

## Things the real audit entries taught us

Three behaviours of the elevator shape this module, all confirmed against entries it wrote for a
real prod elevation on 2026-08-03.

**`request_id` is not a join key.** A grant and its matching revoke carry *different* request IDs —
the revoke is a fresh request raised by the elevator's scheduler. Nothing in the pair links them, so
the revoke finds its trail through the same `<user>-<start>` rendezvous window as everything else.

**`reason` means two different things.** On a grant it is the human justification a named approver
agreed to. On a scheduled revoke it is the literal string `scheduled_revocation`. The revoke
attestation therefore reports it as `revocation_trigger`, never as a reason — putting a machine
token where an auditor expects prose would be worse than leaving the field out.

**The grant usually arrives before any session**, so this module is normally the one that *begins*
the trail and the session reporters join it later. The timestamp in a trail name is when the work
started, and an approved elevation is a perfectly good start.

## The revoke search window

A revoke lands a whole `permission_duration` after the grant that opened the trail — 90 minutes in
the entries we have. Searching only `trail_window_hours` either side of the revoke would find the
trail for a short elevation and miss it for a long one, stranding the revoke on a trail of its own.

So a revoke widens its search by the elevation's own duration, taken from the entry. That holds for
an elevation of any length, including one handed back early. Grants use the plain window.

`trail_window_hours` must match the root module's setting. The two halves of a trail have to agree
about which work belongs together — and because the two modules are called from different
repositories, they can end up pinned at different versions, so relying on the two defaults agreeing
is relying on two versions agreeing. Setting it explicitly in both places is how to be sure.

## Unmapped accounts

`instance_flows` maps AWS account id to Kosli flow. An elevation into an account that is **not** in
the map is logged and skipped — no trail, no attestation, no alarm.
