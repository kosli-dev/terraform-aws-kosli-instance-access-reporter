# The old pipeline's defining flaw is not that it fails, but that it fails
# silently: it returns 500 and nobody finds out. This alarm turns every failure
# mode - an unpopulated API token secret, a changed wrapper script, a Kosli API
# outage, an unattributable transcript - from silence into a message.
#
# What each failure means for the evidence differs by reporter, so the caller
# supplies alarm_description rather than this module inventing one.

resource "aws_cloudwatch_metric_alarm" "errors" {
  count = var.create_error_alarm ? 1 : 0

  alarm_name        = "${var.function_name}-errors"
  alarm_description = var.alarm_description

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = module.lambda.lambda_function_name
  }

  alarm_actions = var.alarm_sns_topic_arns
  ok_actions    = var.alarm_sns_topic_arns

  tags = var.tags
}
