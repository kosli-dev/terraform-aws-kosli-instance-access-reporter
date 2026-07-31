locals {
  exec_session_reporter_name = "${var.name_prefix}-exec-session-reporter"
  transcript_reporter_name   = "${var.name_prefix}-transcript-reporter"

  kosli_cli_layer_arn = try(
    jsondecode(data.http.kosli_cli_layer_mapping.response_body)[var.kosli_cli_version][data.aws_region.current.region],
    null
  )

  # Both lambdas ship the same code: the handlers, plus the shared library that
  # guarantees they compute trail names identically.
  lambda_source_path = [
    {
      path     = "${path.module}/deployment/instance-access-src"
      patterns = ["!.*/__pycache__/.*"]
    },
    {
      path          = "${path.module}/deployment/kosli_access"
      prefix_in_zip = "kosli_access"
      patterns      = ["!.*/__pycache__/.*"]
    },
  ]

  common_environment_variables = {
    KOSLI_HOST                      = var.kosli_host
    KOSLI_ORG                       = var.kosli_org
    KOSLI_FLOW_NAME                 = var.kosli_flow_name
    KOSLI_API_TOKEN_SECRET_ARN      = var.kosli_api_token_secret_arn
    TRAIL_WINDOW_HOURS              = tostring(var.trail_window_hours)
    TRAIL_LIST_PAGE_LIMIT           = tostring(var.trail_list_page_limit)
    TRAIL_LIST_MAX_PAGES            = tostring(var.trail_list_max_pages)
    IDENTITY_LOOKUP_TIMEOUT_SECONDS = tostring(var.identity_lookup_timeout_seconds)
  }
}

# The Kosli CLI ships as a lambda layer, published per version and per region.
# A missing combination must fail at plan, in front of whoever is standing the
# account up, rather than at 2am on the first real access.
resource "terraform_data" "kosli_cli_layer_available" {
  input = local.kosli_cli_layer_arn

  lifecycle {
    precondition {
      condition     = local.kosli_cli_layer_arn != null
      error_message = "No Kosli CLI lambda layer is published for version ${var.kosli_cli_version} in region ${data.aws_region.current.region}. Check ${var.kosli_cli_layer_mapping_url} for the versions and regions available."
    }

    precondition {
      condition     = var.identity_lookup_timeout_seconds < var.transcript_reporter_timeout_seconds
      error_message = "identity_lookup_timeout_seconds (${var.identity_lookup_timeout_seconds}) must be less than transcript_reporter_timeout_seconds (${var.transcript_reporter_timeout_seconds}), or the lambda is killed mid-lookup and the failure is reported as a timeout rather than as an unattributable transcript."
    }
  }
}
