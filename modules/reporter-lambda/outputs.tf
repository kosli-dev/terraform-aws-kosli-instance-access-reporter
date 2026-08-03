output "function_name" {
  description = "Name of the reporter lambda."
  value       = module.lambda.lambda_function_name
}

output "function_arn" {
  description = "ARN of the reporter lambda."
  value       = module.lambda.lambda_function_arn
}

output "role_arn" {
  description = "ARN of the reporter's IAM role."
  value       = aws_iam_role.this.arn
}

output "kosli_cli_layer_arn" {
  description = "The Kosli CLI lambda layer this reporter is using."
  value       = local.kosli_cli_layer_arn
}
