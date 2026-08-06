# How an instance account calls the reporter, alongside the resources it needs
# to already have. In Kosli this is terraform-base-infra; the ECS cluster, the
# exec logs bucket and its KMS key already exist there, so in practice only the
# secret container and the module block below are new.

provider "aws" {
  region = local.region
}

locals {
  region = "eu-central-1"
}

data "aws_caller_identity" "current" {}

# The container is a resource, created with no version, so a brand new account
# can build the secret and the lambdas in a single apply. Populate the value
# separately - the lambdas read it at runtime, so it never enters state.
resource "aws_secretsmanager_secret" "kosli_api_token_instance_access" {
  name                           = "infrastructure/kosli_api_token_instance_access"
  description                    = "Kosli API token for the instance access reporter service account"
  recovery_window_in_days        = 30
  force_overwrite_replica_secret = true

  replica {
    region = "eu-west-2"
  }
}

resource "aws_kms_key" "ecs_exec_logs" {
  description         = "S3 bucket for ECS exec logs"
  enable_key_rotation = true
}

resource "aws_s3_bucket" "ecs_exec_logs" {
  bucket = "ecs-exec-logs-${data.aws_caller_identity.current.account_id}-${local.region}"
}

# Without this the bucket would be SSE-S3 and the key above would be decorative.
# It is what makes ecs_exec_logs_kms_key_arn meaningful: reading a transcript
# then needs kms:Decrypt as well as s3:GetObject, and the module grants both.
resource "aws_s3_bucket_server_side_encryption_configuration" "ecs_exec_logs" {
  bucket = aws_s3_bucket.ecs_exec_logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.ecs_exec_logs.arn
    }
  }
}

# Both source buckets in Kosli already set this, which is what lets a second
# pipeline subscribe to the same events without modifying the first.
resource "aws_s3_bucket_notification" "ecs_exec_logs" {
  bucket      = aws_s3_bucket.ecs_exec_logs.id
  eventbridge = true
}

module "instance_access_reporter" {
  source = "../.."

  env_name        = "infra-dev"
  kosli_org       = "kosli"
  kosli_flow_name = "instance-access-infra-dev"

  kosli_api_token_secret_arn = aws_secretsmanager_secret.kosli_api_token_instance_access.arn

  ecs_exec_logs_bucket_name = aws_s3_bucket.ecs_exec_logs.id
  ecs_exec_logs_bucket_arn  = aws_s3_bucket.ecs_exec_logs.arn
  ecs_exec_logs_kms_key_arn = aws_kms_key.ecs_exec_logs.arn

  alarm_sns_topic_arns = [aws_sns_topic.warning_alerts.arn]

  tags = {
    Terraform = "true"
    Component = "instance-access-audit"
  }
}

resource "aws_sns_topic" "warning_alerts" {
  name = "warning-alerts"
}
