output "elevation_reporter_function_name" {
  description = "Name of the lambda triggered by an elevator audit entry landing in S3."
  value       = module.reporter.function_name
}

output "elevation_reporter_function_arn" {
  description = "ARN of the lambda triggered by an elevator audit entry landing in S3."
  value       = module.reporter.function_arn
}

output "elevation_reporter_role_arn" {
  description = "ARN of the elevation reporter's IAM role."
  value       = module.reporter.role_arn
}

output "event_rule_arn" {
  description = "ARN of the EventBridge rule, so a caller can assert the reporter is deployed."
  value       = aws_cloudwatch_event_rule.sso_elevator_audit_entry.arn
}

output "instance_flows" {
  description = "The account-to-flow map in force, so a caller can assert it covers every instance it expects."
  value       = var.instance_flows
}

output "kosli_cli_layer_arn" {
  description = "The Kosli CLI lambda layer the reporter is using."
  value       = module.reporter.kosli_cli_layer_arn
}
