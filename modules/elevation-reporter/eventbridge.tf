# The elevator's audit bucket already sets eventbridge = true, and EventBridge
# fans out to any number of rules, so this rule sits alongside the one
# session-saver uses without touching a single shared resource. The old
# pipeline keeps running until it is retired.

resource "aws_cloudwatch_event_rule" "sso_elevator_audit_entry" {
  name        = "${var.name_prefix}-sso-elevator-audit-entry"
  description = "The SSO Elevator recorded an elevation grant or revoke"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [var.sso_elevator_bucket_name]
      }
      object = {
        key = [{ suffix = ".json" }]
      }
    }
  })

  tags = var.tags
}

# Deliberately not filtered on operation_type: the pattern can only match the
# object key, which is a bare UUID, and grants and revokes are indistinguishable
# until the object is read. Both are wanted anyway.
resource "aws_cloudwatch_event_target" "sso_elevator_audit_entry" {
  rule      = aws_cloudwatch_event_rule.sso_elevator_audit_entry.name
  target_id = local.elevation_reporter_name
  arn       = module.reporter.function_arn
}
