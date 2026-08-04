locals {
  exec_session_reporter_name = "${var.name_prefix}-exec-session-reporter"
  transcript_reporter_name   = "${var.name_prefix}-transcript-reporter"
}

# The transcript reporter's CloudTrail polling budget has to fit inside the
# lambda's own timeout, or the lambda is killed mid-lookup and the failure is
# reported as a timeout rather than as an unattributable transcript - which
# sends whoever is woken by the alarm looking in the wrong place.
resource "terraform_data" "transcript_lookup_budget" {
  input = {
    identity_lookup_timeout_seconds     = var.identity_lookup_timeout_seconds
    transcript_reporter_timeout_seconds = var.transcript_reporter_timeout_seconds
  }

  lifecycle {
    precondition {
      condition     = var.identity_lookup_timeout_seconds < var.transcript_reporter_timeout_seconds
      error_message = "identity_lookup_timeout_seconds (${var.identity_lookup_timeout_seconds}) must be less than transcript_reporter_timeout_seconds (${var.transcript_reporter_timeout_seconds}), or the lambda is killed mid-lookup and the failure is reported as a timeout rather than as an unattributable transcript."
    }
  }
}
