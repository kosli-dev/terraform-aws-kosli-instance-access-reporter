# reporter-lambda

**Internal.** Do not call this module directly. It exists so that the three reporters in this
repository — the exec session reporter, the transcript reporter and the elevation reporter — are the
same lambda with different wiring, rather than three copies of the same sixty lines of Terraform.

It owns everything the reporters have in common:

- **The package.** One `source_path`, so every reporter ships the same handlers and the same
  `kosli_access` library. This is the reason the two halves of a trail cannot disagree about how a
  trail is named: there is only one place that says which code goes into the zip.
- **The Kosli CLI layer.** Resolved for the requested version and the current region, with a
  precondition so a missing combination fails at plan.
- **The runtime**, which is not freely changeable — see the root README.
- **The role**, which can write its own logs and read the Kosli API token, plus whatever extra
  policy documents the caller passes in.
- **The retry behaviour** and the **error alarm**.

A caller supplies only what genuinely differs between reporters: the handler, the trigger, the extra
IAM, the timeout and memory, and the environment variables that say which flow to write to.

## No defaults

Every variable except `extra_policy_documents` and `extra_environment_variables` is required, even
where the calling module has a sensible default for the same thing. That is deliberate: a default in
both places is a default that can drift, and the caller's is the one a user reads.
