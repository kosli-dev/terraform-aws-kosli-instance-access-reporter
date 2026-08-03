# One lambda, one trigger. It reads the elevator's audit entry out of S3 and
# attaches the elevation - and the person who approved it - to the trail the
# session reporters either have already opened or will open later.
#
# It is the same reporter-lambda the session reporters are, reached from one
# directory up. That is the point of keeping both halves in one repository: this
# lambda and the session reporters run the *same* kosli_access.trail
# implementation, packaged from the same source by the same module, so they
# cannot disagree about which trail an elevation and a session share.

module "reporter" {
  source = "../reporter-lambda"

  function_name = local.elevation_reporter_name
  description   = "Reports an SSO elevation grant or revoke to the Kosli trail for that instance access"
  handler       = "elevation_reporter.lambda_handler"

  # It reads one small S3 object and makes a handful of Kosli calls; unlike the
  # transcript reporter it has no CloudTrail lookup to wait for.
  timeout_seconds = var.elevation_reporter_timeout_seconds
  memory_size     = var.elevation_reporter_memory_size

  trigger = {
    name       = "ElevatorAuditEntryEvent"
    source_arn = aws_cloudwatch_event_rule.sso_elevator_audit_entry.arn
  }

  extra_policy_documents = [data.aws_iam_policy_document.read_audit_entries.json]

  extra_environment_variables = {
    # No KOSLI_FLOW_NAME. This lambda writes into whichever instance's flow the
    # elevation was granted into, so it carries the whole map instead.
    INSTANCE_FLOWS = jsonencode(var.instance_flows)
  }

  alarm_description = "The Kosli instance access elevation reporter failed. An SSO elevation may not have reached its Kosli trail, leaving a session recorded without the approval that authorised it."

  kosli_org                         = var.kosli_org
  kosli_host                        = var.kosli_host
  kosli_api_token_secret_arn        = var.kosli_api_token_secret_arn
  trail_window_hours                = var.trail_window_hours
  trail_list_page_limit             = var.trail_list_page_limit
  trail_list_max_pages              = var.trail_list_max_pages
  kosli_cli_version                 = var.kosli_cli_version
  kosli_cli_layer_mapping_url       = var.kosli_cli_layer_mapping_url
  lambda_retry_attempts             = var.lambda_retry_attempts
  cloudwatch_logs_retention_in_days = var.cloudwatch_logs_retention_in_days
  create_error_alarm                = var.create_error_alarms
  alarm_sns_topic_arns              = var.alarm_sns_topic_arns
  tags                              = var.tags
}
