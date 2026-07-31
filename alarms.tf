# The old pipeline's defining flaw is not that it fails, but that it fails
# silently: it returns 500 and nobody finds out. These alarms turn every
# failure mode - an unpopulated API token secret, a changed wrapper script, a
# Kosli API outage, an unattributable transcript - from silence into a message.

locals {
  alarmed_lambdas = var.create_error_alarms ? {
    exec_session = {
      function_name = module.exec_session_reporter.lambda_function_name
      description   = "The Kosli instance access exec session reporter failed. An ECS exec session may have gone unrecorded."
    }
    transcript = {
      function_name = module.transcript_reporter.lambda_function_name
      description   = "The Kosli instance access transcript reporter failed. An ECS exec transcript may not have reached its Kosli trail."
    }
  } : {}
}

resource "aws_cloudwatch_metric_alarm" "reporter_errors" {
  for_each = local.alarmed_lambdas

  alarm_name        = "${each.value.function_name}-errors"
  alarm_description = each.value.description

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value.function_name
  }

  alarm_actions = var.alarm_sns_topic_arns
  ok_actions    = var.alarm_sns_topic_arns

  tags = var.tags
}
