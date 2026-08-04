# Both reporters moved inside the shared reporter-lambda module. Nothing about
# the deployed resources changed - same function names, same role names, same
# alarm names - only their addresses in state, so these blocks let an existing
# workspace apply without destroying and recreating anything. Without them the
# plan destroys and recreates roles, policies and functions that all have fixed
# names, and the create can collide with the destroy.
#
# Safe to delete once every workspace has applied once.
#
# terraform_data.kosli_cli_layer_available is deliberately absent: it holds no
# infrastructure, so letting it be replaced costs nothing.

moved {
  from = module.exec_session_reporter
  to   = module.session.module.lambda
}

moved {
  from = aws_iam_role.exec_session_reporter
  to   = module.session.aws_iam_role.this
}

moved {
  from = aws_iam_policy.exec_session_reporter
  to   = module.session.aws_iam_policy.this
}

moved {
  from = aws_iam_role_policy_attachment.exec_session_reporter
  to   = module.session.aws_iam_role_policy_attachment.this
}

moved {
  from = aws_cloudwatch_metric_alarm.reporter_errors["exec_session"]
  to   = module.session.aws_cloudwatch_metric_alarm.errors[0]
}

moved {
  from = module.transcript_reporter
  to   = module.transcript.module.lambda
}

moved {
  from = aws_iam_role.transcript_reporter
  to   = module.transcript.aws_iam_role.this
}

moved {
  from = aws_iam_policy.transcript_reporter
  to   = module.transcript.aws_iam_policy.this
}

moved {
  from = aws_iam_role_policy_attachment.transcript_reporter
  to   = module.transcript.aws_iam_role_policy_attachment.this
}

moved {
  from = aws_cloudwatch_metric_alarm.reporter_errors["transcript"]
  to   = module.transcript.aws_cloudwatch_metric_alarm.errors[0]
}
