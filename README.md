# terraform-aws-kosli-instance-access-reporter

Records interactive access to a Kosli instance as audit evidence on a
[Kosli](https://www.kosli.com) trail: **who** opened a shell, **on which instance**, **why**,
**when**, and **what they typed**.

> **Pre-release.** This module is being built and proven in Kosli's own lower environments. There
> are no tagged releases yet and the interface will break without notice. Pin a git SHA if you
> depend on it in the meantime.

## What "instance access" means here

Kosli runs no servers. There are no EC2 instances to log into. Everything this module records
concerns opening an interactive shell *inside a running Fargate container*, via
`aws ecs execute-command`.

Each AWS account running a workload is a **Kosli instance**, so the subject is *instance access*,
not "server access". If you are reading this from outside Kosli: substitute "AWS account running
one of your ECS workloads" for "Kosli instance" and everything else follows.

## What it produces

One Kosli flow per instance, and one trail per piece of work. A trail is named
`<user>-<session-start-utc>` — for example `graham-2026-07-31-1234` — and carries:

| Attestation | Trigger | What it holds |
| --- | --- | --- |
| `user-identity` | exec | Raw CloudTrail `userIdentity`: Identity Center email, `onBehalfOf` ID |
| `access-reason` | exec | The reason given to the wrapper script, extracted for an auditor |
| `access-command` | exec | The raw `requestParameters.command`, kept as the primary evidence |
| `service-identity` | exec | The ECS task, service and image the shell was opened in |
| `access-denied` | exec | Only when the call was refused; carries the error code |
| `command-logs` | transcript | The full terminal transcript, attached raw |

`access-reason` is marked non-compliant when no reason was supplied, and `access-denied` is always
non-compliant. The extracted reason is *derived* from `access-command`, never a replacement for it.

The transcript is *attached*, not referenced. Kosli is intended to be the definitive record — the
thing an auditor is shown — and a trail that merely points at an S3 object stops being evidence the
moment that object ages out.

## How it works

Two lambdas, two EventBridge rules, no shared state and no database.

```
CloudTrail ExecuteCommand ──▶ exec_session_reporter ──▶ find or begin trail ──▶ 4 attestations
S3 ObjectCreated (transcript) ─▶ transcript_reporter ──▶ find or begin trail ──▶ transcript attached
```

Three properties fall out of that shape, and they are the point of the design:

**The ECS exec event is self-sufficient.** Both the human identity and the session start come from
the CloudTrail event alone, with no store to consult. So the module works in environments that have
no privilege-elevation step at all, it keeps working when a grant is revoked before the evidence is
written, and access made without the wrapper script is still captured.

**Each path is independently sufficient.** Neither lambda blocks on the other. The transcript path
resolves identity from the same CloudTrail event the other path is triggered by, so the two cannot
disagree about which trail a session belongs to — they compute the name from the same `eventTime`
using the same shared code.

**Failures are loud.** Every failure raises, and every lambda has a CloudWatch alarm on its `Errors`
metric. An unattributable transcript, an unpopulated API token secret, a Kosli outage: all of them
become a message rather than a gap in the evidence.

### Several sessions can share one trail

The motivating case: someone opens a shell, runs a migration, exits, then remembers a second
migration. That is one piece of work and belongs on one trail.

So the reporter lists trails newest-first, takes the newest whose name begins `<user>-` and whose
session start is within `trail_window_hours` of *this* session's start, and begins a new trail only
if there is none. Two unrelated accesses in one day fall outside each other's window and get
separate trails automatically, and a window is not a calendar date, so 23:59 and 00:10 match.

The match is on the timestamp in the trail *name*, never on Kosli's `created_at`. `created_at` is
when Kosli first saw a write for the trail, which can be hours after the session started if the
transcript path wins the race. The name carries the true session start.

### The access reason needs no change to the wrapper script

Kosli's `enter_aws.sh -r "<reason>"` bakes the reason into the ECS command string, which lands
verbatim in the CloudTrail event as `requestParameters.command`. The reporter extracts it from
there. No second reporting path, no script modification, and it works in the lower environments
where there is no elevation step.

A missing reason is itself flagged on the trail. Calling `aws ecs execute-command` directly, without
the wrapper, produces an `access-reason` attestation that says so explicitly and is marked
non-compliant — omitting the attestation would look like a reporting failure, which says something
quite different to an auditor.

## Usage

```hcl
module "instance_access_reporter" {
  source = "github.com/kosli-dev/terraform-aws-kosli-instance-access-reporter?ref=<sha>"

  kosli_org       = "kosli"
  kosli_flow_name = "prod-instance-access"

  kosli_api_token_secret_arn = aws_secretsmanager_secret.kosli_api_token_instance_access.arn

  ecs_exec_logs_bucket_name = module.ecs_exec_logs_bucket.s3_bucket_id
  ecs_exec_logs_bucket_arn  = module.ecs_exec_logs_bucket.s3_bucket_arn
  ecs_exec_logs_kms_key_arn = aws_kms_key.kms_ecs_exec_logs.arn

  alarm_sns_topic_arns = [aws_sns_topic.warning_alerts.arn]
  tags                 = local.tags
}
```

See [`examples/instance-account`](examples/instance-account) for a runnable version with its
prerequisites.

## Prerequisites

**ECS exec logging into an S3 bucket that emits EventBridge events.** Set
`execute_command_configuration` on the cluster with `logging = "OVERRIDE"`, and
`eventbridge = true` on the bucket notification. EventBridge fans out to any number of rules, so
turning this on does not disturb anything else already subscribed to the same bucket.

**A Kosli flow.** The reporter begins trails in `kosli_flow_name`; it does not create the flow. At
Kosli these are declared in `terraform-kosli-app`, one per instance.

**A Secrets Manager secret holding a Kosli API token.** Pass the ARN as a *resource* reference, not
a data source lookup. A data source is read at plan time, so a brand new account could not create
the secret and the lambdas in a single apply. Create the container with no version and populate the
value separately; the lambdas read it at runtime, so the token never enters Terraform state or the
function configuration, and rotation does not need a redeploy.

Use a dedicated service account token, not one shared with whatever manages your flows and
policies. These lambdas only begin trails and attest to them.

## Deployment notes

**Deploy from a root module that already runs everywhere**, rather than giving this module its own
root module with one tfvars file per account. Per-account opt-in deployment is how coverage gaps
appear: an account is added, nobody remembers the extra deployment, and the gap is silent. For the
same reason this module has no enable flag defaulting to `false`.

**Every region where a session can happen needs its own deployment.** CloudTrail management events
are regional, and the exec logs bucket is per-account-per-region, so a region with no reporter in it
captures nothing.

Note the emphasis: *where a session can happen*. A standby region holding only replicated backups
has no clusters and no containers, so there is nothing to capture there and nothing to deploy. If
that region is built out later, the reporter arrives with it — provided it is called from a root
module that region already runs, which is the same argument as above.

**Apply the primary region before the secondary** when the API token secret uses a `replica` block:
the replica has its own regional ARN, and a separate workspace has to look it up.

## Requirements

| Name | Version |
| --- | --- |
| terraform | >= 1.5.0 |
| aws | >= 6.0 |
| http | >= 3.4 |

The Kosli CLI is attached as a lambda layer, resolved for the requested version and the current
region. A combination with no published layer fails at plan, not at runtime.

## Inputs

| Name | Description | Default |
| --- | --- | --- |
| `kosli_org` | Kosli organisation to report to | required |
| `kosli_flow_name` | Flow holding this instance's access trails | required |
| `kosli_api_token_secret_arn` | Secrets Manager secret holding the API token | required |
| `ecs_exec_logs_bucket_name` | Bucket holding ECS exec transcripts | required |
| `ecs_exec_logs_bucket_arn` | ARN of that bucket | required |
| `ecs_exec_logs_kms_key_arn` | KMS key the transcripts are encrypted with | required |
| `kosli_host` | Kosli endpoint | `https://app.kosli.com` |
| `kosli_cli_version` | Kosli CLI lambda layer version | `v2.36.3` |
| `name_prefix` | Prefix for every resource name | `kosli-instance-access` |
| `trail_window_hours` | How far apart two sessions can start and share a trail | `3` |
| `trail_list_page_limit` | Trails fetched per page when searching | `30` |
| `trail_list_max_pages` | Maximum pages scanned; hitting the cap is logged | `3` |
| `identity_lookup_timeout_seconds` | Budget for resolving a transcript's identity | `840` |
| `exec_session_reporter_timeout_seconds` | Timeout for the ExecuteCommand lambda | `60` |
| `transcript_reporter_timeout_seconds` | Timeout for the transcript lambda | `900` |
| `transcript_reporter_memory_size` | Memory for the transcript lambda | `512` |
| `lambda_retry_attempts` | Asynchronous invocation retries | `2` |
| `cloudwatch_logs_retention_in_days` | Retention for the reporters' own logs | `90` |
| `create_error_alarms` | Alarm on lambda errors | `true` |
| `alarm_sns_topic_arns` | Topics to notify when a reporter fails | `[]` |
| `kosli_cli_layer_mapping_url` | Where to resolve the CLI layer ARN | Kosli's published mapping |
| `tags` | Tags for the created resources | `{}` |

## Outputs

`exec_session_reporter_function_name`, `exec_session_reporter_function_arn`,
`exec_session_reporter_role_arn`, `transcript_reporter_function_name`,
`transcript_reporter_function_arn`, `transcript_reporter_role_arn`, `event_rule_arns`,
`kosli_cli_layer_arn`.

## Not built yet

- **Elevation context.** A second module, for the account running the privilege elevator, attesting
  the elevation reason and the approver alongside the session reason recorded here. It will live in
  this repository so that it shares the trail-naming implementation rather than reimplementing it.
- **A reconciliation sweep.** A scheduled job asserting that every session `ssm describe-sessions`
  knows about has a trail, and that every account in the organisation has a reporter deployed.

## Development

```console
python -m venv .venv && . .venv/bin/activate
pip install -r deployment/requirements-test.txt
python -m pytest
terraform fmt -check -recursive
```

The lambda code lives in `deployment/`:

- `deployment/kosli_access/` — the shared library. Trail naming, the rendezvous window, the reason
  parser, the CloudTrail lookup and the Kosli CLI wrapper. Every lambda in this repository uses it,
  so that no two of them can drift apart on how a trail is named.
- `deployment/instance-access-src/` — the two handlers.

## Licence

MIT. See [LICENSE](LICENSE).
