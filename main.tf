# Two lambdas, two triggers, no shared state. Each is independently sufficient:
# neither blocks on the other, and neither needs an elevation grant to write
# anything, which is what makes this work in the lower environments.

module "exec_session_reporter" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "8.8.0"

  function_name = local.exec_session_reporter_name
  description   = "Reports an ECS exec session to Kosli when CloudTrail sees ExecuteCommand"
  handler       = "exec_session_reporter.lambda_handler"
  runtime       = "python3.11"

  create_package = true
  publish        = true
  source_path    = local.lambda_source_path

  layers = [local.kosli_cli_layer_arn]

  create_role = false
  lambda_role = aws_iam_role.exec_session_reporter.arn

  timeout     = var.exec_session_reporter_timeout_seconds
  memory_size = 256

  maximum_retry_attempts = var.lambda_retry_attempts

  environment_variables = local.common_environment_variables

  allowed_triggers = {
    ExecuteCommandEvent = {
      principal  = "events.amazonaws.com"
      source_arn = aws_cloudwatch_event_rule.ecs_execute_command.arn
    }
  }

  cloudwatch_logs_retention_in_days = var.cloudwatch_logs_retention_in_days

  tags = var.tags

  depends_on = [terraform_data.kosli_cli_layer_available]
}

module "transcript_reporter" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "8.8.0"

  function_name = local.transcript_reporter_name
  description   = "Attaches an ECS exec transcript to its Kosli trail when one lands in S3"
  handler       = "transcript_reporter.lambda_handler"
  runtime       = "python3.11"

  create_package = true
  publish        = true
  source_path    = local.lambda_source_path

  layers = [local.kosli_cli_layer_arn]

  create_role = false
  lambda_role = aws_iam_role.transcript_reporter.arn

  timeout     = var.transcript_reporter_timeout_seconds
  memory_size = var.transcript_reporter_memory_size

  maximum_retry_attempts = var.lambda_retry_attempts

  environment_variables = local.common_environment_variables

  allowed_triggers = {
    TranscriptUploadedEvent = {
      principal  = "events.amazonaws.com"
      source_arn = aws_cloudwatch_event_rule.ecs_exec_transcript_uploaded.arn
    }
  }

  cloudwatch_logs_retention_in_days = var.cloudwatch_logs_retention_in_days

  tags = var.tags

  depends_on = [terraform_data.kosli_cli_layer_available]
}
