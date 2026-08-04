module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "8.8.0"

  function_name = var.function_name
  description   = var.description
  handler       = var.handler

  # Not freely changeable: the Kosli CLI layer declares the runtimes it is
  # compatible with, and Lambda rejects a function that asks for one outside
  # that list. A mismatch appears as an InvalidParameterValueException at apply
  # rather than at plan, so check the layer before changing this.
  runtime = "python3.14"

  create_package = true
  publish        = true
  source_path    = local.lambda_source_path

  # Every reporter packages the same source, so without this they hash to the
  # same builds/<hash>.zip and race each other building it - one renames the
  # shared .tmp into place while another is still writing it, and that apply
  # fails.
  hash_extra = var.function_name

  layers = [local.kosli_cli_layer_arn]

  create_role = false
  lambda_role = aws_iam_role.this.arn

  timeout     = var.timeout_seconds
  memory_size = var.memory_size

  # maximum_retry_attempts is only honoured when the async event config is
  # created; without this the setting is silently ignored. EventBridge invokes
  # the unqualified function, so only that qualifier needs a config - a
  # per-version one would be replaced on every publish for no benefit.
  create_async_event_config                 = true
  create_current_version_async_event_config = false
  maximum_retry_attempts                    = var.lambda_retry_attempts

  environment_variables = local.environment_variables

  allowed_triggers = {
    (var.trigger.name) = {
      principal  = "events.amazonaws.com"
      source_arn = var.trigger.source_arn
    }
  }

  cloudwatch_logs_retention_in_days = var.cloudwatch_logs_retention_in_days

  tags = var.tags

  depends_on = [terraform_data.kosli_cli_layer_available]
}

# The Kosli CLI ships as a lambda layer, published per version and per region. A
# missing combination must fail at plan, in front of whoever is standing the
# account up, rather than at 2am on the first real access. This is not
# theoretical: the SSO account runs in eu-north-1, where no reporter had ever
# been deployed before the elevation reporter.
resource "terraform_data" "kosli_cli_layer_available" {
  input = local.kosli_cli_layer_arn

  lifecycle {
    precondition {
      condition     = local.kosli_cli_layer_arn != null
      error_message = "No Kosli CLI lambda layer is published for version ${var.kosli_cli_version} in region ${data.aws_region.current.region}, which ${var.function_name} needs. Check ${var.kosli_cli_layer_mapping_url} for the versions and regions available."
    }
  }
}
