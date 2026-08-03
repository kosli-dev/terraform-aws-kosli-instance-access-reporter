locals {
  kosli_cli_layer_arn = try(
    jsondecode(data.http.kosli_cli_layer_mapping.response_body)[var.kosli_cli_version][data.aws_region.current.region],
    null
  )

  # Every reporter ships the same code: the handlers, plus the shared library
  # that guarantees they compute trail names identically. Naming that code here,
  # once, is what makes it an assertion rather than a convention - no reporter
  # can be pointed at a different copy, because there is only one place a copy
  # is named.
  lambda_source_path = [
    {
      path     = "${path.module}/../../deployment/instance-access-src"
      patterns = ["!.*/__pycache__/.*"]
    },
    {
      path          = "${path.module}/../../deployment/kosli_access"
      prefix_in_zip = "kosli_access"
      patterns      = ["!.*/__pycache__/.*"]
    },
  ]

  # The trail settings are here rather than in each caller for the same reason:
  # the reporters have to agree about which events belong to one piece of work,
  # and a window configured in two places is a window that can differ.
  environment_variables = merge(
    {
      KOSLI_HOST                 = var.kosli_host
      KOSLI_ORG                  = var.kosli_org
      KOSLI_API_TOKEN_SECRET_ARN = var.kosli_api_token_secret_arn
      TRAIL_WINDOW_HOURS         = tostring(var.trail_window_hours)
      TRAIL_LIST_PAGE_LIMIT      = tostring(var.trail_list_page_limit)
      TRAIL_LIST_MAX_PAGES       = tostring(var.trail_list_max_pages)
    },
    var.extra_environment_variables,
  )
}
