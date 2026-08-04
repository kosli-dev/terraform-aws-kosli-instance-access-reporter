# Only the access each reporter needs beyond writing its own logs and reading
# the Kosli API token, which reporter-lambda grants to all of them. Keeping the
# extra access here means the interesting half of a reporter's permissions is in
# the module that explains why it needs them.

# --- ECS exec session reporter -----------------------------------------------

data "aws_iam_policy_document" "describe_ecs_tasks" {
  statement {
    sid       = "DescribeTasks"
    effect    = "Allow"
    actions   = ["ecs:DescribeTasks"]
    resources = ["arn:aws:ecs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:task/*"]
  }
}

# --- Transcript reporter ------------------------------------------------------

data "aws_iam_policy_document" "read_transcripts" {
  statement {
    sid       = "ReadTranscripts"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.ecs_exec_logs_bucket_arn}/*"]
  }

  # The bucket is encrypted with a customer managed key, so reading a
  # transcript needs kms:Decrypt as well as s3:GetObject.
  statement {
    sid       = "DecryptTranscripts"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [var.ecs_exec_logs_kms_key_arn]
  }

  # The transcript carries no identity: SSM only ever sees the ECS
  # service-linked role. CloudTrail is the only source of the human.
  statement {
    sid       = "ResolveSessionIdentity"
    effect    = "Allow"
    actions   = ["cloudtrail:LookupEvents"]
    resources = ["*"]
  }
}
