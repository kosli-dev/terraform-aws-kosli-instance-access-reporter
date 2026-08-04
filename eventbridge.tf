# Both source buckets and the organisation CloudTrail already fan out through
# EventBridge, and EventBridge fans out to any number of rules. So this module
# subscribes to exactly the events the older pipeline subscribes to, without
# modifying a single shared resource.

# CloudTrail management events are regional, so this rule must exist in every
# region where a session can happen - including the DR regions.
resource "aws_cloudwatch_event_rule" "ecs_execute_command" {
  name        = "${var.name_prefix}-ecs-execute-command"
  description = "An ECS exec session was requested"

  event_pattern = jsonencode({
    source      = ["aws.ecs"]
    detail-type = ["AWS API Call via CloudTrail"]
    detail = {
      eventSource = ["ecs.amazonaws.com"]
      eventName   = ["ExecuteCommand"]
    }
  })

  tags = var.tags
}

# Deliberately not filtered on responseElements.session.sessionId: a refused
# ExecuteCommand has an errorCode and no session, and those attempts are
# audit-relevant - arguably more so than the successful ones.
resource "aws_cloudwatch_event_target" "ecs_execute_command" {
  rule      = aws_cloudwatch_event_rule.ecs_execute_command.name
  target_id = local.exec_session_reporter_name
  arn       = module.session.function_arn
}

resource "aws_cloudwatch_event_rule" "ecs_exec_transcript_uploaded" {
  name        = "${var.name_prefix}-ecs-exec-transcript-uploaded"
  description = "An ECS exec transcript was uploaded"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [var.ecs_exec_logs_bucket_name]
      }
      object = {
        key = [{ suffix = ".log" }]
      }
    }
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "ecs_exec_transcript_uploaded" {
  rule      = aws_cloudwatch_event_rule.ecs_exec_transcript_uploaded.name
  target_id = local.transcript_reporter_name
  arn       = module.transcript.function_arn
}
