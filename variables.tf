variable "name_prefix" {
  type        = string
  default     = "kosli-instance-access"
  description = "Prefix for the names of every AWS resource this module creates. Deliberately shares no substring with the older evidence-reporter resources, so the two pipelines cannot be confused during the parallel run."
}

variable "kosli_org" {
  type        = string
  description = "The Kosli organisation to report to (the value for the CLI --org flag)."
}

variable "kosli_flow_name" {
  type        = string
  description = "The Kosli flow that holds this instance's access trails, for example prod-instance-access. Created in terraform-kosli-app, not here."
}

variable "kosli_host" {
  type        = string
  default     = "https://app.kosli.com"
  description = "The Kosli endpoint to report to."
}

variable "kosli_api_token_secret_arn" {
  type        = string
  description = "ARN of the Secrets Manager secret holding the Kosli API token. Pass a resource reference rather than a data source lookup, so a brand new account can create the secret and the lambdas in a single apply. The lambdas read the value at runtime, so it never enters Terraform state."
}

variable "kosli_cli_version" {
  type        = string
  default     = "v2.36.3"
  description = "The version of the Kosli CLI lambda layer to attach."
}

variable "ecs_exec_logs_bucket_name" {
  type        = string
  description = "Name of the S3 bucket holding ECS exec transcripts for this account and region."
}

variable "ecs_exec_logs_bucket_arn" {
  type        = string
  description = "ARN of the S3 bucket holding ECS exec transcripts, used to scope the transcript reporter's s3:GetObject permission."
}

variable "ecs_exec_logs_kms_key_arn" {
  type        = string
  description = "ARN of the KMS key the ECS exec transcripts are encrypted with. Reading a transcript needs kms:Decrypt on this key, not just s3:GetObject."
}

variable "trail_window_hours" {
  type        = number
  default     = 3
  description = "How far apart two sessions by the same person can start and still share a trail. The motivating case is a migration run in the morning and a second one remembered an hour later: one piece of work, one trail."
}

variable "trail_list_page_limit" {
  type        = number
  default     = 30
  description = "Trails fetched per page when searching for a trail to join. At roughly two accesses per day this is about two weeks of history."
}

variable "trail_list_max_pages" {
  type        = number
  default     = 3
  description = "Maximum pages of trails to scan. Hitting this cap is logged as a warning rather than passing silently."
}

variable "identity_lookup_timeout_seconds" {
  type        = number
  default     = 840
  description = "How long the transcript reporter polls CloudTrail for the ExecuteCommand event that identifies the person. EventBridge delivery is near-instant but lookup-events visibility can lag by minutes, so this is generous by design. Must be less than transcript_reporter_timeout_seconds."
}

variable "exec_session_reporter_timeout_seconds" {
  type        = number
  default     = 60
  description = "Timeout for the lambda triggered by the CloudTrail ExecuteCommand event."
}

variable "transcript_reporter_timeout_seconds" {
  type        = number
  default     = 900
  description = "Timeout for the lambda triggered by a transcript landing in S3. Large enough to contain the CloudTrail identity lookup budget."
}

variable "transcript_reporter_memory_size" {
  type        = number
  default     = 512
  description = "Memory for the transcript reporter, which downloads the transcript to /tmp before attaching it."
}

variable "lambda_retry_attempts" {
  type        = number
  default     = 2
  description = "Asynchronous invocation retries. EventBridge invokes these lambdas asynchronously, so a retry is a free second chance at a transient Kosli or CloudTrail failure."
}

variable "cloudwatch_logs_retention_in_days" {
  type        = number
  default     = 90
  description = "Retention for the reporters' own CloudWatch log groups."
}

variable "create_error_alarms" {
  type        = bool
  default     = true
  description = "Whether to alarm on lambda errors. The old pipeline's defining flaw is that it returned 500 and nobody found out, so this defaults to on."
}

variable "alarm_sns_topic_arns" {
  type        = list(string)
  default     = []
  description = "SNS topics to notify when a reporter fails. Leave empty only if the alarms are wired up elsewhere."
}

variable "kosli_cli_layer_mapping_url" {
  type        = string
  default     = "https://lambda-layer-mapping-ccc19615fd6c05ace42e71c551995458dbdb1be7.s3.eu-central-1.amazonaws.com/lambda_layer_versions.json"
  description = "Where to look up the Kosli CLI lambda layer ARN for this version and region."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Tags to assign to the AWS resources this module creates."
}
