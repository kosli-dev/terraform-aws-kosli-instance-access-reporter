output "exec_session_reporter_function_name" {
  description = "Name of the lambda triggered by the CloudTrail ExecuteCommand event."
  value       = module.session.function_name
}

output "exec_session_reporter_function_arn" {
  description = "ARN of the lambda triggered by the CloudTrail ExecuteCommand event."
  value       = module.session.function_arn
}

output "exec_session_reporter_role_arn" {
  description = "ARN of the exec session reporter's IAM role."
  value       = module.session.role_arn
}

output "transcript_reporter_function_name" {
  description = "Name of the lambda triggered by a transcript landing in S3."
  value       = module.transcript.function_name
}

output "transcript_reporter_function_arn" {
  description = "ARN of the lambda triggered by a transcript landing in S3."
  value       = module.transcript.function_arn
}

output "transcript_reporter_role_arn" {
  description = "ARN of the transcript reporter's IAM role."
  value       = module.transcript.role_arn
}

output "event_rule_arns" {
  description = "ARNs of the EventBridge rules, so a caller can assert the reporter is deployed in every account and region it expects."
  value = {
    ecs_execute_command          = aws_cloudwatch_event_rule.ecs_execute_command.arn
    ecs_exec_transcript_uploaded = aws_cloudwatch_event_rule.ecs_exec_transcript_uploaded.arn
  }
}

output "kosli_cli_layer_arn" {
  description = "The Kosli CLI lambda layer both reporters are using."
  value       = module.session.kosli_cli_layer_arn
}
