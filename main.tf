# Two lambdas, two triggers, no shared state. Each is independently sufficient:
# neither blocks on the other, and neither needs an elevation grant to write
# anything, which is what makes this work in the lower environments.
#
# Both are the same reporter-lambda with a different handler, trigger and IAM.
# That module is where the package, the CLI layer, the runtime, the role and the
# retry behaviour are declared once for every reporter in this repository; what
# appears below is only what actually differs between these two.

module "session" {
  source = "./modules/reporter-lambda"

  function_name = local.exec_session_reporter_name
  description   = "Reports an ECS exec session to Kosli when CloudTrail sees ExecuteCommand"
  handler       = "exec_session_reporter.lambda_handler"

  timeout_seconds = var.exec_session_reporter_timeout_seconds
  memory_size     = 256

  trigger = {
    name       = "ExecuteCommandEvent"
    source_arn = aws_cloudwatch_event_rule.ecs_execute_command.arn
  }

  extra_policy_documents = [data.aws_iam_policy_document.describe_ecs_tasks.json]

  extra_environment_variables = {
    KOSLI_FLOW_NAME = var.kosli_flow_name
  }

  alarm_description = "The Kosli instance access exec session reporter failed in ${var.env_name}. An ECS exec session may have gone unrecorded."

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

module "transcript" {
  source = "./modules/reporter-lambda"

  function_name = local.transcript_reporter_name
  description   = "Attaches an ECS exec transcript to its Kosli trail when one lands in S3"
  handler       = "transcript_reporter.lambda_handler"

  # Large enough to contain the CloudTrail identity lookup budget, and enough
  # memory to download the transcript to /tmp before attaching it.
  timeout_seconds = var.transcript_reporter_timeout_seconds
  memory_size     = var.transcript_reporter_memory_size

  trigger = {
    name       = "TranscriptUploadedEvent"
    source_arn = aws_cloudwatch_event_rule.ecs_exec_transcript_uploaded.arn
  }

  extra_policy_documents = [data.aws_iam_policy_document.read_transcripts.json]

  extra_environment_variables = {
    KOSLI_FLOW_NAME = var.kosli_flow_name

    # Only this reporter resolves an identity from CloudTrail, so only this one
    # has a polling budget.
    IDENTITY_LOOKUP_TIMEOUT_SECONDS = tostring(var.identity_lookup_timeout_seconds)
  }

  alarm_description = "The Kosli instance access transcript reporter failed in ${var.env_name}. An ECS exec transcript may not have reached its Kosli trail."

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
