data "aws_iam_policy_document" "assume" {
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

# Scoped to this reporter's own log group, not to every log group sharing the
# name prefix. A reporter has no business writing to another reporter's logs.
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
      "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.function_name}",
      "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.function_name}:*",
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

# Writing its own logs and reading the API token is all any reporter needs in
# common. Everything else - describing an ECS task, reading a transcript,
# reading an elevator audit entry - is the caller's to grant, so the extra
# access each reporter has stays visible in the module that needs it.
data "aws_iam_policy_document" "this" {
  source_policy_documents = concat(
    [
      data.aws_iam_policy_document.logs.json,
      data.aws_iam_policy_document.read_kosli_api_token.json,
    ],
    var.extra_policy_documents,
  )
}

resource "aws_iam_role" "this" {
  name               = var.function_name
  description        = "Role for ${var.function_name}"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = var.tags
}

# An IAM policy description is immutable, so editing the text below replaces the
# policy, and a replacement detaches it from the role until the new one is
# attached. A reporter invoked in that window fails for want of permissions. The
# policy *document* is mutable, so changing what a reporter may do is an ordinary
# in-place update; it is only the prose that is expensive.
resource "aws_iam_policy" "this" {
  name        = var.function_name
  description = "Policy for ${var.function_name}"
  policy      = data.aws_iam_policy_document.this.json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "this" {
  role       = aws_iam_role.this.name
  policy_arn = aws_iam_policy.this.arn
}
