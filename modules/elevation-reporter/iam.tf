# Only the access this reporter needs beyond writing its own logs and reading
# the Kosli API token, which reporter-lambda grants it.
#
# Read-only on the elevator's audit bucket, and nothing else. The bucket is
# object-locked under GOVERNANCE for a year; this role has no business being
# able to write to it, and it does not.
data "aws_iam_policy_document" "read_audit_entries" {
  statement {
    sid       = "ReadElevatorAuditEntries"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.sso_elevator_bucket_name}/*"]
  }

  dynamic "statement" {
    for_each = var.sso_elevator_bucket_kms_key_arn == null ? [] : [var.sso_elevator_bucket_kms_key_arn]

    content {
      sid       = "DecryptAuditEntries"
      effect    = "Allow"
      actions   = ["kms:Decrypt"]
      resources = [statement.value]
    }
  }
}
