data "aws_iam_policy_document" "lambda_assume" {
  statement {
    sid     = "LambdaAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "logs" {
  statement {
    sid    = "WriteOwnLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*",
      "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.name_prefix}-*:*",
    ]
  }
}

# The lambda reads the token at runtime, so it needs this grant. In exchange,
# the token is in neither Terraform state nor the function configuration, and a
# rotated token is picked up by the next cold start rather than a redeploy.
data "aws_iam_policy_document" "read_kosli_api_token" {
  statement {
    sid       = "ReadKosliApiToken"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.kosli_api_token_secret_arn]
  }
}

# --- ECS exec session reporter -----------------------------------------------

data "aws_iam_policy_document" "describe_ecs_tasks" {
  statement {
    sid       = "DescribeTasks"
    effect    = "Allow"
    actions   = ["ecs:DescribeTasks"]
    resources = ["arn:aws:ecs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:task/*"]
  }
}

data "aws_iam_policy_document" "exec_session_reporter" {
  source_policy_documents = [
    data.aws_iam_policy_document.logs.json,
    data.aws_iam_policy_document.read_kosli_api_token.json,
    data.aws_iam_policy_document.describe_ecs_tasks.json,
  ]
}

resource "aws_iam_role" "exec_session_reporter" {
  name               = local.exec_session_reporter_name
  description        = "Role for the Kosli instance access exec session reporter"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_policy" "exec_session_reporter" {
  name        = local.exec_session_reporter_name
  description = "Policy for the Kosli instance access exec session reporter"
  policy      = data.aws_iam_policy_document.exec_session_reporter.json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "exec_session_reporter" {
  role       = aws_iam_role.exec_session_reporter.name
  policy_arn = aws_iam_policy.exec_session_reporter.arn
}

# --- Transcript reporter ------------------------------------------------------

data "aws_iam_policy_document" "read_transcripts" {
  statement {
    sid       = "ReadTranscripts"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.ecs_exec_logs_bucket_arn}/*"]
  }

  # The bucket is encrypted with a customer managed key, so reading a
  # transcript needs kms:Decrypt as well as s3:GetObject.
  statement {
    sid       = "DecryptTranscripts"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [var.ecs_exec_logs_kms_key_arn]
  }

  # The transcript carries no identity: SSM only ever sees the ECS
  # service-linked role. CloudTrail is the only source of the human.
  statement {
    sid       = "ResolveSessionIdentity"
    effect    = "Allow"
    actions   = ["cloudtrail:LookupEvents"]
    resources = ["*"]
  }
}

data "aws_iam_policy_document" "transcript_reporter" {
  source_policy_documents = [
    data.aws_iam_policy_document.logs.json,
    data.aws_iam_policy_document.read_kosli_api_token.json,
    data.aws_iam_policy_document.read_transcripts.json,
  ]
}

resource "aws_iam_role" "transcript_reporter" {
  name               = local.transcript_reporter_name
  description        = "Role for the Kosli instance access transcript reporter"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_policy" "transcript_reporter" {
  name        = local.transcript_reporter_name
  description = "Policy for the Kosli instance access transcript reporter"
  policy      = data.aws_iam_policy_document.transcript_reporter.json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "transcript_reporter" {
  role       = aws_iam_role.transcript_reporter.name
  policy_arn = aws_iam_policy.transcript_reporter.arn
}
