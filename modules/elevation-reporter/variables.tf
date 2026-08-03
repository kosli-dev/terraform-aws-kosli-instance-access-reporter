variable "name_prefix" {
  type        = string
  default     = "kosli-instance-access"
  description = "Prefix for the names of every AWS resource this module creates. The same prefix the root module uses, and deliberately sharing no substring with the older evidence-reporter resources, so the two pipelines cannot be confused during the parallel run."
}

variable "kosli_org" {
  type        = string
  description = "The Kosli organisation to report to (the value for the CLI --org flag)."
}

variable "kosli_host" {
  type        = string
  default     = "https://app.kosli.com"
  description = "The Kosli endpoint to report to."
}

variable "instance_flows" {
  type        = map(string)
  description = "Map of AWS account id to the Kosli flow holding that instance's access trails, for example {\"358426185766\" = \"instance-access-prod\"}. Unlike the root module, which is deployed per account and so knows its own flow, this one lambda serves every instance and looks the flow up from the account an elevation was granted into. There is deliberately no derivation rule: a wrong guess writes real evidence to the wrong instance's flow. Accounts absent from this map are logged and skipped - see the README."

  validation {
    condition     = length(var.instance_flows) > 0
    error_message = "instance_flows must contain at least one account, or the reporter can never attach an elevation to a trail."
  }

  validation {
    condition     = alltrue([for account in keys(var.instance_flows) : can(regex("^[0-9]{12}$", account))])
    error_message = "Every key in instance_flows must be a 12-digit AWS account id, since it is matched against account_id in the elevator's audit entry."
  }
}

variable "kosli_api_token_secret_arn" {
  type        = string
  description = "ARN of the Secrets Manager secret holding the Kosli API token. The lambda reads the value at runtime, so it never enters Terraform state and a rotated token needs no apply."
}

variable "kosli_cli_version" {
  type        = string
  default     = "v2.36.3"
  description = "The version of the Kosli CLI lambda layer to attach."
}

variable "sso_elevator_bucket_name" {
  type        = string
  description = "Name of the S3 bucket the SSO Elevator writes its audit entries to. It already emits to EventBridge, so subscribing to it does not modify anything the existing session-saver depends on."
}

variable "sso_elevator_bucket_kms_key_arn" {
  type        = string
  default     = null
  description = "ARN of the KMS key the elevator's audit bucket is encrypted with, if it uses a customer managed key. Kosli's bucket is SSE-S3, so this is normally left unset; reading an object then needs only s3:GetObject."
}

variable "trail_window_hours" {
  type        = number
  default     = 3
  description = "How far apart two events by the same person can be and still share a trail. Must match the root module's setting: the two halves of a trail have to agree about which work belongs together. A revoke widens this by the elevation's own duration, so a long elevation still finds the trail its grant opened."
}

variable "trail_list_page_limit" {
  type        = number
  default     = 30
  description = "Trails fetched per page when searching for a trail to join."
}

variable "trail_list_max_pages" {
  type        = number
  default     = 3
  description = "Maximum pages of trails to scan. Hitting this cap is logged as a warning rather than passing silently."
}

variable "elevation_reporter_timeout_seconds" {
  type        = number
  default     = 60
  description = "Timeout for the lambda. It reads one small S3 object and makes a handful of Kosli calls; unlike the transcript reporter it has no CloudTrail lookup to wait for."
}

variable "elevation_reporter_memory_size" {
  type        = number
  default     = 256
  description = "Memory for the elevation reporter."
}

variable "lambda_retry_attempts" {
  type        = number
  default     = 2
  description = "Asynchronous invocation retries. EventBridge invokes this lambda asynchronously, so a retry is a free second chance at a transient Kosli failure."
}

variable "cloudwatch_logs_retention_in_days" {
  type        = number
  default     = 90
  description = "Retention for the reporter's own CloudWatch log group."
}

variable "create_error_alarms" {
  type        = bool
  default     = true
  description = "Whether to alarm on lambda errors. The old pipeline's defining flaw is that it returned 500 and nobody found out, so this defaults to on."
}

variable "alarm_sns_topic_arns" {
  type        = list(string)
  default     = []
  description = "SNS topics to notify when the reporter fails. Leave empty only if the alarms are wired up elsewhere."
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
