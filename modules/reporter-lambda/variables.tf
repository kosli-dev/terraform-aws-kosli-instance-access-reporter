# Internal module. Every variable that the calling module also has is required
# here and has no default, so there is exactly one place a default is written.

variable "function_name" {
  type        = string
  description = "Name of the lambda. Also names its role, its policy and its alarm, so that everything belonging to one reporter is findable by one string."
}

variable "description" {
  type        = string
  description = "What this reporter does, shown on the lambda in the console."
}

variable "handler" {
  type        = string
  description = "The handler inside deployment/instance-access-src, for example exec_session_reporter.lambda_handler."
}

variable "timeout_seconds" {
  type        = number
  description = "Lambda timeout. The transcript reporter needs a large one because it polls CloudTrail; the others do not."
}

variable "memory_size" {
  type        = number
  description = "Lambda memory. Only the transcript reporter needs more than the minimum, because it downloads the transcript to /tmp."
}

variable "trigger" {
  type = object({
    name       = string
    source_arn = string
  })
  description = "The EventBridge rule that invokes this reporter. The name becomes the lambda permission's statement id, so changing it replaces the permission."
}

variable "extra_policy_documents" {
  type        = list(string)
  default     = []
  description = "Rendered IAM policy documents to merge into this reporter's policy, on top of writing its own logs and reading the Kosli API token. Statement sids must not collide."
}

variable "extra_environment_variables" {
  type        = map(string)
  default     = {}
  description = "Environment variables specific to this reporter, merged over the ones every reporter gets. This is where a reporter says which flow it writes to."
}

variable "kosli_org" {
  type        = string
  description = "The Kosli organisation to report to (the value for the CLI --org flag)."
}

variable "kosli_host" {
  type        = string
  description = "The Kosli endpoint to report to."
}

variable "kosli_api_token_secret_arn" {
  type        = string
  description = "ARN of the Secrets Manager secret holding the Kosli API token. Granted to the role and passed to the lambda, which reads the value at runtime."
}

variable "trail_window_hours" {
  type        = number
  description = "How far apart two events by the same person can be and still share a trail. Every reporter gets the same value from here, because they have to agree about which events belong to one piece of work."
}

variable "trail_list_page_limit" {
  type        = number
  description = "Trails fetched per page when searching for a trail to join."
}

variable "trail_list_max_pages" {
  type        = number
  description = "Maximum pages of trails to scan. Hitting this cap is logged as a warning rather than passing silently."
}

variable "kosli_cli_version" {
  type        = string
  description = "The version of the Kosli CLI lambda layer to attach."
}

variable "kosli_cli_layer_mapping_url" {
  type        = string
  description = "Where to look up the Kosli CLI lambda layer ARN for this version and region."
}

variable "lambda_retry_attempts" {
  type        = number
  description = "Asynchronous invocation retries. EventBridge invokes every reporter asynchronously, so a retry is a free second chance at a transient failure."
}

variable "cloudwatch_logs_retention_in_days" {
  type        = number
  description = "Retention for this reporter's own CloudWatch log group."
}

variable "create_error_alarm" {
  type        = bool
  description = "Whether to alarm on this reporter's Errors metric."
}

variable "alarm_description" {
  type        = string
  description = "What a failure of this reporter means for the evidence. Read by whoever is woken by the alarm, so it should say what may now be missing."
}

variable "alarm_sns_topic_arns" {
  type        = list(string)
  description = "SNS topics to notify when this reporter fails."
}

variable "tags" {
  type        = map(string)
  description = "Tags to assign to the AWS resources this module creates."
}
