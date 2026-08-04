# The reporter moved inside the shared reporter-lambda module. Nothing about the
# deployed resources changed - same function name, same role name, same alarm
# name - only their addresses in state, so these blocks let an existing
# workspace apply without destroying and recreating anything. Without them the
# plan destroys and recreates a role, a policy and a function that all have
# fixed names, and the create can collide with the destroy.
#
# Safe to delete once every workspace has applied once.

moved {
  from = module.elevation_reporter
  to   = module.reporter.module.lambda
}

moved {
  from = aws_iam_role.elevation_reporter
  to   = module.reporter.aws_iam_role.this
}

moved {
  from = aws_iam_policy.elevation_reporter
  to   = module.reporter.aws_iam_policy.this
}

moved {
  from = aws_iam_role_policy_attachment.elevation_reporter
  to   = module.reporter.aws_iam_role_policy_attachment.this
}

moved {
  from = aws_cloudwatch_metric_alarm.elevation_reporter_errors[0]
  to   = module.reporter.aws_cloudwatch_metric_alarm.errors[0]
}
