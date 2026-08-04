data "aws_region" "current" {}

data "aws_caller_identity" "current" {}

data "http" "kosli_cli_layer_mapping" {
  url = var.kosli_cli_layer_mapping_url
}
